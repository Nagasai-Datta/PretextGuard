"""Phase 6: fine-tune DistilBERT on the seven tactics. Runs on Colab's GPU (also works on a CPU, slowly).

Run from the project root (the Colab notebook does this for you):
    python -m src.models.train --data PATH_TO/tactic_data.parquet --out OUTPUT_FOLDER

Reads  the one upload table made by src.models.dataset (train and validation rows only; a test row stops the run)
Writes into the output folder:
    tactic_model/               the weights (.safetensors), tokenizer, config and thresholds.json of the chosen model
    tactic_training_log.csv     one row per condition, seed and epoch: training loss, validation loss, validation macro-F1
    tactic_seed_summary.csv     one row per condition and seed: the best epoch and its scores, and which seed was chosen
    tactic_val_probs.csv        the chosen model's probabilities on every validation email (the Mac checks its own against these)
    tactic_run_info.json        settings, library versions, thresholds, data checksum: everything needed to repeat the run

Two conditions are trained, each with seeds 42, 43 and 44:
    mix        the real train emails plus the synthetic train emails (this one becomes the model)
    real_only  the real train emails alone (a comparison, to measure whether the synthetic emails help)

How one training run works (the loop below is the whole of it):
 1. Tokenise: each email becomes up to 512 word-piece numbers; a batch is padded only to its longest email.
 2. Forward pass: DistilBERT plus a small 7-output layer gives seven numbers per email (logits).
 3. Loss: binary cross-entropy on each tactic separately, with pos_weight so a rare positive counts like
    many negatives (negatives divided by positives, at most 10).
 4. Backward pass and an AdamW step change every weight a little (learning rate 3e-5, warm-up then linear decay).
 5. After each epoch (one pass over the training emails) the model predicts the real and synthetic validation
    emails. The epoch is scored by macro-F1 over authority, urgency, scarcity and secrecy on the REAL validation
    emails at threshold 0.5; ties go to the lower validation loss. Training stops after 3 epochs without
    improvement, and the best epoch's weights are kept (early stopping, the guard against overfitting).
 6. The best seed (same score) becomes the model. Its thresholds for the four main tactics are tuned on the real
    validation emails; the three rare tactics (reciprocity, social proof, liking) stay at 0.5, because tuning on
    fewer than 10 positives would only fit noise.

The validation scores are therefore a little optimistic: validation picked the epoch, the seed and the thresholds.
The honest number is the test split, used once in Phase 13. Test rows never reach this script.

The labels are LLM labels from one model family (Phase 5), so every F1 is agreement with those labels, not with people.
GPU arithmetic is not bit-exact between runs: "same seed" means similar results, not identical ones.
"""

import argparse
import json
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import transformers
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from src.data.label_schema import TACTICS
from src.data.paths import TACTIC_DATA_PARQUET
from src.eval.metrics import macro_f1, tune_threshold
from src.models.dataset import (
    CONDITIONS,
    MAIN_TACTICS,
    check_table,
    labels_of,
    load_table,
    sha256_of_file,
    training_rows,
    validation_rows,
)
from src.models.predict import ID2LABEL, LABEL2ID, MAX_TOKENS, THRESHOLDS_FILE, predict_probs

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # silences a harmless warning when batches are tokenised
# Hugging Face prints a long report each time a model loads (the new classifier layer is "missing", the unused
# word-prediction layers are "unexpected"). Both are normal here; new_model() checks the part that matters.
transformers.logging.set_verbosity_error()

BASE_MODEL = "distilbert/distilbert-base-uncased"  # uncased: the Kaggle Enron and Ling text is all lowercase
SEEDS = (42, 43, 44)
MAX_EPOCHS = 8
PATIENCE = 3
LEARNING_RATE = 3e-5
BATCH_SIZE = 16
WEIGHT_DECAY = 0.01
WARMUP_SHARE = 0.1
GRAD_CLIP = 1.0
POS_WEIGHT_CAP = 10.0
SELECT_THRESHOLD = 0.5          # the cutoff used to score an epoch, before thresholds are tuned


