"""Phase 13: the N3 ablation. Does checking each claim against the evidence for THAT claim beat the simpler ways of using the same information?

Run from the project root (after prepare_test for the split, and with the train and validation per-email tables built, which the first run does):
    python -m src.eval.ablation_n3 --split validation --train-limit 20000     # a dress rehearsal (writes to data/processed/rehearsal/)
    python -m src.eval.ablation_n3 --split test                               # the one test run (needs results/eval_freeze.csv)

Systems (src/eval/systems.py): full (the frozen claim-routed score), text only, headers only, parallel fusion of the two (BEC-Guard style) and, in the architecture ablation, a flat classifier.
All learned systems are fitted on the train split, and every learned system is held to the SAME false-alarm rate on validation ham as the frozen score (src/eval/stats.py matched_cut), so a
system cannot win by flagging more mail. The cuts are fixed on validation and applied once to the test split.

Reads  data/processed/eval_features/world_{train,validation,<split>}.parquet     the per-email answers of every system's inputs (src/eval/world.py)
       data/synthetic/synthetic.csv                                              the synthetic attack/twin pairs of the split, for the synthetic BEC arm (reported apart)
Writes results/n3_systems.csv       per system and scope: precision, recall, F1, false-alarm rate and AUC pooled over attacks against ham (with 95% intervals over subject groups), and per source
                                    the detection rate (attack sources), the false-alarm rate (ham sources) and the flag rate (spam sources); each also among the emails with a checked claim
       results/n3_differences.csv   the full system minus each other system, paired: F1, recall, false-alarm rate, and per source
       results/n3_cuts.csv          each system's cut, the false-alarm rate it was held to, and what it flags on validation and on this split
       results/n3_synthetic_bec.csv synthetic colleague-impersonation emails with CLEARLY SYNTHETIC header blocks written for this ablation, and their benign twins from the organisation's own domain
       results/n3_checks.csv        PASS/FAIL checks

How to read it. Pooled F1 mixes two things, corpus and detection, because no source holds both attacks (Nazario, phishing_pot, Nigerian Fraud) and ordinary mail (Apache, CEAS, Enron, Ling,
SpamAssassin). The per-source rates are the fair reading: the detection rate of each attack source and the false-alarm rate of each ham source, side by side for each system. The 'checked claim'
scope keeps only the emails where the full system had a claim it could check: the part of the data where claim-conditioned verification can say anything at all.

WHAT THIS CAN AND CANNOT SAY. The learned systems see attack labels and the frozen score does not; the headers-only system can partly learn which corpus an email came from. Both favour the learned
systems, so a tie is not a defeat for the frozen score and a win for the frozen score is not a margin to trust blindly: the intervals say how far a difference is from noise. The synthetic arm uses text
written by one language model and header blocks written by rule; it shows what each system does when the sender is a free mailbox or a look-alike domain claiming to be a colleague, and says nothing
about how common that is. The claims come from a rule-based extractor scored against LLM labels from one model family.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from src.eval import common, freeze, systems, world as world_module
from src.data import paths
from src.eval.stats import Tally, auc_interval, f1_counts, ratio
from src.router.build import read_thresholds_file

SYNTHETIC_ORG = "example.com"
SYNTHETIC_LOOKALIKE = "examp1e.com"
NAMES = ["Daniel Reed", "Sophie Turner", "Marcus Hale", "Priya Nair", "Tom Becker", "Elena Rossi", "Hugo Lang", "Aisha Khan", "Oliver Grant", "Mei Chen"]


# ---------------------------------------------------------------------------------------------------------------------
# The evaluation of a set of systems on one world table
# ---------------------------------------------------------------------------------------------------------------------

def build_tally(world, flag, clusters):
    """A Tally with, for every system, the pooled outcomes (attack against ham), the same among emails with a checked claim, and per-source counts."""
    attack, ham, _ = systems.roles(world)
    checked = world["checked"].to_numpy(dtype=bool)
    source = world["source"].to_numpy()
    tally = Tally(clusters)
    for name, f in flag.items():
        for scope, mask in (("", np.ones(len(world), dtype=bool)), ("c", checked)):
            tally.add("tp%s_%s" % (scope, name), attack & f & mask)
            tally.add("fp%s_%s" % (scope, name), ham & f & mask)
            tally.add("fn%s_%s" % (scope, name), attack & ~f & mask)
            tally.add("tn%s_%s" % (scope, name), ham & ~f & mask)
    for k, s in enumerate(sorted(set(source))):
        in_source = source == s
        tally.add("n_%d" % k, in_source)
        tally.add("nc_%d" % k, in_source & checked)
        for name, f in flag.items():
            tally.add("f_%s_%d" % (name, k), f & in_source)
            tally.add("fc_%s_%d" % (name, k), f & in_source & checked)
    return tally, sorted(set(source))


def pooled_functions(name, scope):
    """{metric: function of a Tally view} for one system; scope '' (all emails) or 'c' (emails with a checked claim)."""
    tp, fp, fn, tn = ("%s%s_%s" % (x, scope, name) for x in ("tp", "fp", "fn", "tn"))
    return {"precision": lambda v: ratio(v[tp], v[tp] + v[fp]), "recall": lambda v: ratio(v[tp], v[tp] + v[fn]), "f1": lambda v: f1_counts(v[tp], v[fp], v[fn]),
            "false_alarm_rate": lambda v: ratio(v[fp], v[fp] + v[tn])}


def evaluate(world, scores, cuts, clusters, split, with_auc=True):
    """(rows for n3_systems.csv, the tally, the source names)."""
    flag = systems.flags(scores, cuts)
    tally, sources = build_tally(world, flag, clusters)
    attack, ham, spam = systems.roles(world)
    category_of = {s: world.loc[world["source"] == s, "category"].iloc[0] for s in sources}
    kind_of = {"phishing": "detection_rate", "fraud": "detection_rate", "ham": "false_alarm_rate", "spam": "spam_flag_rate"}
    rows = []
    for name in [n for n in systems.ORDER if n in flag]:
        for scope, label in (("", "pooled attacks against ham"), ("c", "pooled, emails with a checked claim")):
            for metric, fn in pooled_functions(name, scope).items():
                point, low, high = tally.interval(fn)
                n_pos = int(tally.point(lambda v: v["tp%s_%s" % (scope, name)] + v["fn%s_%s" % (scope, name)])) if metric in ("precision", "recall", "f1") else \
                    int(tally.point(lambda v: v["fp%s_%s" % (scope, name)] + v["tn%s_%s" % (scope, name)]))
                rows.append({"split": split, "scope": label, "system": name, "metric": metric, **common.interval_cells("value", (point, low, high)), "n": n_pos,
                             "hits": None, "cut": cuts[name],
                             "note": "n counts the attacks (precision, recall, F1) or the ham emails (false-alarm rate)"})
        if with_auc:
            keep = attack | ham
            point, low, high = auc_interval(scores[name][keep], attack[keep], np.asarray(clusters)[keep])
            rows.append({"split": split, "scope": "pooled attacks against ham", "system": name, "metric": "auc", **common.interval_cells("value", (point, low, high)), "n": int(keep.sum()),
                         "hits": None, "cut": cuts[name], "note": "threshold-free: the chance a random attack scores above a random legitimate email"})
        for k, s in enumerate(sources):
            for scope, label in (("", "source"), ("c", "source, emails with a checked claim")):
                prefix = "f" if scope == "" else "fc"
                denominator = "n_%d" % k if scope == "" else "nc_%d" % k
                n = int(tally.point(lambda v: v[denominator]))
                hits = int(tally.point(lambda v: v["%s_%s_%d" % (prefix, name, k)]))
                if n >= common.MIN_POSITIVES:
                    point, low, high = tally.interval(lambda v: ratio(v["%s_%s_%d" % (prefix, name, k)], v[denominator]))
                else:
                    point = low = high = None
                rows.append({"split": split, "scope": "%s: %s (%s)" % (label, s, category_of[s]), "system": name, "metric": kind_of[category_of[s]],
                             **common.interval_cells("value", (point, low, high)), "n": n, "hits": hits, "cut": cuts[name],
                             "note": "" if n >= common.MIN_POSITIVES else "fewer than %d items: count only" % common.MIN_POSITIVES})
    return rows, tally, sources, flag


def difference_rows(tally, sources, flag, split):
    """Paired differences: the full system minus every other system."""
    rows = []
    others = [n for n in systems.ORDER if n in flag and n != "full"]
    for other in others:
        for scope, label in (("", "pooled attacks against ham"), ("c", "pooled, emails with a checked claim")):
            a, b = pooled_functions("full", scope), pooled_functions(other, scope)
            for metric in ("f1", "recall", "false_alarm_rate"):
                point, low, high = tally.interval(lambda v, a=a, b=b, metric=metric: a[metric](v) - b[metric](v))
                rows.append({"split": split, "scope": label, "system_a": "full", "system_b": other, "metric": metric + " (full minus other)", **common.interval_cells("difference", (point, low, high))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------------
# The synthetic BEC arm
# ---------------------------------------------------------------------------------------------------------------------

def authentication(domain):
    return "Authentication-Results: mx.%s; spf=pass smtp.mailfrom=%s; dkim=pass header.d=%s; dmarc=pass header.from=%s\n" % (SYNTHETIC_ORG, domain, domain, domain)


def synthetic_header_block(index, role, subject):
    """A CLEARLY SYNTHETIC header block. Attacks come from a free mailbox (even pairs) or from a look-alike domain the attacker controls and that passes its own authentication (odd pairs);
    every third attack also has a Reply-To to another free mailbox. The benign twin comes from the organisation's own domain with authentication that passes."""
    name = NAMES[index % len(NAMES)]
    local = name.lower().replace(" ", ".")
    lines = ["To: Maria Lopez <maria@%s>" % SYNTHETIC_ORG, "Subject: %s" % subject, "Date: Mon, 05 Oct 2026 09:%02d:00 +0000" % (index % 60),
             "Message-ID: <synthetic-bec-%d-%s@%s>" % (index, role, SYNTHETIC_ORG)]
    if role == "attack":
        if index % 2 == 0:
            lines.insert(0, "From: %s <%s.finance@gmail.com>" % (name, local))
            auth = authentication("gmail.com")
        else:
            lines.insert(0, "From: %s <%s@%s>" % (name, local, SYNTHETIC_LOOKALIKE))
            auth = authentication(SYNTHETIC_LOOKALIKE)
        if index % 3 == 0:
            lines.append("Reply-To: %s.private@protonmail.com" % local)
    else:
        lines.insert(0, "From: %s <%s@%s>" % (name, local, SYNTHETIC_ORG))
        auth = authentication(SYNTHETIC_ORG)
    return "\n".join(lines) + "\n" + auth


