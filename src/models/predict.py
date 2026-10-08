"""Phase 6: load the trained tactic classifier and turn emails into seven tactic probabilities.

The model was trained on Colab (src/models/train.py) and its files sit in artifacts/tactic_model/. This module
runs it on the Mac's CPU, one email at a time or in batches, and never touches the network:

    from src.models.predict import TacticClassifier
    classifier = TacticClassifier()                     # load once (the API does this at start-up)
    classifier.predict(body_redacted)                   # {"urgency": {"probability": 0.91, "threshold": 0.4, "fired": True}, ...}

    python -m src.models.predict "This is the CFO. Wire it today and tell no one."     # command-line try-out

train.py and validate.py reuse predict_probs, so training, Colab validation and Mac validation all run the same code.

Safety of the model files:
- Weights are read from a .safetensors file (plain numbers). The older .bin format is a pickle, which can run
  code when loaded; use_safetensors=True refuses it.
- local_files_only=True: nothing is downloaded at run time, and trust_remote_code is never set, so no code
  from a model folder is ever executed.
- load_tactic_model checks that the model's seven outputs are in the project's tactic order, so a model saved
  with a different order cannot silently attach urgency's probability to authority.
- Text is cut at 2,000 characters (model_text) and then at 512 tokens, so input size cannot slow the model down.
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src.data.label_schema import TACTICS
from src.data.paths import TACTIC_MODEL_DIR
from src.models.dataset import model_text

MAX_TOKENS = 512          # DistilBERT cannot read more than 512 word pieces
BATCH_SIZE = 16
THRESHOLDS_FILE = "thresholds.json"
ID2LABEL = {i: t for i, t in enumerate(TACTICS)}
LABEL2ID = {t: i for i, t in enumerate(TACTICS)}


def read_thresholds(model_dir):
    """The per-tactic thresholds saved next to the weights: {tactic: number between 0 and 1}, all seven present."""
    with open(model_dir / THRESHOLDS_FILE, encoding="utf-8") as handle:
        thresholds = json.load(handle)
    if set(thresholds) != set(TACTICS) or not all(isinstance(v, (int, float)) and 0 < v < 1 for v in thresholds.values()):
        raise ValueError("%s must hold one number between 0 and 1 for each of %s" % (THRESHOLDS_FILE, TACTICS))
    return {t: float(thresholds[t]) for t in TACTICS}


def load_tactic_model(model_dir=TACTIC_MODEL_DIR, device="cpu"):
    """Load (model, tokenizer, thresholds) from a folder written by train.py. Offline, safetensors only."""
    model_dir = Path(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True, use_safetensors=True)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    order = [model.config.id2label[i] for i in range(model.config.num_labels)]
    if order != list(TACTICS):
        raise ValueError("the model's outputs are %s, expected %s" % (order, list(TACTICS)))
    return model.to(device).eval(), tokenizer, read_thresholds(model_dir)


def predict_probs(model, tokenizer, texts, batch_size=BATCH_SIZE):
    """Probabilities (items x 7, column order = TACTICS) for already-prepared texts, in the order given.

    Each tactic gets its own sigmoid, so the seven numbers are independent and do not add up to 1.
    Padding is per batch (dynamic): a batch is only as long as its longest email.
    """
    texts = list(texts)
    device = next(model.parameters()).device
    model.eval()                      # dropout off
    chunks = []
    with torch.inference_mode():      # no gradients are recorded: faster and lighter
        for start in range(0, len(texts), batch_size):
            batch = tokenizer(texts[start:start + batch_size], truncation=True, max_length=MAX_TOKENS,
                              padding=True, return_tensors="pt").to(device)
            chunks.append(torch.sigmoid(model(**batch).logits).cpu().numpy())
    return np.concatenate(chunks).astype(np.float64) if chunks else np.zeros((0, len(TACTICS)))


class TacticClassifier:
    """The trained model, loaded once. Give it body_redacted text; it applies the same cut as training."""

    def __init__(self, model_dir=TACTIC_MODEL_DIR, device="cpu"):
        self.model, self.tokenizer, self.thresholds = load_tactic_model(model_dir, device)

    def probabilities(self, bodies, batch_size=BATCH_SIZE):
        """Probabilities (items x 7) for a list of body_redacted strings."""
        return predict_probs(self.model, self.tokenizer, [model_text(b) for b in bodies], batch_size)

    def predict(self, body):
        """{tactic: {"probability", "threshold", "fired"}} for one body_redacted string."""
        probs = self.probabilities([body])[0]
        return {t: {"probability": float(p), "threshold": self.thresholds[t], "fired": bool(p >= self.thresholds[t])}
                for t, p in zip(TACTICS, probs)}


def main(argv):
    text = " ".join(argv) if argv else sys.stdin.read()
    if not text.strip():
        raise SystemExit('Usage: python -m src.models.predict "email body"   (or pipe the text in)')
    result = TacticClassifier().predict(text)
    print("%-13s %11s %9s  %s" % ("tactic", "probability", "threshold", "fired"))
    for tactic, row in result.items():
        print("%-13s %11.3f %9.2f  %s" % (tactic, row["probability"], row["threshold"], "YES" if row["fired"] else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
