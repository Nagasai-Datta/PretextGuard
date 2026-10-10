"""Phase 13: the statistics every experiment shares, written by hand (bootstrap intervals, Wilson intervals, AUC, matched false-alarm cuts).

Run the self-test from the project root:
    python -m src.eval.stats

WHY A BOOTSTRAP. A score such as an F1 is computed on one test set. A different test set drawn from the same corpus would give a slightly different
number, and with 12 to 44 positives per tactic the difference can be several points. The bootstrap measures that wobble: draw a new test set of the
same size WITH replacement from the test set, recompute the score, and repeat 1,000 times. The middle 95% of those 1,000 scores is the interval.

WHY WHOLE GROUPS ARE DRAWN. The corpora hold campaigns: hundreds of spam or phishing emails with the same subject, and they were put in one split together
(src/data/split.py). Such emails are near-copies, so drawing single emails would make the test set look bigger than it is and the interval too narrow.
Every experiment therefore passes a CLUSTER id per item (the Phase 1 subject group for emails, the thread for the hijack benchmark, the pair for synthetic
emails) and whole clusters are drawn.

HOW IT IS DONE FAST. A score like F1 only needs counts (tp, fp, fn, tn). The counts are summed per cluster once (`cluster_matrix`). A resample is then
"how many times was each cluster drawn" (a multinomial draw), and the totals of a resample are one matrix product. All statistics of one experiment use the
SAME draws (`Resampler`), so a difference between two systems is a PAIRED difference: both systems are scored on the same resampled emails, which is what
makes a small difference measurable.

Seed 42 and 1,000 resamples everywhere (as in Phase 9), so a rerun gives the same intervals.
"""

import sys

import numpy as np

BOOTSTRAPS = 1000
SEED = 42
MIN_POSITIVES = 10          # the Phase 5 rule: below this a score is a count, not a rate


# ---------------------------------------------------------------------------------------------------------------------
# Counts and rates (work on single numbers and on arrays, so one function serves a point estimate and 1,000 resamples)
# ---------------------------------------------------------------------------------------------------------------------

def ratio(numerator, denominator):
    """numerator / denominator, with nan where the denominator is 0 (the nan is dropped when an interval is taken)."""
    numerator, denominator = np.asarray(numerator, dtype=float), np.asarray(denominator, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denominator > 0, numerator / np.where(denominator > 0, denominator, 1.0), np.nan)


def f1_counts(tp, fp, fn):
    """F1 from counts: 2 tp / (2 tp + fp + fn), the same number as 2PR/(P+R); 0.0 when nothing is positive or predicted (scikit-learn's zero_division=0)."""
    tp, fp, fn = (np.asarray(x, dtype=float) for x in (tp, fp, fn))
    return np.where(2 * tp + fp + fn > 0, 2 * tp / np.where(2 * tp + fp + fn > 0, 2 * tp + fp + fn, 1.0), 0.0)


def outcome_columns(y_true, y_pred):
    """Four 0/1 arrays (tp, fp, fn, tn), one entry per item, ready for cluster_matrix."""
    y_true, y_pred = np.asarray(y_true).astype(bool), np.asarray(y_pred).astype(bool)
    return [(y_true & y_pred).astype(float), (~y_true & y_pred).astype(float), (y_true & ~y_pred).astype(float), (~y_true & ~y_pred).astype(float)]


def cluster_matrix(clusters, columns):
    """(cluster ids, matrix of shape clusters x columns): the per-cluster sums of the given per-item columns."""
    ids, inverse = np.unique(np.asarray(clusters).astype(str), return_inverse=True)
    matrix = np.column_stack([np.bincount(inverse, weights=np.asarray(c, dtype=float), minlength=len(ids)) for c in columns])
    return ids, matrix


def wilson(hits, n, z=1.96):
    """95% Wilson interval of hits/n: (low, high); (None, None) for n = 0."""
    if n == 0:
        return None, None
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


# ---------------------------------------------------------------------------------------------------------------------
# The cluster bootstrap
# ---------------------------------------------------------------------------------------------------------------------

