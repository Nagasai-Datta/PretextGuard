"""Precision, recall, F1 and threshold tuning, written by hand (Phase 6; Phase 13 reuses it).

Every classifier in the project (the keyword baseline and DistilBERT) is scored with these
functions, so the two are always measured the same way. Each tactic is a yes/no question, so
everything here works on one tactic at a time:

    tp  the model said yes and the label says yes
    fp  the model said yes and the label says no       (a false alarm)
    fn  the model said no and the label says yes       (a miss)

    precision = tp / (tp + fp)     of the emails flagged, how many really use the tactic
    recall    = tp / (tp + fn)     of the emails that use it, how many were flagged
    f1        = 2 * precision * recall / (precision + recall)     one number that needs both

When a ratio has an empty denominator the value is 0.0 (nothing flagged means precision 0, as in
scikit-learn's zero_division=0 setting).

A tactic with fewer than MIN_POSITIVES positive items is reported as counts, never as an F1: with
so few positives one email moves F1 by several points and the number would only look precise. This
is the same rule as src/data/labels.py.

tune_threshold picks the cutoff that gives the best F1 on the data it is given. It must only ever be
called on validation data; the test split is used once, with the thresholds already fixed.

The self-test compares every function with scikit-learn on random data (scikit-learn is only imported
inside the self-test, so Colab and the API never need it). Run it from the project root:

    python -m src.eval.metrics
"""

import sys

import numpy as np

MIN_POSITIVES = 10
DEFAULT_GRID = tuple(round(0.05 * i, 2) for i in range(1, 20))  # 0.05, 0.10, ... 0.95


def confusion(y_true, y_pred):
    """(tp, fp, fn, tn) for two yes/no arrays of the same length."""
    y_true = np.asarray(y_true).astype(bool)
    y_pred = np.asarray(y_pred).astype(bool)
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))
    return tp, fp, fn, tn


def precision_recall_f1(tp, fp, fn):
    """(precision, recall, f1) from the three counts; an empty denominator gives 0.0."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def f1_at(scores, y_true, threshold):
    """F1 when every item with score >= threshold is called positive."""
    tp, fp, fn, _ = confusion(y_true, np.asarray(scores) >= threshold)
    return precision_recall_f1(tp, fp, fn)[2]


def tune_threshold(scores, y_true, grid=DEFAULT_GRID, default=0.5):
    """The threshold in grid with the highest F1. Ties go to the one closest to default, then the lower.

    Returns (threshold, f1). A coarse grid is deliberate: the fewer cutoffs we try, the less the
    choice can fit noise in a small validation set.
    """
    best = None
    for threshold in grid:
        f1 = f1_at(scores, y_true, threshold)
        key = (-f1, abs(threshold - default), threshold)
        if best is None or key < best[0]:
            best = (key, threshold, f1)
    return best[1], best[2]


def tactic_rows(y_true, y_pred, tactics):
    """One row per tactic from (items x tactics) yes/no matrices.

    Columns: tactic, items, positives, predicted, tp, fp, fn, precision, recall, f1, reported.
    precision, recall and f1 are None when the tactic has fewer than MIN_POSITIVES positives; the
    counts (tp, fp, fn) are always there.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    rows = []
    for col, tactic in enumerate(tactics):
        tp, fp, fn, _ = confusion(y_true[:, col], y_pred[:, col])
        positives = tp + fn
        enough = positives >= MIN_POSITIVES
        precision, recall, f1 = precision_recall_f1(tp, fp, fn)
        rows.append({
            "tactic": tactic, "items": int(len(y_true)), "positives": positives, "predicted": tp + fp,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4) if enough else None,
            "recall": round(recall, 4) if enough else None,
            "f1": round(f1, 4) if enough else None,
            "reported": "f1" if enough else "count only (fewer than %d positives)" % MIN_POSITIVES,
        })
    return rows


