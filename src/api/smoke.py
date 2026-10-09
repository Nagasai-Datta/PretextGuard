"""Phase 11: a real session with the running server, the trained model and real HTTP.

Start the server in one terminal (keep its output in a file so the canary check can read it):

    python -m src.api.main 2>&1 | tee /tmp/pg_server.log

and run this in another:

    python -m src.api.smoke --server-log /tmp/pg_server.log

The self-test (src/api/selftest.py) calls the app in-process with a stand-in classifier. This script is the other half: the real model, real HTTP
through uvicorn, real timings, a body that really is 4 MB, and real emails from the corpus that contain script payloads. It reads the API key from .env
(or the environment) exactly as the server does, sends only emails it makes up and emails from your own data/processed/staged.parquet to the server on
this machine, and writes only counts and timings to results/api_smoke.csv (no email text).

Rate limits: the script sends about 25 analysis requests, under the 30 a minute allowed, and its last step uses up the /explain allowance on purpose.
Wait a minute before running it again.
"""

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

from src.api.schemas import Report
from src.api.settings import SettingsError, load_settings
from src.data.paths import RESULTS_DIR, STAGED_PARQUET
from src.router.pipeline import check_report
from src.router.selftest import DAVID_GMAIL, HIJACK_TEXT, JOHN, PARAGRAPHS, calm_thread, eml, nested_mime

OUT = RESULTS_DIR / "api_smoke.csv"
CANARY = "SMOKECANARY7788"
XSS_MARKERS = ("<script", "onerror=", "javascript:", "<iframe", "onload=")


class Rows:
    def __init__(self):
        self.rows = []

    def add(self, group, item, ok, value="", expected="", info=False):
        status = "info" if info else ("PASS" if ok else "FAIL")
        self.rows.append([group, item, str(value)[:300], expected, status])
        print("  %s [%s] %s%s" % (status, group, item, "" if ok or info or value == "" else "  -> " + str(value)[:300]))

    @property
    def failed(self):
        return [r for r in self.rows if r[4] == "FAIL"]


def corpus_payloads(limit):
    """Up to `limit` raw emails from the train split of staged.parquet whose text holds a script-like payload (headers + body, at most 250,000 characters each)."""
    if not STAGED_PARQUET.is_file():
        return None
    import pyarrow.parquet as pq
    found = []
    file = pq.ParquetFile(STAGED_PARQUET)
    for batch in file.iter_batches(batch_size=2000, columns=["raw_headers", "body_raw", "split"]):
        table = batch.to_pydict()
        for headers, body, split in zip(table["raw_headers"], table["body_raw"], table["split"]):
            if split != "train" or not isinstance(body, str):
                continue
            low = body.lower()
            if any(marker in low for marker in XSS_MARKERS):
                text = ((headers or "") + "\n\n" + body)[:250_000]
                found.append(text)
                if len(found) >= limit:
                    return found
    return found


