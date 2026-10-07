"""Phase 5: draw the labelled sample and write the annotation batches.

Run from the project root (after the Phase 2 script):
    python -m src.data.batches

Reads  data/processed/cleaned.parquet (id, source, category, split, body_redacted; all three splits,
       because validation and test items need labels too: labelling is not tuning)
Writes data/labelled/sample.csv           the 700 emails drawn: ids and group only, never email text (committed)
       data/labelled/batches/batch_NNN.txt  the full prompt for each batch of 20 emails (NOT committed:
                                          it holds email text, and phishing_pot's licence forbids redistribution)
       data/labelled/annotators.csv       one row per chat service; fill in the model name before annotating
       results/sample_counts.csv          drawn and eligible emails per source, category and split (committed)

The sample is a fixed allocation per source and category (ALLOCATION below), not proportional, so small
sources are not drowned out. Inside each stratum the emails come from all three splits in 60/20/20
shares, picked by the order of SHA-256(seed, id), so the draw is identical on every machine. No keyword
hit is used to pick any email: the Phase 4 results showed the baseline fires on almost no real
reciprocity or social-proof attacks, so selecting by it would pick false positives.

Batches mix categories (a second hash orders the emails), so no chat ever sees twenty attacks in a row.
Each email gets a short local id (b007_03) for the chat to copy; sample.csv maps it back to the real id.
"""

import csv
import hashlib
import sys
from pathlib import Path

import pandas as pd

from src.data.label_schema import ALL_ANNOTATORS, BATCH_SIZE, MIN_WORDS, prepare_text
from src.data.paths import (
    ANNOTATORS_CSV,
    BATCHES_DIR,
    CLEANED_PARQUET,
    LABELLED_DIR,
    RESULTS_DIR,
    SAMPLE_COUNTS_CSV,
    SAMPLE_CSV,
    relative,
)
from src.data.prompts import annotation_prompt, instructions

SEED = 42
SPLITS = ("train", "validation", "test")
SPLIT_SHARES = (0.6, 0.2, 0.2)

# (source, category) -> number of emails: 450 attacks, 150 ham, 100 spam.
ALLOCATION = [
    (("phishing_pot", "phishing"), 150), (("nazario", "phishing"), 150), (("kaggle_nigerian_fraud", "fraud"), 150),
    (("kaggle_enron", "ham"), 50), (("apache_kafka_users", "ham"), 15), (("apache_tomcat_users", "ham"), 15),
    (("kaggle_ceas08", "ham"), 30), (("spamassassin", "ham"), 20), (("kaggle_ling", "ham"), 20),
    (("kaggle_ceas08", "spam"), 40), (("kaggle_enron", "spam"), 30), (("spamassassin", "spam"), 20), (("kaggle_ling", "spam"), 10),
]
TOTAL = sum(n for _, n in ALLOCATION)

ANNOTATOR_ROWS = {
    "annotator_1": ("API", "annotator 1"),
    "annotator_2": ("API", "annotator 2"),
    "tiebreaker": ("API", "tie-breaker"),
}


def sort_key(email_id, salt):
    """A fixed pseudo-random sort key: the same on every machine and library version."""
    return hashlib.sha256(f"{salt}|{email_id}".encode("utf-8")).hexdigest()


def split_sizes(n):
    """Items per split for a stratum of n: 60% train, 20% validation, the rest test."""
    train = int(n * SPLIT_SHARES[0] + 0.5)
    validation = int(n * SPLIT_SHARES[1] + 0.5)
    return train, validation, n - train - validation


def draw_sample(table):
    """Draw the sample. Returns (sample DataFrame, counts rows for sample_counts.csv)."""
    words = table["body_redacted"].fillna("").str.split().str.len()
    long_enough = words >= MIN_WORDS
    chosen, counts = [], []
    for (source, category), n in ALLOCATION:
        in_stratum = (table["source"] == source) & (table["category"] == category)
        for split, wanted in zip(SPLITS, split_sizes(n)):
            in_split = in_stratum & (table["split"] == split)
            pool = table[in_split & long_enough]
            if len(pool) < wanted:
                sys.exit(f"{source}/{category}/{split}: only {len(pool)} eligible emails, {wanted} wanted")
            order = pool["id"].map(lambda email_id: sort_key(email_id, f"{SEED}|draw")).sort_values()
            chosen.append(pool.loc[order.index[:wanted]])
            counts.append({"source": source, "category": category, "split": split, "wanted": wanted,
                           "drawn": wanted, "eligible": len(pool), "too_short": int((in_split & ~long_enough).sum())})
    return pd.concat(chosen), counts


def assign_batches(sample):
    """Mix the sample, cut it into batches of BATCH_SIZE and give every email a local id."""
    sample = sample.assign(_order=sample["id"].map(lambda email_id: sort_key(email_id, f"{SEED}|order")))
    sample = sample.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    sample["batch"] = sample.index // BATCH_SIZE + 1
    sample["local_id"] = [f"b{b:03d}_{i % BATCH_SIZE + 1:02d}" for i, b in zip(sample.index, sample["batch"])]
    return sample


