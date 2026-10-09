"""Phase 11: the FastAPI app. It exposes analyze() and the evaluation numbers, and nothing else.

    python -m src.api.main            # listens on http://127.0.0.1:8000 (settings: python -m src.api.settings)
    python -m src.api.selftest        # the security controls, with a stand-in classifier (no model, no network)
    python -m src.api.smoke           # a real session with the running server and the trained model

ROUTES
    POST /analyze          key   {"email": "...", "org_domain": "acmecorp.com"}      the report, without LIME (about 0.05 s)
    POST /analyze/thread   key   {"messages": ["...", "..."], "org_domain": ...}     the report for the newest message judged against the earlier ones
    POST /explain          key   exactly one of "email" or "messages", + org_domain   the same report with LIME highlights (150 copies, about 5 s)
    GET  /results                the evaluation tables the dashboard may read (?name=score_budget for one table; no name lists them)
    GET  /health                 whether the model is loaded (the port opens only after the start-up load; 503 means the load failed)

The score does not depend on LIME, so the interface shows the score from /analyze first and asks /explain for the highlights afterwards.

HOW A REQUEST IS HANDLED (src/api/security.py has the layers in order). The routes are `async def`: they read the body (already capped), check it with
Pydantic, and hand the analysis to a worker thread (run_in_threadpool). The analysis is CPU-bound Python; run inside an `async def` it would freeze the
whole server for its duration, because there is one event loop (like one Node process). In a worker thread the loop stays free to answer /health, refuse
a wrong key or send a 429 while an analysis runs.

ONE ANALYSIS AT A TIME. The classifier is not built to run twice at once and two analyses would each be half as fast, so a lock lets one through. /analyze
waits up to PRETEXTGUARD_WAIT_SECONDS (2 by default) for the lock, then answers 503 with Retry-After. /explain never waits: one LIME run holds the CPU for
about 5 seconds, so a second request is told to come back instead of queueing. Only clients with the key reach the lock, and each is limited per address.
A worker thread cannot be stopped from outside, so the time one input may hold the lock is the time the pipeline needs for it; the crafted inputs of
Phases 2 to 10 finish in under 5 seconds each.

NOTHING IS STORED. The email lives in memory for the request. The audit log (one JSON line per analysis: request id, time, mode, score, verdict, tactics
that fired, count of contradictions, duration, sizes) has no field that could hold content, and no error message quotes the input.
"""

import time
from contextlib import asynccontextmanager
from threading import Lock

import uvicorn
from fastapi import Depends, FastAPI, Query
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.api.results import ResultStore
from src.api.schemas import AnalyzeRequest, ExplainRequest, Health, InvalidRequest, Report, ResultIndex, ResultTable, ThreadRequest, parse_request, safe_errors
from src.api.security import (ERRORS, ApiError, AuditLog, BodyGuard, OuterGuard, client_of, error_response, make_limiter, make_rate_dependencies,
                              make_require_key, path_label, retry_after, where_of)
from src.api.settings import LIMIT_CONCURRENCY, SettingsError, load_settings
from src.claims.patterns import PATTERN_VERSION
from src.router.pipeline import ReportError
from src.router.score import SCORE_VERSION
from src.verifiers.thread_verifier import THREAD_RULES_VERSION
from src.verifiers.verify import RULES_VERSION

# ==============================================================================================================================================
# >>> TEMPORARY, FOR TESTING ONLY <<<   CORS IS WIDE OPEN WHILE THIS IS True.
# True lets a web page from ANY origin call this API from a browser (any origin, any method, any header, including X-API-Key).
# SET IT TO False BEFORE THIS API IS EVER DEPLOYED OR REACHABLE FROM ANOTHER MACHINE.
# False = no CORS headers at all: the secure design, where the interface reaches the API through a same-origin proxy that adds the key
# (master document Section 8.19). The key is still required on the three POST routes either way, and the Host header check still applies.
# The self-test prints an info line saying which way this is set, and python -m src.api.main prints a warning while it is True.
# ==============================================================================================================================================
CORS_ALLOW_ANY_ORIGIN = True

VERSIONS = {"score": SCORE_VERSION, "rules": RULES_VERSION, "thread_rules": THREAD_RULES_VERSION, "claim_patterns": PATTERN_VERSION}
WARMUP_TEXT = "Hello, this is a start-up check of the analysis pipeline. Please ignore it."
STATUS_CODES = {404: "not_found", 405: "method_not_allowed"}
DENIED = frozenset((401, 413, 415, 429))      # refusals that are about security; the rest of the refusals are logged as 'refused'


