"""Phase 6: the table the tactic classifier trains on, built once on the Mac and uploaded to Colab.

Run from the project root (after Phases 2 and 5):
    python -m src.models.dataset

Reads  data/labelled/labels.csv, data/processed/cleaned.parquet (the text of the labelled real emails)
       and data/synthetic/synthetic.csv
Writes data/processed/tactic_data.parquet   TRAIN AND VALIDATION ROWS ONLY: one row per email with the model's
                                            input text and the seven tactic labels (never committed: full email text)
       results/tactic_data_counts.csv       items and positive labels per origin, split and tactic (committed, counts only)

Why this file exists. Colab never sees the project's data folders, only this one file, which you upload to Google
Drive. It holds no test rows, so test emails and test labels cannot reach the training code (the test labels are used
once, in Phase 13). The model reads exactly the text the annotators labelled: body_redacted cut at 2,000 characters
(prepare_text in src/data/label_schema.py), without the " [TRUNCATED]" note, which only marks long emails and could
become a shortcut the model learns instead of the tactic.

Columns: id, origin ("real" or "synthetic"), group (a real email's category, or a synthetic email's role: attack or
benign), split, text, tactic_authority ... tactic_secrecy (0 or 1).

Other modules import from here: train.py and validate.py use training_rows, validation_rows, labels_of, check_table
and load_table, and Phase 13 will use model_text on the test split. This file never imports torch, so the table can
be built before PyTorch is installed.
"""

import hashlib

import numpy as np
import pandas as pd

from src.data.label_schema import TACTICS, prepare_text
from src.data.paths import (
    CLEANED_PARQUET,
    LABEL_COUNTS_CSV,
    LABELS_CSV,
    RESULTS_DIR,
    SYNTHETIC_COUNTS_CSV,
    SYNTHETIC_CSV,
    TACTIC_DATA_COUNTS_CSV,
    TACTIC_DATA_PARQUET,
    relative,
)

TACTIC_COLUMNS = ["tactic_" + t for t in TACTICS]

# The four tactics with at least 10 real positives in validation and in test (results/label_counts.csv): the only
# ones that can get a real-email F1, so the only ones that choose the epoch, the seed and the thresholds.
MAIN_TACTICS = ("authority", "urgency", "scarcity", "secrecy")
# The other three are counts only on real emails; they learn almost only from synthetic text and keep threshold 0.5.
RARE_TACTICS = tuple(t for t in TACTICS if t not in MAIN_TACTICS)

CONDITIONS = ("mix", "real_only")   # mix = real + synthetic training emails; real_only = the comparison run
UPLOAD_SPLITS = ("train", "validation")  # the test split never goes to Colab
TRUNCATED_NOTE = " [TRUNCATED]"


def model_text(body):
    """The text DistilBERT reads for one email: what the annotators saw, minus the truncation note."""
    return prepare_text(body).removesuffix(TRUNCATED_NOTE)


def read_real(splits):
    """The labelled real emails of the given splits, with their text taken from cleaned.parquet."""
    labels = pd.read_csv(LABELS_CSV, dtype={"id": str})
    labels = labels[labels["split"].isin(splits)]
    cleaned = pd.read_parquet(CLEANED_PARQUET, columns=["id", "body_redacted"], filters=[("id", "in", labels["id"].tolist())])
    merged = labels.merge(cleaned, on="id", how="left", validate="one_to_one")
    missing = int(merged["body_redacted"].isna().sum())
    if missing:
        raise SystemExit("%d labelled emails are missing from cleaned.parquet: rerun the Phase 2 build" % missing)
    return pd.DataFrame({
        "id": merged["id"], "origin": "real", "group": merged["category"], "split": merged["split"],
        "text": merged["body_redacted"].map(model_text), **{c: merged[c].astype(int) for c in TACTIC_COLUMNS},
    })