def synthetic_table(split):
    """A table in the shape of verifiers.build.load_split for the synthetic emails of the split, with header evidence computed by the frozen Phase 3 code."""
    from src.headers.build import process

    synthetic = pd.read_csv(paths.SYNTHETIC_CSV, dtype={"id": str})
    synthetic = synthetic[synthetic["split"] == split].sort_values("id").reset_index(drop=True)
    order = {pair: k for k, pair in enumerate(sorted(set(synthetic["pair"])))}
    blocks = [synthetic_header_block(order[p], r, s) for p, r, s in zip(synthetic["pair"], synthetic["role"], synthetic["subject"])]
    headers = process(pd.DataFrame({"id": synthetic["id"], "raw_headers": blocks}))
    from src.verifiers.build import FACT_COLUMNS

    table = pd.DataFrame({"id": synthetic["id"], "source": "synthetic_bec", "category": ["bec_" + r for r in synthetic["role"]], "split": split, "body_redacted": synthetic["body_redacted"],
                          "signature": "", "contact": ""})
    table = table.merge(headers[["id"] + FACT_COLUMNS], on="id", how="left")
    return table, synthetic


def synthetic_arm(split, models, cuts, classifier_factory, thresholds, workers):
    table, synthetic = synthetic_table(split)
    world = world_module.build_from_table(table, "synthetic_bec_" + split, classifier_factory, thresholds, workers=workers)
    scores = systems.scores_of(models, world)
    flag = systems.flags(scores, cuts)
    is_attack = (synthetic["role"] == "attack").to_numpy()
    tally = Tally(synthetic["pair"].to_numpy())
    for name, f in flag.items():
        tally.add("a_" + name, f & is_attack)
        tally.add("b_" + name, f & ~is_attack)
    tally.add("n_attack", is_attack)
    tally.add("n_benign", ~is_attack)
    rows = []
    for name in [n for n in systems.ORDER if n in flag]:
        for role, key, denominator in (("attack", "a_", "n_attack"), ("benign twin", "b_", "n_benign")):
            point, low, high = tally.interval(lambda v, name=name, key=key, denominator=denominator: ratio(v[key + name], v[denominator]))
            n, hits = int(tally.point(lambda v: v[denominator])), int(tally.point(lambda v: v[key + name]))
            rows.append({"split": split, "system": name, "role": role, "metric": "detection_rate" if role == "attack" else "false_alarm_rate", "n": n, "hits": hits,
                         **common.interval_cells("rate", (point, low, high) if n >= common.MIN_POSITIVES else (None, None, None)),
                         "note": "synthetic text and synthetic headers written for this ablation; pairs are the bootstrap clusters" + ("" if n >= common.MIN_POSITIVES else "; count only")})
        diff_point, low, high = tally.interval(lambda v, name=name: ratio(v["a_" + name], v["n_attack"]) - ratio(v["b_" + name], v["n_benign"]))
        rows.append({"split": split, "system": name, "role": "attack minus twin", "metric": "flag rate difference", "n": int(is_attack.sum()), "hits": None,
                     **common.interval_cells("rate", (diff_point, low, high)), "note": "detection rate minus false-alarm rate on the paired twins"})
    return pd.DataFrame(rows), world


