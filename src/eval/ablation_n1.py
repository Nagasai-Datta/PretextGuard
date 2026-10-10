"""Phase 13: the N1 ablation. How much of a phishing detector's accuracy is link-reading?

Run from the project root:
    python -m src.eval.n1_data                                       # BEFORE Colab: builds the training and validation samples (train and validation emails only)
    ... train on Colab (notebooks/phase13_n1_models.ipynb), put the two model folders in artifacts/, the three small files in results/ ...
    python -m src.eval.ablation_n1 --split validation --limit 1500    # a dress rehearsal on 1,500 validation emails (about 5 minutes; writes to data/processed/rehearsal/)
    python -m src.eval.ablation_n1 --split test                       # the one test run (about 45 minutes on the Mac's CPU, saved in chunks so a stop loses nothing; needs results/eval_freeze.csv)

The question (master document Section 4.2). Phishing detectors reach 97 to 99% partly by reading links: a link predicts the label in the corpora. Real pretexting has no link. Model A is trained on the RAW
body (links, addresses, file names as they were), model B on the REDACTED body ([URL] [EMAIL] [DOMAIN] [FILE]); both are DistilBERT and are trained alike on the same emails (src/eval/n1_train.py on Colab). A TF-IDF
plus logistic regression pair is a cheap second check, fitted on the same sample and on the whole train split. Each model is tested on the same held-out emails in four views:
    raw                  every test email, text as it was
    redacted             every test email, links and addresses replaced
    linkfree_raw         only the emails that naturally had no link (696 attacks and 5,880 not-attack emails in test, results/preprocess_checks.csv), text as it was
    linkfree_redacted    the same emails, redacted
The hypothesis is that A drops sharply from raw to redacted and B holds. The measure is the paired difference (A's drop minus B's drop) with a 95% interval; whatever the interval says is reported.
A link-presence rule (flag an email when it had a link) is added as a floor: it shows how much accuracy a link alone can give.

Reads  data/processed/cleaned.parquet            the emails of the split in both views, and the train split for the TF-IDF fits
       data/processed/n1_data.parquet            the sample the DistilBERT models trained on (the TF-IDF 'sample' fits use the same emails)
       artifacts/n1_model_a/, n1_model_b/        the two DistilBERT models (placed by hand after Colab)
       results/n1_run_info.json, n1_val_probs.csv  what Colab recorded; the Mac must reproduce its probabilities
Writes results/n1_scores.csv            per model and view: attack-class precision, recall, F1, false-positive rate (all not-attack, ham, spam), and per source the recall (attack sources) or false-positive
                                        rate (ham and spam sources); 95% intervals draw whole subject groups
       results/n1_differences.csv       paired differences: A raw minus redacted, B raw minus redacted, A's drop minus B's drop, A minus B per view; per model family
       results/n1_view_counts.csv       what the views contain: emails, share with a link and share changed by the redaction, per class and source
       results/n1_checks.csv            PASS/FAIL checks (counts equal Phase 2's, the Mac reproduces Colab's probabilities, scikit-learn cross-check, no test row in training)

WHAT THIS CAN AND CANNOT SAY. Attacks and not-attack emails come from different corpora (phishing_pot, Nazario and Nigerian Fraud against Apache, CEAS, Enron, Ling and SpamAssassin), so a model can separate
them by writing style or source without reading a link, and the style-confound test (style_confound.py) measures how separable the corpora are. If both models score about the same on every view, the finding is
that link-reading is not what carries accuracy in these data, not that redaction is free in general. The labels here are corpus labels, not LLM labels. One training sample (about 9,000 emails), two seeds per
model, one test set: the interval covers the test sample, not the training randomness. The naturally link-free attacks come mostly from Nigerian Fraud, Nazario and phishing_pot; the per-source rows show it.
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

from src.data import paths
from src.eval import common, freeze
from src.eval.n1_model import clip
from src.eval.stats import Tally, f1_counts, ratio

THRESHOLD = common.N1_THRESHOLD
TFIDF = {"ngram_range": (1, 2), "min_df": 3, "max_features": 300000, "sublinear_tf": True}
LOGISTIC = {"C": 1.0, "solver": "liblinear", "class_weight": "balanced", "max_iter": 200, "random_state": 0}
CHUNK = 800
PARITY_EMAILS = 200
PARITY_TOLERANCE = 0.001
VIEWS = (("raw", "raw", False), ("redacted", "redacted", False), ("linkfree_raw", "raw", True), ("linkfree_redacted", "redacted", True))
FAMILIES = (("distilbert", "distilbert_A", "distilbert_B"), ("tfidf_sample", "tfidf_A_sample", "tfidf_B_sample"), ("tfidf_full", "tfidf_A_full", "tfidf_B_full"))
MODELS = ("distilbert_A", "distilbert_B", "tfidf_A_sample", "tfidf_B_sample", "tfidf_A_full", "tfidf_B_full", "link_rule")
EMAIL_COLUMNS = ["id", "source", "category", "split", "is_attack", "has_url", "body_clean", "body_redacted"]


def load_emails(split, limit=0):
    """The emails of one split with both views, cut at the models' character limit."""
    table = pd.read_parquet(paths.CLEANED_PARQUET, columns=EMAIL_COLUMNS, filters=[("split", "==", split)]).reset_index(drop=True)
    if set(table["split"]) - {split}:
        raise SystemExit("a row of another split was loaded")
    if limit and limit < len(table):
        table = table.sample(limit, random_state=42).reset_index(drop=True)
    return pd.DataFrame({"id": table["id"].astype(str), "source": table["source"], "category": table["category"], "is_attack": table["is_attack"].astype(bool), "has_url": table["has_url"].astype(bool),
                         "raw": [clip(t) for t in table["body_clean"]], "redacted": [clip(t) for t in table["body_redacted"]]})


