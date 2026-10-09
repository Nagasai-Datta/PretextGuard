"""Phase 11: the self-test of the API's security controls, with crafted requests and a stand-in classifier.

Run from the project root:   python -m src.api.selftest              (about 30 seconds; writes results/api_checks.csv)
                             python -m src.api.selftest --no-write   (prints only)

The app is called in-process through FastAPI's TestClient (no network, no server). The classifier is the stand-in of src/router/selftest.py, because the
trained weights exist only on the Mac; everything else is the real code: the real settings, middleware, rate limiter, schemas, routes, error handlers,
audit log, results store and the whole analyze() pipeline with the real spaCy claim extractor. The real model, the real server and real HTTP are
src/api/smoke.py.

WHAT IS CHECKED, by group:
    settings      the key rules, the placeholder, the .env reader, fail-closed start-up, nothing leaks the key
    functional    every route returns what analyze() returns, typed; /results serves only its allow-list; the thread and LIME routes
    auth          no key, wrong key, repeated key, key in the URL, odd bytes; authentication before the body is read; constant-time compare
    validation    wrong content type, bad JSON, wrong types, unknown fields, size and count limits, domain shapes, nesting and key floods, surrogates
    size          Content-Length that lies, is missing (chunked) or is not a number, counted as the bytes arrive (a direct ASGI harness)
    limits        the global and per-route rate limits, wrong keys counted, shared and separate allowances, a forged X-Forwarded-For, a switched-off limiter
    concurrency   a busy classifier answers 503 (waiting for /analyze, at once for /explain), parallel requests, the lock is never left held
    errors        ReportError, unexpected errors and a missing model give fixed messages and a request id and never the message of the exception
    headers       security headers on every kind of response, CORS (closed by design, open when the temporary switch CORS_ALLOW_ANY_ORIGIN is on), no docs by default,
                  the Host header, request ids
    audit         one line per analysis with a fixed set of fields, hostile values cleaned, and a canary string that must appear in no log line
    xss           markup, scripts and template payloads in every part of an email never reach a response as markup

A test that always passes proves nothing, so src/api/mutation_check.py breaks the controls one at a time (the key check, the body count, the log
cleaning, the lock, and so on) in a scratch copy and confirms that this self-test fails each time.
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
import tempfile
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", message=".*starlette.testclient.*")      # Starlette prefers the httpx2 package for its TestClient; the pinned httpx works

from fastapi.testclient import TestClient

from src.api import results as results_module
from src.api.main import CORS_ALLOW_ANY_ORIGIN, VERSIONS, create_app, serve_options
from src.api.results import RESULT_FILES, ResultStore
from src.api.schemas import ErrorResponse, Report
from src.api.security import AUDIT_FIELDS, AUDIT_LOGGER, ERRORS, AuditLog, clean_value, key_digest, keys_match
from src.api.settings import (LIMIT_CONCURRENCY, MAX_BODY_BYTES, MAX_EMAIL_BYTES, MAX_THREAD_BYTES, MAX_THREAD_MESSAGES, Settings, SettingsError,
                              check_key, load_settings, new_key, read_env_file)
from src.data.paths import PROJECT_ROOT, RESULTS_DIR
from src.router.pipeline import Analyzer, ReportError, check_report
from src.router.selftest import DAVID_GMAIL, HIJACK_TEXT, HONEST, JOHN, MARY, NEWSLETTER, PARAGRAPHS, StubClassifier, calm_thread, eml

KEY = "selftest-key-" + "Qw3rTy9Zx" * 3                      # 40 characters, many different ones
CANARY = "ZQX7CANARY9431"                                     # a string that must appear in no log line and no error response
OUT = RESULTS_DIR / "api_checks.csv"
BIG = {"rate_analyze": "100000/minute", "rate_explain": "100000/minute", "rate_global": "1000000/minute"}
XSS_PAYLOADS = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "<svg/onload=alert(1)>", "\"><script>alert(document.cookie)</script>", "javascript:alert(1)",
                "<iframe srcdoc='<script>alert(1)</script>'>", "<!-- x --><b>bold</b>", "]]><script>x</script>", "{{7*7}} ${7*7} #{7*7} ${jndi:ldap://x.example/a}",
                "`backtick` <a href=\"javascript:alert(1)\">link</a>", "&lt;script&gt;alert(1)&lt;/script&gt;", chr(0x202e) + "<b>rlo</b>", "<math><mtext></table></mglyph><style><img src=x onerror=alert(1)>"]


# ------------------------------------------------------------------------------------------------------------------ the tools

class Checks:
    def __init__(self):
        self.rows = []

    def add(self, group, item, ok, value="", expected="", info=False):
        status = "info" if info else ("PASS" if ok else "FAIL")
        self.rows.append([group, item, str(value)[:300], expected, status])
        print("  %s [%s] %s%s" % (status, group, item, "" if ok or info or value == "" else "  -> " + str(value)[:300]))

    @property
    def failed(self):
        return [r for r in self.rows if r[4] == "FAIL"]


class Capture(logging.Handler):
    """Collects the text of log records. Records of the test client itself (httpx logs every URL it requests) are not the server's and are skipped."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        if record.name.split(".")[0] not in ("httpx", "httpcore", "httpx2", "httpcore2"):
            self.lines.append(record.getMessage())


def asgi_request(app, method, path, headers, chunks):
    """Call the ASGI app directly with a body that arrives in the given chunks (no Content-Length unless a header says so): the way to send a body
    whose Content-Length lies or is missing. Returns (status, response headers as a dict, body bytes)."""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "", "headers": [(k.lower().encode(), v.encode("latin-1")) for k, v in headers], "client": ("203.0.113.9", 5000),
             "server": ("localhost", 80)}
    pending, sent = list(chunks), []

    async def receive():
        if pending:
            body = pending.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(pending)}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], {k.decode().lower(): v.decode("latin-1") for k, v in start["headers"]}, body


