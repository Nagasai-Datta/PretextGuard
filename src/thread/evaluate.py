"""Phase 9: score the thread verifier (N2) on the thread-hijack benchmark.

Run from the project root (after src.thread.build and src.data.hijack_benchmark collect; needs the tactic model and spaCy):
    python -m src.thread.evaluate --train-only                  # development: the train threads only
    python -m src.thread.evaluate --train-only --show-misses    # also print the rules that fired on up to 8 missed attacks per variant (synthetic text only)
    python -m src.thread.evaluate                               # the final run of a frozen version: also scores the VALIDATION threads, once

For every case of data/threads/cases.csv (src/data/hijack_benchmark.py explains the five variants) the script asks three things:
    N2      does the thread verifier find a medium or high contradiction in the candidate, judged against the real messages before it?
    Phase 8 does the header verifier or the request verifier (what the system had before Phase 9) find one in the candidate alone?
    either  does at least one of them?
and scans the thread (real messages before the candidate, then the candidate) for the index where it flips. Hijacked cases (A, B, C)
are scored by detection, which signal caught them and whether the flip index is the candidate's; real and synthetic negatives
(neg_real, neg_synth) by false alarms. The gain of N2 is the share of hijacks that N2 finds and Phase 8 does not.

Rates come with a 95% bootstrap interval that resamples THREADS, not cases (the cases of one thread share its history). A cell with fewer
than 10 cases is reported as a count only (the rule of Phase 5: no rate from a handful of cases).

WHAT THIS CAN AND CANNOT SAY. The attacks are synthetic and the headers of the injected messages are written by rule (hijack_benchmark.py), so
the detection rates say that the rules do what they are defined to do against this construction, not how often real attackers behave this way.
Variant A copies the real sender's server, mail program and IDs on purpose: it shows what only the content signals can see. The real next reply
(neg_real) gives the false alarms on real mail. Rules are written from the definitions and revised only after reading TRAIN results: `--train-only`
never scores a validation case; the final run scores validation once; the test split is read in Phase 13 (src/eval/ablation_n2.py).

Writes results/thread_scores.csv (counts and rates) and results/hijack_checks.csv (PASS/FAIL checks).
"""

import argparse
import time

import numpy as np
import pandas as pd

from src.data.hijack_benchmark import LABEL, VARIANTS, candidate_message, case_thread
from src.data.paths import HIJACK_CASES_CSV, HIJACK_CHECKS_CSV, HIJACK_INJECTIONS_CSV, HIJACK_PLAN_CSV, RESULTS_DIR, THREAD_SCORES_CSV, THREADS_PARQUET, relative
from src.models.dataset import model_text
from src.thread import builder
from src.thread.features import attach_features, load_thresholds
from src.thread.selftest import self_test
from src.verifiers.rows import check_row
from src.verifiers.thread_verifier import RULES, THREAD_RULES_VERSION, scan_thread, verify_thread_message
from src.verifiers.verify import RULES_VERSION, verify_claims

MIN_CASES = 10                # fewer cases than this in a cell and only the count is reported
BOOTSTRAPS = 1000
SEED = 42
FLAG = ("medium", "high")
GROUPS = {"tactic_onset": "onset", "request_drift": "request", "sending_path": "path", "thread_integrity": "integrity",
          "prior_relationship": "prior", "single_email": "single"}
REQUEST_CLAIMS = {"payment_request", "payment_change", "credential_request", "gift_card", "data_request"}


def group_of(rule):
    """The signal group of a thread rule: onset, request, path, integrity ... (tv_bank_* and tv_req_* are both request drift)."""
    kind = RULES[rule][0]
    return "request" if kind in REQUEST_CLAIMS or kind == "any request" else GROUPS.get(kind, kind)


def flagged(rows):
    return any(r["contradiction"] and r["severity"] in FLAG for r in rows)


def groups_fired(rows):
    return {group_of(r["rule"]) for r in rows if r["contradiction"] and r["severity"] in FLAG}


