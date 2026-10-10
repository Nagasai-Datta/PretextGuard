"""Phase 13: fine-tune the two N1 models, A on the raw view of an email body and B on the redacted view. Runs on Colab's GPU (also works on a CPU, slowly).

Run from the project root (the notebook notebooks/phase13_n1_models.ipynb does this for you):
    python -m src.eval.n1_train --data PATH_TO/n1_data.parquet --out OUTPUT_FOLDER

Reads  the one upload table made by src.eval.n1_data (a training sample and a validation sample, train and validation rows only; a test row stops the run)
Writes into the output folder:
    n1_model_a/ and n1_model_b/   the chosen weights (.safetensors), tokenizer and config of each model
    n1_training_log.csv           one row per model, seed and epoch: training loss, validation loss, validation attack-class precision, recall and F1
    n1_val_probs.csv              the chosen models' attack probabilities on the validation sample (the Mac checks its own against these)
    n1_run_info.json              settings, library versions, GPU, data checksum, code commit, base-model revision and the chosen seed and epoch of each model

Both models are trained exactly alike, on the same emails; only the text they read differs:
    A  reads text_raw       (links, addresses and file names as they were)
    B  reads text_redacted  (links, addresses, domains and file names replaced by [URL] [EMAIL] [DOMAIN] [FILE])
How one training run works is the same as in src/models/train.py: tokenise (up to 512 word pieces), forward pass, binary cross-entropy with a weight on the rarer class, backward pass, an AdamW step
(learning rate 3e-5, 10% warm-up, linear decay), and after every epoch a score on the validation sample. There is one output (attack or not), so one threshold: 0.5, fixed, never tuned.
The epoch and the seed of each model are chosen by the validation attack-class F1 on that model's own view (ties go to the lower validation loss). Two seeds per model, two epochs.
The validation sample is the only data besides the training sample that this script sees; the test split never reaches Colab.

Mixed precision (fp16) is used on the GPU to halve the time; --no-fp16 turns it off. GPU arithmetic is not bit-exact between runs: 'same seed' means similar results, not identical ones.
The labels are the corpus labels (phishing and fraud corpora against ham and spam corpora), not LLM labels.
"""

import argparse
import json
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
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

from src.eval.n1_model import MAX_TOKENS, clip, new_model, predict
from src.eval.stats import f1_counts

BASE_MODEL = "distilbert/distilbert-base-uncased"       # uncased: the Kaggle Enron and Ling text is all lowercase
VIEWS = {"a": ("text_raw", "n1_model_a"), "b": ("text_redacted", "n1_model_b")}
SEEDS = (42, 43)
EPOCHS = 2
LEARNING_RATE = 3e-5
BATCH_SIZE = 16
WEIGHT_DECAY = 0.01
WARMUP_SHARE = 0.1
GRAD_CLIP = 1.0
POS_WEIGHT_CAP = 10.0
THRESHOLD = 0.5


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def sha256_of_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def base_revision(model_name):
    try:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(model_name, "config.json")).parent.name
    except Exception:
        return "unknown (a local folder, or the Hub could not be reached)"