class Resampler:
    """The draws of one experiment: for each of n_boot resamples, how many times each of n_clusters clusters was drawn.

    interval(matrix, fn) -> (point, low, high). matrix has one row per cluster (cluster_matrix) and fn turns a vector of summed columns into the statistic;
    fn must also accept a (n_boot x columns) array and return one value per row (the helpers above do). Using one Resampler for several statistics
    makes them share their draws, so a difference of two statistics is a paired difference."""

    def __init__(self, n_clusters, n_boot=BOOTSTRAPS, seed=SEED):
        if n_clusters < 1:
            raise ValueError("a bootstrap needs at least one cluster")
        rng = np.random.default_rng(seed)
        self.n_clusters = n_clusters
        self.weights = rng.multinomial(n_clusters, np.full(n_clusters, 1.0 / n_clusters), size=n_boot).astype(np.float64)

    def draws(self, matrix, fn):
        """The statistic on every resample (a vector of n_boot values; nan where it is undefined)."""
        matrix = np.asarray(matrix, dtype=float)
        if matrix.shape[0] != self.n_clusters:
            raise ValueError("the matrix has %d clusters, the resampler %d" % (matrix.shape[0], self.n_clusters))
        return np.asarray(fn(self.weights @ matrix), dtype=float)

    def interval(self, matrix, fn):
        matrix = np.asarray(matrix, dtype=float)
        point = float(fn(matrix.sum(axis=0)))
        values = self.draws(matrix, fn)
        if np.isnan(values).all():
            return point, None, None
        low, high = np.nanpercentile(values, [2.5, 97.5])
        return point, float(low), float(high)


class Tally:
    """Named per-item columns, summed per cluster, with one shared Resampler. The tool every ablation uses to put an interval on any statistic of its counts.

        tally = Tally(clusters)
        tally.add("tp_full", ...); tally.add("fp_full", ...)
        tally.interval(lambda v: f1_counts(v["tp_full"], v["fp_full"], v["fn_full"]))        # (point, low, high)

    v[name] is the summed column (one number for the point estimate, a vector of n_boot numbers for the resamples), so the same function serves both, and a
    statistic that uses columns of two systems is a paired difference."""

    class View:
        def __init__(self, array, index):
            self.array, self.index = array, index

        def __getitem__(self, name):
            return self.array[..., self.index[name]]

    def __init__(self, clusters, n_boot=BOOTSTRAPS, seed=SEED):
        self.ids, self.inverse = np.unique(np.asarray(clusters).astype(str), return_inverse=True)
        self.n_boot, self.seed = n_boot, seed
        self.index, self.columns, self._matrix, self._resampler, self._draws = {}, [], None, None, None

    def add(self, name, values):
        values = np.asarray(values, dtype=float)
        if len(values) != len(self.inverse):
            raise ValueError("column %s has %d items, the clusters %d" % (name, len(values), len(self.inverse)))
        self.index[name] = len(self.columns)
        self.columns.append(np.bincount(self.inverse, weights=values, minlength=len(self.ids)))
        self._matrix = self._draws = None

    def add_outcomes(self, prefix, y_true, y_pred):
        """tp_, fp_, fn_ and tn_ columns for one yes/no prediction."""
        for suffix, column in zip(("tp", "fp", "fn", "tn"), outcome_columns(y_true, y_pred)):
            self.add("%s_%s" % (suffix, prefix), column)

    def matrix(self):
        if self._matrix is None:
            self._matrix = np.column_stack(self.columns)
        return self._matrix

    def resampler(self):
        if self._resampler is None:
            self._resampler = Resampler(len(self.ids), self.n_boot, self.seed)
        return self._resampler

    def point(self, fn):
        return float(fn(Tally.View(self.matrix().sum(axis=0), self.index)))

    def interval(self, fn):
        """(point, low, high) of fn(view); low and high are None when the statistic is undefined on every resample."""
        matrix = self.matrix()
        point = float(fn(Tally.View(matrix.sum(axis=0), self.index)))
        if self._draws is None:                       # the summed columns of all resamples, computed once however many statistics are asked for
            self._draws = self.resampler().weights @ matrix
        values = np.asarray(fn(Tally.View(self._draws, self.index)), dtype=float)
        if np.isnan(values).all():
            return point, None, None
        low, high = np.nanpercentile(values, [2.5, 97.5])
        return point, float(low), float(high)


# ---------------------------------------------------------------------------------------------------------------------
# AUC
# ---------------------------------------------------------------------------------------------------------------------

def weighted_auc(scores, labels, weights=None):
    """Area under the ROC curve: the chance that a random positive item scores above a random negative one (ties count half).

    Written from that definition: sort the distinct scores, and for each score group add (its positive weight) x (the negative weight below it
    plus half the negative weight tied with it). weights are item weights (default 1); the bootstrap passes the number of times an item's cluster was drawn."""
    scores, labels = np.asarray(scores, dtype=float), np.asarray(labels).astype(bool)
    weights = np.ones(len(scores)) if weights is None else np.asarray(weights, dtype=float)
    _, inverse = np.unique(scores, return_inverse=True)
    groups = inverse.max() + 1 if len(inverse) else 0
    positive = np.bincount(inverse, weights=weights * labels, minlength=groups)
    negative = np.bincount(inverse, weights=weights * ~labels, minlength=groups)
    total_positive, total_negative = positive.sum(), negative.sum()
    if total_positive == 0 or total_negative == 0:
        return float("nan")
    below = np.cumsum(negative) - negative
    return float((positive * (below + 0.5 * negative)).sum() / (total_positive * total_negative))


