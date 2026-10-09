"""Phase 10: run src/router/build.py on a tiny made-up dataset, so the long runs on the real data are not the first time the code runs.

Run from the project root:   python -m src.router.build_selftest        (about a minute; needs spaCy and the other libraries, not the model or the data)

It builds in a temporary folder what Phases 2, 3, 7, 8 and 9 build for the real data (cleaned and header tables, claims, threads, a small hijack
benchmark) from hand-made emails, with the stand-in tactic classifier of src/router/selftest.py, and then runs the three modes of build.py on it:
development (--train-only), calibration (--calibrate) and the final run (with --parity). It checks that every results file is written with the right
columns, that the counts add up, that the budget and the grid behave, that the benchmark shows what it must (the thread verifier finds the takeover that
the Phase 8 verifiers cannot), and that the real analyze() and the batch code give the same band. Nothing here touches your real data or results.
The numbers it produces mean nothing: the emails are made up.
"""

import sys
import tempfile
import time
import types
from pathlib import Path

import pandas as pd

import json

import src.router.build as build
from src.router import score as score_module
import src.verifiers.build as verifier_build
from src.claims.extractor import extract_many
from src.data.hijack_benchmark import LABEL
from src.data.label_schema import TACTICS
from src.headers.build import process
from src.preprocess.clean import clean_body
from src.preprocess.redact import redact
from src.router.pipeline import Analyzer, parse_message
from src.router.selftest import DAVID_BODY, HIJACK_TEXT, JOHN, MARY, PARAGRAPHS, StubClassifier, auth, eml
from src.thread.build import flatten

QUOTE = ("We agreed last week on the new payment schedule and the revised amounts for the second quarter, and you promised to send the signed papers "
         "by Friday afternoon so that the finance team can book everything before the end of the month.")


def header_block(sender, to, subject, auth_domain=None, reply_to=None, n=0):
    lines = ["From: %s" % sender, "To: %s" % to, "Subject: %s" % subject, "Date: Mon, 05 Oct 2026 09:%02d:00 +0000" % (n % 60), "Message-ID: <e%d@mail.example>" % n]
    if reply_to:
        lines.append("Reply-To: %s" % reply_to)
    block = "\n".join(lines) + "\n"
    if auth_domain:
        block += auth(auth_domain)
    return block


def made_up_emails():
    """[(source, category, split, header block, body)] for both splits."""
    rows, n = [], 0
    for split in ("train", "validation"):
        for i in range(50):                                  # ordinary internal mail that checks out
            n += 1
            rows.append(("spamassassin", "ham", split, header_block("Dana Roy <dana%d@acmecorp.com>" % i, "Maria <maria@acmecorp.com>", "Invoice", "acmecorp.com", n=n),
                         "Hi Maria,\n\nThis is Dana from Finance. Please process the invoice for the October delivery when you can.\n\nThanks\n"))
        for i in range(2):                                   # a partner writing in the same way: a low finding in ordinary mail
            n += 1
            rows.append(("spamassassin", "ham", split, header_block("Sam Rivera <sam%d@partner-example.org>" % i, "Maria <maria@acmecorp.com>", "Ticket", n=n),
                         "Hi Maria,\n\nThis is Sam from Finance. Please process the invoice for the October delivery when you can.\n\nThanks\n"))
        for i in range(30):                                  # a corpus with no header evidence at all
            n += 1
            rows.append(("kaggle_enron", "ham", split, "From: Pat Lee <pat%d@enron.example>\nTo: Maria <maria@acmecorp.com>\nSubject: Notes\n" % i,
                         "Hi Maria,\n\nThis is Pat from Finance. Please process the invoice for the October delivery when you can.\n\nThanks\n"))
        for i in range(25):                                  # spam with nothing to check
            n += 1
            rows.append(("kaggle_ceas08", "spam", split, header_block("Deals <news%d@shop-example.com>" % i, "Maria <maria@acmecorp.com>", "Sale", n=n),
                         "Our autumn sale starts this week with new products in every category.\n"))
        for i in range(20):                                  # the David email from a free mailbox
            n += 1
            rows.append(("nazario", "phishing", split, header_block("David Chen <david.chen%d@gmail.com>" % i, "Maria <maria@acmecorp.com>", "Urgent wire", "gmail.com",
                                                                      "david.finance%d@protonmail.com" % i, n=n), DAVID_BODY))
        for i in range(20):
            n += 1
            rows.append(("kaggle_nigerian_fraud", "fraud", split, header_block("Barrister <b%d@yahoo.com>" % i, "Maria <maria@acmecorp.com>", "Business", n=n),
                         "Hi,\n\nI am the director of foreign operations. Please reply to me with your details so that I can transfer the funds. Keep it confidential, it is a secret.\n"))
    return rows