def validation_scores(probabilities, labels):
    """Attack-class precision, recall and F1 at the fixed threshold, and the mean binary cross-entropy, on the validation sample."""
    predicted = probabilities >= THRESHOLD
    truth = labels.astype(bool)
    tp, fp, fn = int((truth & predicted).sum()), int((~truth & predicted).sum()), int((truth & ~predicted).sum())
    p = np.clip(probabilities, 1e-7, 1 - 1e-7)
    loss = float(-(labels * np.log(p) + (1 - labels) * np.log(1 - p)).mean())
    return {"precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0, "f1": float(f1_counts(tp, fp, fn)), "loss": loss}


def train_seed(args, view_column, seed, train, validation, device, weight):
    """Train one seed with the epochs asked for. Returns (log rows, best epoch's summary, best weights, best epoch's validation probabilities)."""
    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = new_model(args.model, device)
    texts = [clip(t) for t in train[view_column]]
    labels = train["is_attack"].to_numpy(dtype=np.float32)
    val_texts, val_labels = [clip(t) for t in validation[view_column]], validation["is_attack"].to_numpy(dtype=np.float64)

    def collate(indices):
        batch = tokenizer([texts[i] for i in indices], truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt")
        batch["labels"] = torch.tensor(labels[indices])
        return batch

    loader = DataLoader(range(len(texts)), batch_size=args.batch_size, shuffle=True, generator=torch.Generator().manual_seed(seed), collate_fn=collate)
    total_steps = args.epochs * len(loader)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=WEIGHT_DECAY)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(WARMUP_SHARE * total_steps), total_steps)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([weight], dtype=torch.float32, device=device))
    fp16 = args.fp16 and device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=fp16)
    log, best = [], None
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        model.train()
        total = 0.0
        for batch in loader:
            target = batch.pop("labels").to(device)
            batch = batch.to(device)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=fp16):
                logits = model(**batch).logits[:, 0]
            loss = loss_fn(logits.float(), target)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            total += loss.item() * len(target)
        train_loss = total / len(texts)
        probabilities = predict(model, tokenizer, val_texts, use_fp16=fp16)
        scores = validation_scores(probabilities, val_labels)
        key = (scores["f1"], -scores["loss"])
        improved = best is None or key > best["key"]
        if improved:
            best = {"key": key, "epoch": epoch, "scores": scores, "probabilities": probabilities, "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
        log.append({"seed": seed, "epoch": epoch, "train_loss": round(train_loss, 5), "val_loss": round(scores["loss"], 5), "val_precision": round(scores["precision"], 5),
                    "val_recall": round(scores["recall"], 5), "val_f1": round(scores["f1"], 5)})
        print("  seed %d epoch %d/%d  train loss %.4f  validation loss %.4f  attack F1 %.4f (precision %.3f, recall %.3f) %s (%.0f s)" % (
            seed, epoch, args.epochs, train_loss, scores["loss"], scores["f1"], scores["precision"], scores["recall"], "<- best so far" if improved else "", time.time() - started))
    for row in log:
        row["selected_in_seed"] = row["epoch"] == best["epoch"]
    return log, best


def save_model(args, state, folder):
    model = new_model(args.model, "cpu")
    model.load_state_dict(state)
    folder.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(folder)
    AutoTokenizer.from_pretrained(args.model).save_pretrained(folder)


def main(argv):
    parser = argparse.ArgumentParser(description="Fine-tune the two N1 models (Phase 13).")
    parser.add_argument("--data", type=Path, required=True, help="the upload table from src.eval.n1_data")
    parser.add_argument("--out", type=Path, required=True, help="output folder (created if missing)")
    parser.add_argument("--model", default=BASE_MODEL, help="base model: a Hugging Face id or a local folder")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--lr", type=float, default=LEARNING_RATE)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--views", nargs="+", choices=sorted(VIEWS), default=sorted(VIEWS), help="a = raw view, b = redacted view")
    parser.add_argument("--no-fp16", dest="fp16", action="store_false", help="full precision (slower)")
    args = parser.parse_args(argv)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    device_name = torch.cuda.get_device_name(0) if device == "cuda" else platform.processor() or platform.machine()
    print("PyTorch %s, transformers %s, device: %s (%s), fp16 %s" % (torch.__version__, transformers.__version__, device, device_name, args.fp16 and device == "cuda"))
    if device == "cpu":
        print("WARNING: no GPU found. On Colab choose Runtime > Change runtime type > T4 GPU. Training on a CPU takes hours.")
    table = pd.read_parquet(args.data)
    if set(table["split"]) != {"train", "validation"}:
        raise SystemExit("the data file must hold train and validation rows only (it holds %s): the test split never reaches this script" % sorted(set(table["split"])))
    if not table["id"].is_unique or set(table[table["split"] == "train"]["id"]) & set(table[table["split"] == "validation"]["id"]):
        raise SystemExit("the data file repeats an id or has an id in both splits")
    train, validation = table[table["split"] == "train"].reset_index(drop=True), table[table["split"] == "validation"].reset_index(drop=True)
    positives = float(train["is_attack"].sum())
    weight = min((len(train) - positives) / max(positives, 1.0), POS_WEIGHT_CAP)
    print("Data: %d training emails (%d attacks, pos_weight %.2f), %d validation emails (%d attacks), sha256 %s" % (
        len(train), positives, weight, len(validation), validation["is_attack"].sum(), sha256_of_file(args.data)[:16]))
    args.out.mkdir(parents=True, exist_ok=True)

    started = time.time()
    revision = base_revision(args.model)
    logs, probs, chosen = [], [], {}
    for key in args.views:
        column, folder = VIEWS[key]
        print("\n=== model %s: reads %s ===" % (key.upper(), column))
        best_overall = None
        for seed in args.seeds:
            log, best = train_seed(args, column, seed, train, validation, device, weight)
            logs += [{"model": key.upper(), **row} for row in log]
            if best_overall is None or best["key"] > best_overall["best"]["key"]:
                best_overall = {"seed": seed, "best": best}
        best = best_overall["best"]
        print("  chosen: seed %d, epoch %d, validation attack F1 %.4f" % (best_overall["seed"], best["epoch"], best["scores"]["f1"]))
        save_model(args, best["state"], args.out / folder)
        chosen[key.upper()] = {"view": column, "seed": best_overall["seed"], "epoch": best["epoch"], "validation_attack_f1": round(best["scores"]["f1"], 5),
                               "validation_precision": round(best["scores"]["precision"], 5), "validation_recall": round(best["scores"]["recall"], 5)}
        probs.append(pd.DataFrame({"model": key.upper(), "id": validation["id"], "probability": np.round(best["probabilities"], 6)}))
        pd.DataFrame(logs).to_csv(args.out / "n1_training_log.csv", index=False)
        pd.concat(probs).to_csv(args.out / "n1_val_probs.csv", index=False)

    info = {"finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "minutes": round((time.time() - started) / 60, 1), "base_model": args.model, "base_model_revision": revision,
            "code_commit": git_commit(), "data_sha256": sha256_of_file(args.data),
            "versions": {"python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__, "numpy": np.__version__, "pandas": pd.__version__},
            "device": device_name, "fp16": bool(args.fp16 and device == "cuda"),
            "settings": {"seeds": args.seeds, "epochs": args.epochs, "learning_rate": args.lr, "batch_size": args.batch_size, "weight_decay": WEIGHT_DECAY, "warmup_share": WARMUP_SHARE,
                         "grad_clip": GRAD_CLIP, "pos_weight": round(weight, 4), "pos_weight_cap": POS_WEIGHT_CAP, "max_tokens": MAX_TOKENS, "threshold": THRESHOLD,
                         "selection": "validation attack-class F1 on the model's own view at threshold %.1f, ties to the lower validation loss" % THRESHOLD},
            "training_emails": len(train), "training_attacks": int(positives), "validation_emails": len(validation), "chosen": chosen}
    (args.out / "n1_run_info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print("\nDone in %.1f minutes. Outputs in %s:" % ((time.time() - started) / 60, args.out))
    for path in sorted(args.out.rglob("*")):
        if path.is_file():
            print("  %-60s %8.1f MB" % (path.relative_to(args.out), path.stat().st_size / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
