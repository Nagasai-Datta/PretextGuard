"""Phase 11: do the self-test's checks really test the controls? Break one control at a time and see whether a check notices.

    python -m src.api.mutation_check          # about 3 minutes; writes results/api_mutations.csv (--no-write: print only)

A test that always passes proves nothing. For each control in MUTATIONS below this script copies the code to a scratch folder, changes one line so
that the control no longer works (the key check accepts anything, the body is no longer counted, the log is no longer cleaned, ...), runs the self-test
there and records which checks failed. A control is CAUGHT when at least one check fails. A mutation that no check notices is a hole in the self-test and
is reported as NOT CAUGHT; the run then exits with an error. The real code is never touched.

In the vocabulary of testing this is mutation testing, done by hand-picked mutations: the interesting ones for a security review, not random ones.
"""

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.data.paths import PROJECT_ROOT, RESULTS_DIR

OUT = RESULTS_DIR / "api_mutations.csv"
SKIP = {".git", ".env", "data", "venv", "artifacts", "notebooks", "docs", "frontend", "node_modules", "__pycache__"}      # the secret .env is never copied

# (what is broken, file, the exact text to replace, the text that replaces it)
MUTATIONS = [
    ("the key check accepts every request", "src/api/security.py", "if len(values) != 1 or not keys_match(values[0], expected):", "if False:"),
    ("the key is compared with == instead of hmac.compare_digest", "src/api/security.py", "return hmac.compare_digest(key_digest(provided), expected_digest)", "return key_digest(provided) == expected_digest"),
    ("a repeated X-API-Key header is accepted", "src/api/security.py", "if len(values) != 1 or not keys_match(values[0], expected):", "if len(values) < 1 or not keys_match(values[-1], expected):"),
    ("the key is checked before the strict rate limit (wrong keys not counted)", "src/api/main.py",
     "dependencies=[Depends(rate_analyze), Depends(require_key)])\n    async def analyze_email", "dependencies=[Depends(require_key), Depends(rate_analyze)])\n    async def analyze_email"),
    ("/explain needs no key", "src/api/main.py", "dependencies=[Depends(rate_explain), Depends(require_key)])", "dependencies=[Depends(rate_explain)])"),
    ("/explain has the same limit as /analyze", "src/api/security.py", "    @limiter.limit(settings.rate_explain)", "    @limiter.limit(settings.rate_analyze)"),
    ("the global limit is removed", "src/api/security.py", "application_limits=[settings.rate_global], ", ""),
    ("the limiter can be switched off from the environment", "src/api/security.py", "    limiter.enabled = True\n", ""),
    ("the client address is taken from X-Forwarded-For", "src/api/security.py", "limiter = Limiter(key_func=get_remote_address,",
     "limiter = Limiter(key_func=lambda r: r.headers.get('x-forwarded-for') or get_remote_address(r),"),
    ("uvicorn trusts proxy headers", "src/api/main.py", "\"proxy_headers\": False", "\"proxy_headers\": True"),
    ("the body is not counted while it streams in", "src/api/security.py", "if state[\"received\"] > self.max_bytes:", "if False:"),
    ("Content-Length is not compared with the limit", "src/api/security.py", "if lengths and int(lengths[0]) > self.max_bytes:", "if False:"),
    ("a Content-Length that is not a plain number is accepted", "src/api/security.py",
     "if len(lengths) > 1 or (lengths and not (lengths[0].isascii() and lengths[0].isdigit() and len(lengths[0]) <= 12)):", "if False:"),
    ("the content type is not checked", "src/api/security.py",
     "if scope[\"method\"] == \"POST\" and headers.get(\"content-type\", \"\").split(\";\", 1)[0].strip().lower() != \"application/json\":", "if False:"),
    ("CORS is open although the switch is off", "src/api/main.py", "    if cors_any_origin:\n        # >>> TEMPORARY: CORS WIDE OPEN", "    if True:\n        # >>> TEMPORARY: CORS WIDE OPEN"),
    ("the Host header is not checked", "src/api/main.py", "    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))\n", ""),
    ("no Content-Security-Policy header", "src/api/security.py", "    (\"Content-Security-Policy\", \"default-src 'none'; frame-ancestors 'none'\"),\n", ""),
    ("no Cache-Control: no-store header", "src/api/security.py", "    (\"Cache-Control\", \"no-store\"),\n", ""),
    ("no request id header", "src/api/security.py", "                headers[\"X-Request-ID\"] = request_id\n", ""),
    ("the interactive docs are on", "src/api/main.py", "docs = {} if settings.enable_docs else {\"docs_url\": None, \"redoc_url\": None, \"openapi_url\": None}", "docs = {}"),
    ("unexpected errors are not caught by the outer layer", "src/api/security.py", "        except Exception as error:\n            self.audit.write(\"error\"", "        except KeyboardInterrupt as error:\n            self.audit.write(\"error\""),
    ("the message of a ReportError is logged", "src/api/main.py", "error_class=type(exc).__name__, where=where_of(exc))\n        return error_response(\"internal_error\", request_id)",
     "error_class=type(exc).__name__, where=where_of(exc), reason=str(exc))\n        return error_response(\"internal_error\", request_id)"),
    ("there is no lock around the classifier", "src/api/main.py", "if not (state.lock.acquire(timeout=wait) if wait > 0 else state.lock.acquire(blocking=False)):", "if False:"),
    ("the lock is not released after an analysis", "src/api/main.py", "    finally:\n        state.lock.release()\n    size, count", "    finally:\n        pass\n    size, count"),
    ("the names of unknown fields are echoed in 422 answers", "src/api/schemas.py",
     "loc = [part if isinstance(part, int) or part in KNOWN_LOC else \"?\" for part in item.get(\"loc\", ())][:6]", "loc = [part for part in item.get(\"loc\", ())][:6]"),
    ("unknown fields are allowed in a request", "src/api/schemas.py", "model_config = ConfigDict(extra=\"forbid\", strict=True)", "model_config = ConfigDict(extra=\"ignore\", strict=True)"),
    ("the number of top-level fields is not limited", "src/api/schemas.py", "if len(data) > MAX_TOP_LEVEL_KEYS:", "if False:"),
    ("org_domain is not checked", "src/api/schemas.py", "OrgDomain = Annotated[str | None, Field(max_length=MAX_DOMAIN_CHARS + 50), AfterValidator(check_domain)]",
     "OrgDomain = Annotated[str | None, Field(max_length=MAX_DOMAIN_CHARS + 50)]"),
    ("the size of an email in bytes is not checked", "src/api/schemas.py", "EmailText = Annotated[str, Field(min_length=1, max_length=MAX_EMAIL_BYTES), AfterValidator(check_email_bytes)]",
     "EmailText = Annotated[str, Field(min_length=1, max_length=MAX_EMAIL_BYTES)]"),
    ("the total size of a thread is not checked", "src/api/schemas.py", "        if thread_bytes(self.messages) > MAX_THREAD_BYTES:\n            raise ValueError(\"thread too large\")\n        return self\n\n\nclass ExplainRequest",
     "        return self\n\n\nclass ExplainRequest"),
    ("audit values are not cleaned", "src/api/security.py", "return \"\".join(ch if ch in SAFE_CHARS else \"_\" for ch in value[:MAX_LOG_STRING])", "return value"),
    ("the audit log accepts any field", "src/api/security.py", "if name not in AUDIT_FIELDS:\n                raise KeyError(\"audit field %r is not allowed\" % name)", "if False:\n                pass"),
    ("the results name is used as a file name", "src/api/results.py", "return self.tables.get(name) if isinstance(name, str) else None", "return read_table(RESULTS_DIR / (name + '.csv')) or self.tables.get(name)"),
    ("result cells are not made display-safe", "src/api/results.py", "return display_safe(text[:MAX_CELL_CHARS])\n\n\ndef read_table", "return text[:MAX_CELL_CHARS]\n\n\ndef read_table"),
    ("the placeholder key is accepted", "src/api/settings.py", "    if key.strip().lower() in PLACEHOLDER_KEYS:", "    if False:"),
    ("a short key is accepted", "src/api/settings.py", "    if len(key) < MIN_KEY_CHARS:", "    if False:"),
    ("the server listens on all interfaces by default", "src/api/settings.py", "    host: str = \"127.0.0.1\"", "    host: str = \"0.0.0.0\""),
]


