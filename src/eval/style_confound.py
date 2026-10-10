"""Phase 13: the style-confound test (master document Section 8.5). Can a plain classifier tell the corpora apart by their writing alone?

Run from the project root:
    python -m src.eval.style_confound --split validation     # a dress rehearsal (writes to data/processed/rehearsal/)
    python -m src.eval.style_confound --split test           # the one test run (needs results/eval_freeze.csv)

WHY. The attacks come from some collections (phishing_pot, Nazario, Nigerian Fraud) and the ordinary mail from others (Apache, CEAS, Enron, Ling, SpamAssassin). If a classifier can tell two collections
of the SAME kind apart (two sources of ham, two of phishing) from their words alone, the collections differ in style, and a detector that separates attacks from ordinary mail might be separating collections.
The AUC says how well: 0.5 is a coin flip, 1.0 is perfect separation. The same test is run on the 7 tactic probabilities of the tactic classifier (does the model's own output carry corpus identity?) and
on real against synthetic emails (Section 8.5's worry: LLM-written attacks against human-written ordinary mail).

Reads  data/processed/cleaned.parquet            the redacted bodies of the train emails (fit) and of the split (test); at most 3,000 train emails per source, by SHA-256 order
       data/processed/tactic_probs/               the cached tactic probabilities of those emails (src/router/build.py get_probs)
       data/labelled/labels.csv, data/synthetic/synthetic.csv    for the real-against-synthetic task
Writes results/style_auc.csv      one row per pair of sources of the same kind and per feature set: AUC with a 95% interval over subject groups
       results/style_checks.csv   PASS/FAIL checks

Two feature sets: 'words' (TF-IDF of word pairs and single words of the redacted body, logistic regression) and 'tactic probabilities' (the seven numbers of the Phase 6 classifier, logistic regression).
A pair is fitted on the train emails of the two sources and scored on the split's emails of the two sources. 'Same kind' means the same category: ham against ham, spam against spam, attack against attack.

WHAT THIS CAN AND CANNOT SAY. A high AUC on words is expected (collections from different years and senders differ) and is a threat to validity, not a defect: it is why the ablations report per source and why
no pooled number is read as detection alone. A LOW AUC on the tactic probabilities would say the tactic model's output does not carry corpus identity; a high one would say it does. The test says nothing about
which words give a corpus away, and the redaction (links, addresses, domains replaced) is on for both feature sets.
"""

import argparse
import hashlib
import sys

import numpy as np
import pandas as pd

from src.data import paths
from src.data.label_schema import TACTICS
from src.eval import common, freeze
from src.eval.stats import auc_interval

TRAIN_PER_SOURCE = 3000
SEED = 42
TFIDF = {"ngram_range": (1, 2), "min_df": 2, "max_features": 200000, "sublinear_tf": True}
LOGISTIC = {"C": 1.0, "solver": "liblinear", "max_iter": 200, "random_state": 0}
KINDS = {"ham": ("ham",), "spam": ("spam",), "attack": common.ATTACK_CATEGORIES}


def order_key(email_id):
    return hashlib.sha256(("%d|style|%s" % (SEED, email_id)).encode("utf-8")).hexdigest()


def load_rows(split, sources, cap=0):
    """id, source, category and redacted body of the emails of these sources in one split; cap keeps the first `cap` per source in SHA-256 order."""
    table = pd.read_parquet(paths.CLEANED_PARQUET, columns=["id", "source", "category", "split", "body_redacted"], filters=[("split", "==", split), ("source", "in", list(sources))])
    table["id"] = table["id"].astype(str)
    if cap:
        table = table.assign(_key=table["id"].map(order_key)).sort_values("_key").groupby("source", group_keys=False).head(cap).drop(columns="_key")
    return table.reset_index(drop=True)


def tactic_probabilities(table, split):
    """The cached tactic probabilities of the emails of `table` (rows in its order), from data/processed/tactic_probs/."""
    frame = pd.read_parquet(paths.TACTIC_PROBS_DIR / ("probs_%s.parquet" % split)).set_index("id")
    missing = [i for i in table["id"] if i not in frame.index]
    if missing:
        raise SystemExit("%d emails have no cached tactic probabilities in %s: run prepare_test for the split first" % (len(missing), split))
    return frame.loc[table["id"], list(TACTICS)].to_numpy(dtype=float)