def run(url, key, server_log, corpus_count, out):
    rows = Rows()
    auth = {"X-API-Key": key}
    session = requests.Session()

    def post(path, payload, key_header=True, timeout=120, **kwargs):
        headers = dict(auth) if key_header else {}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        started = time.perf_counter()
        response = session.post(url + path, json=payload, headers=headers, timeout=timeout, **kwargs) if payload is not None else session.post(url + path, headers=headers, timeout=timeout, **kwargs)
        return response, time.perf_counter() - started

    # 1 health and results
    try:
        health = session.get(url + "/health", timeout=10)
    except requests.RequestException as error:
        print("Cannot reach %s (%s). Start the server first:  python -m src.api.main" % (url, type(error).__name__))
        return None
    body = health.json()
    rows.add("health", "GET /health: 200, model loaded, versions listed", health.status_code == 200 and body.get("model_loaded") is True, "%s, model_loaded %s" % (health.status_code, body.get("model_loaded")))
    index = session.get(url + "/results", timeout=10)
    table = session.get(url + "/results", params={"name": "score_budget"}, timeout=10)
    rows.add("results", "GET /results lists the tables and GET /results?name=score_budget returns one", index.status_code == 200 and len(index.json().get("files", [])) >= 30 and table.status_code == 200
             and table.json().get("rows"), "%d tables" % len(index.json().get("files", [])))

    # 2 authentication on the real server
    r1, _ = post("/analyze", {"email": "hello"}, key_header=False)
    r2, _ = post("/analyze", {"email": "hello"}, headers={"X-API-Key": "wrong-key-" + CANARY})
    rows.add("auth", "no key and a wrong key are 401", r1.status_code == 401 and r2.status_code == 401, [r1.status_code, r2.status_code])

    # 3 a real analysis, timings
    r, seconds = post("/analyze", {"email": DAVID_GMAIL})
    report = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and check_report(report) == [] and Report.model_validate(report).model_dump() == report
    rows.add("analyze", "POST /analyze with the real model: 200, the report passes check_report and the typed Report model", ok, r.status_code)
    rows.add("analyze", "the David email: verdict, score and tactics that fired (what the real model made of the stand-in test email)", True,
             "%s %s %s" % (report.get("verdict"), report.get("score"), [t["name"] for t in report.get("tactics", []) if t["fired"]]), info=True)
    times = []
    for _ in range(5):
        r, seconds = post("/analyze", {"email": DAVID_GMAIL})
        times.append(seconds)
    rows.add("timing", "5 analyses of the David email, no LIME: mean and slowest seconds (the server was warm)", max(times) < 5, "mean %.3f, slowest %.3f" % (sum(times) / len(times), max(times)), "slowest under 5 s")

    # 4 LIME
    r, explain_seconds = post("/explain", {"email": DAVID_GMAIL})
    explained = r.json() if r.status_code == 200 else {}
    fired = [t for t in explained.get("tactics", []) if t["fired"]]
    rows.add("explain", "POST /explain: 200, LIME ran when a tactic fired, highlights fit the text, the score equals the one without LIME",
             r.status_code == 200 and explained.get("explained") is bool(fired) and explained.get("score") == report.get("score") and check_report(explained) == []
             and all(explained["text_read"][h["start"]:h["end"]] == h["text"] for t in explained.get("tactics", []) for h in t["highlights"]), "%s fired %d" % (r.status_code, len(fired)))
    rows.add("timing", "one explanation (150 LIME copies), seconds (the Phase 10 figure on the Mac was 4.9)", explain_seconds < 15, "%.1f" % explain_seconds, "under 15 s")

    # 5 a thread
    thread = calm_thread(4) + [eml(4, JOHN, "Re: Invoice 77", HIJACK_TEXT, previous=PARAGRAPHS[3], ip="52.10.20.30")]
    r, seconds = post("/analyze/thread", {"messages": thread})
    thread_report = r.json() if r.status_code == 200 else {}
    rows.add("thread", "POST /analyze/thread: 200, thread mode, 5 messages", r.status_code == 200 and thread_report.get("mode") == "thread" and thread_report["thread"]["messages"] == 5 and check_report(thread_report) == [])
    rows.add("thread", "the account-takeover thread: verdict, score and the message where it flipped (with the real model)", True,
             "%s %s flip %s in %.2f s" % (thread_report.get("verdict"), thread_report.get("score"), (thread_report.get("thread") or {}).get("flip_index"), seconds), info=True)

    # 6 the MIME bomb of Phase 10
    bomb = nested_mime(3000)
    r, seconds = post("/analyze", {"email": bomb})
    rows.add("robust", "3,000 nested MIME levels (the email that crashed the Phase 10 parser): 200 with the depth limit noted, in time",
             r.status_code == 200 and "mime_too_deep" in r.json().get("coverage", {}).get("limits", []) and seconds < 5, "%s %.2f s" % (r.status_code, seconds))

    # 7 sizes over real HTTP
    big = b'{"email": "' + b"a" * 5_000_000 + b'"}'
    r, _ = post("/analyze", None, data=big, headers={"Content-Type": "application/json"})
    rows.add("size", "a 5 MB body with a Content-Length: 413", r.status_code == 413, r.status_code)

    def chunks(count, size):
        for _ in range(count):
            yield b" " * size

    outcome = "?"
    try:
        r = session.post(url + "/analyze", data=chunks(43, 100_000), headers=dict(auth, **{"Content-Type": "application/json"}), timeout=60)
        outcome = r.status_code
    except requests.RequestException as error:
        outcome = "connection closed (%s)" % type(error).__name__
    rows.add("size", "a streamed 4.3 MB body with no Content-Length: refused with 413 (or the connection is closed once the limit is passed)", outcome == 413 or str(outcome).startswith("connection closed"), outcome)
    try:
        r = requests.post(url + "/analyze", data=chunks(60, 100_000), headers={"Content-Type": "application/json"}, timeout=60)
        outcome = r.status_code
    except requests.RequestException as error:
        outcome = "connection closed (%s)" % type(error).__name__
    rows.add("size", "a streamed 6 MB body with no key: refused with 401 without being read (or the connection is closed)", outcome == 401 or str(outcome).startswith("connection closed"), outcome)
    health_after = session.get(url + "/health", timeout=10)
    rows.add("size", "the server still answers after the oversize bodies", health_after.status_code == 200)

    # 8 concurrency on the real model
    started = time.perf_counter()
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda i: post("/analyze", {"email": DAVID_GMAIL})[0].status_code, range(4)))
    rows.add("concurrency", "4 analyses at once: each answered 200 (queued behind the lock) or 503 busy, nothing else", set(results) <= {200, 503} and 200 in results, "%s in %.2f s" % (results, time.perf_counter() - started))
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(lambda: post("/explain", {"email": DAVID_GMAIL}))
        time.sleep(0.7)
        second, second_seconds = post("/explain", {"email": DAVID_GMAIL})
        waiter, waiter_seconds = post("/analyze", {"email": DAVID_GMAIL})
        first_response, first_seconds = first.result()
    detail = "first %s in %.1f s; second %s in %.2f s; analyze %s in %.2f s" % (first_response.status_code, first_seconds, second.status_code, second_seconds, waiter.status_code, waiter_seconds)
    if first_seconds < 1.5:
        rows.add("concurrency", "the explanation finished too quickly to overlap with a second request, so the busy answer was not tested", True, detail, info=True)
    else:
        rows.add("concurrency", "while one explanation runs a second /explain is refused at once (503 busy) and /analyze waits its 2 s, then 503 (or 200 if the explanation was shorter)",
                 first_response.status_code == 200 and second.status_code == 503 and second_seconds < 1.0 and waiter.status_code in (200, 503), detail)

    # 9 the canary
    mail = DAVID_GMAIL.replace("Hi Maria,", "Hi %s," % CANARY).replace("Urgent wire", CANARY)
    r, _ = post("/analyze", {"email": mail}, headers={"User-Agent": CANARY, "X-Request-ID": CANARY})
    post("/analyze", {"email": "x", "org_domain": CANARY + " <b>"})
    post("/analyze", {"email": "x", CANARY: 1})
    post("/analyze", {"email": CANARY}, headers={"X-API-Key": CANARY})
    reached = r.status_code == 200 and CANARY in r.text
    if server_log:
        log = Path(server_log).read_text(encoding="utf-8", errors="replace") if Path(server_log).is_file() else ""
        rows.add("audit", "the canary %s (sent in an email body, a Subject, a header, a field name, a domain and a wrong key) is in the successful report but not in the server log %s" % (CANARY, server_log),
                 reached and bool(log) and CANARY not in log and key not in log, "log %d characters, canary in log: %s, key in log: %s" % (len(log), CANARY in log, key in log))
        lines = [json.loads(l) for l in log.splitlines() if l.startswith('{"time"')]
        rows.add("audit", "the log holds JSON audit lines for the analyses of this run", sum(1 for l in lines if l.get("event") == "analysis") >= 12,
                 "%d audit lines, %d analyses" % (len(lines), sum(1 for l in lines if l.get("event") == "analysis")))
    else:
        rows.add("audit", "the canary reached the pipeline (it is in the successful report); run with --server-log FILE to check that it is not in the server log", reached, "not checked against a log", info=True)

    # 10 real emails from the corpus
    payloads = corpus_payloads(corpus_count)
    if payloads is None:
        rows.add("xss", "real corpus emails with script payloads: data/processed/staged.parquet is not on this machine", True, "skipped", info=True)
    else:
        bad, statuses = [], []
        for text in payloads:
            for path, payload in (("/analyze", {"email": text}),):
                r, _ = post(path, payload)
                statuses.append(r.status_code)
                if r.status_code == 200 and any(ch in r.text for ch in "<>`"):
                    bad.append(path)
        rows.add("xss", "%d real emails from the corpus that contain script-like payloads: all analysed, and no response holds '<', '>' or a backtick" % len(payloads), bool(payloads) and not bad and set(statuses) == {200},
                 "statuses %s, markup in responses: %d" % (sorted(set(statuses)), len(bad)))

    # 11 the rate limit, last (it uses up the allowance)
    responses = [post("/explain", {"email": "x"}, headers={"X-API-Key": "guess-%d" % i})[0] for i in range(8)]
    codes = [r.status_code for r in responses]
    limited = next((r for r in responses if r.status_code == 429), None)
    rows.add("limits", "wrong keys on /explain are counted: 429 appears within 8 tries (the allowance is 6 a minute and earlier explanations used some)", limited is not None, codes)
    rows.add("limits", "the 429 carries Retry-After (seconds) and the fixed message", limited is not None and limited.headers.get("retry-after", "").isdigit() and limited.json().get("code") == "rate_limited",
             "retry-after %s" % (limited.headers.get("retry-after") if limited is not None else None))

    rows.add("run", "server", True, url, info=True)
    rows.add("run", "python", True, sys.version.split()[0], info=True)
    rows.add("run", "requests", True, requests.__version__, info=True)
    rows.add("run", "run at", True, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), info=True)
    passed = sum(1 for r in rows.rows if r[4] == "PASS")
    print("\n%d checks: %d PASS, %d FAIL, %d info" % (passed + len(rows.failed), passed, len(rows.failed), sum(1 for r in rows.rows if r[4] == "info")))
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["check", "item", "value", "expected", "status"])
            writer.writerows(rows.rows)
        print("wrote %s" % out)
    return rows


def main(argv):
    parser = argparse.ArgumentParser(description="A real session with the running API server (real model, real HTTP).")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--server-log", help="the file the server's output was saved in (python -m src.api.main 2>&1 | tee FILE): checked for the canary and the key")
    parser.add_argument("--corpus", type=int, default=3, help="how many real emails with script payloads to send (default 3; 0 skips)")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    try:
        key = load_settings().api_key
    except SettingsError as error:
        print("Cannot read the API key: %s" % error)
        return 1
    rows = run(args.url.rstrip("/"), key, args.server_log, args.corpus, None if args.no_write else OUT)
    return 0 if rows is not None and not rows.failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