def read_synthetic(splits):
    """The synthetic attack and benign-twin emails of the given splits (their text is already redacted)."""
    synthetic = pd.read_csv(SYNTHETIC_CSV, dtype={"id": str})
    synthetic = synthetic[synthetic["split"].isin(splits)]
    return pd.DataFrame({
        "id": synthetic["id"], "origin": "synthetic", "group": synthetic["role"], "split": synthetic["split"],
        "text": synthetic["body_redacted"].map(model_text), **{c: synthetic[c].astype(int) for c in TACTIC_COLUMNS},
    })


def load_table(path=TACTIC_DATA_PARQUET):
    """Read the upload table back (on the Mac or on Colab)."""
    return pd.read_parquet(path)


def training_rows(table, condition):
    """The rows a condition trains on: mix = all train rows, real_only = the real train rows."""
    if condition not in CONDITIONS:
        raise ValueError("condition must be one of %s" % (CONDITIONS,))
    rows = table[table["split"] == "train"]
    if condition == "real_only":
        rows = rows[rows["origin"] == "real"]
    return rows.sort_values("id").reset_index(drop=True)


def validation_rows(table):
    """All validation rows (real and synthetic) in a fixed order, sorted by id, so Colab and the Mac batch alike."""
    return table[table["split"] == "validation"].sort_values("id").reset_index(drop=True)


def labels_of(rows):
    """The seven tactic labels of the rows as a float32 matrix (items x 7), column order = TACTICS."""
    return rows[TACTIC_COLUMNS].to_numpy(dtype=np.float32)


