"""Phase 13: the frozen risk score (version 0.2) on the test split, once: where the emails land, and the false-alarm budget, which the test split measures cleanly.

Run from the project root:
    python -m src.eval.score_test --split validation     # a dress rehearsal (writes to data/processed/rehearsal/)
    python -m src.eval.score_test --split test           # the one test run (needs results/eval_freeze.csv)

Reads  data/processed/eval_features/world_<split>.parquet     the full system's answer for every email (built once from the claims, probabilities and verifiers; src/eval/world.py)
       data/processed/threads.parquet, thread_features/        the real, unmodified threads of the split and their cached features
       results/score_budget.csv, score_distribution.csv        the Phase 10 validation figures, printed beside the test figures
Writes results/score_test_distribution.csv    emails per band, per category, source and source+category, with BOTH denominators (all emails; emails with a checked claim)
       results/score_test_budget.csv          the false-alarm budget per source of legitimate mail (ham) and of real thread messages, with Wilson 95% intervals, and the validation figures
       results/score_test_checks.csv          PASS/FAIL checks

What this measures. The score numbers (high 60, medium 35, low 5, pressure 0.25, bands at 35 and 70, the reliability factors) were frozen in Phase 10 after calibration on validation against a
false-alarm budget declared before validation was read: High risk for at most 1% and Suspicious or above for at most 5% of the CHECKED legitimate emails (ham) of each source and of the real thread
messages of each source with at least 20 checked. Phase 10 corrected its definition of legitimate mail (ham only, not spam) after the validation emails had been read, so its validation figures are a check
and THIS run is the clean measurement. A group over the budget is a finding, reported as it is (Phase 10 already found one: the Enron thread messages, because of the quote check tv_quote_mismatch).

What it cannot say. Nobody labelled which emails contain a contradicted claim, so there is no precision or recall of the score here. Attacks and legitimate mail come from different corpora with different
header evidence (the Kaggle Enron and Ling emails carry none), so the share of each category in each band is a DESCRIPTION, reported per source and with both denominators; the detection comparison of the
N3 ablation (ablation_n3.py) holds every system to the same false-alarm rate instead.
"""

import argparse
import sys

import pandas as pd

from src.data import paths
from src.eval import common, freeze, world as world_module
from src.router.build import budget_rows, config_table, distribution_table, load_real_threads, read_thresholds_file, scored, thread_units
from src.router.score import DEFAULT_CONFIG, SCORE_VERSION
from src.thread.features import attach_features


def compare_with_validation(budget):
    """Add the Phase 10 validation figures to the test budget table (same kind and group), when results/score_budget.csv has them."""
    path = paths.RESULTS_DIR / "score_budget.csv"
    budget = budget.copy()
    for column in ("validation_checked_n", "validation_suspicious_or_high_pct", "validation_high_pct"):
        budget[column] = None
    if path.exists():
        old = pd.read_csv(path)
        old = old[old["split"] == "validation"].set_index(["kind", "group"])
        for i, r in budget.iterrows():
            key = (r["kind"], r["group"])
            if key in old.index:
                budget.loc[i, "validation_checked_n"] = old.loc[key, "checked_n"]
                budget.loc[i, "validation_suspicious_or_high_pct"] = old.loc[key, "suspicious_or_high_pct"]
                budget.loc[i, "validation_high_pct"] = old.loc[key, "high_pct"]
    return budget


