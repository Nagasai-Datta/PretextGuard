# src/api/

Phase 11: the **FastAPI backend with all its security controls**. It puts `analyze()` (Phase 10) behind HTTP and serves the evaluation numbers; it exposes nothing else. Phase 12 (the React interface) talks only to this API.

## Run it

Make a key once and put it in `.env`:

```bash
python -m src.api.settings --new-key
```

Copy the printed text into `.env` as `PRETEXTGUARD_API_KEY=...`. Then:

| Command | What it does |
|---|---|
| `python -m src.api.settings` | Shows the settings that would be used (the key is masked); stops with a message if the key is missing, the placeholder or under 24 characters |
| `python -m src.api.selftest` | The security controls with crafted requests and a stand-in classifier, in-process, about 30 seconds. Writes `results/api_checks.csv` (88 checks) |
| `python -m src.api.mutation_check` | Breaks 37 controls one at a time in a scratch copy and confirms that a self-test check fails each time, about 2 minutes. Writes `results/api_mutations.csv` |
| `python -m src.api.main 2>&1 \| tee /tmp/pg_server.log` | Starts the server on `http://127.0.0.1:8000` with the trained model. The port opens when the model is loaded (a few seconds). The log file is outside the repository on purpose; it holds metadata only |
| `python -m src.api.smoke --server-log /tmp/pg_server.log` | In a second terminal: a real session with the running server and the real model; writes `results/api_smoke.csv`. Wait a minute before running it again (it uses up the `/explain` allowance on purpose) |

The weights (`artifacts/tactic_model/`) and `src/router/reliability.json` must be on the machine that runs the server.

> **TEMPORARY: CORS is wide open for testing.** `CORS_ALLOW_ANY_ORIGIN = True` at the top of `main.py` (marked in capitals) lets a web page from any origin call the API from a browser, and `python -m src.api.main` prints a warning while it is on. **Set it to `False` before the API is ever deployed or reachable from another machine.** The key is still required on the three POST routes and the Host header check still applies; `/health` and `/results` are public data anyway. The self-test checks both settings and records the shipped one as an `info` row in `results/api_checks.csv`.

## The routes

| Route | Key | Body | Answer |
|---|---|---|---|
| `POST /analyze` | yes | `{"email": "...", "org_domain": "acmecorp.com"}` (`org_domain` optional) | The report of master document Section 6.3, without LIME highlights (about 0.05 s) |
| `POST /analyze/thread` | yes | `{"messages": ["...", "..."], "org_domain": ...}` (1 to 50 messages, any order) | The same report for a thread: the newest message by `Date` is judged against the earlier ones |
| `POST /explain` | yes | Exactly one of `email` or `messages`, plus the optional `org_domain` | The same report with LIME highlights (150 copies, about 5 s). The score is the same as without LIME |
| `GET /results` | no | none; `?name=score_budget` for one table | The list of evaluation tables the dashboard may read, or one table as `{name, description, columns, rows}` |
| `GET /health` | no | none | `{"status": "ok", "model_loaded": true, ...}`, or 503 if the model failed to load |

The key goes in the `X-API-Key` header, never in the URL. The interface shows the score from `/analyze` first and asks `/explain` for the highlights afterwards.

An example with `curl` (the Mac, from the project root, server running):

```bash
export KEY=$(grep '^PRETEXTGUARD_API_KEY=' .env | cut -d= -f2-)
python -c "import json, sys; print(json.dumps({'email': open(sys.argv[1], encoding='utf-8', errors='replace').read()}))" email.eml > request.json
curl -s -X POST http://127.0.0.1:8000/analyze -H "X-API-Key: $KEY" -H "Content-Type: application/json" --data @request.json
```

`email.eml` is a raw email with or without headers. A body pasted without headers is analysed as a body: the coverage block of the report says which checks could not run.

## Errors

Every error is JSON `{"detail": "<fixed sentence>", "code": "<code>", "request_id": "<32 hex>"}` (422 adds `"errors": [{"loc": [...], "type": "..."}]`). The sentences are fixed: nothing the client sent is ever repeated in an error or a log line, and nothing from an exception message.

| Code | Status | When |
|---|---|---|
| `unauthorized` | 401 | No `X-API-Key`, a wrong one, or the header twice |
| `bad_length` | 400 | `Content-Length` is not one plain number |
| `analysis_rejected` | 400 | The pipeline refused the input (it cannot happen after validation; it is a safety net) |
| `not_found`, `method_not_allowed` | 404, 405 | Unknown route or table name; wrong method |
| `too_large` | 413 | Over 4,000,000 bytes, declared or counted while streaming in |
| `unsupported_media_type` | 415 | A POST that is not `application/json` |
| `invalid_request` | 422 | The body does not fit the schema: where (`loc`) and what kind (`type`) only |
| `rate_limited` | 429 | Over a limit; `Retry-After` says how many seconds |
| `internal_error` | 500 | A bug (the report failed its own checks, or something unexpected). Quote the request id |
| `model_unavailable`, `busy` | 503 | The model is not loaded; the classifier is busy (`Retry-After`) |