# ---------------------------------------------------------------------------------------------------------------------
# TF-IDF and logistic regression
# ---------------------------------------------------------------------------------------------------------------------

def fit_tfidf(texts, labels):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    vectorizer = TfidfVectorizer(**TFIDF, dtype=np.float32)
    matrix = vectorizer.fit_transform(texts)
    model = LogisticRegression(**LOGISTIC).fit(matrix, np.asarray(labels).astype(int))
    return vectorizer, model


def tfidf_probabilities(bundle, texts):
    vectorizer, model = bundle
    return model.predict_proba(vectorizer.transform(texts))[:, 1]


def tfidf_models(split_table):
    """{model name: {view: probabilities on the split}} for the four TF-IDF models. Needs the train split and the sample list of n1_data.parquet."""
    if not paths.N1_DATA_PARQUET.exists():
        raise SystemExit("%s does not exist: run  python -m src.eval.n1_data  first" % paths.N1_DATA_PARQUET.name)
    sample_ids = set(pd.read_parquet(paths.N1_DATA_PARQUET, columns=["id", "split"]).query("split == 'train'")["id"])
    train = pd.read_parquet(paths.CLEANED_PARQUET, columns=["id", "is_attack", "body_clean", "body_redacted"], filters=[("split", "==", "train")])
    train["id"] = train["id"].astype(str)
    out = {}
    for tag, part in (("sample", train[train["id"].isin(sample_ids)]), ("full", train)):
        labels = part["is_attack"].astype(bool).to_numpy()
        for letter, view, column in (("A", "raw", "body_clean"), ("B", "redacted", "body_redacted")):
            print("  fitting TF-IDF + logistic regression %s on the %s train emails (%d), %s view" % (letter, tag, len(part), view))
            bundle = fit_tfidf([clip(t) for t in part[column]], labels)
            out["tfidf_%s_%s" % (letter, tag)] = {"raw": tfidf_probabilities(bundle, split_table["raw"].tolist()), "redacted": tfidf_probabilities(bundle, split_table["redacted"].tolist())}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# DistilBERT
# ---------------------------------------------------------------------------------------------------------------------

def weights_digest(model_dir):
    path = model_dir / "model.safetensors"
    return freeze.sha256_of(path) if path.exists() else "missing"