def judge(case, messages, candidate, facts, thresholds):
    """Run N2, the Phase 8 verifiers and the scan for one case. messages: the real thread with features; candidate and facts: candidate_message()."""
    k = int(case["index"])
    thread = case_thread(case["variant"], messages, k, candidate)
    n2_rows = verify_thread_message(thread, k, thresholds)
    p8_rows = verify_claims(candidate["claims"] or [], facts, "", model_text(candidate["redacted"]))
    scan = scan_thread(thread, thresholds)
    return {
        "case_id": case["case_id"], "thread": case["thread"], "split": case["split"], "source": case["source"], "variant": case["variant"], "label": int(case["label"]),
        "index": k, "n2": flagged(n2_rows), "p8": flagged(p8_rows), "either": flagged(n2_rows) or flagged(p8_rows),
        "groups": sorted(groups_fired(n2_rows)), "flip": scan["flip_index"],
        "n2_rules": sorted({r["rule"] for r in n2_rows if r["contradiction"]}), "p8_rules": sorted({r["rule"] for r in p8_rows if r["contradiction"]}),
        "problems": sum(len(check_row(r, RULES)) for r in n2_rows),
    }


# ------------------------------------------------------------------------------------------------ the numbers

def bootstrap(hits, clusters, rng):
    """95% interval of hits/total when whole clusters (threads) are resampled with replacement."""
    ids = sorted(set(clusters))
    per = {c: [0, 0] for c in ids}
    for hit, cluster in zip(hits, clusters):
        per[cluster][0] += int(hit)
        per[cluster][1] += 1
    sums = np.array([per[c][0] for c in ids], dtype=float)
    sizes = np.array([per[c][1] for c in ids], dtype=float)
    rates = []
    for _ in range(BOOTSTRAPS):
        pick = rng.integers(0, len(ids), len(ids))
        rates.append(sums[pick].sum() / sizes[pick].sum())
    return float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5))


def metric_row(split, source, variant, metric, hits, clusters, rng, note=""):
    n = len(hits)
    row = {"split": split, "source": source, "variant": variant, "metric": metric, "n": n, "hits": int(sum(hits)), "rate": None, "ci_low": None, "ci_high": None, "note": note}
    if n >= MIN_CASES:
        low, high = bootstrap(hits, clusters, rng)
        row.update({"rate": round(sum(hits) / n, 3), "ci_low": round(low, 3), "ci_high": round(high, 3)})
    else:
        row["note"] = (note + "; " if note else "") + "fewer than %d cases: count only" % MIN_CASES
    return row


def score_table(detail):
    rng = np.random.default_rng(SEED)
    rows = []
    for (split, source), part in detail.groupby(["split", "source"]):
        pools = [(v, part[part.variant == v]) for v in VARIANTS if (part.variant == v).any()]
        attacks = part[part.label == 1]
        pools.append(("attacks (A+B+C)", attacks))
        for variant, sub in pools:
            if sub.empty:
                continue
            clusters = sub["thread"].tolist()
            if variant.startswith("neg_"):
                for metric, column in (("false_alarm_n2", "n2"), ("false_alarm_phase8", "p8"), ("false_alarm_either", "either")):
                    rows.append(metric_row(split, source, variant, metric, sub[column].tolist(), clusters, rng))
                rows.append(metric_row(split, source, variant, "false_alarm_scan", [f is not None and not pd.isna(f) for f in sub["flip"]], clusters, rng,
                                       "the scan flags some message of the thread"))
                continue
            for metric, column in (("detect_n2", "n2"), ("detect_phase8", "p8"), ("detect_either", "either")):
                rows.append(metric_row(split, source, variant, metric, sub[column].tolist(), clusters, rng))
            rows.append(metric_row(split, source, variant, "gain_n2_over_phase8", (sub["n2"] & ~sub["p8"]).tolist(), clusters, rng, "found by N2, missed by the Phase 8 verifiers"))
            for group in ("onset", "request", "path", "integrity"):
                rows.append(metric_row(split, source, variant, "signal_" + group, [group in g for g in sub["groups"]], clusters, rng, "N2 contradiction of this signal"))
            exact = [(f == i) if not pd.isna(f) else False for f, i in zip(sub["flip"], sub["index"])]
            early = [(f < i) if not pd.isna(f) else False for f, i in zip(sub["flip"], sub["index"])]
            rows.append(metric_row(split, source, variant, "flip_exact", exact, clusters, rng, "the scan flips at the injected message"))
            rows.append(metric_row(split, source, variant, "flip_early", early, clusters, rng, "the scan flips BEFORE the injected message (a false alarm on a real message)"))
    return pd.DataFrame(rows)