def default_loader(settings):
    """Load the trained classifier and spaCy and run one analysis of a fixed text, so a broken install stops the start-up and the first user is not slow."""
    from src.router.pipeline import Analyzer
    analyzer = Analyzer(explain_samples=settings.explain_samples)
    analyzer.analyze(WARMUP_TEXT, explain=False)
    return analyzer


def input_stats(raw):
    """(bytes, messages) of the text or list of texts handed to the pipeline: sizes only, for the audit log."""
    items = raw if isinstance(raw, list) else [raw]
    return sum(len(item.encode("utf-8", errors="replace")) for item in items), len(items)


def analyse_locked(state, raw, org_domain, explain, request_id):
    """The analysis in a worker thread, behind the lock. Raises ApiError (busy, model unavailable, input rejected); anything else is a bug and goes up."""
    analyzer = state.analyzer
    if analyzer is None:
        raise ApiError("model_unavailable", headers={"Retry-After": "30"})
    wait = 0 if explain else state.settings.wait_seconds
    if not (state.lock.acquire(timeout=wait) if wait > 0 else state.lock.acquire(blocking=False)):
        raise ApiError("busy", headers={"Retry-After": "5" if explain else "2"})
    started = time.perf_counter()
    try:
        report = analyzer.analyze(raw, org_domain=org_domain, explain=explain, request_id=request_id)
    except (TypeError, ValueError) as error:
        # validation has already run, so the pipeline refusing the input means a bug: answer 400, but log it as an error (class and place only)
        state.audit.write("error", request_id=request_id, status=400, error_class=type(error).__name__, where=where_of(error))
        raise ApiError("analysis_rejected")
    finally:
        state.lock.release()
    size, count = input_stats(raw)
    state.audit.write("analysis", request_id=request_id, mode=report["mode"], explain=explain, explained=report["explained"], score=report["score"],
                      verdict=report["verdict"], tactics=[t["name"] for t in report["tactics"] if t["fired"]],
                      contradictions=sum(1 for row in report["ledger"] if row["contradiction"] is True),
                      duration_ms=int((time.perf_counter() - started) * 1000), bytes=size, messages=count)
    return report


