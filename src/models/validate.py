"""Phase 6: score the trained tactic classifier on the validation emails, on the Mac's CPU, and run the checks.

Run from the project root, after moving the Colab outputs into place (notebooks/README.md, "Back on the Mac"):
    python -m src.models.validate

Reads  data/processed/tactic_data.parquet            the table that was uploaded (validation rows used here)
       artifacts/tactic_model/                       the chosen weights, tokenizer and thresholds from Colab
       results/tactic_run_info.json, tactic_training_log.csv, tactic_seed_summary.csv, tactic_val_probs.csv   from Colab
Writes results/tactic_validation_scores.csv           precision, recall and F1 per tactic, system and validation set
       results/tactic_checks.csv                     PASS/FAIL checks, including "the Mac reproduces Colab"

What is scored, and how:
 - distilbert        the model in artifacts/, run here on the CPU, with its thresholds (tuned on real validation for
                     authority, urgency, scarcity and secrecy; 0.5 for the rare three).
 - distilbert_real_only   the comparison model trained without synthetic emails (Colab's probabilities and thresholds).
 - keyword_default   the Phase 4 keyword baseline, every tactic fires at score 1.0 (its default, untuned).
 - keyword_tuned     the same baseline with one threshold per main tactic tuned on the same real validation emails, so
                     the comparison with the tuned DistilBERT is fair. Phase 13 repeats it on the test split.
 Real validation emails and synthetic validation emails are always scored separately. A tactic with fewer than 10
 positives gets counts (tp, fp, fn), never an F1. The baseline reads the same cut text as the model. On synthetic
 emails the baseline gets recall only: twins that made it fire were dropped, so its precision there would be fake.

The validation scores are a little optimistic (validation picked the epoch, the seed and the thresholds). The honest
number is the test split, used once in Phase 13. The labels are LLM labels from one model family (Phase 5): every
score here is agreement with those labels, not with people.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import transformers

from src.baseline.keywords import DEFAULT_THRESHOLD, score_tactics
from src.data.label_schema import TACTICS
from src.data.paths import (
    RESULTS_DIR,
    TACTIC_CHECKS_CSV,
    TACTIC_DATA_PARQUET,
    TACTIC_MODEL_DIR,
    TACTIC_RUN_INFO_JSON,
    TACTIC_SEED_SUMMARY_CSV,
    TACTIC_TRAINING_LOG_CSV,
    TACTIC_VAL_PROBS_CSV,
    TACTIC_VALIDATION_SCORES_CSV,
)
from src.eval.metrics import macro_f1, tactic_rows, tune_threshold
from src.models.dataset import MAIN_TACTICS, check_table, labels_of, load_table, print_checks, sha256_of_file, validation_rows
from src.models.predict import load_tactic_model, predict_probs

PARITY_TOLERANCE = 0.001                       # the Mac's CPU must reproduce Colab's probabilities this closely
KEYWORD_GRID = (0.5, 1.0, 1.5, 2.0, 3.0)       # keyword scores move in steps of 0.5 (weak 0.5, strong 1.0)
WEIGHT_FILES_NOT_ALLOWED = (".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt")   # formats that can hold code


def keyword_scores(texts):
    """Keyword baseline scores (items x 7) for the texts, column order = TACTICS."""
    scores = np.zeros((len(texts), len(TACTICS)))
    for row, text in enumerate(texts):
        result = score_tactics(text)
        for col, tactic in enumerate(TACTICS):
            scores[row, col] = result[tactic]["score"]
    return scores


def predictions(scores, thresholds):
    """Yes/no matrix: score >= the tactic's threshold (thresholds is {tactic: number})."""
    return scores >= np.array([thresholds[t] for t in TACTICS])


def score_rows(system, data, y, predicted, thresholds, recall_only=False):
    """Table rows for one system on one validation set, plus the macro-F1 row over the main tactics."""
    rows = []
    for row in tactic_rows(y, predicted, TACTICS):
        row = {"data": data, "system": system, "threshold": thresholds[row["tactic"]], **row}
        if recall_only:                              # keyword baseline on synthetic emails: precision would be fake
            row["precision"] = row["f1"] = None
            row["reported"] = "recall only (twins were filtered against this baseline)"
            row["recall"] = round(row["tp"] / row["positives"], 4) if row["positives"] else None
        rows.append(row)
    if not recall_only:
        rows.append({"data": data, "system": system, "tactic": "macro_main4", "items": int(len(y)),
                     "f1": round(macro_f1(y, predicted, TACTICS, MAIN_TACTICS), 4),
                     "reported": "mean F1 over " + ", ".join(MAIN_TACTICS)})
    return rows