def print_scores(scores):
    pd.set_option("display.width", 230)
    show = scores.copy()
    show["rate"] = [("%.1f%% [%.1f, %.1f]" % (100 * r, 100 * lo, 100 * hi)) if pd.notna(r) else "count only" for r, lo, hi in zip(show.rate, show.ci_low, show.ci_high)]
    for (split, source), part in show.groupby(["split", "source"]):
        print("\n%s, %s threads (rate with a 95%% interval over threads; hits / n)" % (split, source))
        table = part.assign(value=[("%s  (%d/%d)" % (r, h, n)) for r, h, n in zip(part.rate, part.hits, part.n)]).pivot(index="metric", columns="variant", values="value").fillna("")
        print(table.to_string())


# ------------------------------------------------------------------------------------------------------ checks

def make_checks(detail, cases, scores, problems, splits, started, thresholds_source):
    checks = []

    def add(check, item, value, expected, status):
        checks.append({"check": check, "item": item, "value": value, "expected": expected, "status": status})

    passed, total = self_test(verbose=False)
    add("selftest", "thread self-test", "%s of %d" % ("all" if passed else "NOT all", total), "all pass", "PASS" if passed else "FAIL")
    add("rows_valid", "thread-verifier rows that fail check_row", problems, "0", "PASS" if not problems else "FAIL")
    spread = cases.groupby("thread")["split"].nunique()
    add("leakage_guard", "threads in more than one split", int((spread > 1).sum()), "0", "PASS" if (spread == 1).all() else "FAIL")
    add("leakage_guard", "splits scored in this run", "+".join(splits), "train only (--train-only) or train and validation; never test", "PASS" if set(splits) <= {"train", "validation"} else "FAIL")
    wrong = [c for c in cases.to_dict("records") if int(c["label"]) != LABEL[c["variant"]]]
    add("labels", "cases whose label does not fit their variant", len(wrong), "0", "PASS" if not wrong else "FAIL")
    per_thread = cases.groupby("thread")["variant"].apply(set)
    missing = [t for t, v in per_thread.items() if not {"neg_real", "neg_synth", "A", "C"} <= v]
    add("structure", "threads missing one of neg_real, neg_synth, A, C", len(missing), "0", "PASS" if not missing else "FAIL")
    # Construction invariants: an attacker who copies the details cannot be caught by those details. A violation is a bug in the rule or in the injection.
    for variant, forbidden in (("A", {"path", "integrity"}), ("B", {"integrity"}), ("C", {"path"}), ("neg_synth", {"path", "integrity"})):
        sub = detail[detail.variant == variant]
        broken = sum(1 for g in sub["groups"] if forbidden & set(g))
        add("isolation", "variant %s cases where a %s signal fires (the injection copies those details)" % (variant, "/".join(sorted(forbidden))), broken, "0", "PASS" if broken == 0 else "FAIL")
    for split in splits:
        part = scores[(scores.split == split) & (scores.metric == "false_alarm_n2") & (scores.variant == "neg_real")]
        for row in part.to_dict("records"):
            if row["rate"] is None or pd.isna(row["rate"]):
                continue
            add("false_alarms", "%s %s: N2 false-alarm rate on the real next reply (neg_real)" % (split, row["source"]), "%.1f%%" % (100 * row["rate"]),
                "<= 20% (a finding if not)", "PASS" if row["rate"] <= 0.20 else "info")
    add("run", "thread rules version / header and request rules version", "%s / %s" % (THREAD_RULES_VERSION, RULES_VERSION), "", "info")
    add("run", "tactic thresholds from", thresholds_source, "", "info")
    add("run", "cases scored", len(detail), "", "info")
    add("run", "validation cases scored in this run", "no (--train-only)" if "validation" not in splits else "yes", "yes in the final run of a frozen version", "info" if "validation" not in splits else "PASS")
    add("run", "seconds", round(time.time() - started), "", "info")
    return pd.DataFrame(checks)