def run(split, rerun=None, workers=1, classifier=None, featurize=attach_features, thresholds=None, limit=0):
    guard = freeze.begin("score_test", split, rerun)
    checks = common.Checks()

    def classifier_factory():
        nonlocal classifier
        if classifier is None:
            from src.models.predict import TacticClassifier
            classifier = TacticClassifier()
        return classifier

    thresholds = thresholds or getattr(classifier, "thresholds", None) or read_thresholds_file()
    config = DEFAULT_CONFIG
    world = world_module.load_world(split, limit, workers, classifier_factory, thresholds)
    units = scored(world_module.units_from(world, split), config)
    threads = load_real_threads(split, featurize)
    thread_part = thread_units(threads, thresholds, split)
    distribution = distribution_table(units, config, split)
    budget = compare_with_validation(budget_rows(units + thread_part, config, split))
    common.write_table(guard, "score_test_distribution", distribution)
    common.write_table(guard, "score_test_budget", budget)

    # ---- print
    print("\nRisk score %s on the %s split: Suspicious or above / High risk, among all emails and among emails with a checked claim" % (SCORE_VERSION, split))
    show = distribution[distribution["group_by"].isin(["category", "source"])]
    for r in show.itertuples():
        print("  %-9s %-24s emails %6d  suspicious+ %5s%% high %5s%%   | checked %5d  suspicious+ %5s%% high %5s%%" % (
            r.group_by, r.group, r.emails, "-" if pd.isna(r.suspicious_or_high_pct) else "%.2f" % r.suspicious_or_high_pct, "-" if pd.isna(r.high_pct) else "%.2f" % r.high_pct,
            r.checked_emails, "-" if pd.isna(r.checked_suspicious_or_high_pct) else "%.2f" % r.checked_suspicious_or_high_pct, "-" if pd.isna(r.checked_high_pct) else "%.2f" % r.checked_high_pct))
    print("\nFalse-alarm budget on checked legitimate mail (ham) and real thread messages, with the validation figure of Phase 10 beside it:")
    for r in budget.itertuples():
        print("  %-10s %-24s checked %5d  suspicious+ %6s%%  high %6s%%  %-34s validation suspicious+ %s%%  %s" % (
            r.kind, r.group, r.checked_n, "-" if pd.isna(r.suspicious_or_high_pct) else "%.2f" % r.suspicious_or_high_pct, "-" if pd.isna(r.high_pct) else "%.2f" % r.high_pct, r.budget,
            "-" if pd.isna(r.validation_suspicious_or_high_pct) else "%.2f" % r.validation_suspicious_or_high_pct, r.budget_note))

    # ---- checks
    allrow = distribution[distribution["group_by"] == "all"].iloc[0]
    checks.add("counts", "every email of the split is in the distribution once", "%d / %d" % (allrow["emails"], len(world)), "equal",
               int(allrow["emails"]) == len(world) and int(allrow["low"] + allrow["suspicious"] + allrow["high"]) == len(world))
    checks.add("counts", "emails with a checked claim never exceed all emails", int(allrow["checked_emails"]), "<= %d" % len(world), int(allrow["checked_emails"]) <= len(world))
    sizes = pd.read_csv(paths.SPLIT_COUNTS_CSV)
    expected = int(sizes[split].sum()) if split in sizes.columns else None
    checks.add("leakage_guard", "emails scored equal the %s column of results/split_counts.csv" % split, len(world), expected, expected is None or limit > 0 or len(world) == expected)
    config_path = paths.RESULTS_DIR / "score_config.csv"
    if config_path.exists():
        frozen = pd.read_csv(config_path)
        now = config_table(config)
        frozen_map, now_map = dict(zip(frozen["setting"], frozen["value"].astype(str))), dict(zip(now["setting"], now["value"].astype(str)))
        differ = [k for k in now_map if k in frozen_map and frozen_map[k] != now_map[k]]
        checks.add("frozen_numbers", "the score numbers equal results/score_config.csv", "equal" if not differ else "different: " + ", ".join(differ), "equal", not differ)
    checks.add("frozen_numbers", "score version", SCORE_VERSION, "", None)
    over = budget[budget["budget"] == "OVER"]
    for r in over.itertuples():
        checks.add("budget", "OVER (a finding, not a failure): %s %s" % (r.kind, r.group), "%s; %s" % (r.suspicious_or_high_pct, r.budget_note), "within the budget", None)
    passed = budget[budget["budget"] == "PASS"]
    checks.add("budget", "groups judged / within the budget / over", "%d / %d / %d" % (len(passed) + len(over), len(passed), len(over)), "", None)
    spam = budget[budget["kind"] == "email_spam"]
    checks.add("budget", "spam is listed for information and never judged", "%d groups" % len(spam), "budget column says info", all(str(b).startswith("info") for b in spam["budget"]))
    common.write_table(guard, "score_test_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return distribution, budget, checks


def main(argv):
    parser = argparse.ArgumentParser(description="The frozen risk score on the test split (Phase 13).")
    freeze.add_run_arguments(parser)
    parser.add_argument("--workers", type=int, default=1, help="processes for the claim extraction if the cache is incomplete")
    parser.add_argument("--limit", type=int, default=0, help="a random sample of N emails (rehearsal only)")
    args = parser.parse_args(argv)
    if args.limit and args.split == "test":
        raise SystemExit("--limit is for rehearsals: the test run scores every email")
    _, _, checks = run(args.split, args.rerun, max(1, args.workers), limit=args.limit)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
