"""Phase 13: loading and running the two N1 DistilBERT models (attack against not-attack, one output each). Used by n1_train.py (Colab) and ablation_n1.py (the Mac).

Model A is trained on the RAW view of a body (links, addresses and file names as they were, src/preprocess keeps them in body_clean); model B on the REDACTED view (body_redacted, where links become
[URL] and so on). Everything else is identical, so any difference between them is the effect of the redaction.

Text is cut at 4,000 characters before it is tokenised (a bound on the work an attacker-sized email can cause) and at 512 word pieces by the tokenizer.
"""

import numpy as np
import torch
import transformers
from transformers import AutoModelForSequenceClassification, AutoTokenizer

transformers.logging.set_verbosity_error()      # the load report of a new classification layer is expected here; new_model() checks the part that matters

MAX_TOKENS = 512
MAX_CHARS = 4000
BATCH_SIZE = 32
HEAD_PREFIXES = ("pre_classifier.", "classifier.")      # the only weights a base checkpoint may lack: the new output layers


def clip(text):
    """The text the models read: at most MAX_CHARS characters; anything that is not a string is empty."""
    return text[:MAX_CHARS] if isinstance(text, str) else ""


def new_model(base, device):
    """DistilBERT with a fresh single-output layer, safetensors only; stops if anything but the new layers failed to load."""
    model, info = AutoModelForSequenceClassification.from_pretrained(base, num_labels=1, use_safetensors=True, output_loading_info=True)
    unexpected = [k for k in info["missing_keys"] if not k.startswith(HEAD_PREFIXES)]
    if unexpected:
        raise SystemExit("the base model did not load: missing %s" % unexpected[:5])
    return model.to(device)


def load(model_dir, device="cpu"):
    """(model, tokenizer) of a model written by n1_train.py. Offline, safetensors only, exactly one output."""
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True, use_safetensors=True)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    if model.config.num_labels != 1:
        raise ValueError("%s: an N1 model has exactly one output, this one has %d" % (model_dir, model.config.num_labels))
    return model.to(device).eval(), tokenizer


def predict(model, tokenizer, texts, batch_size=BATCH_SIZE, use_fp16=False):
    """Attack probabilities (a float array, one per text, in the order given). Texts are processed shortest first so a batch is not padded to one long email; the order is restored."""
    texts = [clip(t) for t in texts]
    device = next(model.parameters()).device
    model.eval()
    order = np.argsort([len(t) for t in texts], kind="stable")
    out = np.zeros(len(texts), dtype=np.float64)
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            index = order[start:start + batch_size]
            batch = tokenizer([texts[i] for i in index], truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt").to(device)
            if use_fp16 and device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(**batch).logits
            else:
                logits = model(**batch).logits
            out[index] = torch.sigmoid(logits[:, 0].float()).cpu().numpy()
    return out