def sha256_of_file(path):
    """SHA-256 of a file's bytes: proves Colab trained on the very file the Mac holds."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def count_rows(table):
    """Long-format counts: for each origin and split, the items and the positives of every tactic."""
    rows = []
    for (origin, split), part in table.groupby(["origin", "split"]):
        for tactic, column in zip(TACTICS, TACTIC_COLUMNS):
            rows.append({"origin": origin, "split": split, "tactic": tactic,
                         "positives": int(part[column].sum()), "items": int(len(part))})
    return pd.DataFrame(rows)


def _phase5_positives():
    """Real and synthetic positives per split and tactic as Phase 5 recorded them (None where the file is missing)."""
    real = synthetic = None
    if LABEL_COUNTS_CSV.exists():
        counts = pd.read_csv(LABEL_COUNTS_CSV)
        counts = counts[(counts["group_type"] == "split") & (counts["kind"] == "tactic")]
        real = {(r.group, r.label): int(r.positives) for r in counts.itertuples()}
    if SYNTHETIC_COUNTS_CSV.exists():
        counts = pd.read_csv(SYNTHETIC_COUNTS_CSV)
        synthetic = {(r.group, r.label): int(r.value) for r in counts.itertuples()}
    return real, synthetic


def check_table(table, compare_phase5=True):
    """PASS/FAIL checks on the upload table. Returns rows of (check, item, value, expected, status)."""
    rows = []

    def add(check, item, value, expected, passed):
        rows.append((check, item, value, expected, "PASS" if passed else "FAIL"))

    splits = sorted(table["split"].unique())
    add("no_test_rows", "splits in the file", "+".join(splits), "train and validation only", set(splits) <= set(UPLOAD_SPLITS))
    add("unique_ids", "duplicate ids", int(table["id"].duplicated().sum()), "0", not table["id"].duplicated().any())
    empty = int((table["text"].str.strip() == "").sum())
    add("text_present", "empty texts", empty, "0", empty == 0)
    binary = bool(table[TACTIC_COLUMNS].isin([0, 1]).all().all())
    add("labels_binary", "label values", "0 or 1" if binary else "other values", "0 or 1", binary)

    validation = table[(table["split"] == "validation") & (table["origin"] == "real")]
    for tactic in TACTICS:
        positives = int(validation["tactic_" + tactic].sum())
        main = tactic in MAIN_TACTICS
        add("main_tactics", "%s: real validation positives" % tactic, positives,
            ">= 10 (main tactic)" if main else "< 10 (rare tactic)", (positives >= 10) == main)

    synthetic = table[table["origin"] == "synthetic"]
    attacks = synthetic[synthetic["group"] == "attack"]
    twins = synthetic[synthetic["group"] == "benign"]
    add("twins_have_no_tactic", "benign twins with a tactic", int(twins[TACTIC_COLUMNS].to_numpy().sum()), "0",
        int(twins[TACTIC_COLUMNS].to_numpy().sum()) == 0)
    quiet = int((attacks[TACTIC_COLUMNS].sum(axis=1) == 0).sum())
    add("attacks_have_a_tactic", "synthetic attacks with no tactic", quiet, "0", quiet == 0)

    if compare_phase5:
        real_counts, synthetic_counts = _phase5_positives()
        for split in sorted(set(splits) & set(UPLOAD_SPLITS)):
            for tactic, column in zip(TACTICS, TACTIC_COLUMNS):
                part = table[(table["split"] == split) & (table["origin"] == "real")]
                if real_counts is not None and (split, tactic) in real_counts:
                    add("matches_phase5", "real %s %s positives" % (split, tactic), int(part[column].sum()),
                        str(real_counts[(split, tactic)]), int(part[column].sum()) == real_counts[(split, tactic)])
                part = synthetic[synthetic["split"] == split]
                key = (split, "tactic_" + tactic)
                if synthetic_counts is not None and key in synthetic_counts:
                    add("matches_phase5", "synthetic %s %s positives" % (split, tactic), int(part[column].sum()),
                        str(synthetic_counts[key]), int(part[column].sum()) == synthetic_counts[key])
    return rows


def print_checks(checks):
    """Print check rows; a check name with more than three rows, all passing, is shown as one line."""
    names = list(dict.fromkeys(c[0] for c in checks))
    for name in names:
        rows = [c for c in checks if c[0] == name]
        if len(rows) > 3 and all(r[4] == "PASS" for r in rows):
            print("  PASS %-22s all %d items" % (name, len(rows)))
            continue
        for check, item, value, expected, status in rows:
            print("  %-4s %-22s %-40s %s%s" % (status, check, item, value, " (expected %s)" % expected if expected else ""))


def main():
    pd.set_option("display.width", 200)
    print("Reading labels, cleaned bodies and synthetic emails (train and validation only) ...")
    real = read_real(UPLOAD_SPLITS)
    synthetic = read_synthetic(UPLOAD_SPLITS)
    table = pd.concat([real, synthetic], ignore_index=True)

    empty = table["text"].str.strip() == ""
    if empty.any():
        print("  %d emails have no text after cutting and are left out" % int(empty.sum()))
        table = table[~empty]
    table = table.sort_values(["origin", "split", "id"]).reset_index(drop=True)

    counts = count_rows(table)
    wide = counts.pivot_table(index=["origin", "split"], columns="tactic", values="positives", aggfunc="first")[list(TACTICS)]
    wide.insert(0, "items", counts.groupby(["origin", "split"])["items"].first())
    print("\nItems and positive labels per origin and split:")
    print(wide.to_string())

    words = table["text"].str.split().str.len()
    print("\nWords per email: median %d, 90th percentile %d, longest %d" % (words.median(), words.quantile(0.9), words.max()))

    checks = check_table(table)
    print("\nChecks:")
    print_checks(checks)
    failed = [c for c in checks if c[4] == "FAIL"]
    if failed:
        raise SystemExit("%d checks failed: the table was not written" % len(failed))

    TACTIC_DATA_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(TACTIC_DATA_PARQUET, index=False)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(TACTIC_DATA_COUNTS_CSV, index=False)
    print("\nWrote %s (%d rows, %.1f MB, sha256 %s)" % (
        relative(TACTIC_DATA_PARQUET), len(table), TACTIC_DATA_PARQUET.stat().st_size / 1e6, sha256_of_file(TACTIC_DATA_PARQUET)[:16]))
    print("Wrote %s" % relative(TACTIC_DATA_COUNTS_CSV))
    print("\nNext: upload %s to Google Drive (folder pretextguard). It holds full email text: never commit it." % relative(TACTIC_DATA_PARQUET))


if __name__ == "__main__":
    main()