def show(scores, data, caption):
    """Print one validation set as a table: F1 where allowed, tp/fp/fn counts where not."""
    part = scores[scores["data"] == data]
    systems = list(dict.fromkeys(part["system"]))
    print("\n%s" % caption)
    print("%-14s %9s  %s" % ("tactic", "positives", "  ".join("%-18s" % s for s in systems)))
    for tactic in list(TACTICS) + ["macro_main4"]:
        cells = []
        for system in systems:
            hit = part[(part["system"] == system) & (part["tactic"] == tactic)]
            if hit.empty:
                cells.append("%-18s" % "-")
                continue
            row = hit.iloc[0]
            if pd.notna(row["f1"]):
                cells.append("%-18s" % ("F1 %.3f" % row["f1"]))
            elif tactic == "macro_main4":
                cells.append("%-18s" % "-")
            elif row["reported"].startswith("recall only"):
                cells.append("%-18s" % ("recall %s (%d of %d)" % ("n/a" if pd.isna(row["recall"]) else "%.2f" % row["recall"], row["tp"], row["positives"])))
            else:
                cells.append("%-18s" % ("tp %d fp %d fn %d" % (row["tp"], row["fp"], row["fn"])))
        positives = "" if tactic == "macro_main4" else str(int(part[part["tactic"] == tactic]["positives"].iloc[0]))
        print("%-14s %9s  %s" % (tactic, positives, "  ".join(cells)))