def cached_probabilities(split, model_key, view, table, model_dir, loader):
    """Attack probabilities of the table's emails from model_key reading `view`, from the cache where possible. The cache is saved after every chunk and thrown away when the weights change."""
    folder = paths.N1_PROBS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stem = "%s_%s_%s" % (split, model_key, view)
    data_path, side_path = folder / (stem + ".parquet"), folder / (stem + ".json")
    digest = weights_digest(model_dir)
    cached = {}
    if data_path.exists() and side_path.exists() and json.loads(side_path.read_text(encoding="utf-8")).get("weights_sha256") == digest:
        frame = pd.read_parquet(data_path)
        cached = dict(zip(frame["id"], frame["probability"]))
    missing = table[~table["id"].isin(cached)]
    if len(missing):
        model, tokenizer = loader(model_dir)
        from src.eval.n1_model import predict

        order = missing.assign(_n=missing[view].str.len()).sort_values("_n", kind="stable")
        print("  %s reading the %s view: %d of %d emails need a prediction (the rest are cached)" % (model_key, view, len(order), len(table)))
        from tqdm import tqdm

        for start in tqdm(range(0, len(order), CHUNK), desc="  %s %s" % (model_key, view), unit=" x%d emails" % CHUNK):
            part = order.iloc[start:start + CHUNK]
            for uid, p in zip(part["id"], predict(model, tokenizer, part[view].tolist())):
                cached[uid] = float(p)
            pd.DataFrame({"id": list(cached), "probability": list(cached.values())}).to_parquet(data_path, index=False)
            side_path.write_text(json.dumps({"weights_sha256": digest, "model": model_key, "view": view}), encoding="utf-8")
    return np.array([cached[i] for i in table["id"]])


def distilbert_models(split, table, loader):
    out = {}
    for key, folder in (("A", paths.N1_MODEL_A_DIR), ("B", paths.N1_MODEL_B_DIR)):
        if not (folder / "model.safetensors").exists():
            raise SystemExit("%s is missing: train the N1 models on Colab (notebooks/phase13_n1_models.ipynb) and put the folder in artifacts/" % folder)
        out["distilbert_" + key] = {view: cached_probabilities(split, "distilbert_" + key, view, table, folder, loader) for view in ("raw", "redacted")}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------------------------------------------------

def predictions_of(models, table):
    """{model: {text view: boolean array}} at the fixed threshold; the link rule flags an email that had a link."""
    out = {name: {view: probabilities >= THRESHOLD for view, probabilities in views.items()} for name, views in models.items()}
    out["link_rule"] = {"raw": table["has_url"].to_numpy(dtype=bool)}
    return out


def build_tally(table, predictions, clusters):
    attack = table["is_attack"].to_numpy(dtype=bool)
    category = table["category"].to_numpy()
    ham, spam = category == "ham", category == "spam"
    source = table["source"].to_numpy()
    sources = sorted(set(source))
    linkfree = ~table["has_url"].to_numpy(dtype=bool)
    tally = Tally(clusters)
    for view, _, free in VIEWS:
        mask = linkfree if free else np.ones(len(table), dtype=bool)
        for k, s in enumerate(sources):
            tally.add("n%d_%s" % (k, view), (source == s) & mask)
        for name, by_view in predictions.items():
            text_view = next(t for v, t, f in VIEWS if v == view)
            if text_view not in by_view:
                continue
            f = by_view[text_view]
            tag = "%s_%s" % (name, view)
            tally.add("tp_" + tag, attack & f & mask)
            tally.add("fp_" + tag, ~attack & f & mask)
            tally.add("fn_" + tag, attack & ~f & mask)
            tally.add("tn_" + tag, ~attack & ~f & mask)
            tally.add("fph_" + tag, ham & f & mask)
            tally.add("tnh_" + tag, ham & ~f & mask)
            tally.add("fps_" + tag, spam & f & mask)
            tally.add("tns_" + tag, spam & ~f & mask)
            for k, s in enumerate(sources):
                tally.add("s%d_%s" % (k, tag), (source == s) & f & mask)
    return tally, sources


def metric_functions(tag):
    tp, fp, fn, tn = ("%s_%s" % (x, tag) for x in ("tp", "fp", "fn", "tn"))
    fph, tnh, fps, tns = ("%s_%s" % (x, tag) for x in ("fph", "tnh", "fps", "tns"))
    return {"precision": lambda v: ratio(v[tp], v[tp] + v[fp]), "recall": lambda v: ratio(v[tp], v[tp] + v[fn]), "f1": lambda v: f1_counts(v[tp], v[fp], v[fn]),
            "false_positive_rate": lambda v: ratio(v[fp], v[fp] + v[tn]), "false_positive_rate_ham": lambda v: ratio(v[fph], v[fph] + v[tnh]),
            "false_positive_rate_spam": lambda v: ratio(v[fps], v[fps] + v[tns])}