def macro_f1(y_true, y_pred, tactics, use):
    """Mean F1 over the tactics named in use (a subset of tactics); unrounded."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    values = []
    for tactic in use:
        col = list(tactics).index(tactic)
        tp, fp, fn, _ = confusion(y_true[:, col], y_pred[:, col])
        values.append(precision_recall_f1(tp, fp, fn)[2])
    return float(np.mean(values))


# --------------------------------------------------------------------------------------
# Self-test: python -m src.eval.metrics
# --------------------------------------------------------------------------------------

def self_test():
    """Compare every function with scikit-learn and with hand-worked cases. Returns True when all pass."""
    from sklearn.metrics import f1_score, precision_score, recall_score

    ok = True

    def check(name, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        print("  %-4s %s %s" % ("PASS" if passed else "FAIL", name, detail))

    # 1. A case worked by hand: 3 true positives, 1 false alarm, 2 misses, 4 true negatives.
    y_true = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    y_pred = [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]
    check("confusion counts", confusion(y_true, y_pred) == (3, 1, 2, 4))
    p, r, f = precision_recall_f1(3, 1, 2)
    check("precision 3/4, recall 3/5, f1 = 2*0.75*0.6/1.35",
          abs(p - 0.75) < 1e-12 and abs(r - 0.6) < 1e-12 and abs(f - 2 * 0.75 * 0.6 / 1.35) < 1e-12)

    # 2. Empty denominators give 0.0 and never divide by zero.
    check("nothing flagged gives precision 0", precision_recall_f1(0, 0, 4) == (0.0, 0.0, 0.0))
    check("no positives in the data gives recall 0", precision_recall_f1(0, 3, 0) == (0.0, 0.0, 0.0))

    # 3. Random data against scikit-learn: 200 columns of 300 items with different positive rates.
    rng = np.random.default_rng(42)
    worst = 0.0
    for trial in range(200):
        rate = rng.uniform(0.02, 0.6)
        truth = (rng.random(300) < rate).astype(int)
        pred = (rng.random(300) < rng.uniform(0.02, 0.6)).astype(int)
        tp, fp, fn, _ = confusion(truth, pred)
        mine = precision_recall_f1(tp, fp, fn)
        theirs = (precision_score(truth, pred, zero_division=0), recall_score(truth, pred, zero_division=0),
                  f1_score(truth, pred, zero_division=0))
        worst = max(worst, max(abs(a - b) for a, b in zip(mine, theirs)))
    check("200 random trials agree with scikit-learn", worst < 1e-12, "(largest difference %.1e)" % worst)

    # 4. Threshold tuning: a clean split is found; ties go to the threshold closest to the default.
    scores = np.array([0.9, 0.85, 0.8, 0.7, 0.65, 0.6])
    truth = np.array([1, 1, 1, 0, 0, 0])
    threshold, f1 = tune_threshold(scores, truth)
    # Any cutoff in (0.70, 0.80] separates the two groups: 0.75 and 0.80 are on the grid, 0.75 is nearer 0.5.
    check("tune_threshold on a clean split gives F1 1.0 at the tied cutoff nearest 0.5", f1 == 1.0 and threshold == 0.75,
          "(got %.2f, %.2f)" % (threshold, f1))
    check("f1_at matches scikit-learn", abs(f1_at(scores, truth, 0.75) - f1_score(truth, scores >= 0.75)) < 1e-12)
    flat_threshold, _ = tune_threshold(np.zeros(5), np.array([0, 0, 0, 0, 0]))
    check("no positives anywhere falls back to the default threshold", flat_threshold == 0.5)

    # 5. tactic_rows hides F1 below MIN_POSITIVES and macro_f1 averages the chosen tactics.
    truth = np.zeros((40, 2), dtype=int)
    truth[:12, 0] = 1
    truth[:3, 1] = 1
    pred = truth.copy()
    pred[0, 0] = 0
    rows = tactic_rows(truth, pred, ["common", "rare"])
    check("a tactic with 12 positives gets an F1", rows[0]["f1"] is not None and rows[0]["positives"] == 12)
    check("a tactic with 3 positives is counts only", rows[1]["f1"] is None and rows[1]["tp"] == 3)
    expected = precision_recall_f1(11, 0, 1)[2]
    check("macro_f1 over one tactic equals that tactic's F1", abs(macro_f1(truth, pred, ["common", "rare"], ["common"]) - expected) < 1e-12)
    check("macro_f1 over two tactics is their mean",
          abs(macro_f1(truth, pred, ["common", "rare"], ["common", "rare"]) - (expected + 1.0) / 2) < 1e-12)
    return ok


if __name__ == "__main__":
    print("Metrics self-test (hand-written functions against scikit-learn):")
    sys.exit(0 if self_test() else 1)