def main(argv):
    parser = argparse.ArgumentParser(description="Score the tactic classifier on the validation emails (Phase 6).")
    parser.add_argument("--data", type=Path, default=TACTIC_DATA_PARQUET)
    parser.add_argument("--model-dir", type=Path, default=TACTIC_MODEL_DIR)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help="where the Colab result files are and the outputs go")
    args = parser.parse_args(argv)
    results = args.results_dir
    pd.set_option("display.width", 220)

    table = load_table(args.data)
    val = validation_rows(table)
    texts = val["text"].tolist()
    y = labels_of(val)
    real = (val["origin"] == "real").to_numpy()
    print("Validation emails: %d real, %d synthetic" % (real.sum(), (~real).sum()))

    info = json.loads((results / TACTIC_RUN_INFO_JSON.name).read_text(encoding="utf-8"))
    colab = pd.read_csv(results / TACTIC_VAL_PROBS_CSV.name, dtype={"id": str})
    log = pd.read_csv(results / TACTIC_TRAINING_LOG_CSV.name)
    seeds = pd.read_csv(results / TACTIC_SEED_SUMMARY_CSV.name)

    def colab_probs(condition):
        part = colab[colab["condition"] == condition].set_index("id").reindex(val["id"])
        if part.isna().any().any():
            raise SystemExit("tactic_val_probs.csv does not cover the validation emails (%s)" % condition)
        return part[["p_" + t for t in TACTICS]].to_numpy()

    print("Loading the model on the CPU (offline) and predicting ...")
    model, tokenizer, thresholds = load_tactic_model(args.model_dir, "cpu")
    started = time.time()
    mac = predict_probs(model, tokenizer, texts)
    seconds = time.time() - started
    print("  %d emails in %.1f s (%.2f s per email)" % (len(texts), seconds, seconds / len(texts)))

    # ---- scores -------------------------------------------------------------------------------------------------
    keyword = keyword_scores(texts)
    default_thresholds = {t: DEFAULT_THRESHOLD for t in TACTICS}
    tuned = dict(default_thresholds)
    for tactic in MAIN_TACTICS:
        col = TACTICS.index(tactic)
        tuned[tactic], _ = tune_threshold(keyword[real, col], y[real, col], grid=KEYWORD_GRID, default=DEFAULT_THRESHOLD)

    systems = [("distilbert", predictions(mac, thresholds), thresholds, False)]
    if "real_only" in info["conditions"]:
        real_only_thresholds = info["conditions"]["real_only"]["thresholds"]
        systems.append(("distilbert_real_only", predictions(colab_probs("real_only"), real_only_thresholds), real_only_thresholds, False))
    systems += [("keyword_default", predictions(keyword, default_thresholds), default_thresholds, True),
                ("keyword_tuned", predictions(keyword, tuned), tuned, True)]

    rows = []
    for name, predicted, used, is_keyword in systems:
        rows += score_rows(name, "real_validation", y[real], predicted[real], used)
        rows += score_rows(name, "synthetic_validation", y[~real], predicted[~real], used, recall_only=is_keyword)
    scores = pd.DataFrame(rows)
    scores = scores[["data", "system", "tactic", "threshold", "items", "positives", "predicted", "tp", "fp", "fn",
                     "precision", "recall", "f1", "reported"]]
    results.mkdir(parents=True, exist_ok=True)
    scores.to_csv(results / TACTIC_VALIDATION_SCORES_CSV.name, index=False)

    show(scores, "real_validation", "REAL validation emails (%d). F1 where a tactic has 10 or more positives, otherwise counts." % real.sum())
    show(scores, "synthetic_validation", "SYNTHETIC validation emails (%d), reported apart from the real ones. Keyword rows: recall only." % (~real).sum())
    print("\nThresholds, distilbert: %s" % ", ".join("%s %.2f" % kv for kv in thresholds.items()))
    print("Thresholds, keyword_tuned: %s" % ", ".join("%s %.1f" % (t, tuned[t]) for t in MAIN_TACTICS))
    print("Scores are agreement with LLM labels from one model family, and a little optimistic (validation chose the epoch, seed and thresholds).")

    # ---- training record ----------------------------------------------------------------------------------------
    print("\nSeeds (best epoch of each; the chosen seed has the highest validation macro-F1):")
    print(seeds.to_string(index=False))

    # ---- checks -------------------------------------------------------------------------------------------------
    checks = list(check_table(table))

    def add(check, item, value, expected, passed):
        checks.append((check, item, value, expected, "PASS" if passed else "FAIL" if passed is not None else "info"))

    local_hash = sha256_of_file(args.data)
    add("data_matches_colab", "sha256 of the upload table", local_hash[:16], info["data_sha256"][:16], local_hash == info["data_sha256"])
    weight_files = sorted(p.name for p in args.model_dir.iterdir())
    risky = [n for n in weight_files if n.endswith(WEIGHT_FILES_NOT_ALLOWED)]
    add("safetensors_only", "weights file", "model.safetensors" if "model.safetensors" in weight_files else "missing", "model.safetensors",
        "model.safetensors" in weight_files)
    add("safetensors_only", "pickle-style files in the model folder", len(risky), "0", not risky)
    saved = json.loads((args.model_dir / "thresholds.json").read_text(encoding="utf-8"))
    add("thresholds_valid", "model thresholds equal the run's", "equal" if saved == info["conditions"]["mix"]["thresholds"] else "different",
        "equal", saved == info["conditions"]["mix"]["thresholds"])
    add("thresholds_valid", "rare tactics stay at 0.5", ", ".join("%.2f" % thresholds[t] for t in TACTICS if t not in MAIN_TACTICS), "0.50 each",
        all(thresholds[t] == 0.5 for t in TACTICS if t not in MAIN_TACTICS))
    add("probabilities_valid", "all probabilities", "between 0 and 1" if np.isfinite(mac).all() and mac.min() >= 0 and mac.max() <= 1 else "invalid",
        "finite, between 0 and 1", bool(np.isfinite(mac).all() and mac.min() >= 0 and mac.max() <= 1))

    difference = float(np.abs(mac - colab_probs("mix")).max())
    add("mac_reproduces_colab", "largest probability difference, all validation emails", "%.6f" % difference,
        "<= %.3f" % PARITY_TOLERANCE, difference <= PARITY_TOLERANCE)
    add("mac_reproduces_colab", "same predictions after thresholds",
        "%d of %d differ" % (int((predictions(mac, thresholds) != predictions(colab_probs("mix"), thresholds)).sum()), mac.size), "0",
        bool((predictions(mac, thresholds) == predictions(colab_probs("mix"), thresholds)).all()))
    add("same_library_versions", "transformers (Colab / Mac)", "%s / %s" % (info["versions"]["transformers"], transformers.__version__),
        "equal", info["versions"]["transformers"] == transformers.__version__)
    add("same_library_versions", "torch (Colab / Mac), for the record", "%s / %s" % (info["versions"]["torch"], torch.__version__), "", None)

    predicted = predictions(mac, thresholds)
    for tactic in MAIN_TACTICS:
        share = float(predicted[real, TACTICS.index(tactic)].mean())
        add("not_degenerate", "%s: share of real validation emails flagged" % tactic, "%.1f%%" % (100 * share), "above 0% and below 100%", 0 < share < 1)

    for condition in sorted(log["condition"].unique()):
        for seed in sorted(log[log["condition"] == condition]["seed"].unique()):
            part = log[(log["condition"] == condition) & (log["seed"] == seed)].sort_values("epoch")
            first, last = float(part["train_loss"].iloc[0]), float(part["train_loss"].iloc[-1])
            add("training_loss_fell", "%s seed %d: epoch 1 to last epoch" % (condition, seed), "%.3f to %.3f" % (first, last), "falls", last < first)
    chosen = seeds[seeds["chosen"]]
    for row in chosen.itertuples():
        part = log[(log["condition"] == row.condition) & (log["seed"] == row.seed) & (log["epoch"] == row.best_epoch)].iloc[0]
        add("overfitting_watch", "%s chosen seed %d, epoch %d: train loss / validation loss" % (row.condition, row.seed, row.best_epoch),
            "%.3f / %.3f" % (part["train_loss"], part["val_loss"]), "", None)

    print("\nChecks:")
    print_checks(checks)
    pd.DataFrame(checks, columns=["check", "item", "value", "expected", "status"]).to_csv(results / TACTIC_CHECKS_CSV.name, index=False)
    failed = [c for c in checks if c[4] == "FAIL"]
    print("\nWrote %s and %s" % (results / TACTIC_VALIDATION_SCORES_CSV.name, results / TACTIC_CHECKS_CSV.name))
    print("%d checks failed" % len(failed) if failed else "All checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
