"""Phase 11: the security controls of the API, each one small enough to read in a minute.

    OuterGuard      the outermost layer: a request id for every request, the security headers on every response (also on the ones other layers
                    make), and a last-resort answer when something unexpected is raised
    BodyGuard       Content-Length and Content-Type checked before a byte is read, and the body counted while it streams in
    rate limits     slowapi: one limit for every route together (counted before anything is read) and a stricter one per route (counted before the
                    key is checked, so wrong keys use up the allowance too)
    require_key     the API key, compared in constant time
    AuditLog        one JSON line per event, built from a fixed list of fields, so content cannot get in

In Express terms an ASGI middleware class is `app.use((req, res, next) => ...)`: it receives each request before the routes do and can answer it or
pass it on. A FastAPI dependency (Depends) is like middleware that only the routes that list it run, and it can raise an error that becomes the answer.

THE ORDER OF THE LAYERS (outside to inside) for a request:
    OuterGuard -> TrustedHost (Host header) -> slowapi (global limit) -> BodyGuard (size, content type) -> routing
    -> route dependencies: strict rate limit, then API key -> the route reads and checks the body -> the analysis
Everything cheap and everything that needs no secret comes first. The body is read and parsed only after the key has been accepted (FastAPI would
parse it before running dependencies if the route declared a body parameter, so the routes read it themselves: see main.py).

WHAT NEVER GOES INTO AN ERROR OR A LOG LINE: email text, header values, addresses, the key, the Host or any other header a client sent, the query
string. Errors are fixed sentences plus a request id; log lines come from AuditLog, which only accepts the fields listed in AUDIT_FIELDS and
reduces every value to a short string of safe characters.
"""

import hashlib
import hmac
import json
import logging
import math
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.api.settings import MAX_BODY_BYTES

AUDIT_LOGGER = "pretextguard.audit"
KNOWN_PATHS = frozenset(("/analyze", "/analyze/thread", "/explain", "/results", "/health"))
DOCS_PATHS = frozenset(("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"))

# code -> (HTTP status, fixed sentence). The sentences never contain anything the client sent.
ERRORS = {
    "bad_request": (400, "The request could not be understood."),
    "bad_length": (400, "The Content-Length header is not valid."),
    "analysis_rejected": (400, "The input could not be analysed."),
    "unauthorized": (401, "A valid API key is required in the X-API-Key header."),
    "not_found": (404, "Not found."),
    "method_not_allowed": (405, "Method not allowed."),
    "too_large": (413, "The request is larger than the limit."),
    "unsupported_media_type": (415, "Send the body as application/json."),
    "invalid_request": (422, "The request did not match the expected shape."),
    "rate_limited": (429, "Too many requests. Wait and try again."),
    "internal_error": (500, "The server could not complete the request. This is a bug, not a problem with your input. Quote the request id."),
    "model_unavailable": (503, "The analysis model is not loaded."),
    "busy": (503, "The classifier is busy. Try again in a moment."),
}


class ApiError(Exception):
    """An error with a code from ERRORS. The exception handler in main.py turns it into the JSON answer; extra headers (Retry-After) ride along."""

    def __init__(self, code, headers=None, errors=None):
        super().__init__(code)
        self.code, self.headers, self.errors = code, dict(headers or {}), errors


def error_response(code, request_id, headers=None, errors=None):
    status, detail = ERRORS[code]
    body = {"detail": detail, "code": code, "request_id": request_id}
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, headers=headers)


# ------------------------------------------------------------------------------------------------------------------------ audit log

AUDIT_FIELDS = frozenset(("event", "request_id", "mode", "explain", "explained", "score", "verdict", "tactics", "contradictions", "duration_ms", "bytes",
                          "messages", "status", "path", "reason", "client", "error_class", "where"))
SAFE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _.:/-")
MAX_LOG_STRING = 80
MAX_LOG_LIST = 12