def score_rows(table, tally, sources, predictions, split):
    category_of = {s: table.loc[table["source"] == s, "category"].iloc[0] for s in sources}
    rows = []
    for view, text_view, _ in VIEWS:
        for name in MODELS:
            if text_view not in predictions[name]:
                continue
            tag = "%s_%s" % (name, view)
            positives = int(tally.point(lambda v: v["tp_" + tag] + v["fn_" + tag]))
            negatives = int(tally.point(lambda v: v["fp_" + tag] + v["tn_" + tag]))
            for metric, fn in metric_functions(tag).items():
                point, low, high = tally.interval(fn)
                n = positives if metric in ("precision", "recall", "f1") else negatives
                rows.append({"split": split, "model": name, "view": view, "scope": "overall", "metric": metric, **common.interval_cells("value", (point, low, high)), "n": n, "hits": None,
                             "note": "n counts the attacks (precision, recall, F1) or the not-attack emails (false-positive rates)"})
            for k, s in enumerate(sources):
                n = int(tally.point(lambda v: v["n%d_%s" % (k, view)]))
                hits = int(tally.point(lambda v: v["s%d_%s" % (k, tag)]))
                metric = "recall" if category_of[s] in common.ATTACK_CATEGORIES else "false_positive_rate"
                interval = tally.interval(lambda v: ratio(v["s%d_%s" % (k, tag)], v["n%d_%s" % (k, view)])) if n >= common.MIN_POSITIVES else (None, None, None)
                rows.append({"split": split, "model": name, "view": view, "scope": "source: %s (%s)" % (s, category_of[s]), "metric": metric, **common.interval_cells("value", interval), "n": n,
                             "hits": hits, "note": "" if n >= common.MIN_POSITIVES else "fewer than %d emails: count only" % common.MIN_POSITIVES})
    return rows


def difference_rows(tally, predictions, split):
    rows = []
    for family, a, b in FAMILIES:
        if a not in predictions or b not in predictions:
            continue
        for metric in ("f1", "recall", "false_positive_rate"):
            def m(name, view, metric=metric):
                return metric_functions("%s_%s" % (name, view))[metric]
            contrasts = {
                "A: raw minus redacted": lambda v, m=m: m(a, "raw")(v) - m(a, "redacted")(v),
                "B: raw minus redacted": lambda v, m=m: m(b, "raw")(v) - m(b, "redacted")(v),
                "A's drop minus B's drop": lambda v, m=m: (m(a, "raw")(v) - m(a, "redacted")(v)) - (m(b, "raw")(v) - m(b, "redacted")(v)),
                "A minus B on raw": lambda v, m=m: m(a, "raw")(v) - m(b, "raw")(v),
                "A minus B on redacted": lambda v, m=m: m(a, "redacted")(v) - m(b, "redacted")(v),
                "A minus B on linkfree_redacted": lambda v, m=m: m(a, "linkfree_redacted")(v) - m(b, "linkfree_redacted")(v),
                "A: linkfree_raw minus linkfree_redacted": lambda v, m=m: m(a, "linkfree_raw")(v) - m(a, "linkfree_redacted")(v),
                "A: raw minus linkfree_raw": lambda v, m=m: m(a, "raw")(v) - m(a, "linkfree_raw")(v),
            }
            for contrast, fn in contrasts.items():
                point, low, high = tally.interval(fn)
                rows.append({"split": split, "family": family, "contrast": contrast, "metric": metric, **common.interval_cells("difference", (point, low, high))})
    return pd.DataFrame(rows)


def view_counts(table, split):
    rows = []
    changed = (table["raw"] != table["redacted"]).to_numpy()
    for view, free in (("all", False), ("linkfree", True)):
        part = table[~table["has_url"]] if free else table
        for (source, category), group in part.groupby(["source", "category"]):
            rows.append({"split": split, "view": view, "source": source, "category": category, "is_attack": category in common.ATTACK_CATEGORIES, "emails": len(group),
                         "with_a_link": int(group["has_url"].sum()), "link_share_pct": round(100 * float(group["has_url"].mean()), 1),
                         "text_changed_by_redaction_pct": round(100 * float(changed[group.index].mean()), 1)})
    return pd.DataFrame(rows)