## The controls (OWASP mapping in master document Section 10)

| Control | How | Checked by |
|---|---|---|
| Authentication | `X-API-Key`, compared as SHA-256 digests with `hmac.compare_digest` (constant time); exactly one header; the key is never read from the URL; the server refuses to start with the placeholder, a missing key or one under 24 characters or with fewer than 8 different characters | `selftest` groups settings and auth |
| Authentication before parsing | The key is checked before the body is read or parsed, so an unauthenticated client costs the server almost nothing | `selftest` auth |
| Rate limiting | slowapi, per client address (the socket peer; `X-Forwarded-For` is never trusted): one limit for all routes together (120 a minute, counted before anything is read), a stricter one per route (30 a minute for analysis, 6 for `/explain`), moving window. The strict limits are counted before the key check, so wrong keys use up the allowance | `selftest` limits |
| Size limits | 4,000,000 bytes per request, counted as the bytes arrive (Content-Length can lie or be missing); 300,000 bytes per email; 50 messages and 1,500,000 bytes per thread; at most 10 top-level fields; a nesting depth the JSON parser refuses; MIME nested over 20 levels is read as plain text with a coverage note | `selftest` validation and size |
| Schemas | Pydantic, no unknown fields, no type conversion, a domain-shape check without a regular expression; one of `email` or `messages` for `/explain` | `selftest` validation |
| Content type | A POST must be `application/json`. With no CORS and a content type that needs a preflight, a web page on another origin cannot make the browser send a request the API accepts | `selftest` validation, headers |
| Host header | Only `127.0.0.1` and `localhost` (settable): a defence against DNS rebinding | `selftest` headers |
| No CORS (switch) | The design has no `Access-Control` header on any answer; the interface uses a same-origin proxy (Phase 12), so the key stays out of the browser. **While `CORS_ALLOW_ANY_ORIGIN = True` in `main.py` (testing only, marked TEMPORARY) every origin is allowed, preflights are answered, and `X-Request-ID` and `Retry-After` are readable by the page** | `selftest` headers (both settings) |
| Response headers | `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`, and `X-Request-ID` on every answer including errors and 500s | `selftest` headers |
| Docs off | `/docs`, `/redoc` and `/openapi.json` are 404 unless `PRETEXTGUARD_ENABLE_DOCS=1` | `selftest` headers |
| Output safety | The report is checked by `check_report` (no `<`, `>` or backtick anywhere) and by the typed `Report` model; `/results` cells are made display-safe too | `selftest` xss |
| Errors | Fixed sentences, a request id, never the message of an exception; the log has the class of the error and where it was raised | `selftest` errors |
| Audit log | One JSON line per event from a fixed list of fields; values are reduced to safe characters; a canary string sent everywhere must appear in no log line | `selftest` audit, `smoke` |
| Concurrency | One analysis at a time behind a lock; `/analyze` waits 2 s then 503; `/explain` never waits; uvicorn answers 503 beyond 20 open connections | `selftest` concurrency |
| No persistence | Nothing is written to disk; the email lives in memory for the request | by construction; the audit fields cannot hold content |
| `/results` allow-list | A fixed dictionary of table names built at start-up from `RESULT_FILES` in `results.py`; a name is looked up, never turned into a path | `selftest` functional |
| Dependency hygiene | Pinned in `requirements.txt`; `pip-audit` found nothing | Nagasai's `pip-audit` run |

`python -m src.api.mutation_check` is the evidence that these checks test something: it removes each of 37 controls in turn and the self-test must fail.

### The layers, outside to inside

`OuterGuard` (request id, response headers, last-resort 500) -> `TrustedHost` (Host header) -> slowapi (global limit) -> `BodyGuard` (Content-Length, content type, byte count) -> routing -> route dependencies (strict rate limit, then the key) -> the route reads and checks the body -> the analysis.

Everything cheap and everything that needs no secret comes first. FastAPI would normally parse a declared body before running dependencies, which would put the key check after the parsing; the routes read the body themselves (`parse_request` in `schemas.py`) so the order above holds.

## Cost and concurrency

The classifier is CPU-bound Python. The routes are `async def` and hand the analysis to a worker thread (`run_in_threadpool`); run inside the async function itself, one analysis would freeze every other request, including a refusal or `/health`. A lock lets one analysis run at a time. LIME costs the classifier work of about 150 emails (4.9 s at 150 copies on the Mac, 10.6 s at 300), so it is its own route with its own, smaller allowance. Only a client with the key can reach the lock, and each address is limited.

## The audit log