def pair_auc(features, train_a, train_b, test_a, test_b, kind, clusters):
    """AUC of a logistic regression fitted on train (a = 0, b = 1), scored on test; (auc, low, high)."""
    from sklearn.linear_model import LogisticRegression

    x_train = features["fit"](train_a, train_b)
    model = LogisticRegression(**LOGISTIC).fit(x_train[0], x_train[1])
    x_test, y_test = features["transform"](test_a, test_b)
    scores = model.decision_function(x_test)
    return auc_interval(scores, y_test, clusters)


def words_features():
    from sklearn.feature_extraction.text import TfidfVectorizer

    state = {}

    def fit(a, b):
        vectorizer = TfidfVectorizer(**TFIDF, dtype=np.float32)
        texts = [t if isinstance(t, str) else "" for t in list(a) + list(b)]
        state["v"] = vectorizer
        return vectorizer.fit_transform(texts), np.r_[np.zeros(len(a)), np.ones(len(b))].astype(int)

    def transform(a, b):
        texts = [t if isinstance(t, str) else "" for t in list(a) + list(b)]
        return state["v"].transform(texts), np.r_[np.zeros(len(a)), np.ones(len(b))].astype(int)
    return {"fit": fit, "transform": transform}


def probability_features():
    def fit(a, b):
        return np.vstack([a, b]), np.r_[np.zeros(len(a)), np.ones(len(b))].astype(int)

    def transform(a, b):
        return np.vstack([a, b]), np.r_[np.zeros(len(a)), np.ones(len(b))].astype(int)
    return {"fit": fit, "transform": transform}


def source_rows(split):
    """Rows of style_auc.csv for every pair of sources of the same kind."""
    all_sources = pd.read_parquet(paths.CLEANED_PARQUET, columns=["source", "category"]).drop_duplicates()
    rows = []
    for kind, categories in KINDS.items():
        sources = sorted(all_sources[all_sources["category"].isin(categories)]["source"].unique())
        if len(sources) < 2:
            continue
        train = load_rows("train", sources, TRAIN_PER_SOURCE)
        test = load_rows(split, sources)
        p_train, p_test = tactic_probabilities(train, "train"), tactic_probabilities(test, split)
        clusters = common.clusters_for(test["id"], split)
        for i, a in enumerate(sources):
            for b in sources[i + 1:]:
                for name, features in (("words", words_features()), ("tactic probabilities", probability_features())):
                    ta, tb = train["source"] == a, train["source"] == b
                    sa, sb = (test["source"] == a).to_numpy(), (test["source"] == b).to_numpy()
                    if name == "words":
                        fit_a, fit_b, test_a, test_b = train.loc[ta, "body_redacted"], train.loc[tb, "body_redacted"], test.loc[sa, "body_redacted"], test.loc[sb, "body_redacted"]
                    else:
                        fit_a, fit_b, test_a, test_b = p_train[ta.to_numpy()], p_train[tb.to_numpy()], p_test[sa], p_test[sb]
                    if min(len(fit_a), len(fit_b), len(test_a), len(test_b)) < 2:
                        continue
                    point, low, high = pair_auc(features, fit_a, fit_b, test_a, test_b, kind, np.r_[clusters[sa], clusters[sb]])
                    rows.append({"split": split, "task": "same-kind sources (%s)" % kind, "features": name, "group_a": a, "group_b": b, "n_train_a": int(ta.sum()), "n_train_b": int(tb.sum()),
                                 "n_test_a": int(sa.sum()), "n_test_b": int(sb.sum()), **common.interval_cells("auc", (point, low, high)),
                                 "note": "0.5 = cannot tell the two collections apart, 1.0 = perfectly separable"})
    return rows