# ---------------------------------------------------------------------------------------------------------------------

def show(rows, split):
    table = pd.DataFrame(rows)
    print("\nPooled attacks against ham (%s split; %s). Value [95%% interval over subject groups]" % (split, common.LABEL_NOTE))
    print("%-9s %-34s %-28s %-28s %-28s %-24s %-24s" % ("system", "", "F1", "recall", "false-alarm rate", "precision", "AUC"))
    for name in systems.ORDER:
        part = table[(table["system"] == name)]
        if part.empty:
            continue

        def cell(metric, scope="pooled attacks against ham", percent=False):
            r = part[(part["scope"] == scope) & (part["metric"] == metric)]
            if r.empty or pd.isna(r["value"].iloc[0]):
                return "-"
            r = r.iloc[0]
            return ("%.1f%% [%.1f, %.1f]" % (100 * r["value"], 100 * r["value_ci_low"], 100 * r["value_ci_high"])) if percent else "%.3f [%.3f, %.3f]" % (r["value"], r["value_ci_low"], r["value_ci_high"])
        print("%-9s %-34s %-28s %-28s %-28s %-24s %-24s" % (name, systems.DESCRIPTION[name][:34], cell("f1"), cell("recall", percent=True), cell("false_alarm_rate", percent=True), cell("precision"), cell("auc")))
    sources = table[table["scope"].str.startswith("source: ")]
    print("\nPer source: detection rate (attack sources), false-alarm rate (ham sources), flag rate (spam sources)")
    names = [n for n in systems.ORDER if n in set(sources["system"])]
    print("%-52s %s" % ("source", "  ".join("%-9s" % n for n in names)))
    for scope in dict.fromkeys(sources["scope"]):
        cells = []
        for n in names:
            r = sources[(sources["scope"] == scope) & (sources["system"] == n)].iloc[0]
            cells.append("%-9s" % ("n=%d/%d" % (r["hits"], r["n"]) if pd.isna(r["value"]) else "%.1f%%" % (100 * r["value"])))
        print("%-52s %s" % (scope.replace("source: ", ""), "  ".join(cells)))