One line per event on standard output, for example `{"time":"2026-10-09T12:00:00.000+00:00","event":"analysis","request_id":"...","mode":"email","explain":false,"explained":false,"score":100,"verdict":"High risk","tactics":["urgency","secrecy"],"contradictions":3,"duration_ms":52,"bytes":606,"messages":1}`. Events: `analysis`, `denied` (401, 413, 415, 429 and a bad length: with the status, the reason and the client address), `refused` (400, 404, 405, 422, 503), `error` (class and place of an unexpected error), `startup`, `startup_failed`. The client address is logged only for refusals, because investigating a guessed key needs it; no analysis line holds it. uvicorn's own access log (method, path, status, address) is separate and holds no body or header.

## Files

| File | Job |
|---|---|
| `settings.py` | The settings and the fixed size caps; reads `.env`; refuses to start with a bad key; `--new-key` makes one |
| `schemas.py` | The Pydantic request models and the typed `Report`; `parse_request`; `safe_errors` (where and what kind, never what was sent) |
| `security.py` | `OuterGuard`, `BodyGuard`, the rate limiter and its dependencies, the key check, `AuditLog`, the fixed error table |
| `results.py` | The allow-list of result files and the reader that turns them into JSON tables |
| `main.py` | `create_app` (the routes, the error handlers, the lock, the start-up load), `serve_options`, and `python -m src.api.main` |
| `selftest.py` | 88 checks in 11 groups, written to `results/api_checks.csv` |
| `mutation_check.py` | Breaks the controls one at a time and confirms the self-test notices; `results/api_mutations.csv` |
| `smoke.py` | A real session with the running server and the real model; `results/api_smoke.csv` |

## In Express terms

| Express | Here |
|---|---|
| `app.use((req, res, next) => ...)` | An ASGI middleware class (`OuterGuard`, `BodyGuard`): it sees the request before the routes and can answer it |
| `app.get('/x', handler)` | `@app.get("/x")` above a function |
| A middleware that only some routes use | `Depends(...)`: a function the route lists; if it raises, the route does not run |
| Joi or Zod | A Pydantic model |
| `express-rate-limit` | slowapi (its key function says who counts as one client) |
| `app.use(helmet())` | The headers in `OuterGuard` |
| The error-handling middleware `(err, req, res, next)` | `@app.exception_handler(SomeError)` |
| One Node process, one event loop | One uvicorn worker, one event loop; CPU work goes to a thread so the loop stays free |

## Known limits

- **CORS is open at the moment.** See the TEMPORARY note at the top of this file. With it open, any page in your browser can send requests to the API, and the only barrier is the key; no cookies are used, so there is nothing for a page to ride on, but do not leave it on.
- **Slow clients.** uvicorn has no timeout for a request whose headers never finish. Twenty such connections fill the 20 slots and everyone else gets 503 until they close (tested by hand). The server listens on the loopback address only; if it is ever exposed, put a reverse proxy with request timeouts in front of it.
- **One process.** The rate limits and the lock live in memory, so they hold for one worker. A second worker would double both (and load the model twice); run one.
- **The Vite proxy shares one client address.** Everything the interface sends comes from `127.0.0.1`, so all users of one proxy share one allowance. For a single-user demo that is intended.
- **A worker thread cannot be stopped.** One input can hold the lock for as long as the pipeline needs it (the crafted inputs of Phases 2 to 10 take under 5 seconds each); only holders of the key can try.
- **The lock is not fair.** Under load which waiting request gets the classifier next is not first come, first served.
- **No TLS.** The server speaks plain HTTP on the loopback address. A deployment terminates TLS in a reverse proxy and then also sets `--forwarded-allow-ips` deliberately.
- **Starlette's `TestClient`** prints a deprecation notice about `httpx` (it prefers `httpx2`); the self-test hides it. `httpx` 0.28.1 is pinned because it is the established package.

## The interface (Phase 12)

The React interface in [`frontend/`](../../frontend/README.md) is the first client of this API. How it uses it:

- It calls the API through its own server: a proxy rule forwards `/api` to `http://127.0.0.1:8000` and adds the `X-API-Key` header, read from `.env` inside `vite.config.js`. The browser never holds the key and never makes a cross-origin request, so CORS is not needed (the switch can be `False`).
- `POST /analyze` first (the score, band, action and `coverage.note` are shown at once), then `POST /explain` for the highlights; one request at a time, because the server runs one analysis at a time.
- It handles 401, 413, 422 (the refused fields are listed from `errors[].loc`), 429 and 503 `busy` (a counter on the button for `Retry-After`), 503 `model_unavailable` and an unreachable API; every error body is `{"detail", "code", "request_id", "errors"?}`.
- Every string of a report is drawn as a text node. Highlights and claims are offsets in Python characters (code points) into `text_read` or `signature_read` and are cut with `Array.from`, not with a JavaScript string slice.
- The dashboard draws from `GET /results` and `GET /results?name=...`. A result file is served only after its name is in `RESULT_FILES` in `results.py`; Phase 12 added `frontend_checks`, `frontend_mutations` and `frontend_browser_checks`.