def reading(differences, family):
    """One neutral sentence about the N1 contrast from its numbers."""
    row = differences[(differences["family"] == family) & (differences["contrast"] == "A's drop minus B's drop") & (differences["metric"] == "f1")]
    if row.empty or pd.isna(row["difference"].iloc[0]):
        return "no reading"
    d, low, high = row.iloc[0]["difference"], row.iloc[0]["difference_ci_low"], row.iloc[0]["difference_ci_high"]
    verdict = ("A loses more attack-class F1 than B when the links go (the interval is above 0)" if low > 0 else
               "A loses less than B (the interval is below 0)" if high < 0 else "the interval includes 0: A's drop is not distinguishable from B's")
    return "%s: A's drop minus B's drop in attack-class F1 = %+.3f [%+.3f, %+.3f]: %s" % (family, d, low, high, verdict)


def run(split, rerun=None, limit=0, loader=None, models_override=None):
    guard = freeze.begin("ablation_n1", split, rerun)
    checks = common.Checks()
    if loader is None:
        from src.eval.n1_model import load as loader
    table = load_emails(split, limit)
    clusters = common.clusters_for(table["id"], split)
    print("N1 on %d %s emails (%d attacks, %d with a link)" % (len(table), split, table["is_attack"].sum(), table["has_url"].sum()))
    models = models_override if models_override is not None else {**tfidf_models(table), **distilbert_models(split, table, loader)}
    predictions = predictions_of(models, table)
    tally, sources = build_tally(table, predictions, clusters)
    rows = score_rows(table, tally, sources, predictions, split)
    differences = difference_rows(tally, predictions, split)
    counts = view_counts(table, split)
    common.write_table(guard, "n1_scores", pd.DataFrame(rows))
    common.write_table(guard, "n1_differences", differences)
    common.write_table(guard, "n1_view_counts", counts)

    # ---- print
    scores = pd.DataFrame(rows)
    overall = scores[scores["scope"] == "overall"]
    print("\nAttack-class F1 and false-positive rate [95%% interval over subject groups] (threshold %.1f; corpus labels)" % THRESHOLD)
    print("%-16s %-18s %-24s %-26s %-24s %-24s" % ("model", "view", "F1", "recall", "false-positive rate", "FPR on spam"))
    for name in MODELS:
        for view, text_view, _ in VIEWS:
            part = overall[(overall["model"] == name) & (overall["view"] == view)]
            if part.empty:
                continue

            def cell(metric, percent=False):
                r = part[part["metric"] == metric].iloc[0]
                if pd.isna(r["value"]):
                    return "-"
                return ("%.1f%% [%.1f, %.1f]" % (100 * r["value"], 100 * r["value_ci_low"], 100 * r["value_ci_high"])) if percent else "%.3f [%.3f, %.3f]" % (r["value"], r["value_ci_low"], r["value_ci_high"])
            print("%-16s %-18s %-24s %-26s %-24s %-24s" % (name, view, cell("f1"), cell("recall", True), cell("false_positive_rate", True), cell("false_positive_rate_spam", True)))
    print()
    for family, _, _ in FAMILIES:
        print(reading(differences, family))

    # ---- checks
    if not limit:
        expected = paths.PREPROCESS_CHECKS_CSV
        if expected.exists():
            pre = pd.read_csv(expected)
            pre = pre[pre["check"] == "link_free"]
            free = ~table["has_url"]
            for is_attack, label in ((True, "attacks"), (False, "not-attack emails")):
                item = "is_attack=%s link_free=True split=%s" % (is_attack, split)
                want = pre[pre["item"] == item]["value"]
                have = int(((table["is_attack"] == is_attack) & free).sum())
                if len(want):
                    checks.add("counts", "naturally link-free %s in %s equal results/preprocess_checks.csv" % (label, split), have, int(want.iloc[0]), have == int(want.iloc[0]))
    sizes = pd.read_csv(paths.SPLIT_COUNTS_CSV)
    if split in sizes.columns and not limit:
        checks.add("counts", "emails of the split equal results/split_counts.csv", len(table), int(sizes[split].sum()), len(table) == int(sizes[split].sum()))
    checks.add("fixed_threshold", "the cut of every model", THRESHOLD, "0.5 (fixed, never tuned)", THRESHOLD == 0.5)
    if paths.N1_DATA_PARQUET.exists():
        sample = pd.read_parquet(paths.N1_DATA_PARQUET, columns=["id", "split"])
        leak = int(sample["id"].isin(set(table["id"])).sum()) if split != "validation" else 0
        checks.add("leakage_guard", "emails of the evaluated split that were in the models' training or validation sample", leak, "0", leak == 0)
        checks.add("leakage_guard", "splits in the sample the models saw", ",".join(sorted(set(sample["split"]))), "train,validation", set(sample["split"]) == {"train", "validation"})
    info_path = paths.RESULTS_DIR / "n1_run_info.json"
    if info_path.exists() and paths.N1_DATA_PARQUET.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))
        have = freeze.sha256_of(paths.N1_DATA_PARQUET)
        checks.add("data_matches_colab", "sha256 of the upload table", have[:16], str(info["data_sha256"])[:16], have == info["data_sha256"])
    parity_path = paths.RESULTS_DIR / "n1_val_probs.csv"
    if models_override is None and parity_path.exists() and paths.N1_DATA_PARQUET.exists():
        colab = pd.read_csv(parity_path, dtype={"id": str})
        sample = pd.read_parquet(paths.N1_DATA_PARQUET)
        sample = sample[sample["split"] == "validation"].head(PARITY_EMAILS)
        worst = 0.0
        for key, folder, column in (("A", paths.N1_MODEL_A_DIR, "text_raw"), ("B", paths.N1_MODEL_B_DIR, "text_redacted")):
            from src.eval.n1_model import predict

            model, tokenizer = loader(folder)
            mine = predict(model, tokenizer, sample[column].tolist())
            theirs = colab[colab["model"] == key].set_index("id").reindex(sample["id"])["probability"].to_numpy()
            worst = max(worst, float(np.nanmax(np.abs(mine - theirs))))
        checks.add("mac_reproduces_colab", "largest probability difference on %d validation-sample emails, both models" % len(sample), "%.6f" % worst, "<= %.3f" % PARITY_TOLERANCE, worst <= PARITY_TOLERANCE)
    try:
        from sklearn.metrics import f1_score
        attack = table["is_attack"].to_numpy(dtype=bool)
        worst = 0.0
        for name in MODELS:
            for view, text_view, free in VIEWS:
                if text_view not in predictions[name]:
                    continue
                mask = ~table["has_url"].to_numpy(dtype=bool) if free else np.ones(len(table), dtype=bool)
                mine = scores[(scores["model"] == name) & (scores["view"] == view) & (scores["scope"] == "overall") & (scores["metric"] == "f1")]["value"].iloc[0]
                if mask.any():
                    worst = max(worst, abs(float(mine) - f1_score(attack[mask], predictions[name][text_view][mask], zero_division=0)))
        checks.add("metrics", "hand-written attack-class F1 equals scikit-learn for every model and view", "%.1e" % worst, "< 1e-3", worst < 1e-3)
    except ImportError:
        checks.add("metrics", "scikit-learn cross-check", "scikit-learn is not installed", "", None)
    for name in MODELS:
        share = float(np.mean(predictions[name]["raw"]))
        checks.add("not_degenerate", "%s: share of raw-view emails flagged" % name, "%.1f%%" % (100 * share), "above 0% and below 100%", 0 < share < 1)
    checks.add("run", "labels", "corpus labels (attack corpora against the rest), not LLM labels", "", None)
    common.write_table(guard, "n1_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return scores, differences, checks


def main(argv):
    parser = argparse.ArgumentParser(description="The N1 ablation: raw-trained against redaction-trained models on raw, redacted and link-free views (Phase 13).")
    freeze.add_run_arguments(parser)
    parser.add_argument("--limit", type=int, default=0, help="a random sample of N emails of the evaluated split (rehearsal only)")
    args = parser.parse_args(argv)
    if args.split == "test" and args.limit:
        raise SystemExit("--limit is for rehearsals: the test run scores every email")
    _, _, checks = run(args.split, args.rerun, args.limit)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