def auc_interval(scores, labels, clusters, n_boot=BOOTSTRAPS, seed=SEED):
    """(auc, low, high): the AUC and its 95% cluster-bootstrap interval. The scores are sorted once; each resample only changes the item weights."""
    scores, labels = np.asarray(scores, dtype=float), np.asarray(labels).astype(bool)
    ids, inverse = np.unique(np.asarray(clusters).astype(str), return_inverse=True)
    resampler = Resampler(len(ids), n_boot, seed)
    point = weighted_auc(scores, labels)
    values = np.array([weighted_auc(scores, labels, w[inverse]) for w in resampler.weights])
    if np.isnan(values).all():
        return point, None, None
    low, high = np.nanpercentile(values, [2.5, 97.5])
    return point, float(low), float(high)


# ---------------------------------------------------------------------------------------------------------------------
# Matched false-alarm cut
# ---------------------------------------------------------------------------------------------------------------------

def matched_cut(negative_scores, target_rate):
    """The cut such that 'flag when score > cut' flags at most target_rate of the negative items (legitimate mail).

    Used to hold every system to the same false-alarm rate before their detection is compared. The cut is the (k+1)-th largest negative score with
    k = floor(target x n): at most k negatives score strictly above it. Ties can only lower the flagged share, never raise it."""
    negative_scores = np.sort(np.asarray(negative_scores, dtype=float))[::-1]
    k = int(np.floor(target_rate * len(negative_scores) + 1e-9))
    return float(negative_scores[k]) if k < len(negative_scores) else float("-inf")


# ---------------------------------------------------------------------------------------------------------------------
# Self-test: python -m src.eval.stats
# ---------------------------------------------------------------------------------------------------------------------