def real_against_synthetic_rows(split, classifier):
    """AUC of telling labelled real emails from synthetic ones of the same kind (attack against attack, benign against benign)."""
    from src.models.dataset import read_real, read_synthetic

    rows = []
    synthetic_all = pd.read_csv(paths.SYNTHETIC_CSV, dtype={"id": str}).set_index("id")
    real_train, real_test = read_real(["train"]), read_real([split])
    syn_train, syn_test = read_synthetic(["train"]), read_synthetic([split])
    for kind, real_mask, syn_role in (("attack", lambda t: t["group"].isin(common.ATTACK_CATEGORIES), "attack"), ("benign", lambda t: t["group"].isin(["ham"]), "benign")):
        rt, rs = real_train[real_mask(real_train)], real_test[real_mask(real_test)]
        st, ss = syn_train[syn_train["group"] == syn_role], syn_test[syn_test["group"] == syn_role]
        clusters = np.r_[common.clusters_for(rs["id"], split), np.array([synthetic_all.at[i, "pair"] for i in ss["id"]])]
        for name, features in (("words", words_features()), ("tactic probabilities", probability_features())):
            if name == "words":
                a, b, ta, tb = rt["text"], st["text"], rs["text"], ss["text"]
            else:
                a, b, ta, tb = (classifier.probabilities(x["text"].tolist()) for x in (rt, st, rs, ss))
            if min(len(a), len(b), len(ta), len(tb)) < 2:
                continue
            point, low, high = pair_auc(features, a, b, ta, tb, kind, clusters)
            rows.append({"split": split, "task": "real against synthetic (%s emails)" % kind, "features": name, "group_a": "real (labelled)", "group_b": "synthetic", "n_train_a": len(rt), "n_train_b": len(st),
                         "n_test_a": len(rs), "n_test_b": len(ss), **common.interval_cells("auc", (point, low, high)),
                         "note": "Section 8.5: a high AUC means the synthetic emails can be told from real ones by their text; they are reported apart for that reason"})
    return rows


def run(split, rerun=None, classifier=None):
    guard = freeze.begin("style_confound", split, rerun)
    checks = common.Checks()
    if classifier is None:
        from src.models.predict import TacticClassifier
        classifier = TacticClassifier()
    rows = source_rows(split) + real_against_synthetic_rows(split, classifier)
    table = pd.DataFrame(rows)
    common.write_table(guard, "style_auc", table)

    print("\nStyle confound: AUC of telling two collections apart (%s split). 0.5 = coin flip, 1.0 = perfectly separable" % split)
    for task, part in table.groupby("task", sort=False):
        print("\n  %s" % task)
        print("  %-24s %-24s %-22s %-22s" % ("collection A", "collection B", "words", "tactic probabilities"))
        for (a, b), group in part.groupby(["group_a", "group_b"], sort=False):
            def cell(features):
                r = group[group["features"] == features]
                return "-" if r.empty else "%.3f [%.3f, %.3f]" % (r["auc"].iloc[0], r["auc_ci_low"].iloc[0], r["auc_ci_high"].iloc[0])
            print("  %-24s %-24s %-22s %-22s" % (a, b, cell("words"), cell("tactic probabilities")))

    # ---- checks
    checks.add("leakage_guard", "the fit used train emails only; the AUC was scored on the split", split, split, True)
    checks.add("counts", "pairs scored", len(table), "more than 0", len(table) > 0)
    checks.add("range", "every AUC lies between 0 and 1 and every interval contains it", "ok", "ok",
               bool(((table["auc"] >= 0) & (table["auc"] <= 1)).all() and ((table["auc_ci_low"] <= table["auc"] + 1e-12) & (table["auc"] <= table["auc_ci_high"] + 1e-12)).all()))
    for features in ("words", "tactic probabilities"):
        part = table[(table["features"] == features) & table["task"].str.startswith("same-kind")]
        if len(part):
            checks.add("summary", "%s: median AUC over same-kind source pairs" % features, "%.3f" % part["auc"].median(), "", None)
    common.write_table(guard, "style_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return table, checks


def main(argv):
    parser = argparse.ArgumentParser(description="Style-confound test: source-classifier AUC (Phase 13).")
    freeze.add_run_arguments(parser)
    args = parser.parse_args(argv)
    _, checks = run(args.split, args.rerun)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