def made_up_threads(count=12):
    """[(thread id, source, [records])] of calm 5-message threads between two people; the split is set later."""
    threads = []
    for t in range(count):
        records = []
        for i in range(5):
            who = JOHN if i % 2 == 0 else MARY
            raw = eml(i, who, ("Re: " if i else "") + "Invoice %d" % t, PARAGRAPHS[(i + t) % len(PARAGRAPHS)], previous=PARAGRAPHS[(i + t - 1) % len(PARAGRAPHS)] if i else None,
                      ip="52.10.20.%d" % (30 + i % 2))
            record = parse_message(raw, None, "t%d|m%d" % (t, i))["record"]
            record.update({"source": "apache", "thread_id": "apache_t%d" % t, "position": i})
            records.append(record)
        threads.append(("apache_t%d" % t, "apache", records))
    return threads


def stub_featurize(messages, name):
    """Tactic probabilities (the stand-in classifier) and claims (the real extractor) for message dictionaries, as src/thread/features.py attach_features does."""
    if not messages:
        return messages
    probabilities = StubClassifier().probabilities([m["redacted"] for m in messages])
    claims, _ = extract_many([m["redacted"] for m in messages])
    for m, row, found in zip(messages, probabilities, claims):
        m["tactics"], m["claims"] = {t: round(float(p), 4) for t, p in zip(TACTICS, row)}, found
    return messages


def build_world(folder):
    """Write the made-up tables into folder and point build.py at them. Returns the made-up emails (for the parity check)."""
    folder = Path(folder)
    (folder / "results").mkdir()
    emails = made_up_emails()
    ids = ["id%04d" % i for i in range(len(emails))]
    headers = process(pd.DataFrame({"id": ids, "raw_headers": [e[3] for e in emails]}))
    cleaned_rows = []
    for uid, (source, category, split, block, body) in zip(ids, emails):
        c = clean_body(body)
        cleaned_rows.append({"id": uid, "source": source, "category": category, "split": split, "body_clean": c["body_clean"], "body_redacted": redact(c["body_clean"])[0],
                             "signature": c["signature"]})
    pd.DataFrame(cleaned_rows).to_parquet(folder / "cleaned.parquet", index=False)
    headers.to_parquet(folder / "headers.parquet", index=False)
    pd.DataFrame({"id": ids, "raw_headers": [e[3] for e in emails], "body_raw": [e[4] for e in emails]}).to_parquet(folder / "staged.parquet", index=False)

    threads = made_up_threads()
    table = flatten([records for _, _, records in threads], set())
    table["split"] = ["train" if int(tid.split("_t")[1]) % 2 == 0 else "validation" for tid in table["thread_id"]]
    table.to_parquet(folder / "threads.parquet", index=False)
    cases, injections = [], []
    for tid, source, records in threads:
        split = "train" if int(tid.split("_t")[1]) % 2 == 0 else "validation"
        injections.append({"thread": tid, "attack_body": HIJACK_TEXT, "benign_body": PARAGRAPHS[4], "fake_quote": QUOTE})
        for variant in ("neg_real", "neg_synth", "A", "B", "C"):
            cases.append({"case_id": "%s|%s" % (tid, variant), "thread": tid, "source": source, "split": split, "variant": variant, "label": LABEL[variant], "index": 3})
    pd.DataFrame(cases).to_csv(folder / "cases.csv", index=False)
    pd.DataFrame(injections).to_csv(folder / "injections.csv", index=False)

    verifier_build.CLEANED_PARQUET, verifier_build.HEADERS_PARQUET, verifier_build.CLAIMS_CACHE_DIR = folder / "cleaned.parquet", folder / "headers.parquet", folder / "claims_cache"
    build.THREADS_PARQUET, build.STAGED_PARQUET, build.TACTIC_PROBS_DIR = folder / "threads.parquet", folder / "staged.parquet", folder / "tactic_probs"
    build.HIJACK_CASES_CSV, build.HIJACK_INJECTIONS_CSV, build.RESULTS_DIR = folder / "cases.csv", folder / "injections.csv", folder / "results"
    build.SCORE_FILES = {name: folder / "results" / ("score_%s.csv" % name) for name in build.SCORE_FILES}
    return emails