def run(split, rerun=None, workers=1, classifier=None, thresholds=None, limit=0, train_limit=0, featurize=None):
    guard = freeze.begin("ablation_n3", split, rerun)
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

    models = systems.fit(train, systems.LEARNED)
    validation_scores = systems.scores_of(models, validation)
    target, observed = systems.target_rate(validation, validation_scores)
    cuts = systems.choose_cuts(validation, validation_scores, target)
    print("The frozen score flags %.2f%% of the validation ham; every learned system is held to %.2f%% (floor %.1f%%)" % (100 * observed, 100 * target, 100 * common.MATCHED_FPR_FLOOR))

    scores = systems.scores_of(models, test)
    clusters = common.clusters_for(test["id"], split)
    rows, tally, sources, flag = evaluate(test, scores, cuts, clusters, split)
    if split != "validation":
        validation_rows, *_ = evaluate(validation, validation_scores, cuts, common.clusters_for(validation["id"], "validation"), "validation", with_auc=False)
        rows += [r for r in validation_rows if r["scope"] == "pooled attacks against ham"]
    show([r for r in rows if r["split"] == split], split)
    differences = difference_rows(tally, sources, flag, split)
    attack, ham, spam = systems.roles(test)
    cut_rows = []
    for name in [n for n in systems.ORDER if n in flag]:
        validation_flag = (validation_scores[name] > cuts[name])
        v_attack, v_ham, _ = systems.roles(validation)
        cut_rows.append({"split": split, "system": name, "description": systems.DESCRIPTION[name], "cut": cuts[name], "target_false_alarm_rate": common.round_or_none(target),
                         "frozen_score_validation_ham_rate": common.round_or_none(observed), "validation_ham_flag_rate": common.round_or_none(float(validation_flag[v_ham].mean())),
                         "validation_attack_flag_rate": common.round_or_none(float(validation_flag[v_attack].mean())), "split_ham_flag_rate": common.round_or_none(float(flag[name][ham].mean())),
                         "split_attack_flag_rate": common.round_or_none(float(flag[name][attack].mean())), "split_spam_flag_rate": common.round_or_none(float(flag[name][spam].mean())) if spam.any() else None,
                         "features": len(systems.FEATURES.get(name, [])) if name in systems.FEATURES else None})
    cut_table = pd.DataFrame(cut_rows)
    bec, bec_world = synthetic_arm(split, models, cuts, classifier_factory, thresholds, workers)
    common.write_table(guard, "n3_systems", pd.DataFrame(rows))
    common.write_table(guard, "n3_differences", differences)
    common.write_table(guard, "n3_cuts", cut_table)
    common.write_table(guard, "n3_synthetic_bec", bec)

    print("\nSynthetic BEC arm (%d attack emails and their %d benign twins; synthetic text, SYNTHETIC header blocks; reported apart)" % ((bec_world["category"] == "bec_attack").sum(), (bec_world["category"] == "bec_benign").sum()))
    for r in bec[bec["role"].isin(["attack", "benign twin"])].itertuples():
        print("  %-9s %-12s %2d/%-2d  %s" % (r.system, r.role, r.hits, r.n, "-" if pd.isna(r.rate) else "%.1f%% [%.1f, %.1f]" % (100 * r.rate, 100 * r.rate_ci_low, 100 * r.rate_ci_high)))

    # ---- checks
    expected = common.split_total(split)
    if expected is not None and not limit:
        checks.add("counts", "emails of the split equal results/split_counts.csv", len(test), expected, len(test) == expected)
    checks.add("leakage_guard", "learned systems were fitted on", "train (%d emails: %d attacks, %d ham)" % (len(train), int(systems.roles(train)[0].sum()), int(systems.roles(train)[1].sum())), "train only", True)
    checks.add("leakage_guard", "cuts were fixed on", "validation ham (%d emails)" % int(systems.roles(validation)[1].sum()), "validation only", True)
    for name in systems.LEARNED + ("fusion",):
        rate = float(cut_table[cut_table["system"] == name]["validation_ham_flag_rate"].iloc[0])
        checks.add("matched_false_alarm", "%s flags at most the target share of the validation ham" % name, "%.4f" % rate, "<= %.4f" % target, rate <= target + 1e-12)
    for name in [n for n in systems.ORDER if n in flag]:
        share = float(flag[name].mean())
        checks.add("not_degenerate", "%s: share of all emails of the split flagged" % name, "%.2f%%" % (100 * share), "above 0% and below 100%", 0 < share < 1)
    try:
        from sklearn.metrics import f1_score, roc_auc_score
        keep = attack | ham
        worst_f1 = worst_auc = 0.0
        for name in [n for n in systems.ORDER if n in flag]:
            mine = [r for r in rows if r["split"] == split and r["scope"] == "pooled attacks against ham" and r["system"] == name]
            f1 = next(r["value"] for r in mine if r["metric"] == "f1")
            auc = next(r["value"] for r in mine if r["metric"] == "auc")
            worst_f1 = max(worst_f1, abs(f1 - f1_score(attack[keep], flag[name][keep], zero_division=0)))
            worst_auc = max(worst_auc, abs(auc - roc_auc_score(attack[keep], scores[name][keep])))
        checks.add("metrics", "hand-written pooled F1 equals scikit-learn for every system", "%.1e" % worst_f1, "< 1e-3", worst_f1 < 1e-3)
        checks.add("metrics", "hand-written AUC equals scikit-learn for every system", "%.1e" % worst_auc, "< 1e-3", worst_auc < 1e-3)
    except ImportError:
        checks.add("metrics", "scikit-learn cross-check", "scikit-learn is not installed", "", None)
    checks.add("synthetic", "synthetic BEC pairs scored", int((bec_world["category"] == "bec_attack").sum()), "equal to the twins", int((bec_world["category"] == "bec_attack").sum()) == int((bec_world["category"] == "bec_benign").sum()))
    checks.add("run", "what favours the learned systems", "attack labels in the fit; corpus identity visible in the headers", "stated in the README and the report", None)
    common.write_table(guard, "n3_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return rows, differences, cut_table, bec, checks


def main(argv):
    parser = argparse.ArgumentParser(description="The N3 ablation: full system against text only, headers only and parallel fusion (Phase 13).")
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
