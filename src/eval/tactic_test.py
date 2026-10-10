"""Phase 13: the tactic classifier and the keyword baseline on the test split, once, with every threshold fixed beforehand.

Run from the project root:
    python -m src.eval.tactic_test --split validation     # a dress rehearsal on the validation emails; writes to data/processed/rehearsal/
    python -m src.eval.tactic_test --split test           # the one test run (needs results/eval_freeze.csv; logged in results/eval_test_log.csv)

Reads  data/labelled/labels.csv, cleaned.parquet     the labelled real emails of the split (140 in test) and their text
       data/synthetic/synthetic.csv                  the synthetic attacks and their benign twins of the split (31 pairs in test)
       artifacts/tactic_model/                       the classifier and its thresholds (tuned on real validation in Phase 6)
       results/tactic_validation_scores.csv          the keyword baseline's thresholds (tuned on real validation in Phase 6) and the validation scores
Writes results/tactic_test_scores.csv                precision, recall, F1 with a 95% bootstrap interval, per system, tactic and data set, and the validation F1 beside it
       results/tactic_test_checks.csv                PASS/FAIL checks
       results/analysis_cooccurrence.csv             which tactics occur together in the labels and in the predictions (analysis only, never a claim)
       results/analysis_confusion_pairs.csv          when the classifier misses tactic A, which tactic B does it flag by mistake on the same email

What is scored. DistilBERT with the thresholds of artifacts/tactic_model/thresholds.json, the keyword baseline at its default threshold (1.0) and at the thresholds tuned on
real validation. Real and synthetic emails are scored apart. A tactic with fewer than 10 positives gets counts, never an F1 (Phase 5 rule). On synthetic emails the keyword baseline
gets recall only (twins that made it fire were dropped from the data, so its precision there would be fake). Synthetic attack emails per tactic are below 10 in test for urgency,
liking, secrecy and reciprocity, so a POOLED synthetic set (validation and test together) is added and labelled as pooled. Every F1 has a 95% interval from a bootstrap that
draws whole subject groups (src/eval/stats.py), and the difference DistilBERT minus the tuned keyword baseline in macro-F1 over the four main tactics is a PAIRED difference.

WHAT THIS CAN AND CANNOT SAY. Every score is agreement with LLM labels from one model family (Phase 5), not with people. The validation scores of Phase 6 are slightly optimistic
(validation chose the epoch, the seed and the thresholds); the test scores are the honest ones, and the gap between the two is printed. With 12 to 44 positives per tactic, two
systems that differ by a few points are not distinguishable; the intervals say so.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from src.baseline.keywords import DEFAULT_THRESHOLD, score_tactics
from src.data import paths
from src.data.label_schema import TACTICS
from src.eval import common, freeze
from src.eval.metrics import tactic_rows
from src.eval.stats import MIN_POSITIVES, Resampler, cluster_matrix, f1_counts, outcome_columns
from src.models.dataset import MAIN_TACTICS, TACTIC_COLUMNS, read_real, read_synthetic

SYSTEMS = ("distilbert", "keyword_default", "keyword_tuned")


def keyword_matrix(texts):
    """Keyword baseline scores (items x 7), column order = TACTICS."""
    scores = np.zeros((len(texts), len(TACTICS)))
    for row, text in enumerate(texts):
        result = score_tactics(text)
        for col, tactic in enumerate(TACTICS):
            scores[row, col] = result[tactic]["score"]
    return scores


def tuned_keyword_thresholds(validation_scores):
    """{tactic: threshold} of the tuned keyword baseline, as fixed on real validation in Phase 6 (default for a tactic that was not tuned)."""
    part = validation_scores[(validation_scores["system"] == "keyword_tuned") & (validation_scores["data"] == "real_validation")]
    found = {r.tactic: float(r.threshold) for r in part.itertuples() if r.tactic in TACTICS}
    return {t: found.get(t, DEFAULT_THRESHOLD) for t in TACTICS}


def f1_of(t, offset=0):
    return f1_counts(t[..., offset], t[..., offset + 1], t[..., offset + 2])


def macro_of(t, offset=0):
    """Mean F1 over the four main tactics, from columns tp, fp, fn laid out 3 per main tactic starting at offset."""
    return np.mean([f1_of(t, offset + 3 * k) for k in range(len(MAIN_TACTICS))], axis=0)


def main_columns(y, pred):
    """tp, fp, fn per main tactic as 12 per-item columns."""
    cols = []
    for tactic in MAIN_TACTICS:
        c = TACTICS.index(tactic)
        cols += outcome_columns(y[:, c], pred[:, c])[:3]
    return cols


def score_data(data, items, y, predictions, thresholds, clusters, validation):
    """Rows for one data set. predictions: {system: yes/no matrix}; thresholds: {system: {tactic: number}}. Returns (rows, paired difference row or None)."""
    resampler = None
    rows = []
    ids, _ = cluster_matrix(clusters, [np.ones(len(clusters))])
    resampler = Resampler(len(ids))
    for system, pred in predictions.items():
        recall_only = system.startswith("keyword") and data.startswith("synthetic")
        for row in tactic_rows(y, pred, TACTICS):
            tactic = row["tactic"]
            col = TACTICS.index(tactic)
            out = {"data": data, "system": system, "tactic": tactic, "threshold": thresholds[system][tactic], **{k: v for k, v in row.items() if k != "tactic"}}
            out.update({"f1_ci_low": None, "f1_ci_high": None, "validation_f1": validation.get((system, tactic)) if data.startswith("real") else None, "note": common.LABEL_NOTE})
            if recall_only:
                out.update({"precision": None, "f1": None, "reported": "recall only (twins were filtered against this baseline)",
                            "recall": round(row["tp"] / row["positives"], 4) if row["positives"] else None})
            elif out["f1"] is not None:
                _, matrix = cluster_matrix(clusters, outcome_columns(y[:, col], pred[:, col])[:3])
                _, low, high = resampler.interval(matrix, f1_of)
                out.update({"f1_ci_low": common.round_or_none(low), "f1_ci_high": common.round_or_none(high)})
            rows.append(out)
        if not recall_only:
            _, matrix = cluster_matrix(clusters, main_columns(y, pred))
            point, low, high = resampler.interval(matrix, macro_of)
            rows.append({"data": data, "system": system, "tactic": "macro_main4", "items": items, "f1": round(point, 4), "f1_ci_low": common.round_or_none(low),
                         "f1_ci_high": common.round_or_none(high), "validation_f1": validation.get((system, "macro_main4")) if data.startswith("real") else None,
                         "reported": "mean F1 over " + ", ".join(MAIN_TACTICS), "note": common.LABEL_NOTE})
    pair = None
    if "distilbert" in predictions and "keyword_tuned" in predictions and not data.startswith("synthetic"):
        _, matrix = cluster_matrix(clusters, main_columns(y, predictions["distilbert"]) + main_columns(y, predictions["keyword_tuned"]))
        point, low, high = resampler.interval(matrix, lambda t: macro_of(t, 0) - macro_of(t, 12))
        pair = {"data": data, "system": "distilbert minus keyword_tuned", "tactic": "macro_main4", "items": items, "f1": round(point, 4), "f1_ci_low": common.round_or_none(low),
                "f1_ci_high": common.round_or_none(high), "reported": "paired difference of macro-F1 over " + ", ".join(MAIN_TACTICS), "note": common.LABEL_NOTE}
    return rows, pair


def cooccurrence(y, pred):
    """Long table: for every pair of tactics, in how many emails both occur (labels) or are both predicted. Analysis only."""
    rows = []
    for scope, matrix in (("labels", y), ("predicted", pred)):
        matrix = np.asarray(matrix).astype(bool)
        for a, ta in enumerate(TACTICS):
            for b, tb in enumerate(TACTICS):
                both = int((matrix[:, a] & matrix[:, b]).sum())
                either = int((matrix[:, a] | matrix[:, b]).sum())
                rows.append({"scope": scope, "tactic_a": ta, "tactic_b": tb, "emails_both": both, "emails_a": int(matrix[:, a].sum()), "emails_b": int(matrix[:, b].sum()),
                             "jaccard": round(both / either, 4) if either else None})
    return pd.DataFrame(rows)


def confusion_pairs(y, pred):
    """For every ordered pair (a, b): emails where tactic a is missed (labelled, not predicted) AND tactic b is flagged by mistake (predicted, not labelled)."""
    y, pred = np.asarray(y).astype(bool), np.asarray(pred).astype(bool)
    rows = []
    for a, ta in enumerate(TACTICS):
        missed_a = y[:, a] & ~pred[:, a]
        for b, tb in enumerate(TACTICS):
            if a == b:
                continue
            false_b = ~y[:, b] & pred[:, b]
            rows.append({"missed_tactic": ta, "flagged_by_mistake": tb, "emails": int((missed_a & false_b).sum()), "missed_total": int(missed_a.sum()), "false_alarm_total": int(false_b.sum())})
    return pd.DataFrame(rows)


def validation_lookup():
    """{(system, tactic): validation F1} for the real validation rows of Phase 6 (the macro row is called macro_main4)."""
    path = paths.TACTIC_VALIDATION_SCORES_CSV
    if not path.exists():
        return pd.DataFrame(columns=["data", "system", "tactic", "threshold", "f1"]), {}
    table = pd.read_csv(path)
    real = table[table["data"] == "real_validation"]
    return table, {(r.system, r.tactic): (None if pd.isna(r.f1) else float(r.f1)) for r in real.itertuples()}


def run(split, rerun=None, classifier=None):
    guard = freeze.begin("tactic_test", split, rerun)
    if classifier is None:
        from src.models.predict import TacticClassifier
        classifier = TacticClassifier()
    checks = common.Checks()
    validation_table, validation = validation_lookup()
    keyword_tuned = tuned_keyword_thresholds(validation_table)
    thresholds = {"distilbert": dict(classifier.thresholds), "keyword_default": {t: DEFAULT_THRESHOLD for t in TACTICS}, "keyword_tuned": keyword_tuned}

    real = read_real([split]).sort_values("id").reset_index(drop=True)
    synthetic = read_synthetic([split]).sort_values("id").reset_index(drop=True)
    pair_of = pd.read_csv(paths.SYNTHETIC_CSV, dtype={"id": str}).set_index("id")["pair"]
    pool_splits = ("validation", "test") if split == "test" else ("train", "validation")
    pooled = read_synthetic(list(pool_splits)).sort_values("id").reset_index(drop=True)
    datasets = [("real_" + split, real, common.clusters_for(real["id"], split)),
                ("synthetic_" + split, synthetic, np.array([pair_of[i] for i in synthetic["id"]])),
                ("synthetic_pooled_" + "_".join(pool_splits), pooled, np.array([pair_of[i] for i in pooled["id"]]))]

    rows, pairs, truth, preds_real = [], [], {}, {}
    for data, frame, clusters in datasets:
        y = frame[TACTIC_COLUMNS].to_numpy(dtype=int)
        probabilities = classifier.probabilities(frame["text"].tolist())
        predictions = {"distilbert": probabilities >= np.array([thresholds["distilbert"][t] for t in TACTICS])}
        keyword = keyword_matrix(frame["text"].tolist())
        for name in ("keyword_default", "keyword_tuned"):
            predictions[name] = keyword >= np.array([thresholds[name][t] for t in TACTICS])
        data_rows, pair = score_data(data, len(frame), y, predictions, thresholds, clusters, validation)
        rows += data_rows
        if pair:
            pairs.append(pair)
        truth[data] = (y, predictions, probabilities, frame)
        if data == "real_" + split:
            preds_real = (y, predictions["distilbert"])
    scores = pd.DataFrame(rows + pairs)
    columns = ["data", "system", "tactic", "threshold", "items", "positives", "predicted", "tp", "fp", "fn", "precision", "recall", "f1", "f1_ci_low", "f1_ci_high", "validation_f1", "reported", "note"]
    scores = scores.reindex(columns=columns)
    common.write_table(guard, "tactic_test_scores", scores)
    common.write_table(guard, "analysis_cooccurrence", cooccurrence(*preds_real))
    common.write_table(guard, "analysis_confusion_pairs", confusion_pairs(*preds_real))

    show(scores, "real_" + split)
    for data in ("synthetic_" + split, datasets[2][0]):
        show(scores, data)

    # ---- checks
    y_real, predictions_real, probabilities_real, frame_real = truth["real_" + split]
    counts_path = paths.LABEL_COUNTS_CSV
    if counts_path.exists():
        counts = pd.read_csv(counts_path)
        counts = counts[(counts["group_type"] == "split") & (counts["group"] == split) & (counts["kind"] == "tactic")].set_index("label")
        for tactic in TACTICS:
            have = int(y_real[:, TACTICS.index(tactic)].sum())
            checks.add("labels", "%s positives among the real %s emails equal results/label_counts.csv" % (tactic, split), have, int(counts.loc[tactic, "positives"]), have == int(counts.loc[tactic, "positives"]))
        checks.add("labels", "real %s emails equal results/label_counts.csv" % split, len(real), int(counts["items"].iloc[0]), len(real) == int(counts["items"].iloc[0]))
    checks.add("leakage_guard", "splits of the emails scored", ",".join(sorted(set(real["split"]) | set(synthetic["split"]))), split, set(real["split"]) | set(synthetic["split"]) == {split})
    checks.add("thresholds", "the classifier's thresholds are fixed numbers between 0 and 1", ", ".join("%s %.2f" % kv for kv in thresholds["distilbert"].items()), "all in (0, 1)",
               all(0 < v < 1 for v in thresholds["distilbert"].values()))
    checks.add("thresholds", "keyword thresholds come from real validation (results/tactic_validation_scores.csv)", ", ".join("%s %.1f" % (t, keyword_tuned[t]) for t in MAIN_TACTICS), "", None)
    checks.add("probabilities", "all probabilities finite and between 0 and 1", "ok", "ok", bool(np.isfinite(probabilities_real).all() and probabilities_real.min() >= 0 and probabilities_real.max() <= 1))
    try:
        from sklearn.metrics import f1_score
        worst = 0.0
        for system, pred in predictions_real.items():
            for tactic in TACTICS:
                col = TACTICS.index(tactic)
                mine = scores[(scores["data"] == "real_" + split) & (scores["system"] == system) & (scores["tactic"] == tactic)]["f1"].iloc[0]
                if pd.notna(mine):
                    worst = max(worst, abs(float(mine) - f1_score(y_real[:, col], pred[:, col], zero_division=0)))
        checks.add("metrics", "hand-written F1 equals scikit-learn on every system and tactic with an F1", "%.1e" % worst, "< 1e-3 (the table rounds to 4 decimals)", worst < 1e-3)
    except ImportError:
        checks.add("metrics", "scikit-learn cross-check", "scikit-learn is not installed", "", None)
    for tactic in TACTICS:
        row = scores[(scores["data"] == "real_" + split) & (scores["system"] == "distilbert") & (scores["tactic"] == tactic)].iloc[0]
        if row["positives"] < MIN_POSITIVES:
            checks.add("counts_only", "%s: %d positives, so only counts are reported" % (tactic, row["positives"]), "tp %d fp %d fn %d" % (row["tp"], row["fp"], row["fn"]), "no F1", pd.isna(row["f1"]))
    common.write_table(guard, "tactic_test_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return scores, checks


def show(scores, data):
    part = scores[scores["data"] == data]
    if part.empty:
        return
    systems = list(dict.fromkeys(part["system"]))
    print("\n%s (F1 with a 95%% interval where a tactic has 10 or more positives, else counts; %s)" % (data, common.LABEL_NOTE))
    print("%-14s %9s  %s" % ("tactic", "positives", "  ".join("%-30s" % s for s in systems)))
    for tactic in list(TACTICS) + ["macro_main4"]:
        cells = []
        for system in systems:
            hit = part[(part["system"] == system) & (part["tactic"] == tactic)]
            if hit.empty:
                cells.append("%-30s" % "-")
                continue
            r = hit.iloc[0]
            if pd.notna(r["f1"]):
                cells.append("%-30s" % ("F1 %.3f [%.3f, %.3f]" % (r["f1"], r["f1_ci_low"], r["f1_ci_high"]) if pd.notna(r["f1_ci_low"]) else "F1 %.3f" % r["f1"]))
            elif tactic == "macro_main4":
                cells.append("%-30s" % "-")
            elif isinstance(r["reported"], str) and r["reported"].startswith("recall only"):
                cells.append("%-30s" % ("recall %s (%d of %d)" % ("n/a" if pd.isna(r["recall"]) else "%.2f" % r["recall"], r["tp"], r["positives"])))
            else:
                cells.append("%-30s" % ("tp %d fp %d fn %d" % (r["tp"], r["fp"], r["fn"])))
        positives = "" if tactic == "macro_main4" else str(int(part[part["tactic"] == tactic]["positives"].iloc[0]))
        print("%-14s %9s  %s" % (tactic, positives, "  ".join(cells)))
    diff = part[part["system"] == "distilbert minus keyword_tuned"]
    if len(diff):
        r = diff.iloc[0]
        print("macro-F1, DistilBERT minus tuned keyword baseline (paired): %+.3f [%+.3f, %+.3f]" % (r["f1"], r["f1_ci_low"], r["f1_ci_high"]))


def main(argv):
    parser = argparse.ArgumentParser(description="Score the tactic classifier and the keyword baseline on the test split (Phase 13).")
    freeze.add_run_arguments(parser)
    args = parser.parse_args(argv)
    _, checks = run(args.split, args.rerun)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