def set_seed(seed):
    """Fix every random number generator, so a run is repeatable up to GPU arithmetic."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def pos_weights(labels, cap=POS_WEIGHT_CAP):
    """Per tactic: negatives divided by positives, at most cap. A tactic with no positives gets cap."""
    positives = labels.sum(axis=0)
    negatives = len(labels) - positives
    return np.minimum(negatives / np.maximum(positives, 1), cap)


def weighted_bce(probs, labels, weight):
    """The same loss the training uses (BCEWithLogitsLoss with pos_weight), from probabilities, as a mean."""
    p = np.clip(probs, 1e-7, 1 - 1e-7)
    return float((-(weight * labels * np.log(p) + (1 - labels) * np.log(1 - p))).mean())


def new_model(model_name, device):
    """DistilBERT with a fresh 7-output layer, in multi-label mode, safetensors only.

    The only weights allowed to be missing from the base checkpoint are the new classification layers
    (pre_classifier and classifier). Anything else missing would mean the pre-trained part silently failed to
    load and we would be fine-tuning a random network.
    """
    model, info = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=len(TACTICS), id2label=ID2LABEL, label2id=LABEL2ID,
        problem_type="multi_label_classification", use_safetensors=True, output_loading_info=True)
    unexpected_missing = [k for k in info["missing_keys"] if not k.startswith(("pre_classifier.", "classifier."))]
    if unexpected_missing:
        raise SystemExit("the base model did not load: missing %s" % unexpected_missing[:5])
    return model.to(device)


def train_seed(args, seed, train, val, device, weight, keep_weights):
    """Train one seed with early stopping. Returns (summary, log rows, best-epoch validation probabilities, best weights)."""
    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = new_model(args.model, device)

    texts = train["text"].tolist()
    y_train = labels_of(train)
    y_val = labels_of(val)
    real = (val["origin"] == "real").to_numpy()
    val_texts = val["text"].tolist()

    def collate(indices):
        batch = tokenizer([texts[i] for i in indices], truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt")
        batch["labels"] = torch.tensor(y_train[indices])
        return batch

    loader = DataLoader(range(len(texts)), batch_size=args.batch_size, shuffle=True,
                        generator=torch.Generator().manual_seed(seed), collate_fn=collate)
    total_steps = args.epochs * len(loader)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=WEIGHT_DECAY)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(WARMUP_SHARE * total_steps), total_steps)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(weight, dtype=torch.float32, device=device))

    log, best, stale = [], None, 0
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        model.train()                                     # dropout on
        total = 0.0
        for batch in loader:
            labels = batch.pop("labels").to(device)
            batch = batch.to(device)
            loss = loss_fn(model(**batch).logits, labels)   # forward pass and loss
            optimizer.zero_grad()
            loss.backward()                                # backward pass: how each weight should change
            nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimizer.step()                               # change the weights a little
            scheduler.step()
            total += loss.item() * len(labels)
        train_loss = total / len(texts)

        probs = predict_probs(model, tokenizer, val_texts)
        val_loss = weighted_bce(probs[real], y_val[real], weight)
        score = macro_f1(y_val[real], probs[real] >= SELECT_THRESHOLD, TACTICS, MAIN_TACTICS)
        key = (score, -val_loss)                           # higher macro-F1 wins; equal F1: lower validation loss
        improved = best is None or key > best["key"]
        if improved:
            stale = 0
            best = {"key": key, "epoch": epoch, "probs": probs, "score": score, "val_loss": val_loss}
            if keep_weights:
                best["state"] = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
        log.append({"seed": seed, "epoch": epoch, "train_loss": round(train_loss, 5), "val_loss": round(val_loss, 5),
                    "val_macro_f1": round(score, 5)})
        print("  seed %d epoch %d/%d  train loss %.4f  validation loss %.4f  macro-F1 %.4f %s (%.0f s)" % (
            seed, epoch, args.epochs, train_loss, val_loss, score, "<- best so far" if improved else "", time.time() - started))
        if stale >= args.patience:
            print("  no improvement for %d epochs: stopping (early stopping)" % args.patience)
            break

    for row in log:
        row["selected"] = row["epoch"] == best["epoch"]
    summary = {"seed": seed, "best_epoch": best["epoch"], "epochs_run": len(log),
               "val_macro_f1": round(best["score"], 5), "val_loss": round(best["val_loss"], 5)}
    return summary, log, best["probs"], best.get("state")


def choose_thresholds(probs, y_val, real):
    """Tuned on real validation emails for the four main tactics; 0.5 for the three rare ones."""
    thresholds = {t: 0.5 for t in TACTICS}
    for tactic in MAIN_TACTICS:
        col = TACTICS.index(tactic)
        thresholds[tactic], _ = tune_threshold(probs[real, col], y_val[real, col])
    return thresholds


def run_condition(args, condition, table, device):
    """Train every seed of one condition and pick the best. Returns everything the output files need."""
    train = training_rows(table, condition)
    val = validation_rows(table)
    weight = pos_weights(labels_of(train))
    print("\n=== condition %s: %d training emails, %d validation emails ===" % (condition, len(train), len(val)))
    print("  pos_weight per tactic: %s" % ", ".join("%s %.2f" % (t, w) for t, w in zip(TACTICS, weight)))

    keep_weights = condition == "mix"
    logs, summaries, results = [], [], {}
    chosen = None
    for seed in args.seeds:
        summary, log, probs, state = train_seed(args, seed, train, val, device, weight, keep_weights)
        for row in log:
            logs.append({"condition": condition, **row})
        summaries.append({"condition": condition, **summary})
        results[seed] = (summary, probs, state)
        if chosen is None or (summary["val_macro_f1"], -summary["val_loss"]) > (results[chosen][0]["val_macro_f1"], -results[chosen][0]["val_loss"]):
            if chosen is not None:
                results[chosen] = (results[chosen][0], results[chosen][1], None)   # free the weights of the loser
            chosen = seed
        else:
            results[seed] = (summary, probs, None)
    for row in summaries:
        row["chosen"] = row["seed"] == chosen

    real = (val["origin"] == "real").to_numpy()
    summary, probs, state = results[chosen]
    thresholds = choose_thresholds(probs, labels_of(val), real)
    print("  chosen seed %d (epoch %d, macro-F1 %.4f); thresholds: %s" % (
        chosen, summary["best_epoch"], summary["val_macro_f1"], ", ".join("%s %.2f" % kv for kv in thresholds.items())))
    prob_frame = pd.DataFrame({"condition": condition, "id": val["id"], "origin": val["origin"]})
    for col, tactic in enumerate(TACTICS):
        prob_frame["p_" + tactic] = np.round(probs[:, col], 6)
    info = {"training_emails": len(train), "pos_weight": {t: round(float(w), 4) for t, w in zip(TACTICS, weight)},
            "chosen_seed": chosen, "chosen_epoch": summary["best_epoch"], "thresholds": thresholds}
    return logs, summaries, prob_frame, info, state, thresholds


def save_model(args, state, thresholds, folder):
    """Write the chosen weights, tokenizer, config and thresholds.json into folder."""
    model = new_model(args.model, "cpu")
    model.load_state_dict(state)
    folder.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(folder)            # model.safetensors + config.json
    AutoTokenizer.from_pretrained(args.model).save_pretrained(folder)
    (folder / THRESHOLDS_FILE).write_text(json.dumps(thresholds, indent=2) + "\n", encoding="utf-8")


def base_revision(model_name):
    """The commit of the Hugging Face base model that was used (the folder name in the download cache), or "unknown".

    Never raises: this only fills a record, and a failure here must not cost a finished training run.
    """
    try:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(model_name, "config.json")).parent.name
    except Exception:
        return "unknown (a local folder, or the Hub could not be reached)"


def git_commit():
    """The commit of the code that ran, or "unknown" outside a Git checkout."""
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def write_records(args, device_name, started, revision, logs, summaries, probs, conditions):
    """Write the four record files for the conditions finished so far (called again after each condition)."""
    pd.DataFrame(logs).to_csv(args.out / "tactic_training_log.csv", index=False)
    pd.DataFrame(summaries).to_csv(args.out / "tactic_seed_summary.csv", index=False)
    pd.concat(probs).to_csv(args.out / "tactic_val_probs.csv", index=False)
    run_info = {
        "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "minutes": round((time.time() - started) / 60, 1),
        "base_model": args.model, "base_model_revision": revision,
        "code_commit": git_commit(), "data_sha256": sha256_of_file(args.data),
        "versions": {"python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__,
                     "numpy": np.__version__, "pandas": pd.__version__},
        "device": device_name,
        "settings": {"seeds": args.seeds, "max_epochs": args.epochs, "patience": args.patience, "learning_rate": args.lr,
                     "batch_size": args.batch_size, "weight_decay": WEIGHT_DECAY, "warmup_share": WARMUP_SHARE,
                     "grad_clip": GRAD_CLIP, "pos_weight_cap": POS_WEIGHT_CAP, "max_tokens": MAX_TOKENS,
                     "selection": "macro-F1 over %s on real validation at threshold %.1f, ties to lower validation loss" % (
                         "+".join(MAIN_TACTICS), SELECT_THRESHOLD)},
        "conditions": conditions,
    }
    (args.out / "tactic_run_info.json").write_text(json.dumps(run_info, indent=2) + "\n", encoding="utf-8")


def main(argv):
    parser = argparse.ArgumentParser(description="Fine-tune DistilBERT on the seven tactics (Phase 6).")
    parser.add_argument("--data", type=Path, default=TACTIC_DATA_PARQUET, help="the upload table from src.models.dataset")
    parser.add_argument("--out", type=Path, required=True, help="output folder (created if missing)")
    parser.add_argument("--model", default=BASE_MODEL, help="base model: a Hugging Face id or a local folder")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--patience", type=int, default=PATIENCE)
    parser.add_argument("--lr", type=float, default=LEARNING_RATE)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--skip-real-only", action="store_true", help="train only the mix condition")
    args = parser.parse_args(argv)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    device_name = torch.cuda.get_device_name(0) if device == "cuda" else platform.processor() or platform.machine()
    print("PyTorch %s, transformers %s, device: %s (%s)" % (torch.__version__, transformers.__version__, device, device_name))
    if device == "cpu":
        print("WARNING: no GPU found. On Colab choose Runtime > Change runtime type > T4 GPU. Training on a CPU takes hours.")

    table = load_table(args.data)
    failed = [c for c in check_table(table, compare_phase5=False) if c[4] == "FAIL"]
    if failed:
        raise SystemExit("data checks failed (the first: %s %s = %s): refusing to train" % failed[0][:3])
    print("Data: %s, %d rows, sha256 %s" % (args.data, len(table), sha256_of_file(args.data)[:16]))

    started = time.time()
    revision = base_revision(args.model)
    all_logs, all_summaries, all_probs, conditions = [], [], [], {}
    for condition in CONDITIONS:
        if condition == "real_only" and args.skip_real_only:
            continue
        logs, summaries, probs, info, state, thresholds = run_condition(args, condition, table, device)
        all_logs += logs
        all_summaries += summaries
        all_probs.append(probs)
        conditions[condition] = info
        args.out.mkdir(parents=True, exist_ok=True)
        if condition == "mix":                        # saved as soon as it is done: a crash later cannot lose it
            save_model(args, state, thresholds, args.out / "tactic_model")
        write_records(args, device_name, started, revision, all_logs, all_summaries, all_probs, conditions)

    print("\nDone in %.1f minutes. Outputs in %s:" % ((time.time() - started) / 60, args.out))
    for path in sorted(args.out.rglob("*")):
        if path.is_file():
            print("  %-45s %8.2f MB" % (path.relative_to(args.out), path.stat().st_size / 1e6))


if __name__ == "__main__":
    main(sys.argv[1:])
