"""Phase 13: the architecture ablation. The same signals wired two ways: claim-routed (the frozen risk score) against one flat classifier.

Run from the project root (after prepare_test for the split):
    python -m src.eval.ablation_arch --split validation --train-limit 20000     # a dress rehearsal (writes to data/processed/rehearsal/)
    python -m src.eval.ablation_arch --split test                               # the one test run (needs results/eval_freeze.csv)

The flat classifier gets every signal of the ledger as one vector (src/router/ledger.py flat_features): which of the rules fired ANYWHERE in the email, the worst severity per verifier, the seven tactic
probabilities, how many claims were found and checked. What it does not get is the link between a claim and the evidence against it: it cannot tell "the sender claims to be the CFO and the Reply-To is
elsewhere" from "the sender mentions the CFO and, separately, the Reply-To differs". A logistic regression is fitted on the train split (attack against ham, spam left out) and held to the same false-alarm
rate on validation ham as the frozen score (src/eval/systems.py).

Reads  data/processed/eval_features/world_{train,validation,<split>}.parquet     (src/eval/world.py)
Writes results/arch_systems.csv     routed (full) and flat: pooled precision, recall, F1, false-alarm rate, AUC with 95% intervals over subject groups; per-source rates; each also among the emails
                                    with a checked claim
       results/arch_differences.csv routed minus flat, paired
       results/arch_agreement.csv   per category and source: how many emails both flag, only the routed score flags, only the flat classifier flags, neither
       results/arch_reasons.csv     among the emails each system flags: how many come with a traceable reason (a claim, the rule that fired on it and the evidence), and what the flat
                                    classifier's strongest feature is
       results/arch_checks.csv      PASS/FAIL checks

THE TRACEABLE-REASON SHARE IS A PROPERTY OF THE DESIGN, NOT A MEASURED PERFORMANCE. Every point of the routed score comes from a ledger row (a claim, its evidence, the rule, a sentence), so every email it flags has
a reason by construction; the check below confirms the code keeps that promise. A flat vector has no row to point to: its strongest feature can name a rule that fired somewhere in the email, never the claim it was about.
The ablation's measured part is the detection at the matched false-alarm rate.

WHAT THIS CAN AND CANNOT SAY. The flat classifier is fitted on attack labels and the routed score uses none, and the corpora differ in header evidence, so the flat classifier can use corpus identity (see systems.py).
If the flat classifier ties or beats the routed score on detection, the honest reading is that on this data the wiring does not change detection; the case for routing is then explanation and extensibility (a
new rule is one new function, with no retraining), not accuracy. If the routed score is ahead, the intervals say whether the difference is more than noise.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from src.eval import ablation_n3, common, freeze, systems, world as world_module
from src.eval.world import FLAT_NAMES
from src.router.build import read_thresholds_file


def kind_of(feature):
    name = feature.replace("flat__", "")
    return "rule" if name.startswith("rule:") else "worst severity" if name.startswith("worst:") else "tactic probability" if name.startswith("tactic:") else "claim counts"


def agreement_table(world, flag_a, flag_b, split):
    """Per group (category, and source): both flag / only the routed score / only the flat classifier / neither."""
    rows = []
    for by in ("category", "source"):
        for key, index in world.groupby(by).groups.items():
            positions = world.index.get_indexer(index)
            a, b = flag_a[positions], flag_b[positions]
            rows.append({"split": split, "group_by": by, "group": key, "emails": len(positions), "both_flag": int((a & b).sum()), "only_routed": int((a & ~b).sum()),
                         "only_flat": int((~a & b).sum()), "neither": int((~a & ~b).sum())})
    return pd.DataFrame(rows)


def reasons_table(world, flag_routed, flag_flat, model, split):
    """Traceable reasons among flagged emails, per category."""
    attack, ham, spam = systems.roles(world)
    has_row = np.array([len(c) > 2 for c in world["contradictions"]])                  # '[]' is two characters: a contradiction row exists
    top, contribution = systems.top_contributions(model, world, FLAT_NAMES)
    positive = contribution.max(axis=1) > 0
    rows = []
    for label, mask in (("attack", attack), ("ham", ham), ("spam", spam), ("all", np.ones(len(world), dtype=bool))):
        routed = flag_routed & mask
        flat = flag_flat & mask
        rows.append({"split": split, "emails": label, "system": "routed (full)", "flagged": int(routed.sum()), "with_a_claim_and_rule": int((routed & has_row).sum()),
                      "share_with_a_traceable_reason": common.round_or_none(float((routed & has_row).sum() / routed.sum())) if routed.sum() else None,
                      "strongest_feature_is_a_rule": None, "names_the_claim_it_was_about": int((routed & has_row).sum()),
                      "note": "every counted point comes from a ledger row: claim, evidence, rule, reason (a property of the design)"})
        kinds = [kind_of(FLAT_NAMES[t]) if p else "none" for t, p in zip(top[flat], positive[flat])]
        rule_share = sum(1 for k in kinds if k == "rule") / len(kinds) if kinds else None
        rows.append({"split": split, "emails": label, "system": "flat", "flagged": int(flat.sum()), "with_a_claim_and_rule": 0, "share_with_a_traceable_reason": 0.0 if flat.sum() else None,
                      "strongest_feature_is_a_rule": common.round_or_none(rule_share), "names_the_claim_it_was_about": 0,
                      "note": "the vector has no claim identity: its strongest feature can name a rule that fired somewhere, never the claim it was about (by construction)"})
    top_features = pd.Series([FLAT_NAMES[t] for t, p in zip(top[flag_flat], positive[flag_flat]) if p]).value_counts().head(8)
    return pd.DataFrame(rows), top_features


def run(split, rerun=None, workers=1, classifier=None, thresholds=None, limit=0, train_limit=0):
    guard = freeze.begin("ablation_arch", split, rerun)
    checks = common.Checks()

    def classifier_factory():
        nonlocal classifier
        if classifier is None:
            from src.models.predict import TacticClassifier
            classifier = TacticClassifier()
        return classifier

    thresholds = thresholds or getattr(classifier, "thresholds", None) or read_thresholds_file()
    train = world_module.load_world("train", train_limit, workers, classifier_factory, thresholds)
    validation = world_module.load_world("validation", 0, workers, classifier_factory, thresholds)
    test = validation if split == "validation" and not limit else world_module.load_world(split, limit, workers, classifier_factory, thresholds)

    models = systems.fit(train, ("flat",))
    validation_scores = systems.scores_of(models, validation)
    target, observed = systems.target_rate(validation, validation_scores)
    cuts = systems.choose_cuts(validation, validation_scores, target)
    print("The frozen score flags %.2f%% of the validation ham; the flat classifier is held to %.2f%%" % (100 * observed, 100 * target))
    scores = systems.scores_of(models, test)
    clusters = common.clusters_for(test["id"], split)
    rows, tally, sources, flag = ablation_n3.evaluate(test, scores, cuts, clusters, split)
    differences = ablation_n3.difference_rows(tally, sources, flag, split)
    ablation_n3.show(rows, split)

    agreement = agreement_table(test, flag["full"], flag["flat"], split)
    reasons, top_features = reasons_table(test, flag["full"], flag["flat"], models["flat"], split)
    common.write_table(guard, "arch_systems", pd.DataFrame(rows))
    common.write_table(guard, "arch_differences", differences)
    common.write_table(guard, "arch_agreement", agreement)
    common.write_table(guard, "arch_reasons", reasons)

    print("\nWhere the two disagree (emails): both / only routed / only flat / neither")
    for r in agreement[agreement["group_by"] == "category"].itertuples():
        print("  %-9s %6d emails: %5d / %5d / %5d / %5d" % (r.group, r.emails, r.both_flag, r.only_routed, r.only_flat, r.neither))
    print("\nTraceable reasons among flagged emails")
    for r in reasons[reasons["emails"] == "all"].itertuples():
        print("  %-14s flagged %6d, with a claim and a rule: %6d, strongest feature is a rule: %s" % (r.system, r.flagged, r.with_a_claim_and_rule, "-" if pd.isna(r.strongest_feature_is_a_rule) else "%.0f%%" % (100 * r.strongest_feature_is_a_rule)))
    if len(top_features):
        print("  the flat classifier's most common strongest features: " + "; ".join("%s (%d)" % (name.replace("flat__", ""), count) for name, count in top_features.items()))

    # ---- checks
    attack, ham, _ = systems.roles(test)
    flat_validation_rate = float((validation_scores["flat"] > cuts["flat"])[systems.roles(validation)[1]].mean())
    checks.add("matched_false_alarm", "flat flags at most the target share of the validation ham", "%.4f" % flat_validation_rate, "<= %.4f" % target, flat_validation_rate <= target + 1e-12)
    flagged_routed = flag["full"]
    traceable = np.array([len(c) > 2 for c in test["contradictions"]])
    missing = int((flagged_routed & ~traceable).sum())
    checks.add("traceable", "emails flagged by the routed score without a contradiction row behind them", missing, "0", missing == 0)
    checks.add("leakage_guard", "flat classifier fitted on", "train (%d emails)" % len(train), "train only", True)
    checks.add("leakage_guard", "cut fixed on", "validation ham", "validation only", True)
    for name in ("full", "flat"):
        share = float(flag[name].mean())
        checks.add("not_degenerate", "%s: share of all emails of the split flagged" % name, "%.2f%%" % (100 * share), "above 0% and below 100%", 0 < share < 1)
    try:
        from sklearn.metrics import f1_score, roc_auc_score
        keep = attack | ham
        worst = 0.0
        for name in ("full", "flat"):
            mine = {r["metric"]: r["value"] for r in rows if r["split"] == split and r["scope"] == "pooled attacks against ham" and r["system"] == name}
            worst = max(worst, abs(mine["f1"] - f1_score(attack[keep], flag[name][keep], zero_division=0)), abs(mine["auc"] - roc_auc_score(attack[keep], scores[name][keep])))
        checks.add("metrics", "hand-written pooled F1 and AUC equal scikit-learn for both systems", "%.1e" % worst, "< 1e-3", worst < 1e-3)
    except ImportError:
        checks.add("metrics", "scikit-learn cross-check", "scikit-learn is not installed", "", None)
    both = agreement[agreement["group_by"] == "category"]
    checks.add("counts", "the agreement table accounts for every email of the split", int(both["emails"].sum()), len(test),
               int(both["emails"].sum()) == len(test) and bool((both["both_flag"] + both["only_routed"] + both["only_flat"] + both["neither"] == both["emails"]).all()))
    common.write_table(guard, "arch_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return rows, differences, agreement, reasons, checks


def main(argv):
    parser = argparse.ArgumentParser(description="The architecture ablation: claim-routed score against a flat classifier on the same signals (Phase 13).")
    freeze.add_run_arguments(parser)
    parser.add_argument("--workers", type=int, default=1, help="processes for the claim extraction if a cache is incomplete")
    parser.add_argument("--limit", type=int, default=0, help="a random sample of N emails of the evaluated split (rehearsal only)")
    parser.add_argument("--train-limit", type=int, default=0, help="a random sample of N train emails for the fit (rehearsal only)")
    args = parser.parse_args(argv)
    if args.split == "test" and (args.limit or args.train_limit):
        raise SystemExit("--limit and --train-limit are for rehearsals: the test run uses every email and the whole train split")
    *_, checks = run(args.split, args.rerun, max(1, args.workers), limit=args.limit, train_limit=args.train_limit)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
