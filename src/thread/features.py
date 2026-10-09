"""Phase 9: the tactic probabilities and claims of thread messages, computed once and cached.

The thread signals compare messages with each other, so every message needs its seven tactic probabilities (the Phase 6
DistilBERT classifier) and its claims (the Phase 7 extractor). Both are slow compared with the rules (the classifier
needs the model folder, which exists only on the Mac; the extractor needs spaCy), so the results are saved per message key in
data/processed/thread_features/<name>.parquet and reused. A cache is thrown away when the claim pattern version, the spaCy model
or the tactic model's training run changes (the stamp beside it says which produced it). The cache is never committed: the claims hold
email text.

    from src.thread.features import attach_features, load_thresholds
    attach_features(messages, "train")        # fills message["tactics"] and message["claims"] for a list of message dictionaries

The imports of torch and spaCy are inside the functions, so the rest of the thread code (and its self-test) runs without them.
"""

import json

import pandas as pd
from tqdm import tqdm

from src.data.label_schema import TACTICS
from src.data.paths import TACTIC_MODEL_DIR, TACTIC_RUN_INFO_JSON, THREAD_FEATURES_DIR
from src.models.dataset import MAIN_TACTICS
from src.thread.signals import DEFAULT_THRESHOLDS

CHUNK = 400   # messages processed (and saved) at a time: a slow run must not lose its work


def load_thresholds(model_dir=TACTIC_MODEL_DIR):
    """({tactic: threshold} for the four main tactics, where it came from). Reads thresholds.json next to the weights if it is there."""
    path = model_dir / "thresholds.json"
    if path.exists():
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return {t: float(data[t]) for t in MAIN_TACTICS}, "artifacts/tactic_model/thresholds.json"
    return dict(DEFAULT_THRESHOLDS), "the Phase 6 values written into signals.py (no model folder here)"


def stamp():
    """What the cached features depend on: claim pattern version, spaCy model and the tactic model's training run."""
    from src.claims.extractor import MODEL_NAME, load_nlp
    from src.claims.patterns import PATTERN_VERSION

    finished = None
    if TACTIC_RUN_INFO_JSON.exists():
        with open(TACTIC_RUN_INFO_JSON, encoding="utf-8") as handle:
            finished = json.load(handle).get("finished_utc")
    return {"pattern_version": PATTERN_VERSION, "spacy_model": "%s %s" % (MODEL_NAME, load_nlp().meta["version"]), "tactic_run": finished}


def read_cache(name, current):
    """{key: (tactics, claims)} from the cache, or {} when there is none or it was made by other versions."""
    table, side = THREAD_FEATURES_DIR / ("%s.parquet" % name), THREAD_FEATURES_DIR / ("%s.json" % name)
    if not (table.exists() and side.exists()):
        return {}
    with open(side, encoding="utf-8") as handle:
        if json.load(handle) != current:
            return {}
    frame = pd.read_parquet(table)
    return {k: (json.loads(t), json.loads(c)) for k, t, c in zip(frame["key"], frame["tactics"], frame["claims"])}


def write_cache(name, current, cached):
    THREAD_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"key": list(cached), "tactics": [json.dumps(v[0]) for v in cached.values()],
                          "claims": [json.dumps(v[1]) for v in cached.values()]})
    frame.to_parquet(THREAD_FEATURES_DIR / ("%s.parquet" % name), index=False)
    with open(THREAD_FEATURES_DIR / ("%s.json" % name), "w", encoding="utf-8") as handle:
        json.dump(current, handle)


def attach_features(messages, name):
    """Set message['tactics'] ({tactic: probability}, all seven) and message['claims'] on every message. Keys must be unique."""
    current = stamp()
    cached = read_cache(name, current)
    todo = list({m["key"]: m for m in messages if m["key"] not in cached}.values())     # one message per key: equal keys mean equal text
    if todo:
        from src.claims.extractor import extract_many
        from src.models.predict import TacticClassifier

        classifier = TacticClassifier()
        print("    %d of %d messages need features (the rest come from the cache %s)" % (len(todo), len(messages), name))
        for start in tqdm(range(0, len(todo), CHUNK), desc="  features", unit=" chunks"):
            part = todo[start:start + CHUNK]
            texts = [m["redacted"] for m in part]
            probabilities = classifier.probabilities(texts)
            claims, _ = extract_many(texts)
            for m, row, found in zip(part, probabilities, claims):
                cached[m["key"]] = ({t: round(float(p), 4) for t, p in zip(TACTICS, row)}, found)
            write_cache(name, current, cached)
    for m in messages:
        m["tactics"], m["claims"] = cached[m["key"]]
    return messages