def js(response):
    """The JSON body of a response, or {} when it has none: a control that breaks should fail its check, not crash the run."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


# --------------------------------------------------------------------------------------------------------------- the self-test

def self_test(write=True, out=OUT):
    c = Checks()
    audit_lines, other_lines = Capture(), Capture()
    audit_logger = logging.getLogger(AUDIT_LOGGER)
    for handler in list(audit_logger.handlers):
        audit_logger.removeHandler(handler)
    audit_logger.addHandler(audit_lines)
    audit_logger.propagate = False
    audit_logger.setLevel(logging.INFO)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(other_lines)
    root.setLevel(logging.DEBUG)
    audit = AuditLog(audit_logger)

    stub = StubClassifier()
    analyzer = Analyzer(classifier=stub, explain_samples=150)
    store = ResultStore(RESULTS_DIR)
    recorded = []                  # every error response of the run: (status, parsed body or None, raw text)

    def base_settings(**overrides):
        values = dict(api_key=KEY, allowed_hosts=("localhost",), wait_seconds=0.5, **BIG)
        values.update(overrides)
        return Settings(**values)

    def build(analyzer=analyzer, loader=None, cors=False, **overrides):
        """An app for a test. CORS is closed here (the secure design) unless a test asks for it; the shipped state of the switch is reported at the end."""
        app = create_app(base_settings(**overrides), analyzer=analyzer, loader=loader, audit=audit, results=store, cors_any_origin=cors)
        return app, TestClient(app, base_url="http://localhost", raise_server_exceptions=False)

    def call(client, method, path, key=True, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        if key is True:
            headers.setdefault("X-API-Key", KEY)
        elif key:
            headers["X-API-Key"] = key
        response = client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = None
            recorded.append((response.status_code, body, response.text))
        return response

    app, client = build()
    post = lambda path, payload, **kw: call(client, "POST", path, json=payload, **kw)

    # ============================================================================================================== settings
    G = "settings"
    c.add(G, "a good key passes; missing, empty, the placeholder, short, with a space, non-ASCII or with few different characters do not",
          check_key(KEY) == [] and all(check_key(k) for k in (None, "", "change-me", "x" * 23, "a" * 30, "has a space inside it " * 2, "ключ" * 10, "abababababababababababab" * 1)),
          [bool(check_key(k)) for k in (None, "", "change-me", "x" * 23, "a" * 30, "ключ" * 10)])
    try:
        Settings(api_key="short-secret-key")
        c.add(G, "Settings refuses a bad key and its message never repeats the key", False)
    except SettingsError as error:
        c.add(G, "Settings refuses a bad key and its message never repeats the key", "short-secret-key" not in str(error) and "24" in str(error), str(error))
    refused = []
    for override in ({"rate_analyze": "lots"}, {"rate_global": ""}, {"explain_samples": 10}, {"explain_samples": 5000}, {"wait_seconds": 99}, {"allowed_hosts": ("*",)},
                     {"allowed_hosts": ()}, {"port": 0}):
        try:
            base_settings(**override)
            refused.append(False)
        except SettingsError:
            refused.append(True)
    c.add(G, "Settings refuses a malformed rate, LIME copies outside 50..2000, a wait over 30 s, a '*' or empty host list and port 0", all(refused), refused)
    with tempfile.TemporaryDirectory() as folder:
        env_path = Path(folder) / ".env"
        env_path.write_text("# comment\n\nPRETEXTGUARD_API_KEY=\"%s\"\nPRETEXTGUARD_RATE_ANALYZE=7/minute\nPRETEXTGUARD_PORT=9000\nnot a setting line\nPRETEXTGUARD_ENABLE_DOCS=1\n" % KEY, encoding="utf-8")
        parsed = read_env_file(env_path)
        loaded = load_settings(environ={}, env_file=env_path)
        wins = load_settings(environ={"PRETEXTGUARD_RATE_ANALYZE": "9/minute"}, env_file=env_path)
        c.add(G, ".env is read (comments, blank lines, quotes), the real environment wins over the file, and defaults fill the rest",
              parsed.get("PRETEXTGUARD_API_KEY") == KEY and loaded.rate_analyze == "7/minute" and loaded.port == 9000 and loaded.enable_docs is True
              and wins.rate_analyze == "9/minute" and loaded.rate_explain == "6/minute" and loaded.host == "127.0.0.1", str(loaded.rate_analyze))
        for name, environ, path in (("a missing key", {}, env_path.with_name("nothing")), ("a non-numeric port", {"PRETEXTGUARD_API_KEY": KEY, "PRETEXTGUARD_PORT": "x"}, None)):
            try:
                load_settings(environ=environ, env_file=path)
                c.add(G, "start-up fails closed on %s" % name, False)
            except SettingsError:
                c.add(G, "start-up fails closed on %s" % name, True)
    try:
        load_settings(environ={}, env_file=PROJECT_ROOT / ".env.example")
        c.add(G, "the placeholder key in .env.example is refused", False)
    except SettingsError as error:
        c.add(G, "the placeholder key in .env.example is refused", "placeholder" in str(error), str(error)[:100])
    keys = {new_key() for _ in range(20)}
    c.add(G, "new_key makes a different key each time and every one passes the key rules", len(keys) == 20 and all(check_key(k) == [] for k in keys) and all(len(k) >= 43 for k in keys))
    shown = "\n".join(base_settings().summary()) + repr(base_settings())
    c.add(G, "the summary and repr of Settings do not contain the key", KEY not in shown and KEY[:4] in shown)
    options = serve_options(base_settings(host="127.0.0.1"))
    c.add(G, "uvicorn is started on the loopback address, with a concurrency limit, no server header and no trust in X-Forwarded-For",
          options["host"] == "127.0.0.1" and options["limit_concurrency"] == LIMIT_CONCURRENCY == 20 and options["server_header"] is False and options["proxy_headers"] is False, str(options))
    c.add(G, "the size caps are the planned ones and are constants (4 MB request, 300,000 bytes per email, 50 messages, 1.5 MB per thread)",
          (MAX_BODY_BYTES, MAX_EMAIL_BYTES, MAX_THREAD_MESSAGES, MAX_THREAD_BYTES) == (4_000_000, 300_000, 50, 1_500_000) and "MAX_EMAIL_BYTES" not in Settings.__dataclass_fields__)
    c.add(G, "the routes are exactly /analyze, /analyze/thread, /explain, /results and /health (no docs, no openapi)",
          sorted(r.path for r in app.routes) == ["/analyze", "/analyze/thread", "/explain", "/health", "/results"], sorted(r.path for r in app.routes))

    # ============================================================================================================ functional
    G = "functional"
    r = call(client, "GET", "/health", key=False)
    health = r.json()
    c.add(G, "GET /health needs no key and reports the model loaded and the versions", r.status_code == 200 and health["model_loaded"] is True and health["status"] == "ok"
          and health["versions"] == VERSIONS and health["explain_samples"] == 150, str(health))
    r = post("/analyze", {"email": DAVID_GMAIL})
    report = r.json()
    direct = json.loads(json.dumps(analyzer.analyze(DAVID_GMAIL, explain=False, request_id="fixed-id")))
    api_copy = dict(report, request_id="fixed-id")
    c.add(G, "POST /analyze returns the pipeline's report unchanged (High risk for the David email, no LIME)", r.status_code == 200 and api_copy == direct and report["verdict"] == "High risk"
          and report["explained"] is False and not any(t["highlights"] for t in report["tactics"]), "%s %s" % (r.status_code, report.get("verdict")))
    c.add(G, "the report passes the pipeline's own check and the typed Report model, and the model gives the same dictionary back",
          check_report(report, analyzer.config) == [] and Report.model_validate(report).model_dump() == report)
    c.add(G, "the response is JSON, never cached, and its request id is the one in the header", r.headers.get("content-type", "").startswith("application/json") and r.headers.get("cache-control") == "no-store"
          and r.headers.get("x-request-id") == report.get("request_id"))
    r = post("/analyze", {"email": DAVID_GMAIL, "org_domain": "OtherCorp.com."})
    r2 = post("/analyze", {"email": DAVID_GMAIL, "org_domain": "gmail.com"})
    c.add(G, "org_domain is lower-cased and used; a free mailbox provider is accepted and noted as ignored", js(r).get("org_domain") == "othercorp.com" and "org_domain_ignored" in js(r2).get("coverage", {}).get("limits", []))
    calm = calm_thread(4)
    takeover = calm + [eml(4, JOHN, "Re: Invoice 77", HIJACK_TEXT, previous=PARAGRAPHS[3], ip="52.10.20.30")]
    r = post("/analyze/thread", {"messages": takeover})
    thread_report = r.json()
    c.add(G, "POST /analyze/thread judges the newest message against the earlier ones and finds the flip point (message 4 of 5)", r.status_code == 200 and thread_report["mode"] == "thread"
          and thread_report["thread"]["flip_index"] == 4 and thread_report["thread"]["messages"] == 5 and Report.model_validate(thread_report).model_dump() == thread_report,
          "%s %s" % (r.status_code, thread_report.get("thread", {}) and thread_report["thread"]["flip_index"]))
    r = post("/analyze/thread", {"messages": [DAVID_GMAIL]})
    c.add(G, "a thread of one message is analysed as a single email", r.status_code == 200 and r.json()["mode"] == "email" and r.json()["thread"] is None)
    before = stub.texts_seen
    r = post("/explain", {"email": DAVID_GMAIL})
    explained = r.json()
    copies = stub.texts_seen - before
    c.add(G, "POST /explain adds LIME highlights that fit the text, uses about 150 copies, and the score is the same as without LIME",
          r.status_code == 200 and explained["explained"] is True and any(t["highlights"] for t in explained["tactics"] if t["fired"]) and 100 <= copies <= 200
          and all(explained["text_read"][h["start"]:h["end"]] == h["text"] for t in explained["tactics"] for h in t["highlights"])
          and explained["score"] == report["score"] and explained["verdict"] == report["verdict"] and check_report(explained, analyzer.config) == [], "copies %d" % copies)
    r = post("/explain", {"messages": takeover})
    c.add(G, "POST /explain also takes a thread", r.status_code == 200 and r.json()["mode"] == "thread" and r.json()["explained"] is True)
    rs = [post("/explain", {"email": DAVID_GMAIL, "messages": [DAVID_GMAIL]}), post("/explain", {}), post("/explain", {"org_domain": "acme.com"})]
    c.add(G, "/explain needs exactly one of email or messages (both, neither and only a domain are 422)", [x.status_code for x in rs] == [422, 422, 422], [x.status_code for x in rs])
    # results
    r = call(client, "GET", "/results", key=False)
    index = r.json()
    present = [name for name in RESULT_FILES if (RESULTS_DIR / (name + ".csv")).is_file()]
    c.add(G, "GET /results needs no key and lists the allow-listed files that exist, with columns and row counts", r.status_code == 200 and [f["name"] for f in index["files"]] == present
          and all(f["columns"] and f["rows"] >= 0 for f in index["files"]) and set(index["missing"]) == set(RESULT_FILES) - set(present), "%d files" % len(index["files"]))
    ok_all, nan_free, detail = True, True, ""
    for entry in index["files"]:
        r = call(client, "GET", "/results", key=False, params={"name": entry["name"]})
        try:
            parsed = json.loads(r.text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
        except ValueError:
            nan_free, detail = False, entry["name"]
            continue
        with (RESULTS_DIR / (entry["name"] + ".csv")).open(newline="", encoding="utf-8") as handle:
            lines = list(csv.reader(handle))
        ok_all &= r.status_code == 200 and parsed["columns"] == entry["columns"] and len(parsed["rows"]) == min(len([l for l in lines[1:] if l]), results_module.MAX_ROWS) == entry["rows"]
        if not ok_all and not detail:
            detail = entry["name"]
    c.add(G, "every allow-listed table is served with the rows of its CSV file and contains no NaN or Infinity", ok_all and nan_free, detail)
    unlisted = [p.stem for p in RESULTS_DIR.glob("*.csv") if p.stem not in RESULT_FILES]
    served = [call(client, "GET", "/results", key=False, params={"name": name}).status_code for name in unlisted + ["../.env", "..%2f.env", "/etc/passwd", "score_budget.csv", "SCORE_BUDGET",
              "score_budget%00", "", CANARY, "a" * 64]]
    c.add(G, "a file in results/ that is not on the allow-list, a path, an extension, another case, a NUL byte, an empty or an unknown name all give 404 and nothing else", set(served) == {404},
          "unlisted files: %s; statuses %s" % (unlisted, sorted(set(served))))
    c.add(G, "a name longer than 64 characters is a 422 (validation of the query), also with no echo", call(client, "GET", "/results", key=False, params={"name": "a" * 65}).status_code == 422)
    cells = [v for row in call(client, "GET", "/results", key=False, params={"name": "score_budget"}).json()["rows"] for v in row.values()] if "score_budget" in present else []
    c.add(G, "numbers in a table are numbers and empty cells are null", not cells or (any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in cells) and any(isinstance(v, str) for v in cells)),
          "%d cells" % len(cells))
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        (folder / "tidy.csv").write_text("name,value,code,note\nmean,0.5,007,\nbad,nan,-3,<script>alert(1)</script>\ninf,inf,1e999,1_000\n", encoding="utf-8")
        (folder / "huge.csv").write_text("a,b\n" + "1,2\n" * 400_000, encoding="utf-8")
        (folder / "rows.csv").write_text("a\n" + "1\n" * 6000, encoding="utf-8")
        (folder / "empty.csv").write_text("", encoding="utf-8")
        (folder / "target.csv").write_text("a\n1\n", encoding="utf-8")
        (folder / "link.csv").symlink_to(folder / "target.csv")
        names = {n: "test" for n in ("tidy", "huge", "rows", "empty", "link", "absent")}
        crafted = ResultStore(folder, names)
        tidy = crafted.get("tidy")
        c.add(G, "the results reader: NaN, infinity and 1_000 stay text, '007' stays text, markup is made display-safe, empty is null, ints and floats are numbers",
              tidy is not None and tidy["rows"][0] == {"name": "mean", "value": 0.5, "code": "007", "note": None} and tidy["rows"][1]["value"] == "nan" and tidy["rows"][1]["code"] == -3
              and "<" not in json.dumps(tidy) and tidy["rows"][2] == {"name": "inf", "value": "inf", "code": "1e999", "note": "1_000"}, str(tidy and tidy["rows"][:3]))
        c.add(G, "the results reader skips a file over 1 MB, an empty file, a symlink and a missing file, and cuts a table at 5,000 rows",
              sorted(crafted.missing) == ["absent", "empty", "huge", "link"] and len(crafted.get("rows")["rows"]) == 5000, "missing %s" % crafted.missing)

    # ================================================================================================================== auth
    G = "auth"
    seen = stub.texts_seen
    wrong = [post("/analyze", {"email": NEWSLETTER}, key=False), post("/analyze", {"email": NEWSLETTER}, key="wrong-key"), post("/analyze", {"email": NEWSLETTER}, key=KEY[:-1]),
             post("/analyze", {"email": NEWSLETTER}, key=KEY + "x"), post("/analyze", {"email": NEWSLETTER}, key=""), post("/analyze", {"email": NEWSLETTER}, key=KEY.upper())]
    c.add(G, "no key, a wrong key, a key one character short or long, an empty key and an upper-cased key are all 401 with WWW-Authenticate and the same fixed body",
          all(x.status_code == 401 and "www-authenticate" in x.headers for x in wrong) and len({x.json()["detail"] for x in wrong}) == 1 and stub.texts_seen == seen, [x.status_code for x in wrong])
    r = client.post("/analyze", json={"email": NEWSLETTER}, headers=[("X-API-Key", KEY), ("X-API-Key", KEY)])
    r2 = client.post("/analyze", json={"email": NEWSLETTER}, headers=[("X-API-Key", "nope"), ("X-API-Key", KEY)])
    c.add(G, "a repeated X-API-Key header is refused, even when one of the values is right", r.status_code == 401 and r2.status_code == 401)
    r = client.post("/analyze?api_key=%s&x-api-key=%s" % (KEY, KEY), json={"email": NEWSLETTER})
    c.add(G, "a key in the URL is never read (URLs end up in logs)", r.status_code == 401)
    r = client.post("/analyze", json={"email": NEWSLETTER}, headers=[("X-API-Key", b"\xff\xfe\x00bad")])
    c.add(G, "a key made of bytes that are not text is a 401, not a crash", r.status_code == 401)
    r = client.post("/analyze", json={"email": NEWSLETTER}, headers={"x-api-key": KEY})
    c.add(G, "header names are case-insensitive: x-api-key works", r.status_code == 200)
    r = [call(client, "POST", p, key=False, json={"email": NEWSLETTER} if p != "/analyze/thread" else {"messages": [NEWSLETTER]}) for p in ("/analyze", "/analyze/thread", "/explain")]
    c.add(G, "all three POST routes need the key", [x.status_code for x in r] == [401, 401, 401])
    r1 = call(client, "POST", "/analyze", key=False, content=b"{not json at all", headers={"Content-Type": "application/json"})
    r2 = call(client, "POST", "/analyze", key="wrong", json={"email": "x" * 300_001})
    r3 = call(client, "POST", "/analyze", key=False, json={"nonsense": 1})
    c.add(G, "the key is checked before the body is read: no key plus a broken, an oversize or a wrong-shaped body is 401, not 422", [r1.status_code, r2.status_code, r3.status_code] == [401, 401, 401],
          [r1.status_code, r2.status_code, r3.status_code])
    c.add(G, "the key comparison hashes both sides and uses hmac.compare_digest (constant time); equal and different keys of equal and unequal length give the right answers",
          "compare_digest" in keys_match.__code__.co_names and keys_match(KEY, key_digest(KEY)) and not keys_match(KEY[:-1] + "!", key_digest(KEY)) and not keys_match("", key_digest(KEY))
          and not keys_match(KEY * 2, key_digest(KEY)))

    # ============================================================================================================ validation
    G = "validation"
    json_header = {"Content-Type": "application/json"}
    rs = [call(client, "POST", "/analyze", content=b'{"email": "hi"}', headers={"Content-Type": ct}) for ct in ("text/plain", "application/x-www-form-urlencoded", "application/jsonp", "text/json", "application/" + CANARY)]
    rs.append(call(client, "POST", "/analyze", content=b'{"email": "hi"}', headers={}))
    c.add(G, "a body that is not application/json (text/plain, a form, jsonp, text/json, no type at all) is 415", {x.status_code for x in rs} == {415}, [x.status_code for x in rs])
    rs = [call(client, "POST", "/analyze", content=b'{"email": "hi"}', headers={"Content-Type": ct}) for ct in ("application/json; charset=utf-8", "Application/JSON", "application/json;charset=UTF-8")]
    c.add(G, "application/json with parameters or in other letter case is accepted", [x.status_code for x in rs] == [200, 200, 200], [x.status_code for x in rs])
    bad_bodies = {"broken JSON": b'{"email": "hi"', "empty body": b"", "BOM and UTF-16": '{"email": "hi"}'.encode("utf-16"), "invalid UTF-8": b'{"email": "\xff\xfe"}', "a list": b"[1, 2]", "null": b"null",
                  "a number": b"5", "NaN": b'{"email": NaN}', "deep nesting": b"[" * 100_000, "a lone surrogate": b'{"email": "\\ud800"}'}
    rs = {name: call(client, "POST", "/analyze", content=body, headers=json_header) for name, body in bad_bodies.items()}
    c.add(G, "bad JSON in ten forms (broken, empty, UTF-16, invalid UTF-8, a list, null, a number, NaN, 100,000-deep nesting, a lone surrogate) is 422 each, never 500",
          all(x.status_code == 422 for x in rs.values()), {k: x.status_code for k, x in rs.items() if x.status_code != 422})
    wrong_types = [{"email": 123}, {"email": ["a"]}, {"email": None}, {"email": {"a": 1}}, {"email": True}, {"email": "ok", "org_domain": 5}, {"email": ""}, {}]
    rs = [post("/analyze", payload) for payload in wrong_types]
    c.add(G, "wrong types (number, list, null, object, boolean), an empty email and an empty object are 422 and name only the field and the kind of error",
          all(x.status_code == 422 and all(set(e) == {"loc", "type"} for e in x.json()["errors"]) for x in rs), [x.status_code for x in rs])
    r = post("/analyze", {"email": "hi", "<script>%s</script>" % CANARY: 1, "org_domain": None})
    c.add(G, "an unknown field is 422 and its (attacker-chosen) name is not echoed", r.status_code == 422 and CANARY not in r.text and r.json()["errors"][0]["loc"] == ["?"], r.text[:200])
    rs = [post("/analyze/thread", {"messages": []}), post("/analyze/thread", {"messages": "abc"}), post("/analyze/thread", {"messages": [1, 2]}), post("/analyze/thread", {"messages": ["a"] * 51}),
          post("/analyze/thread", {"messages": ["a", ""]})]
    c.add(G, "a thread must be 1 to 50 non-empty text messages: empty list, a string, numbers, 51 messages and an empty message are 422", all(x.status_code == 422 for x in rs), [x.status_code for x in rs])
    rs = [post("/analyze", {"email": "a" * 300_001}), post("/analyze", {"email": "€" * 100_001})]
    exact = post("/analyze", {"email": ("Please see the quarterly report. " * 20000)[:300_000]})
    c.add(G, "an email over 300,000 bytes is 422, in characters and in UTF-8 bytes (100,001 euro signs), and exactly 300,000 bytes is analysed", [x.status_code for x in rs] == [422, 422]
          and exact.status_code == 200 and exact.json()["verdict"] == "Low risk", "%s %s" % ([x.status_code for x in rs], exact.status_code))
    message = "x" * 299_000
    rs = [post("/analyze/thread", {"messages": [message] * 6}), post("/explain", {"messages": [message] * 6})]
    full = post("/analyze/thread", {"messages": [eml(i, JOHN if i % 2 == 0 else MARY, "Invoice", PARAGRAPHS[i % 5]) for i in range(MAX_THREAD_MESSAGES)]})
    c.add(G, "a thread over 1.5 MB in total is 422 (6 x 299,000 bytes), and a thread of exactly 50 messages is analysed", [x.status_code for x in rs] == [422, 422] and full.status_code == 200
          and full.json()["thread"]["messages"] == 50, "%s %s" % ([x.status_code for x in rs], full.status_code))
    bad_domains = ["a b.com", "<script>x</script>.com", "acme..com", "-acme.com", "acme-.com", "a" * 64 + ".com", "ünicode.com", ".com", "acme.com/path", "acme.com:8080", "a" * 400, "ac me\n.com"]
    rs = [post("/analyze", {"email": "hi", "org_domain": d}) for d in bad_domains]
    good = [post("/analyze", {"email": "hi", "org_domain": d}) for d in ("AcmeCorp.com", "acme.co.uk.", "localhost", "", None)]
    c.add(G, "org_domain: spaces, markup, empty labels, hyphens at the edges, labels over 63, non-ASCII, paths, ports, 400 characters and a newline are 422; ordinary shapes are accepted",
          all(x.status_code == 422 for x in rs) and all(x.status_code == 200 for x in good), [(d[:12], x.status_code) for d, x in zip(bad_domains, rs) if x.status_code != 422] + [x.status_code for x in good])
    started = time.perf_counter()
    junk = call(client, "POST", "/analyze", content=('{"email": "a",' + ",".join('"k%d":1' % i for i in range(300_000)) + "}").encode(), headers=json_header)
    seconds = time.perf_counter() - started
    c.add(G, "3.5 MB of made-up field names is refused by the field count alone, in well under a second (describing 300,000 errors cost Pydantic 2.3 s)",
          junk.status_code == 422 and js(junk).get("errors", [{}])[0].get("type") == "too_many_fields" and seconds < 1.5, "%.2f s" % seconds)
    r = post("/analyze", {"email": "Pay me \u0000 now, \u0000 please."})
    c.add(G, "a NUL character inside the email text is analysed normally", r.status_code == 200 and check_report(r.json(), analyzer.config) == [])

    # ================================================================================================================== size
    G = "size"
    ok_headers = [("content-type", "application/json"), ("x-api-key", KEY), ("host", "localhost")]
    calls_before = stub.texts_seen
    status, headers, body = asgi_request(app, "POST", "/analyze", ok_headers, [b" " * 1_000_000] * 5)
    c.add(G, "5 MB sent in chunks with no Content-Length: 413 as soon as the count passes 4 MB, the route never ran", status == 413 and json.loads(body)["code"] == "too_large" and stub.texts_seen == calls_before, status)
    status, headers, body = asgi_request(app, "POST", "/analyze", ok_headers + [("content-length", "10")], [b" " * 1_000_000] * 5)
    c.add(G, "Content-Length: 10 with 5 MB actually sent (a lie): the bytes that arrive are counted, 413", status == 413 and stub.texts_seen == calls_before, status)
    status, headers, body = asgi_request(app, "POST", "/analyze", ok_headers + [("content-length", str(MAX_BODY_BYTES + 1))], [b"{}"])
    c.add(G, "a declared Content-Length over 4,000,000 is 413 before a byte is read, and the answer closes the connection", status == 413 and headers.get("connection") == "close"
          and headers.get("x-request-id") == json.loads(body)["request_id"] and headers.get("cache-control") == "no-store", str(headers))
    statuses = {}
    for value in ("abc", "-5", "1e3", "\u00b2", "10, 10", "", "99999999999999"):
        statuses[value] = asgi_request(app, "POST", "/analyze", ok_headers + [("content-length", value)], [b"{}"])[0]
    status, _, _ = asgi_request(app, "POST", "/analyze", ok_headers + [("content-length", "5"), ("content-length", "5")], [b"{}"])
    c.add(G, "a Content-Length that is not one plain number (letters, a sign, an exponent, a superscript digit, a list, empty, 14 digits, repeated) is 400 or 413, never accepted",
          all(s in (400, 413) for s in statuses.values()) and status == 400, "%s %s" % (statuses, status))
    status, headers, body = asgi_request(app, "POST", "/analyze", ok_headers[:1] + ok_headers[2:], [b" " * 1_000_000] * 5)
    status_declared = asgi_request(app, "POST", "/analyze", ok_headers[:1] + ok_headers[2:] + [("content-length", "9999999")], [b"{}"])[0]
    c.add(G, "an oversize body with no key: 413 when the size is declared, and when it is streamed the key check answers 401 without reading the body; nothing was analysed",
          status == 401 and status_declared == 413 and stub.texts_seen == calls_before, "%s %s" % (status, status_declared))
    exact_json = b'{"email": "hi"}' + b" " * (MAX_BODY_BYTES - 15)
    status, _, body = asgi_request(app, "POST", "/analyze", ok_headers, [exact_json[i:i + 100_000] for i in range(0, len(exact_json), 100_000)])
    c.add(G, "a chunked body of exactly 4,000,000 bytes is let through (valid JSON with trailing spaces: analysed)", status == 200, status)

    # ================================================================================================================= limits
    G = "limits"
    app_l, cl = build(rate_analyze="3/minute")
    codes = [call(cl, "POST", "/analyze", json={"email": NEWSLETTER}).status_code for _ in range(4)]
    seen = stub.texts_seen
    last = call(cl, "POST", "/analyze", json={"email": NEWSLETTER})
    c.add(G, "with 3 analyses a minute the fourth is 429 with Retry-After (an integer of seconds), a fixed message and a request id, and a refused request runs no analysis",
          codes == [200, 200, 200, 429] and last.status_code == 429 and last.headers["retry-after"].isdigit() and 0 < int(last.headers["retry-after"]) <= 60 and "request_id" in last.json()
          and last.json()["code"] == "rate_limited" and stub.texts_seen == seen, codes)
    app_l, cl = build(rate_analyze="3/minute")
    codes = [call(cl, "POST", "/analyze", key="guess-%d" % i, json={"email": NEWSLETTER}).status_code for i in range(3)] + [call(cl, "POST", "/analyze", json={"email": NEWSLETTER}).status_code]
    c.add(G, "requests with a wrong key use up the strict allowance (3 wrong keys, then the right key is 429): guessing keys is limited", codes == [401, 401, 401, 429], codes)
    app_l, cl = build(rate_analyze="3/minute")
    codes = [call(cl, "POST", "/analyze", json={"email": NEWSLETTER}).status_code, call(cl, "POST", "/analyze/thread", json={"messages": [NEWSLETTER]}).status_code,
             call(cl, "POST", "/analyze", json={"email": NEWSLETTER}).status_code, call(cl, "POST", "/analyze/thread", json={"messages": [NEWSLETTER]}).status_code]
    c.add(G, "/analyze and /analyze/thread share one allowance", codes == [200, 200, 200, 429], codes)
    app_l, cl = build(rate_explain="2/minute")
    codes = [call(cl, "POST", "/explain", json={"email": DAVID_GMAIL}).status_code for _ in range(3)]
    other = call(cl, "POST", "/analyze", json={"email": NEWSLETTER}).status_code
    c.add(G, "/explain has its own, stricter allowance: the third is 429 while /analyze still works", codes == [200, 200, 429] and other == 200, "%s %s" % (codes, other))
    app_l, cl = build(rate_global="4/minute")
    codes = [call(cl, "GET", "/health", key=False).status_code, call(cl, "GET", "/results", key=False).status_code, call(cl, "POST", "/analyze", key=False, json={"email": "x"}).status_code,
             call(cl, "GET", "/health", key=False).status_code, call(cl, "GET", "/health", key=False).status_code]
    c.add(G, "the global limit counts every route together, and counts a request with no key (4 allowed, the fifth is 429)", codes == [200, 200, 401, 200, 429], codes)
    app_l, cl = build(rate_analyze="2/minute")
    codes = [call(cl, "POST", "/analyze", json={"email": NEWSLETTER}, headers={"X-Forwarded-For": "198.51.100.%d" % i, "X-Real-IP": "198.51.100.%d" % i, "Forwarded": "for=198.51.100.%d" % i}).status_code
             for i in range(3)]
    c.add(G, "a forged X-Forwarded-For, X-Real-IP or Forwarded header does not give a fresh allowance (the client is the socket's peer)", codes == [200, 200, 429], codes)
    saved = os.environ.get("RATELIMIT_ENABLED")
    os.environ["RATELIMIT_ENABLED"] = "False"
    try:
        app_l, cl = build(rate_analyze="2/minute")
        codes = [call(cl, "POST", "/analyze", json={"email": NEWSLETTER}).status_code for _ in range(3)]
        c.add(G, "a stray RATELIMIT_ENABLED=False in the environment does not switch the limits off", codes == [200, 200, 429] and app_l.state.limiter.enabled is True, codes)
    finally:
        if saved is None:
            os.environ.pop("RATELIMIT_ENABLED", None)
        else:
            os.environ["RATELIMIT_ENABLED"] = saved

    # ============================================================================================================ concurrency
    G = "concurrency"
    app_c, cc = build(wait_seconds=0.5)
    app_c.state.lock.acquire()
    started = time.perf_counter()
    r = call(cc, "POST", "/analyze", json={"email": NEWSLETTER})
    waited = time.perf_counter() - started
    started = time.perf_counter()
    r2 = call(cc, "POST", "/explain", json={"email": DAVID_GMAIL})
    quick = time.perf_counter() - started
    app_c.state.lock.release()
    c.add(G, "while the classifier is busy /analyze waits its 0.5 s and answers 503 busy with Retry-After, and /explain answers 503 at once", r.status_code == 503 and r.json()["code"] == "busy"
          and "retry-after" in r.headers and 0.4 <= waited < 3.0 and r2.status_code == 503 and "retry-after" in r2.headers and quick < 0.4, "%.2f s, %.2f s" % (waited, quick))
    c.add(G, "when the classifier is free again the next request works (nothing was left locked)", call(cc, "POST", "/analyze", json={"email": NEWSLETTER}).status_code == 200 and not app_c.state.lock.locked())
    app_p, cp = build(wait_seconds=30)
    call(cp, "POST", "/analyze", json={"email": NEWSLETTER})
    with ThreadPoolExecutor(8) as pool:
        rs = list(pool.map(lambda i: call(cp, "POST", "/analyze", json={"email": DAVID_GMAIL if i % 2 else HONEST}), range(8)))
    verdicts = {(i % 2): r.json()["verdict"] for i, r in enumerate(rs) if r.status_code == 200}
    c.add(G, "8 requests at once are all answered 200 one after the other, each with its own report (no mixing of results between requests)", all(r.status_code == 200 for r in rs)
          and len({r.json()["request_id"] for r in rs}) == 8 and verdicts == {1: "High risk", 0: "Low risk"} and not app_p.state.lock.locked(), [r.status_code for r in rs])

    # ================================================================================================================== errors
    G = "errors"

    class Failing:
        """An analyzer that fails in a chosen way, with the canary in the exception message."""
        explain_samples = 150

        def __init__(self, error):
            self.error = error

        def analyze(self, *args, **kwargs):
            raise self.error

    audit_lines.lines.clear()
    for name, error, status, code in (("ReportError", ReportError("report broke: %s" % CANARY), 500, "internal_error"), ("an unexpected RuntimeError", RuntimeError("boom %s" % CANARY), 500, "internal_error"),
                                      ("a ValueError", ValueError("bad %s" % CANARY), 400, "analysis_rejected"), ("a TypeError", TypeError("bad %s" % CANARY), 400, "analysis_rejected")):
        app_e, ce = build(analyzer=Failing(error))
        r = call(ce, "POST", "/analyze", json={"email": NEWSLETTER})
        body = js(r)
        c.add(G, "%s inside the analysis: %d %s with a fixed message and the request id, the exception's message (with the canary) is nowhere in the answer, and the lock is free"
              % (name, status, code), r.status_code == status and body.get("code") == code and body.get("detail") == ERRORS[code][1] and CANARY not in r.text and body.get("request_id") == r.headers.get("x-request-id")
              and not app_e.state.lock.locked() and "cache-control" in r.headers and "content-security-policy" in r.headers, "%s %s" % (r.status_code, r.text[:120]))
    errors_logged = [json.loads(line) for line in audit_lines.lines if '"event":"error"' in line]
    c.add(G, "the audit log names the class of each error and where it was raised, never its message (a ValueError or TypeError from the pipeline is a bug and is logged too)",
          len(errors_logged) == 4 and {e["error_class"] for e in errors_logged} == {"ReportError", "RuntimeError", "ValueError", "TypeError"}
          and all(".py:" in e["where"] for e in errors_logged) and CANARY not in "".join(audit_lines.lines), str(errors_logged[:1]))

    def broken_loader():
        raise OSError("tactic_model folder not found")

    app_m, cm = build(analyzer=None, loader=broken_loader)
    with cm:
        health_r = call(cm, "GET", "/health", key=False)
        analysis_r = call(cm, "POST", "/analyze", json={"email": NEWSLETTER})
    c.add(G, "if the model cannot be loaded the server still starts: /health is 503 'unavailable' and the analysis routes are 503 model_unavailable, and the audit log says why",
          health_r.status_code == 503 and health_r.json()["model_loaded"] is False and analysis_r.status_code == 503 and analysis_r.json()["code"] == "model_unavailable"
          and any('"event":"startup_failed"' in line and "OSError" in line for line in audit_lines.lines))
    app_m, cm = build(analyzer=None, loader=lambda: analyzer)
    with cm:
        loaded_ok = call(cm, "GET", "/health", key=False).status_code == 200 and call(cm, "POST", "/analyze", json={"email": NEWSLETTER}).status_code == 200
    c.add(G, "the loader runs at start-up (the lifespan) and the model is dropped at shutdown", loaded_ok and app_m.state.analyzer is None)

    # ================================================================================================================ headers
    G = "headers"
    app_h, ch = build(rate_analyze="1/minute")
    samples = {"200": call(ch, "GET", "/health", key=False), "401": call(ch, "POST", "/analyze", key=False, json={}), "404": call(ch, "GET", "/nothing", key=False),
               "405": call(ch, "GET", "/analyze", key=False), "415": call(ch, "POST", "/analyze", key=False, content=b"x", headers={"Content-Type": "text/plain"}),
               "422": call(ch, "POST", "/explain", json={}), "429": None, "400 host": call(ch, "GET", "/health", key=False, headers={"Host": "evil.example"})}
    call(ch, "POST", "/analyze", json={"email": NEWSLETTER})
    samples["429"] = call(ch, "POST", "/analyze", json={"email": NEWSLETTER})
    samples["413"] = type("R", (), {"headers": asgi_request(app_h, "POST", "/analyze", ok_headers + [("content-length", "9999999")], [b"{}"])[1], "status_code": 413})()
    app_503, c503 = build(analyzer=None)
    samples["503"] = call(c503, "POST", "/analyze", json={"email": "x"})
    app_500, c500 = build(analyzer=Failing(RuntimeError("x")))
    samples["500"] = call(c500, "POST", "/analyze", json={"email": "x"})
    wanted = {"cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "x-frame-options": "DENY", "cross-origin-resource-policy": "same-origin",
              "content-security-policy": "default-src 'none'; frame-ancestors 'none'"}
    missing = [(name, h) for name, resp in samples.items() for h, v in wanted.items() if resp.headers.get(h) != v or not resp.headers.get("x-request-id")]
    c.add(G, "the security headers and a request id are on every kind of answer: 200, 400 (bad host), 401, 404, 405, 413, 415, 422, 429, 500 and 503", not missing,
          "%s statuses %s" % (missing[:4], {k: v.status_code for k, v in samples.items()}))
    app_d, cd = build(enable_docs=True)
    docs_off = [call(client, "GET", p, key=False).status_code for p in ("/docs", "/redoc", "/openapi.json")]
    docs_on = [call(cd, "GET", p, key=False) for p in ("/docs", "/openapi.json")]
    c.add(G, "/docs, /redoc and /openapi.json are 404 by default; when switched on for development the docs page loads without the CSP and the API pages keep it",
          docs_off == [404, 404, 404] and [x.status_code for x in docs_on] == [200, 200] and "content-security-policy" not in docs_on[0].headers
          and "content-security-policy" in call(cd, "GET", "/health", key=False).headers, "%s %s" % (docs_off, [x.status_code for x in docs_on]))
    cors_headers = {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-api-key,content-type"}
    r1 = call(client, "OPTIONS", "/analyze", key=False, headers=cors_headers)
    r2 = call(client, "GET", "/health", key=False, headers={"Origin": "https://evil.example"})
    c.add(G, "with the CORS switch off (the secure design) a preflight is 405 and no answer carries an Access-Control header", r1.status_code == 405 and not any(h.startswith("access-control") for h in list(r1.headers) + list(r2.headers)))
    app_o, co = build(cors=True)
    p1 = call(co, "OPTIONS", "/analyze", key=False, headers=cors_headers)
    p2 = call(co, "POST", "/analyze", key=False, json={"email": "x"}, headers={"Origin": "https://evil.example"})
    p3 = call(co, "POST", "/analyze", json={"email": NEWSLETTER}, headers={"Origin": "https://evil.example"})
    c.add(G, "with the CORS switch on (testing only) a preflight from any origin is allowed with the key header, answers carry Access-Control-Allow-Origin: *, errors too, and the security headers are still there",
          p1.status_code == 200 and p1.headers.get("access-control-allow-origin") == "*" and "x-api-key" in p1.headers.get("access-control-allow-headers", "").lower()
          and p2.status_code == 401 and p2.headers.get("access-control-allow-origin") == "*" and p3.status_code == 200 and p3.headers.get("access-control-allow-origin") == "*"
          and "x-request-id" in p3.headers.get("access-control-expose-headers", "").lower() and p1.headers.get("cache-control") == "no-store" and p1.headers.get("access-control-allow-credentials") is None,
          "%s %s %s" % (p1.status_code, p2.status_code, p3.status_code))
    c.add(G, "the Host check still applies with CORS open (a rebinding host is 400)", call(co, "GET", "/health", key=False, headers={"Host": "evil.example", "Origin": "https://evil.example"}).status_code == 400)
    ok_host = call(client, "GET", "/health", key=False, headers={"Host": "localhost:8000"})
    bad_hosts = [call(client, "GET", "/health", key=False, headers={"Host": h}).status_code for h in ("evil.example", "localhost.evil.example", "127.0.0.1.evil.example", "", CANARY + ".example")]
    c.add(G, "the Host header must be one of the allowed names (a defence against DNS rebinding): localhost:8000 is fine, others are 400", ok_host.status_code == 200 and set(bad_hosts) == {400}, bad_hosts)
    rids = []
    for i in range(20):
        r = call(client, "GET", "/health", key=False, headers={"X-Request-ID": "attacker-chosen-%d" % i})
        rids.append(r.headers["x-request-id"])
    c.add(G, "every request gets its own random 32-hex request id; a request id sent by the client is ignored", len(set(rids)) == 20 and all(len(x) == 32 and set(x) <= set("0123456789abcdef") for x in rids)
          and not any("attacker" in x for x in rids))

    # =================================================================================================================== xss
    G = "xss"
    bad_chars = lambda text: any(ch in text for ch in "<>`")
    leaked, statuses = [], []
    for payload in XSS_PAYLOADS:
        mail = DAVID_GMAIL.replace("Hi Maria,", "Hi %s," % payload).replace("Subject: Urgent wire", "Subject: %s" % payload).replace("David Chen <david", "%s <david" % payload.replace("\n", " "))
        thread = takeover[:-1] + [takeover[-1].replace("Quick change", payload + " Quick change")]
        for path, body in (("/analyze", {"email": mail}), ("/analyze/thread", {"messages": thread}), ("/explain", {"email": mail})):
            r = post(path, body)
            statuses.append(r.status_code)
            if r.status_code == 200 and (bad_chars(r.text) or r.headers["content-type"].split(";")[0] != "application/json" or r.headers.get("x-content-type-options") != "nosniff"):
                leaked.append((path, payload[:20]))
    c.add(G, "%d markup, script and template payloads in the body, the From name, the Subject and a thread message never reach a response as '<', '>' or a backtick, on all three analysis routes" % len(XSS_PAYLOADS),
          not leaked and statuses.count(200) >= len(statuses) - 2, "%s statuses %s" % (leaked[:3], sorted(set(statuses))))
    leaked = [(s, t[:60]) for s, b, t in recorded if bad_chars(t)]
    c.add(G, "no error response in this whole run contains '<', '>' or a backtick, whatever the request held", not leaked, str(leaked[:3]))

    # ================================================================================================================== audit
    G = "audit"
    audit_lines.lines.clear()
    r = post("/explain", {"email": DAVID_GMAIL})
    lines = [json.loads(line) for line in audit_lines.lines]
    entry = lines[0] if lines else {}
    c.add(G, "one analysis writes exactly one JSON line with the request id, mode, score, verdict, tactics that fired, contradictions, duration and sizes",
          len(lines) == 1 and entry.get("event") == "analysis" and entry["request_id"] == r.json()["request_id"] and entry["mode"] == "email" and entry["score"] == r.json()["score"]
          and entry["verdict"] == "High risk" and entry["tactics"] == ["urgency", "secrecy"] and entry["contradictions"] == 3 and isinstance(entry["duration_ms"], int)
          and entry["bytes"] == len(DAVID_GMAIL.encode()) and entry["explain"] is True and entry["explained"] is True and "time" in entry, str(entry))
    c.add(G, "every field of every audit line of the run is on the fixed list", all(set(json.loads(line)) <= AUDIT_FIELDS | {"time"} for line in audit_lines.lines))
    try:
        audit.write("test", email="a@b.com")
        refused_field = False
    except KeyError:
        refused_field = True
    nasty = "line1\nline2 \"quoted\" <script>alert(1)</script> a@b.com `x` " + "z" * 500
    cleaned = clean_value(nasty)
    c.add(G, "AuditLog refuses a field that is not on the list; clean_value removes newlines, quotes, markup and '@' and cuts at 80 characters; objects become '?', NaN becomes null",
          refused_field and len(cleaned) == 80 and not set(cleaned) & set('\n"<>`@') and clean_value({"a": 1}) == "?" and clean_value(float("nan")) is None and clean_value([1, "a\nb"]) == [1, "a_b"], cleaned)
    # the canary: hostile values everywhere, then look at every log line
    audit_lines.lines.clear()
    other_lines.lines.clear()
    hostile = [("POST", "/analyze", dict(json={"email": DAVID_GMAIL.replace("Hi Maria,", "Hi %s," % CANARY).replace("Urgent wire", CANARY)}), True),
               ("POST", "/analyze", dict(json={"email": "hi", "org_domain": CANARY + " <b>"}), True), ("POST", "/analyze", dict(json={"email": "hi", CANARY: 1}), True),
               ("POST", "/analyze", dict(content=('{"email": "%s"' % CANARY).encode(), headers=json_header), True), ("POST", "/analyze", dict(json={"email": CANARY}), CANARY),
               ("POST", "/analyze", dict(json={"email": CANARY}), KEY[:-1] + "!"), ("GET", "/results", dict(params={"name": CANARY}), False), ("GET", "/" + CANARY, {}, False),
               ("GET", "/health?x=" + CANARY, dict(headers={"X-Request-ID": CANARY, "User-Agent": CANARY, "Cookie": "s=" + CANARY}), False),
               ("POST", "/analyze", dict(content=b"{}", headers={"Content-Type": "application/" + CANARY}), True), ("GET", "/health", dict(headers={"Host": CANARY + ".example"}), False),
               ("POST", "/analyze/thread", dict(json={"messages": [CANARY] * 3}), True), ("POST", "/explain", dict(json={"email": DAVID_GMAIL.replace("Hi Maria,", CANARY + ",")}), True)]
    reached, echoed = False, []
    for method, path, kwargs, key in hostile:
        r = call(client, method, path, key=key, **kwargs)
        if r.status_code == 200 and CANARY in r.text:
            reached = True
        if r.status_code >= 400 and CANARY in r.text:
            echoed.append((method, path[:20], r.status_code))
    alltext = "\n".join(audit_lines.lines + other_lines.lines)
    c.add(G, "the canary string, sent in the email text, a header name and value, the Host, the URL path and query, the content type, a field name, a domain and as a wrong key, appears in no audit line, "
          "no other log record and no error response (it did reach the pipeline: it is in the successful reports)", reached and not echoed and CANARY not in alltext,
          "reached the pipeline: %s; echoed in %s; in the logs: %s" % (reached, echoed, CANARY in alltext))
    c.add(G, "the real key and the wrong key tried appear in no log line", KEY not in alltext and (KEY[:-1] + "!") not in alltext)
    c.add(G, "no log line holds an '@' (no address of a sender, recipient or client)", "@" not in alltext)
    kinds = {json.loads(line)["event"] for line in audit_lines.lines}
    c.add(G, "refusals are logged as denied (401, 413, 415, 429) or refused (400, 422, 503), with the status, the reason and the client address but no content",
          {"denied", "refused", "analysis"} <= kinds and all(set(json.loads(l)) <= AUDIT_FIELDS | {"time"} for l in audit_lines.lines), str(kinds))

    # ================================================================================================================ the error bodies of the whole run
    G = "errors"
    shape_ok, bad_shape = True, []
    for status, body, text in recorded:
        if body is None or "code" not in body:
            continue                                      # the plain-text 400 of the Host check; the 503 body of /health when the model is not loaded
        try:
            parsed = ErrorResponse.model_validate(body)
            fixed = parsed.detail in {d for _, d in ERRORS.values()}
            if not (fixed and parsed.code in ERRORS and ERRORS[parsed.code][0] == status and len(parsed.request_id or "") == 32):
                shape_ok = False
                bad_shape.append((status, parsed.code))
        except Exception:
            shape_ok = False
            bad_shape.append((status, "invalid"))
    c.add(G, "all %d error responses of this run have the ErrorResponse shape: a fixed sentence, a known code that fits the status, a 32-hex request id" % len(recorded), shape_ok and len(recorded) > 40, "%d responses, bad: %s" % (len(recorded), bad_shape[:3]))

    # ================================================================================================================ wrap up
    versions = {}
    for name in ("fastapi", "starlette", "pydantic", "slowapi", "uvicorn", "httpx", "limits"):
        try:
            from importlib.metadata import version
            versions[name] = version(name)
        except Exception:
            versions[name] = "?"
    c.add("run", "library versions", True, ", ".join("%s %s" % kv for kv in versions.items()), info=True)
    c.add("run", "python", True, sys.version.split()[0], info=True)
    c.add("run", "CORS_ALLOW_ANY_ORIGIN in src/api/main.py", True, ("TRUE: CORS IS WIDE OPEN, TESTING ONLY. Set it to False before any deployment." if CORS_ALLOW_ANY_ORIGIN else "False: no CORS headers (the secure design)"), info=True)
    c.add("run", "classifier", True, "stand-in (src/router/selftest.py StubClassifier); the real model is src/api/smoke.py", info=True)
    c.add("run", "limits tested with", True, "analysis 3/minute, explain 2/minute, global 4/minute (the shipped defaults are 30, 6 and 120)", info=True)
    c.add("run", "run at", True, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), info=True)

    root.removeHandler(other_lines)
    root.setLevel(old_level)
    passed = sum(1 for r in c.rows if r[4] == "PASS")
    print("\n%d checks: %d PASS, %d FAIL, %d info" % (passed + len(c.failed), passed, len(c.failed), sum(1 for r in c.rows if r[4] == "info")))
    if write:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["check", "item", "value", "expected", "status"])
            writer.writerows(c.rows)
        print("wrote %s" % out)
    return not c.failed, c



def main(argv):
    parser = argparse.ArgumentParser(description="Self-test of the API's security controls (stand-in classifier, in-process).")
    parser.add_argument("--no-write", action="store_true", help="print only, do not write results/api_checks.csv")
    parser.add_argument("--out", type=Path, default=OUT, help="where to write the CSV")
    args = parser.parse_args(argv)
    ok, _ = self_test(write=not args.no_write, out=args.out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