def read_batch_file(path):
    """The emails of one batch file as [(local_id, text)], exactly as the annotator saw them."""
    text = Path(path).read_text(encoding="utf-8")
    items, position = [], 0
    while True:
        start = text.find('<email id="', position)
        if start < 0:
            return items
        id_end = text.index('">\n', start)
        body_end = text.index("\n</email>", id_end)
        items.append((text[start + len('<email id="'):id_end], text[id_end + 3:body_end]))
        position = body_end + len("\n</email>")


def write_batch_file(name, items):
    """Write batches/<name>.txt for items = [(local_id, text)] and return its path."""
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    path = BATCHES_DIR / f"{name}.txt"
    path.write_text(annotation_prompt(name, items), encoding="utf-8")
    return path


def write_annotators_file():
    """Create annotators.csv, or bring an existing one up to date: one row per annotator, model names kept.

    The model name is filled in by annotate.py auto (the API model id) or by hand (the model shown in a chat
    window); annotate.py next and save refuse to run without it. Rows of annotators that no longer exist are dropped.
    """
    kept = {}
    if ANNOTATORS_CSV.exists():
        with open(ANNOTATORS_CSV, newline="", encoding="utf-8") as handle:
            kept = {row["annotator"]: row["model_name"] for row in csv.DictReader(handle)}
    with open(ANNOTATORS_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["annotator", "chat_service", "model_name", "role"])
        for annotator in ALL_ANNOTATORS:
            service, role = ANNOTATOR_ROWS[annotator]
            writer.writerow([annotator, service, kept.get(annotator, ""), role])


def existing_replies():
    return [p for annotator in ALL_ANNOTATORS for p in (LABELLED_DIR / annotator).glob("*.txt")] if LABELLED_DIR.exists() else []


def main():
    pd.set_option("display.width", 200)
    table = pd.read_parquet(CLEANED_PARQUET, columns=["id", "source", "category", "split", "body_redacted"])
    print(f"Read {relative(CLEANED_PARQUET)}: {len(table):,} emails (all splits: labelling is not tuning)")

    sample, counts = draw_sample(table)
    sample = assign_batches(sample)

    if SAMPLE_CSV.exists() and existing_replies() and "--force" not in sys.argv:
        old = pd.read_csv(SAMPLE_CSV, usecols=["id", "local_id"])
        if not old.equals(sample[["id", "local_id"]]):
            sys.exit("The sample would change but annotation replies already exist. Nothing was written. Use --force to override.")

    LABELLED_DIR.mkdir(parents=True, exist_ok=True)
    sample[["id", "source", "category", "split", "batch", "local_id"]].to_csv(SAMPLE_CSV, index=False)
    for batch, rows in sample.groupby("batch"):
        write_batch_file(f"batch_{batch:03d}", [(r.local_id, prepare_text(r.body_redacted)) for r in rows.itertuples()])
    write_annotators_file()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(counts).to_csv(SAMPLE_COUNTS_CSV, index=False)

    print("\nDrawn per source and category (train / validation / test), and how many emails were too short to be eligible")
    summary = pd.DataFrame(counts).pivot_table(index=["source", "category"], columns="split", values="drawn", aggfunc="sum")[list(SPLITS)]
    summary["total"] = summary.sum(axis=1)
    summary["too_short"] = pd.DataFrame(counts).groupby(["source", "category"])["too_short"].sum()
    print(summary.to_string())

    print("\nChecks")
    sizes = sample.groupby("batch").size()
    checks = [
        (f"{TOTAL} emails drawn", len(sample) == TOTAL),
        ("every email id appears once", sample["id"].is_unique),
        (f"{len(sizes)} batches, every one of {BATCH_SIZE} emails", bool((sizes == BATCH_SIZE).all())),
        ("local ids are unique", sample["local_id"].is_unique),
        ("sample.csv holds ids and groups, no email text", list(pd.read_csv(SAMPLE_CSV).columns) == ["id", "source", "category", "split", "batch", "local_id"]),
        ("split shares are 60/20/20", sample["split"].value_counts().reindex(SPLITS).tolist() == [round(TOTAL * share) for share in SPLIT_SHARES]),
    ]
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print("\nMix per batch by category, first five batches:")
    print(sample.groupby(["batch", "category"]).size().unstack(fill_value=0).head(5).to_string())

    print("\nThe instructions every batch starts with (read them before annotating: the wording decides the labels)")
    print("-" * 100)
    print(instructions(BATCH_SIZE))
    print("-" * 100)
    for path in (SAMPLE_CSV, ANNOTATORS_CSV, SAMPLE_COUNTS_CSV, BATCHES_DIR):
        print(f"Saved {relative(path)}")


if __name__ == "__main__":
    main()