def mutate(item):
    """(control, file, status, first failing check) for one mutation, run in its own scratch copy."""
    control, path, old, new = item
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder) / "copy"
        shutil.copytree(PROJECT_ROOT, work, ignore=lambda d, names: [n for n in names if n == "__pycache__" or (Path(d) == PROJECT_ROOT and n in SKIP)])
        text = (work / path).read_text(encoding="utf-8")
        if text.count(old) != 1:
            return control, path, "ERROR", "the text to break was found %d times (the code changed; update MUTATIONS)" % text.count(old)
        (work / path).write_text(text.replace(old, new), encoding="utf-8")
        run = subprocess.run([sys.executable, "-m", "src.api.selftest", "--no-write"], cwd=work, capture_output=True, text=True, timeout=900)
    failed = [line.strip()[5:] for line in run.stdout.splitlines() if line.strip().startswith("FAIL")]
    if failed:
        return control, path, "CAUGHT", failed[0][:160]
    if run.returncode != 0:
        return control, path, "CAUGHT", "the self-test crashed: %s" % (run.stderr.strip().splitlines() or ["?"])[-1][:120]
    return control, path, "NOT CAUGHT", ""


def main(argv):
    parser = argparse.ArgumentParser(description="Break one API control at a time and check that the self-test notices.")
    parser.add_argument("--no-write", action="store_true", help="print only, do not write results/api_mutations.csv")
    args = parser.parse_args(argv)
    results = []
    with ThreadPoolExecutor(4) as pool:
        for control, path, status, detail in pool.map(mutate, MUTATIONS):
            print("%-10s %s%s" % (status, control, "" if status == "CAUGHT" and not detail.startswith("the self-test crashed") else "   -> " + detail))
            results.append([control, path, status, detail])
    caught = sum(1 for r in results if r[2] == "CAUGHT")
    print("\n%d of %d broken controls were caught by at least one check" % (caught, len(results)))
    if not args.no_write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["control_broken", "file", "status", "first_failing_check"])
            writer.writerows(results)
        print("wrote %s" % OUT)
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