def main():
    parser = argparse.ArgumentParser(description="Score the thread verifier on the thread-hijack benchmark (Phase 9).")
    parser.add_argument("--train-only", action="store_true", help="score the train threads only (use while writing rules)")
    parser.add_argument("--show-misses", action="store_true", help="print the rules that fired on up to 8 missed attacks per variant (never saved)")
    args = parser.parse_args()
    started = time.time()
    for path in (HIJACK_CASES_CSV, HIJACK_INJECTIONS_CSV, HIJACK_PLAN_CSV, THREADS_PARQUET):
        if not path.exists():
            raise SystemExit("%s is missing: run src.thread.build and src.data.hijack_benchmark collect first" % relative(path))
    thresholds, source = load_thresholds()
    splits = ["train"] if args.train_only else ["train", "validation"]
    cases = pd.read_csv(HIJACK_CASES_CSV)
    injections = pd.read_csv(HIJACK_INJECTIONS_CSV).set_index("thread").to_dict("index")
    table = pd.read_parquet(THREADS_PARQUET)
    wanted = cases[cases.split.isin(splits)]
    threads = builder.table_to_threads(table[table["thread_id"].isin(set(wanted["thread"]))])
    print("Thread rules %s, header and request rules %s; thresholds from %s; %d cases in %s" % (THREAD_RULES_VERSION, RULES_VERSION, source, len(wanted), "+".join(splits)))

    details, problems = [], 0
    for split in splits:
        part = wanted[wanted.split == split]
        real = [m for tid in sorted(set(part["thread"])) for m in threads[tid]]
        attach_features(real, split)
        candidates = []
        for case in part.to_dict("records"):
            candidate, facts = candidate_message(case["variant"], threads[case["thread"]], int(case["index"]), injections[case["thread"]])
            candidates.append((case, candidate, facts))
        attach_features([c for case, c, _ in candidates if case["variant"] != "neg_real"], "hijack")   # the real reply already has its features
        for case, candidate, facts in candidates:
            row = judge(case, threads[case["thread"]], candidate, facts, thresholds)
            problems += row.pop("problems")
            details.append(row)
    detail = pd.DataFrame(details)
    scores = score_table(detail)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    scores.to_csv(THREAD_SCORES_CSV, index=False)
    print_scores(scores)
    if args.show_misses:
        for variant in ("A", "B", "C"):
            missed = detail[(detail.variant == variant) & (~detail.n2)].head(8)
            print("\nMissed %s cases (N2 found nothing medium or high): %d of %d" % (variant, int(((detail.variant == variant) & (~detail.n2)).sum()), int((detail.variant == variant).sum())))
            for row in missed.to_dict("records"):
                print("  %s  N2 contradictions: %s  Phase 8: %s  flip %s" % (row["case_id"], row["n2_rules"] or "-", row["p8_rules"] or "-", row["flip"]))
    checks = make_checks(detail, wanted, scores, problems, splits, started, source)
    checks.to_csv(HIJACK_CHECKS_CSV, index=False)
    print("\nChecks (%s)" % relative(HIJACK_CHECKS_CSV))
    print(checks[checks["status"] != "info"].to_string(index=False))
    print("%d PASS, %d FAIL, %d info" % tuple(int((checks["status"] == s).sum()) for s in ("PASS", "FAIL", "info")))
    print("Saved %s and %s" % (relative(THREAD_SCORES_CSV), relative(HIJACK_CHECKS_CSV)))
    if (checks["status"] == "FAIL").any():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