def self_test(verbose=True):
    from sklearn.metrics import f1_score, roc_auc_score

    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    rng = np.random.default_rng(7)

    # 1. F1 from counts equals scikit-learn on 200 random trials (and the 0/0 case is 0.0)
    worst = 0.0
    for _ in range(200):
        truth = rng.random(300) < rng.uniform(0.02, 0.6)
        pred = rng.random(300) < rng.uniform(0.02, 0.6)
        tp, fp, fn, _tn = (c.sum() for c in outcome_columns(truth, pred))
        worst = max(worst, abs(float(f1_counts(tp, fp, fn)) - f1_score(truth, pred, zero_division=0)))
    check("F1 from counts agrees with scikit-learn on 200 random trials", worst < 1e-12, "largest difference %.1e" % worst)
    check("F1 of nothing positive and nothing predicted is 0.0", float(f1_counts(0, 0, 0)) == 0.0)

    # 2. Wilson interval: the known values for 1 of 20, and the empty case
    low, high = wilson(1, 20)
    check("Wilson 1 of 20 is (0.0089, 0.2361) and 0 of 0 has no interval", abs(low - 0.0089) < 0.001 and abs(high - 0.2361) < 0.001 and wilson(0, 0) == (None, None))

    # 3. Bootstrap of a rate with singleton clusters matches the textbook width; the same data in big clusters is much wider
    n, p = 2000, 0.3
    hits = (rng.random(n) < p).astype(float)
    ids, matrix = cluster_matrix(np.arange(n), [hits, np.ones(n)])
    point, low, high = Resampler(len(ids)).interval(matrix, lambda t: ratio(t[..., 0], t[..., 1]))
    textbook = 2 * 1.96 * np.sqrt(point * (1 - point) / n)
    check("singleton clusters: the interval width is within 15% of the textbook width", abs((high - low) - textbook) / textbook < 0.15, "%.4f against %.4f" % (high - low, textbook))
    blocks = np.repeat(np.arange(40), 50)                                                 # 40 clusters of 50 identical items
    block_hits = np.repeat((rng.random(40) < p).astype(float), 50)
    ids2, matrix2 = cluster_matrix(blocks, [block_hits, np.ones(2000)])
    _, low2, high2 = Resampler(len(ids2)).interval(matrix2, lambda t: ratio(t[..., 0], t[..., 1]))
    check("40 clusters of 50 identical items give a far wider interval than 2,000 independent items", (high2 - low2) > 3 * (high - low), "%.3f against %.3f" % (high2 - low2, high - low))
    check("the same seed gives the same interval", Resampler(len(ids)).interval(matrix, lambda t: ratio(t[..., 0], t[..., 1])) == (point, low, high))

    # 4. A paired difference of a system with itself is exactly 0; of a clearly better system it is positive with an interval above 0
    truth = rng.random(1500) < 0.3
    good = np.where(rng.random(1500) < 0.9, truth, ~truth)
    bad = np.where(rng.random(1500) < 0.7, truth, ~truth)
    cols = outcome_columns(truth, good) + outcome_columns(truth, bad) + outcome_columns(truth, good)
    ids, matrix = cluster_matrix(np.arange(1500), cols)
    rs = Resampler(len(ids))
    same = rs.interval(matrix, lambda t: f1_counts(t[..., 0], t[..., 1], t[..., 2]) - f1_counts(t[..., 8], t[..., 9], t[..., 10]))
    diff = rs.interval(matrix, lambda t: f1_counts(t[..., 0], t[..., 1], t[..., 2]) - f1_counts(t[..., 4], t[..., 5], t[..., 6]))
    check("a system compared with itself has a paired difference of exactly 0 (interval 0 to 0)", same == (0.0, 0.0, 0.0), str(same))
    check("a system with 90% accuracy against one with 70%: the F1 difference is positive and its interval is above 0", diff[0] > 0.1 and diff[1] > 0, str(tuple(round(x, 3) for x in diff)))

    # 4b. Tally gives the same interval as the matrix route, by name
    tally = Tally(np.arange(1500))
    tally.add_outcomes("good", truth, good)
    tally.add_outcomes("bad", truth, bad)
    named = tally.interval(lambda v: f1_counts(v["tp_good"], v["fp_good"], v["fn_good"]) - f1_counts(v["tp_bad"], v["fp_bad"], v["fn_bad"]))
    check("Tally by name gives the same paired interval as the matrix route", np.allclose(named, diff), str(tuple(round(x, 3) for x in named)))
    check("Tally.point equals the plain F1", abs(tally.point(lambda v: f1_counts(v["tp_good"], v["fp_good"], v["fn_good"])) - f1_score(truth, good)) < 1e-12)

    # 5. AUC against scikit-learn, with ties, and the weighted version with unit weights
    worst = 0.0
    for _ in range(100):
        labels = rng.random(400) < rng.uniform(0.1, 0.6)
        scores = np.round(rng.normal(labels * rng.uniform(0, 2), 1.0), 1)             # rounded: many ties
        worst = max(worst, abs(weighted_auc(scores, labels) - roc_auc_score(labels, scores)))
    check("AUC (with ties) agrees with scikit-learn on 100 random trials", worst < 1e-12, "largest difference %.1e" % worst)
    labels = rng.random(600) < 0.4
    scores = rng.normal(labels * 1.5, 1.0)
    point, low, high = auc_interval(scores, labels, np.arange(600))
    check("the AUC interval contains the AUC and is narrower than 0.1", low <= point <= high and high - low < 0.1, "%.3f [%.3f, %.3f]" % (point, low, high))
    check("a perfect separator has AUC 1 and a coin flip about 0.5", weighted_auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0 and abs(weighted_auc(rng.random(4000), rng.random(4000) < 0.5) - 0.5) < 0.03)

    # 6. The matched cut flags at most the target share of the negatives, also with many ties
    worst_share, ok = 0.0, True
    for target in (0.0, 0.005, 0.01, 0.05):
        for scores in (rng.random(1000), np.round(rng.random(1000), 1), np.zeros(1000)):
            cut = matched_cut(scores, target)
            share = float((scores > cut).mean())
            ok &= share <= target + 1e-12
            worst_share = max(worst_share, share)
    check("matched_cut never flags more than the target share of the negatives (also with ties and all-equal scores)", ok, "largest flagged share %.4f" % worst_share)
    check("matched_cut on 1,000 distinct scores at 1% flags exactly 10", int((np.arange(1000.0) > matched_cut(np.arange(1000.0), 0.01)).sum()) == 10)

    passed = all(ok for _, ok, _ in results)
    if verbose:
        for name, ok, detail in results:
            print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name, "  (%s)" % detail if detail else ""))
        print("%d of %d checks passed" % (sum(ok for _, ok, _ in results), len(results)))
    return passed, len(results)


if __name__ == "__main__":
    print("Statistics self-test (against scikit-learn and textbook values):")
    sys.exit(0 if self_test()[0] else 1)