def _exits(call):
    """True when the call stops with SystemExit (a refused combination of options)."""
    try:
        call()
    except SystemExit:
        return True
    return False


def self_test(verbose=True):
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    stub = StubClassifier()
    original = (verifier_build.CLEANED_PARQUET, verifier_build.HEADERS_PARQUET, verifier_build.CLAIMS_CACHE_DIR, build.THREADS_PARQUET, build.STAGED_PARQUET, build.TACTIC_PROBS_DIR,
                build.HIJACK_CASES_CSV, build.HIJACK_INJECTIONS_CSV, build.RESULTS_DIR, build.SCORE_FILES, build.RELIABILITY_JSON)
    original_reliability = dict(score_module.DEFAULT_CONFIG["reliability"])
    original_constant = dict(score_module.RELIABILITY)
    try:
        with tempfile.TemporaryDirectory() as folder:
            emails = build_world(folder)
            factory = lambda: Analyzer(classifier=stub)

            def args(**kwargs):
                return types.SimpleNamespace(**{"train_only": False, "limit": 0, "calibrate": False, "parity": 0, "workers": 1, "weights_only": False, "write_reliability": False, **kwargs})

            def read(name):
                return pd.read_csv(build.SCORE_FILES[name])

            # 1. development run on the train split
            failed = build.run(args(train_only=True), classifier=stub, featurize=stub_featurize, analyzer_factory=factory)
            check("development run (--train-only) finishes with no failed check", failed == 0, "%d failed" % failed)
            files = {name: path.exists() for name, path in build.SCORE_FILES.items()}
            check("it writes every results file", all(files.values()), str([n for n, ok in files.items() if not ok]))
            dist = read("distribution")
            train_total = sum(1 for e in emails if e[2] == "train")
            allrow = dist[(dist["group_by"] == "all")].iloc[0]
            check("the distribution counts every train email once", int(allrow["emails"]) == train_total and int(allrow["low"] + allrow["suspicious"] + allrow["high"]) == train_total,
                  "%s of %d" % (allrow["emails"], train_total))
            by_cat = dist[dist["group_by"] == "category"].set_index("group")
            check("the made-up phishing emails (the David email) land in High risk and the ham and spam do not", by_cat.loc["phishing", "high"] == by_cat.loc["phishing", "emails"]
                  and by_cat.loc["ham", "high"] == 0 and by_cat.loc["spam", "high"] == 0, str(by_cat[["emails", "low", "suspicious", "high"]].to_dict("index")))
            check("emails with no claim to check count as unchecked", int(by_cat.loc["spam", "checked_emails"]) == 0)
            weights = read("rule_weights")
            check("the rule weights table lists header, request and thread rules with a proposed reliability for each",
                  {"header", "request", "thread"} <= set(weights["verifier"]) and weights["proposed_reliability"].isin([0.0, 0.5, 1.0]).all() and len(weights) > 50)
            sam = weights[(weights["rule"] == "hv_int_other_domain") & (weights["group"] == "spamassassin")]
            check("a rule that fires on 2 of 52 checked ordinary emails is counted but not yet judged (under 20 hits)", len(sam) == 1 and int(sam["hits"].iloc[0]) >= 1 and not bool(sam["judged"].iloc[0]),
                  str(sam[["hits", "denominator", "judged"]].to_dict("records")))
            budget = read("budget")
            sa = budget[(budget["kind"] == "email") & (budget["group"] == "spamassassin")]
            check("the budget table judges the made-up spamassassin ham (50 checked emails) and passes it", len(sa) == 1 and sa["budget"].iloc[0] == "PASS", str(sa.to_dict("records")))
            check("a source with no header evidence has no checked emails, so it is not in the budget table", "kaggle_enron" not in set(budget["group"]) or
                  int(budget[budget["group"] == "kaggle_enron"]["checked_n"].iloc[0]) <= 30)
            check("real-thread messages are in the budget table", (budget["kind"] == "thread").any() and "apache" in set(budget[budget["kind"] == "thread"]["group"]))
            grid = read("grid")
            check("the grid has 27 points and exactly one is chosen", len(grid) == 27 and int(grid["chosen"].sum()) == 1)
            chosen = grid[grid["chosen"]].iloc[0]
            check("the chosen point is the initial one when the initial point meets the budget (nearest to the initial numbers)",
                  (chosen["high_points"], chosen["medium_points"], chosen["pressure_step"]) == build.INITIAL, str(chosen.to_dict()))
            check("points that break the meaning (a lone high at 70, a lone medium at 25) are never chosen", not grid[~grid["meaning_ok"]]["chosen"].any()
                  and not build.meaning_ok(70, 35, 0.25) and not build.meaning_ok(60, 25, 0.25) and build.meaning_ok(60, 35, 0.25) and not build.meaning_ok(50, 35, 0.25) and build.meaning_ok(50, 35, 0.35))
            bench = read("benchmark_check")
            a = bench[(bench["variant"] == "A") & (bench["source"] == "apache") & (bench["metric"] == "suspicious_or_high_full")]
            a8 = bench[(bench["variant"] == "A") & (bench["source"] == "apache") & (bench["metric"] == "suspicious_or_high_phase8")]
            check("the benchmark: the takeover (A) reaches Suspicious with the thread verifier and never without it", len(a) == 1 and len(a8) == 1 and int(a["hits"].iloc[0]) == int(a["n"].iloc[0]) > 0
                  and int(a8["hits"].iloc[0]) == 0, "%s vs %s" % (a[["hits", "n"]].to_dict("records"), a8[["hits", "n"]].to_dict("records")))
            c = bench[(bench["variant"] == "C") & (bench["metric"] == "suspicious_or_high_full")]
            check("the benchmark: the forged thread (C) is found by the integrity checks", len(c) == 1 and int(c["hits"].iloc[0]) == int(c["n"].iloc[0]) > 0, str(c[["hits", "n"]].to_dict("records")))
            neg = bench[(bench["variant"] == "neg_real") & (bench["metric"] == "suspicious_or_high_full")]
            check("the benchmark: the calm real next reply is not a false alarm", len(neg) == 1 and int(neg["hits"].iloc[0]) == 0)

            # 1b. the reliability of the rules from every train email, written to a data file
            target = Path(folder) / "reliability.json"
            build.RELIABILITY_JSON = target
            failed = build.run(args(weights_only=True, write_reliability=True), classifier=stub, featurize=stub_featurize, analyzer_factory=factory)
            written = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            weights = read("rule_weights")
            check("--weights-only --write-reliability finishes and writes the data file for the current score version", failed == 0 and written.get("for_score_version") == score_module.SCORE_VERSION,
                  str(written)[:200])
            check("the file holds exactly the rules whose proposed reliability is below 1, and score.load_reliability accepts it",
                  score_module.load_reliability(target) == build.reliability_from(weights) and set(written["reliability"]) <= build.KNOWN_RULES and "tv_path_origin" in written["reliability"],
                  str(written.get("reliability")))
            wrong = Path(folder) / "wrong_version.json"
            wrong.write_text(json.dumps({"for_score_version": "0.0", "reliability": {}}), encoding="utf-8")
            try:
                score_module.load_reliability(wrong)
                check("a reliability file written for another score version is refused", False)
            except ValueError:
                check("a reliability file written for another score version is refused", True)
            bad = Path(folder) / "bad_factor.json"
            bad.write_text(json.dumps({"for_score_version": score_module.SCORE_VERSION, "reliability": {"hv_sig_other_domain": 0.7}}), encoding="utf-8")
            try:
                score_module.load_reliability(bad)
                check("a reliability factor other than 0 or 0.5 is refused", False)
            except ValueError:
                check("a reliability factor other than 0 or 0.5 is refused", True)
            check("the guards refuse --write-reliability without --weights-only and --weights-only with other modes",
                  all(_exits(lambda a=a: build.run(args(**a), classifier=stub)) for a in ({"write_reliability": True}, {"weights_only": True, "calibrate": True}, {"weights_only": True, "limit": 10})))
            frozen = score_module.load_reliability(target)                                          # the freeze of the made-up world
            score_module.DEFAULT_CONFIG["reliability"] = dict(frozen)
            score_module.RELIABILITY.clear()
            score_module.RELIABILITY.update(frozen)

            # 2. calibration on validation
            failed = build.run(args(calibrate=True), classifier=stub, featurize=stub_featurize, analyzer_factory=factory)
            grid = read("grid")
            check("the calibration run (--calibrate) finishes and saves only the grid, on the validation split", failed == 0 and set(grid["split"]) == {"validation"} and len(grid) == 27)

            # 3. the final run with the parity check
            failed = build.run(args(parity=40), classifier=stub, featurize=stub_featurize, analyzer_factory=factory)
            checks_table = read("checks")
            bad = checks_table[checks_table["status"] == "FAIL"]
            check("the final run finishes with no failed check (including the parity check and 'frozen numbers equal the chosen point')", failed == 0 and bad.empty, str(bad[["check", "item", "value"]].to_dict("records")))
            parity = checks_table[checks_table["check"] == "parity"]
            check("analyze() and the batch code give the same band on the made-up validation emails", len(parity) == 1 and parity["status"].iloc[0] == "PASS", str(parity.to_dict("records")))
            config = read("config")
            check("the config file records the frozen numbers and the budgets", {"points_high", "budget_high_risk_share", "score_version"} <= set(config["setting"]))
            stale = checks_table[checks_table["item"].str.startswith("reliability.json equals")]
            check("the final run checks that the file equals the factors computed from every train email, and it does", len(stale) == 1 and stale["status"].iloc[0] == "PASS", str(stale.to_dict("records")))
            budget_now = read("budget")
            check("the budget table lists the rules behind Suspicious or above", "top_rules" in budget_now.columns)
            splits = checks_table[(checks_table["check"] == "leakage_guard")]["value"].iloc[0]
            check("the final run reads train and validation and never test", splits == "train+validation", str(splits))
            dist = read("distribution")
            check("the final distribution is for the validation split", set(dist["split"]) == {"validation"})

            # 4. choose() when nothing meets the budget
            grid_bad = grid.copy()
            grid_bad["budget_ok"] = False
            check("choose() returns nothing when no point meets the budget (the finding is then 'the rules are too noisy')", build.choose(grid_bad) is None)
            grid_two = grid.copy()
            grid_two["budget_ok"] = ((grid_two["high_points"] == 50) & (grid_two["medium_points"] == 35) & (grid_two["pressure_step"] == 0.35)) | ((grid_two["high_points"] == 60) & (grid_two["medium_points"] == 35) & (grid_two["pressure_step"] == 0.35))
            pick = build.choose(grid_two)
            check("choose() takes the qualifying point nearest to the initial numbers", pick is not None and (pick["high_points"], pick["medium_points"], pick["pressure_step"]) == (60, 35, 0.35), str(pick))
            block = "From: a@b.co\nContent-Type: multipart/mixed;\n boundary=xyz\nSubject: Hi\n there\nMIME-Version: 1.0\nContent-Transfer-Encoding: base64\nTo: c@d.co"
            check("strip_mime_headers drops the MIME headers and their continuation lines and keeps the others", build.strip_mime_headers(block) == "From: a@b.co\nSubject: Hi\n there\nTo: c@d.co", repr(build.strip_mime_headers(block)))
            check("wilson() gives the known interval for 1 of 20 and nothing for 0 of 0", abs(build.wilson(1, 20)[0] - 0.0089) < 0.001 and abs(build.wilson(1, 20)[1] - 0.2361) < 0.001 and build.wilson(0, 0) == (None, None))
            check("proposed reliability: 1 up to 5%, 0.5 up to 10%, 0 above", [build.proposed_reliability([r]) for r in (0.04, 0.06, 0.2)] == [1.0, 0.5, 0.0] and build.proposed_reliability([]) == 1.0)
    finally:
        (verifier_build.CLEANED_PARQUET, verifier_build.HEADERS_PARQUET, verifier_build.CLAIMS_CACHE_DIR, build.THREADS_PARQUET, build.STAGED_PARQUET, build.TACTIC_PROBS_DIR,
         build.HIJACK_CASES_CSV, build.HIJACK_INJECTIONS_CSV, build.RESULTS_DIR, build.SCORE_FILES, build.RELIABILITY_JSON) = original
        score_module.DEFAULT_CONFIG["reliability"] = original_reliability
        score_module.RELIABILITY.clear()
        score_module.RELIABILITY.update(original_constant)
    passed = all(ok for _, ok, _ in checks)
    if verbose:
        for name, ok, detail in checks:
            print("  %s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok or not detail else "  -> " + detail))
        print("%d of %d checks passed" % (sum(ok for _, ok, _ in checks), len(checks)))
    return passed, len(checks)


if __name__ == "__main__":
    started = time.time()
    ok, _ = self_test()
    print("%.0f seconds" % (time.time() - started))
    sys.exit(0 if ok else 1)
