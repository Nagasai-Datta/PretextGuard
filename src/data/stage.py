"""Load every source into one table, remove duplicate emails, and save it.

Run from the project root:
    python -m src.data.stage

Writes:
    data/processed/staged.parquet  one row per unique email (not committed: large, holds email text)
    results/staged_counts.csv      rows per source and category (committed; a table for the report)
    results/dedup_pairs.csv        duplicates removed, by source of the removed and the kept copy

Columns of staged.parquet:
    id, source, category, is_attack, has_full_headers, raw_ref, raw_headers, body_raw
(split.py adds the "split" column in the next step.)

Decisions (master document, Section 8.8):
- is_attack is True only for phishing and fraud; spam is not an attack.
- Emails with no readable text in the body are dropped: there is nothing for
  a text model to read.
- Duplicates: each body gets a fingerprint (SHA-256) of its letters and digits
  in lower case, so copies that differ only in spacing, line breaks or
  punctuation match. Of each group of copies, a copy with full headers is kept.
  This happens before the split: the same email in train and test would make
  every score look better than it is (leakage).
"""

import hashlib
import re

import pandas as pd
from tqdm import tqdm

from src.data.loaders import LOADERS
from src.data.paths import (
    DEDUP_PAIRS_CSV,
    PROCESSED_DIR,
    RESULTS_DIR,
    STAGED_COUNTS_CSV,
    STAGED_PARQUET,
    relative,
)

ATTACK_CATEGORIES = {"phishing", "fraud"}
COLUMNS = ["id", "source", "category", "is_attack", "has_full_headers", "raw_ref", "raw_headers", "body_raw"]


def body_fingerprint(text):
    """SHA-256 of the body's letters and digits in lower case, or None if it has none."""
    letters_and_digits = re.sub(r"[\W_]+", "", text.lower())  # \W = anything not a letter, digit or _
    if not letters_and_digits:
        return None
    return hashlib.sha256(letters_and_digits.encode("utf-8")).hexdigest()


def row_id(ref):
    """A short, stable row ID: the first 16 hex characters of the SHA-256 of raw_ref."""
    return hashlib.sha256(ref.encode("utf-8")).hexdigest()[:16]


def load_all():
    """Run every loader and return all records as one DataFrame."""
    records = []
    for name, loader in LOADERS:
        before = len(records)
        records.extend(tqdm(loader(), desc=f"  {name}", unit=" emails"))
        print(f"  {name}: {len(records) - before:,} emails read")
    return pd.DataFrame.from_records(records)


def category_conflicts(table):
    """Count duplicate groups whose copies disagree on category, for example 'ham/spam'."""
    categories_per_group = table.groupby("fingerprint")["category"].nunique()
    mixed_groups = categories_per_group[categories_per_group > 1].index
    mixed = table[table["fingerprint"].isin(mixed_groups)]
    if mixed.empty:
        return pd.Series(dtype=int)
    labels = mixed.groupby("fingerprint")["category"].agg(lambda c: "/".join(sorted(set(c))))
    return labels.value_counts()


def deduplicate(table):
    """Keep one row per fingerprint, preferring rows with full headers.

    Returns the kept rows in their original order, and a table counting the
    removed rows by (removed_source, kept_source).
    """
    # Full-header rows first; "stable" keeps the original order among equals.
    ordered = table.sort_values("has_full_headers", ascending=False, kind="stable")
    is_copy = ordered.duplicated("fingerprint", keep="first")
    kept = ordered[~is_copy]
    removed = ordered[is_copy]

    source_of_kept = kept.set_index("fingerprint")["source"]
    pairs = (
        removed.assign(kept_source=removed["fingerprint"].map(source_of_kept))
        .groupby(["source", "kept_source"])
        .size()
        .reset_index(name="rows")
        .rename(columns={"source": "removed_source"})
        .sort_values("rows", ascending=False)
    )
    return kept.sort_index(), pairs


def main():
    pd.set_option("display.width", 140)

    print("Reading sources")
    table = load_all()
    rows_read = len(table)

    table["fingerprint"] = table["body_raw"].map(body_fingerprint)
    no_text = table["fingerprint"].isna()
    print(f"\nDropped, no readable text in the body: {no_text.sum():,}")
    if no_text.any():
        print(table.loc[no_text, "source"].value_counts().to_string())
    table = table[~no_text]

    conflicts = category_conflicts(table)
    table, pairs = deduplicate(table)

    table["is_attack"] = table["category"].isin(ATTACK_CATEGORIES)
    table["id"] = table["raw_ref"].map(row_id)
    if not table["id"].is_unique:
        raise SystemExit("Two rows share an id; raw_ref values must be unique.")
    table = table[COLUMNS].reset_index(drop=True)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_parquet(STAGED_PARQUET, index=False)
    counts = pd.crosstab(table["source"], table["category"], margins=True, margins_name="total")
    counts.to_csv(STAGED_COUNTS_CSV)
    pairs.to_csv(DEDUP_PAIRS_CSV, index=False)

    print(f"\nRows read:           {rows_read:,}")
    print(f"No text, dropped:    {no_text.sum():,}")
    print(f"Duplicates removed:  {pairs['rows'].sum():,}")
    print(f"Rows kept:           {len(table):,}")
    print(f"Attack rows:         {table['is_attack'].sum():,} (phishing + fraud)")

    print("\nRows per source and category")
    print(counts.to_string())

    print("\nDuplicates removed (removed copy's source -> kept copy's source)")
    print(pairs.to_string(index=False) if not pairs.empty else "none")

    print("\nDuplicate groups whose copies disagree on category (the kept copy's category is used)")
    print(conflicts.to_string() if not conflicts.empty else "none")

    size_mb = STAGED_PARQUET.stat().st_size / 1024**2
    print(f"\nSaved {relative(STAGED_PARQUET)} ({size_mb:.1f} MB)")
    print(f"Saved {relative(STAGED_COUNTS_CSV)}")
    print(f"Saved {relative(DEDUP_PAIRS_CSV)}")


if __name__ == "__main__":
    main()
