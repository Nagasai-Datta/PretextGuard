"""Phase 13: the N2 ablation. Does thread consistency verification catch hijacks that the claim-and-header verifiers (N3) miss?

Run from the project root (after prepare_test for the split):
    python -m src.eval.ablation_n2 --split validation     # a dress rehearsal (writes to data/processed/rehearsal/)
    python -m src.eval.ablation_n2 --split test           # the one test run (needs results/eval_freeze.csv)

Reads  data/processed/threads.parquet, thread_features/     the real threads of the split (Enron and Apache) and their cached features
       data/threads/cases.csv, injections.csv               the hijack benchmark of Phase 9: five cases per base thread (neg_real, neg_synth, A takeover, B look-alike swap, C forged)
Writes results/n2_scores.csv            per source and variant: detection with the thread verifier (N2), with the Phase 8 verifiers alone, with either; the gain of N2; which signal caught the case;
                                        the share of cases where the scan flips at exactly the injected message (hijack-index accuracy); false alarms on the real next reply. Rates come
                                        with 95% bootstrap intervals over THREADS; fewer than 10 cases is a count only
       results/n2_score_benchmark.csv   the same cases scored by the frozen risk score with the thread verifier inside it and without it: share reaching Suspicious or High risk
       results/n2_false_alarms.csv      the thread verifier on every message with a past of the REAL, unmodified threads: how often it raises a medium or high contradiction (every one is a false
                                        alarm), per source and per rule, with intervals over threads
       results/n2_checks.csv            PASS/FAIL checks

How to read it. A hijack case is detected when a verifier raises a medium or high contradiction on the candidate message. The Phase 8 verifiers (header and request) look at one message alone, so they see the
same genuine headers whether the real person or a hijacker wrote it. The thread verifier compares the message with the real messages before it: the content signals (tactic onset, request drift) on Enron,
all four signals (plus sending path and thread integrity) on Apache. The gain of N2 is the share of hijacks that N2 finds and Phase 8 does not.

WHAT THIS CAN AND CANNOT SAY. The base threads are real; the injected messages and their headers are synthetic and written by rule (src/data/hijack_benchmark.py), so a detection rate says that the rules do
what they are defined to do against this construction, not how often real attackers behave this way. Variant A copies the real sender's server, mail program and IDs on purpose and is caught only by
content; raw Enron has no sending-path data or reply IDs, so Enron tests the content signals and the quote check only. A hijacker with mailbox access who copies the style and keeps the tone calm cannot
be caught by these signals. The rules were frozen in Phase 9 and the score in Phase 10; this run scores the test cases once and changes nothing.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from src.data import paths
from src.data.hijack_benchmark import LABEL, candidate_message
from src.eval import common, freeze
from src.eval.stats import Resampler, cluster_matrix, ratio, wilson
from src.models.dataset import MAIN_TACTICS
from src.router.build import benchmark_detail, benchmark_table, load_real_threads, read_thresholds_file
from src.router.score import DEFAULT_CONFIG
from src.thread.evaluate import FLAG, group_of, judge, score_table
from src.thread.features import attach_features
from src.thread.selftest import self_test as thread_self_test
from src.verifiers.thread_verifier import THREAD_RULES_VERSION, verify_thread_message
from src.verifiers.verify import RULES_VERSION


def false_alarm_tables(threads, thresholds, split):
    """(summary per source, per rule) of medium or high contradictions on messages with a past in real threads."""
    records = []
    for tid, messages in threads.items():
        for i in range(1, len(messages)):
            rows = verify_thread_message(messages, i, thresholds)
            fired = sorted({r["rule"] for r in rows if r["contradiction"] and r["severity"] in FLAG})
            records.append({"thread": tid, "source": messages[i]["source"], "flagged": bool(fired), "rules": fired})
    frame = pd.DataFrame(records, columns=["thread", "source", "flagged", "rules"])
    summary, per_rule = [], []
    for source, part in frame.groupby("source"):
        ids, matrix = cluster_matrix(part["thread"], [part["flagged"].astype(float), np.ones(len(part))])
        point, low, high = Resampler(len(ids)).interval(matrix, lambda t: ratio(t[..., 0], t[..., 1]))
        w_low, w_high = wilson(int(part["flagged"].sum()), len(part))
        summary.append({"split": split, "source": source, "threads": part["thread"].nunique(), "messages_with_a_past": len(part), "flagged": int(part["flagged"].sum()),
                        "rate": common.round_or_none(point), "ci_low": common.round_or_none(low), "ci_high": common.round_or_none(high),
                        "wilson_low": common.round_or_none(w_low), "wilson_high": common.round_or_none(w_high),
                        "note": "every medium or high contradiction on a real, unmodified thread is a false alarm; the interval draws whole threads"})
        counts = {}
        for rules in part["rules"]:
            for rule in rules:
                counts[rule] = counts.get(rule, 0) + 1
        for rule, hits in sorted(counts.items(), key=lambda kv: -kv[1]):
            per_rule.append({"split": split, "source": source, "rule": rule, "signal": group_of(rule), "messages_flagged": hits, "messages_with_a_past": len(part),
                             "rate": round(hits / len(part), 4)})
    return pd.DataFrame(summary), pd.DataFrame(per_rule, columns=["split", "source", "rule", "signal", "messages_flagged", "messages_with_a_past", "rate"])


def run(split, rerun=None, classifier=None, featurize=attach_features, thresholds=None):
    guard = freeze.begin("ablation_n2", split, rerun)
    checks = common.Checks()
    thresholds = thresholds or getattr(classifier, "thresholds", None) or read_thresholds_file()
    main_thresholds = {t: thresholds[t] for t in MAIN_TACTICS}           # the four tactics the Phase 9 evaluation read (src/thread/features.py load_thresholds)
    threads = load_real_threads(split, featurize)
    cases = pd.read_csv(paths.HIJACK_CASES_CSV)
    cases = cases[(cases["split"] == split) & cases["thread"].isin(set(threads))].reset_index(drop=True)
    injections = pd.read_csv(paths.HIJACK_INJECTIONS_CSV).set_index("thread").to_dict("index")
    print("%d cases of %d base threads in the %s split" % (len(cases), cases["thread"].nunique(), split))

    # ---- the verifier-level judgement (Phase 9): N2, Phase 8, either; the scan; which signals
    candidates = []
    for case in cases.to_dict("records"):
        candidate, facts = candidate_message(case["variant"], threads[case["thread"]], int(case["index"]), injections[case["thread"]])
        candidates.append((case, candidate, facts))
    featurize([c for case, c, _ in candidates if case["variant"] != "neg_real"], "hijack")
    details, problems = [], 0
    for case, candidate, facts in candidates:
        row = judge(case, threads[case["thread"]], candidate, facts, main_thresholds)
        problems += row.pop("problems")
        details.append(row)
    detail = pd.DataFrame(details)
    scores = score_table(detail)
    common.write_table(guard, "n2_scores", scores)

    # ---- the score-level judgement (Phase 10): the frozen risk score with and without the thread verifier in it
    score_detail = benchmark_detail(cases, threads, injections, thresholds, DEFAULT_CONFIG, featurize)
    benchmark = benchmark_table(score_detail)
    common.write_table(guard, "n2_score_benchmark", benchmark)

    # ---- false alarms on real, unmodified threads
    summary, per_rule = false_alarm_tables(threads, main_thresholds, split)
    common.write_table(guard, "n2_false_alarms", pd.concat([summary.assign(level="summary"), per_rule.assign(level="rule")], ignore_index=True))

    # ---- print
    print("\nVerifier level (medium or high contradiction). Rate [95%% interval over threads] (hits/n)")
    show = scores[scores["variant"].isin(["A", "B", "C", "attacks (A+B+C)", "neg_real"]) & scores["metric"].isin(
        ["detect_n2", "detect_phase8", "detect_either", "gain_n2_over_phase8", "flip_exact", "flip_early", "false_alarm_n2", "false_alarm_phase8"])]
    for (source, variant), part in show.groupby(["source", "variant"]):
        cells = ["%s %s" % (r.metric, ("%.1f%% [%.1f, %.1f] (%d/%d)" % (100 * r.rate, 100 * r.ci_low, 100 * r.ci_high, r.hits, r.n)) if pd.notna(r.rate) else "count %d/%d" % (r.hits, r.n))
                 for r in part.itertuples()]
        print("  %-7s %-16s %s" % (source, variant, "; ".join(cells)))
    print("\nScore level: Suspicious or above / High risk, with the thread verifier in the score and without it")
    for (source, variant), part in benchmark[benchmark["variant"].isin(["A", "B", "C", "neg_real"])].groupby(["source", "variant"]):
        cells = {r.metric: ("%.0f%%" % (100 * r.rate) if pd.notna(r.rate) else "count %d/%d" % (r.hits, r.n)) for r in part.itertuples()}
        print("  %-7s %-9s n=%-3d with: %s / %s   without: %s / %s" % (source, variant, part["n"].iloc[0], cells["suspicious_or_high_full"], cells["high_full"],
                                                                  cells["suspicious_or_high_phase8"], cells["high_phase8"]))
    print("\nFalse alarms of the thread verifier on messages with a past of real threads")
    for r in summary.itertuples():
        print("  %-7s %5d messages in %4d threads: %5.2f%% flagged [%.2f, %.2f]" % (r.source, r.messages_with_a_past, r.threads, 100 * r.rate, 100 * r.ci_low, 100 * r.ci_high))

    # ---- checks
    passed, total = thread_self_test(verbose=False)
    checks.add("selftest", "thread self-test", "%s of %d" % ("all" if passed else "NOT all", total), "all pass", passed)
    checks.add("rows_valid", "thread-verifier rows that fail check_row", problems, "0", problems == 0)
    checks.add("counts", "cases scored equal the cases of the split in data/threads/cases.csv", len(detail), len(cases), len(detail) == len(cases) == len(score_detail))
    spread = pd.read_csv(paths.HIJACK_CASES_CSV).groupby("thread")["split"].nunique()
    checks.add("leakage_guard", "threads in more than one split", int((spread > 1).sum()), "0", bool((spread == 1).all()))
    checks.add("leakage_guard", "split scored", ",".join(sorted(set(cases["split"]))), split, set(cases["split"]) == {split})
    wrong = [c for c in cases.to_dict("records") if int(c["label"]) != LABEL[c["variant"]]]
    checks.add("labels", "cases whose label does not fit their variant", len(wrong), "0", not wrong)
    per_thread = cases.groupby("thread")["variant"].apply(set)
    missing = [t for t, v in per_thread.items() if not {"neg_real", "neg_synth", "A", "C"} <= v]
    checks.add("structure", "threads missing one of neg_real, neg_synth, A, C", len(missing), "0", not missing)
    for variant, forbidden in (("A", {"path", "integrity"}), ("B", {"integrity"}), ("C", {"path"}), ("neg_synth", {"path", "integrity"})):
        sub = detail[detail["variant"] == variant]
        broken = sum(1 for g in sub["groups"] if forbidden & set(g))
        checks.add("isolation", "variant %s cases where a %s signal fires (the injection copies those details)" % (variant, "/".join(sorted(forbidden))), broken, "0", broken == 0)
    for r in summary.itertuples():
        checks.add("false_alarms", "%s: real messages with a past flagged by the thread verifier" % r.source, "%.2f%%" % (100 * r.rate), "reported (a finding if high)", None)
    checks.add("run", "thread rules version / header and request rules version", "%s / %s" % (THREAD_RULES_VERSION, RULES_VERSION), "", None)
    checks.add("run", "thresholds of the four main tactics", ", ".join("%s %.2f" % kv for kv in main_thresholds.items()), "", None)
    common.write_table(guard, "n2_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return scores, benchmark, summary, checks


def main(argv):
    parser = argparse.ArgumentParser(description="The N2 ablation on the hijack benchmark (Phase 13).")
    freeze.add_run_arguments(parser)
    args = parser.parse_args(argv)
    *_, checks = run(args.split, args.rerun)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