def create_app(settings=None, analyzer=None, loader=None, audit=None, results=None, cors_any_origin=None):
    """The app. `settings` default to load_settings() (which refuses to start without a good key); `analyzer` is an already-built Analyzer (tests pass one
    with a stand-in classifier); otherwise `loader` (default: the trained model) builds it at start-up. If loading fails the server still starts, says so
    in /health (503) and answers the analysis routes with 503, and the audit log has the reason. `cors_any_origin` defaults to CORS_ALLOW_ANY_ORIGIN
    (the temporary switch at the top of this file); the self-test builds the app both ways."""
    settings = settings or load_settings()
    if cors_any_origin is None:
        cors_any_origin = CORS_ALLOW_ANY_ORIGIN
    audit = audit or AuditLog()
    limiter = make_limiter(settings)
    rate_analyze, rate_explain = make_rate_dependencies(limiter, settings)
    require_key = make_require_key(settings.api_key)
    loader = loader or (lambda: default_loader(settings))

    @asynccontextmanager
    async def lifespan(app):
        if cors_any_origin:
            audit.write("startup", reason="cors_open_for_testing")
        if app.state.analyzer is None:
            started = time.perf_counter()
            try:
                app.state.analyzer = await run_in_threadpool(loader)
                audit.write("startup", reason="model_loaded", duration_ms=int((time.perf_counter() - started) * 1000))
            except Exception as error:
                audit.write("startup_failed", error_class=type(error).__name__, where=where_of(error), reason=str(error)[:80])
        yield
        app.state.analyzer = None

    docs = {} if settings.enable_docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="PretextGuard API", lifespan=lifespan, redirect_slashes=False, **docs)
    app.state.settings, app.state.audit, app.state.limiter = settings, audit, limiter
    app.state.analyzer, app.state.lock = analyzer, Lock()
    app.state.results = results if results is not None else ResultStore(settings.results_dir)

    # layers, inner to outer (the last one added is the outermost)
    app.add_middleware(BodyGuard, audit=audit)
    app.add_middleware(SlowAPIASGIMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    if cors_any_origin:
        # >>> TEMPORARY: CORS WIDE OPEN, TESTING ONLY. Set CORS_ALLOW_ANY_ORIGIN = False (top of this file) before any deployment. <<<
        # Placed outside the Host check, the rate limits and the body guard so that a browser's preflight (OPTIONS) is answered first and every
        # answer, errors included, carries the headers; OuterGuard is still outside it, so the security headers are on these answers too.
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
                           expose_headers=["X-Request-ID", "Retry-After"], max_age=600)
    app.add_middleware(OuterGuard, audit=audit, docs_enabled=settings.enable_docs)

    # ------------------------------------------------------------------------------------------------------------ errors
    def refusal(request, code, headers=None, errors=None):
        status = ERRORS[code][0]
        request_id = request.state.request_id
        audit.write("denied" if status in DENIED else "refused", request_id=request_id, status=status, reason=code, path=path_label(request.scope), client=client_of(request.scope))
        return error_response(code, request_id, headers=headers, errors=errors)

    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError):
        return refusal(request, exc.code, headers=exc.headers, errors=exc.errors)

    @app.exception_handler(InvalidRequest)
    async def on_invalid(request: Request, exc: InvalidRequest):
        return refusal(request, "invalid_request", errors=exc.errors)

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError):
        return refusal(request, "invalid_request", errors=safe_errors(exc.errors()))

    @app.exception_handler(RateLimitExceeded)
    async def on_rate_limit(request: Request, exc: RateLimitExceeded):
        return refusal(request, "rate_limited", headers={"Retry-After": retry_after(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        return refusal(request, STATUS_CODES.get(exc.status_code, "bad_request"), headers=exc.headers)

    @app.exception_handler(ReportError)
    async def on_report_error(request: Request, exc: ReportError):
        request_id = request.state.request_id
        audit.write("error", request_id=request_id, status=500, path=path_label(request.scope), error_class=type(exc).__name__, where=where_of(exc))
        return error_response("internal_error", request_id)

    # ----------------------------------------------------------------------------------------------------------- routes
    async def read(request, model):
        """The body, read now (the guard has capped it) and checked by Pydantic. Done here, after the key was accepted, not by FastAPI before it."""
        return parse_request(model, await request.body())

    async def run(request, raw, org_domain, explain):
        return await run_in_threadpool(analyse_locked, request.app.state, raw, org_domain, explain, request.state.request_id)

    @app.post("/analyze", response_model=Report, dependencies=[Depends(rate_analyze), Depends(require_key)])
    async def analyze_email(request: Request):
        payload = await read(request, AnalyzeRequest)
        return await run(request, payload.email, payload.org_domain, explain=False)

    @app.post("/analyze/thread", response_model=Report, dependencies=[Depends(rate_analyze), Depends(require_key)])
    async def analyze_thread(request: Request):
        payload = await read(request, ThreadRequest)
        return await run(request, payload.messages, payload.org_domain, explain=False)

    @app.post("/explain", response_model=Report, dependencies=[Depends(rate_explain), Depends(require_key)])
    async def explain(request: Request):
        payload = await read(request, ExplainRequest)
        return await run(request, payload.email if payload.email is not None else payload.messages, payload.org_domain, explain=True)

    @app.get("/results", response_model=ResultIndex | ResultTable)
    async def results_route(request: Request, name: str | None = Query(default=None, max_length=64)):
        store = request.app.state.results
        if name is None:
            return store.index()
        table = store.get(name)
        if table is None:
            raise ApiError("not_found")
        return table

    @app.get("/health", response_model=Health)
    async def health(request: Request):
        loaded = request.app.state.analyzer is not None
        body = Health(status="ok" if loaded else "unavailable", model_loaded=loaded, explain_samples=settings.explain_samples, versions=VERSIONS,
                      results_files=len(request.app.state.results.tables))
        return body if loaded else JSONResponse(body.model_dump(), status_code=503)

    return app


def serve_options(settings):
    """The uvicorn options, in one place so the self-test can check them: the loopback address by default; one process (the model is in memory once);
    at most LIMIT_CONCURRENCY open connections (beyond that uvicorn answers 503); keep-alive connections closed after 5 idle seconds; no 'server:
    uvicorn' header; proxy_headers off, so the client address is the socket's peer, never an X-Forwarded-For header that a client wrote (behind a
    reverse proxy, set --forwarded-allow-ips deliberately)."""
    return {"host": settings.host, "port": settings.port, "limit_concurrency": LIMIT_CONCURRENCY, "timeout_keep_alive": 5, "server_header": False,
            "proxy_headers": False, "log_level": "info"}


def main():
    try:
        settings = load_settings()
    except SettingsError as error:
        hint = "\nMake a key with:  python -m src.api.settings --new-key   and put it in .env as PRETEXTGUARD_API_KEY=..." if "API_KEY" in str(error) else ""
        raise SystemExit("Cannot start: %s%s" % (error, hint))
    print("\n".join(settings.summary()))
    if CORS_ALLOW_ANY_ORIGIN:
        print("*** WARNING: CORS IS WIDE OPEN (CORS_ALLOW_ANY_ORIGIN = True in src/api/main.py). Testing only: set it to False before any deployment. ***")
    print("Loading the model (a few seconds); the port opens when the server is ready.")
    uvicorn.run(create_app(settings), **serve_options(settings))


if __name__ == "__main__":
    main()