def clean_value(value):
    """A log value reduced to a number, a boolean, null, or a short string of letters, digits and _ . : / - (anything else becomes '_')."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 3) if math.isfinite(value) else None
    if isinstance(value, str):
        return "".join(ch if ch in SAFE_CHARS else "_" for ch in value[:MAX_LOG_STRING])
    if isinstance(value, (list, tuple)):
        return [clean_value(item) for item in list(value)[:MAX_LOG_LIST]]
    return "?"


class AuditLog:
    """One JSON line per event to the logger 'pretextguard.audit'. A field that is not in AUDIT_FIELDS is a programming error (KeyError), not a
    silent leak; a value is cleaned by clean_value, so no newline, quote, markup or long text can get into a line."""

    def __init__(self, logger=None):
        self.logger = logger or configure_audit_logging()

    def write(self, event, **fields):
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": clean_value(event)}
        for name, value in fields.items():
            if name not in AUDIT_FIELDS:
                raise KeyError("audit field %r is not allowed" % name)
            record[name] = clean_value(value)
        self.logger.info(json.dumps(record, separators=(",", ":")))


def configure_audit_logging(stream=None):
    """The audit logger with one handler that prints the bare message to stdout (once; later calls reuse it). It does not pass records on to the root logger."""
    logger = logging.getLogger(AUDIT_LOGGER)
    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def where_of(error):
    """Where an exception was raised, as 'file.py:123 function': a place in our code, never a value, so it is safe to log."""
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "unknown"
    last = frames[-1]
    return "%s:%d %s" % (os.path.basename(last.filename), last.lineno, last.name)


def client_of(scope):
    client = scope.get("client")
    return client[0] if client else None


def path_label(scope):
    path = scope.get("path", "")
    return path if path in KNOWN_PATHS else "other"


# ------------------------------------------------------------------------------------------------------------------- the outer layer

SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
)


class OuterGuard:
    """Gives every request a random id (the client cannot choose it, so it cannot forge a log line), puts the security headers and X-Request-ID on every
    response, and answers 500 with a fixed message if anything unexpected gets this far. The details go to the audit log as the class of the error and
    the place in our code where it was raised: never the message, which may quote the input.

    Headers: no-store (a report is about one email and must not be cached anywhere), nosniff (a browser must not guess a type for the JSON), a
    Content-Security-Policy that allows nothing (the answers are data, not pages), no framing, no referrer. The CSP is left off the interactive docs
    pages when they are turned on for development, because they load their own scripts."""

    def __init__(self, app, audit, docs_enabled=False):
        self.app, self.audit, self.docs_enabled = app, audit, docs_enabled

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        relax_csp = self.docs_enabled and scope.get("path") in DOCS_PATHS
        started = False

        async def guarded_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    if not (relax_csp and name == "Content-Security-Policy"):
                        headers[name] = value
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, guarded_send)
        except Exception as error:
            self.audit.write("error", request_id=request_id, status=500, path=path_label(scope), error_class=type(error).__name__, where=where_of(error))
            if not started:
                await error_response("internal_error", request_id)(scope, receive, guarded_send)


class BodyGuard:
    """Checks that cost nothing, before the route runs, and counts the body while it streams in.

    1. Content-Length must be absent or one plain number (digits only, one header) and at most max_bytes: otherwise 400 or 413 straight away.
    2. A POST must say it is application/json (parameters such as charset are ignored): otherwise 415.
    3. The bytes that actually arrive are counted. Content-Length can lie or be missing (chunked uploads have none), so the count, not the header, is
       the limit: once it passes max_bytes the route is told the client has gone, whatever it does next is thrown away, and the answer is 413.
       The connection is then closed (Connection: close) instead of reading the rest."""

    def __init__(self, app, audit, max_bytes=MAX_BODY_BYTES):
        self.app, self.audit, self.max_bytes = app, audit, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        request_id = scope.get("state", {}).get("request_id")

        async def refuse(code):
            self.audit.write("denied", request_id=request_id, status=ERRORS[code][0], reason=code, path=path_label(scope), client=client_of(scope))
            await error_response(code, request_id, headers={"Connection": "close"})(scope, receive, send)

        lengths = headers.getlist("content-length")
        if len(lengths) > 1 or (lengths and not (lengths[0].isascii() and lengths[0].isdigit() and len(lengths[0]) <= 12)):
            return await refuse("bad_length")
        if lengths and int(lengths[0]) > self.max_bytes:
            return await refuse("too_large")
        if scope["method"] == "POST" and headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return await refuse("unsupported_media_type")

        state = {"received": 0, "too_large": False}

        async def counted_receive():
            if state["too_large"]:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > self.max_bytes:
                    state["too_large"] = True
                    return {"type": "http.disconnect"}
            return message

        async def counted_send(message):
            if not state["too_large"]:
                await send(message)

        try:
            await self.app(scope, counted_receive, counted_send)
        except Exception:
            if not state["too_large"]:
                raise
        if state["too_large"]:
            await refuse("too_large")


# --------------------------------------------------------------------------------------------------------------------- rate limits

def make_limiter(settings):
    """The slowapi Limiter. Per client address (the socket's peer, never X-Forwarded-For, which a client can write), a moving window (no burst at the
    edge of a fixed window), one shared 'global' limit for all routes, counted in memory (one process, no database). slowapi also reads RATELIMIT_*
    names from the environment and from .env; a stray RATELIMIT_ENABLED=False would switch the limits off, so `enabled` is forced on here."""
    limiter = Limiter(key_func=get_remote_address, application_limits=[settings.rate_global], strategy="moving-window",
                      headers_enabled=False, key_style="endpoint", storage_uri="memory://")
    limiter.enabled = True
    return limiter


def make_rate_dependencies(limiter, settings):
    """(rate_analyze, rate_explain): FastAPI dependencies that count the request against the strict limit of their route. They are listed before the key
    check on each route, so a request with a wrong key is counted too and guessing keys is limited. /analyze and /analyze/thread share rate_analyze,
    so they share one allowance."""

    @limiter.limit(settings.rate_analyze)
    async def rate_analyze(request: Request):
        return None

    @limiter.limit(settings.rate_explain)
    async def rate_explain(request: Request):
        return None

    return rate_analyze, rate_explain


def retry_after(exc):
    """Seconds to wait after a rate-limit refusal: the length of the window that was exceeded, which is never too short."""
    try:
        return str(int(exc.limit.limit.get_expiry()))
    except Exception:
        return "60"


# ------------------------------------------------------------------------------------------------------------------------- API key

def key_digest(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).digest()


def keys_match(provided, expected_digest):
    """True when `provided` is the key whose SHA-256 digest is `expected_digest`. Both sides are hashed first, so the two values compared always have the
    same length, and hmac.compare_digest takes the same time whatever the number of matching leading bytes: a plain == stops at the first different
    character, and the time it takes can tell an attacker how many characters were right."""
    return hmac.compare_digest(key_digest(provided), expected_digest)


def make_require_key(api_key):
    """The dependency that refuses a request without the right X-API-Key header (exactly one such header; a key in the URL is never read, because URLs
    end up in logs and browser history). Fails closed: no header, a wrong one or a repeated one are all 401."""
    expected = key_digest(api_key)

    async def require_key(request: Request):
        values = request.headers.getlist("x-api-key")
        if len(values) != 1 or not keys_match(values[0], expected):
            raise ApiError("unauthorized", headers={"WWW-Authenticate": 'ApiKey header="X-API-Key"'})

    return require_key
