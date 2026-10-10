"""Phase 13: the data the two N1 DistilBERT models train on, built on the Mac and uploaded to Colab. Train and validation rows only: the test split never goes to Colab.

Run from the project root:
    python -m src.eval.n1_data

Reads  data/processed/cleaned.parquet     the train and validation rows (body_clean = the raw view with links, body_redacted = the payload-free view)
Writes data/processed/n1_data.parquet     the training SAMPLE (at most 800 emails per source and category, chosen by SHA-256 order of seed 42) and a stratified VALIDATION sample of 3,000
                                          emails, with both views of every email (never committed: it holds full email text)
       results/n1_data_counts.csv         emails, attacks and share with a link per split, source and category (counts only)

WHY A SAMPLE. The free Colab GPU would need about three hours to train two models on all 69,542 train emails for two epochs, and a free session can end earlier. A sample of about 9,000 emails (the same
for both models) trains each model in a few minutes per epoch. The TF-IDF models are fitted twice, on this same sample and on the whole train split, so the effect of the sample can be seen. The
sample takes the same number from each source and category, so a huge source (CEAS has 26,000 train emails) cannot drown the small ones.

THE TASK. Attack against not-attack, as in Phase 2's link-free counts: attack = phishing and fraud (is_attack), not-attack = ham and spam. The false-positive rate is reported for ham and for spam apart,
because spam is the legitimate-looking class that carries the most links.
"""

import hashlib
import sys

import pandas as pd

from src.data import paths
from src.eval.n1_model import clip

SEED = 42
SAMPLE_PER_GROUP = 800
VALIDATION_SAMPLE = 3000
MIN_PER_GROUP_VALIDATION = 20
COLUMNS = ["id", "source", "category", "split", "is_attack", "has_url", "body_clean", "body_redacted"]


def order_key(email_id):
    """A fixed pseudo-random position for an email: the SHA-256 of seed and id. Sorting by it gives the same 'random' sample on every machine."""
    return hashlib.sha256(("%d|%s" % (SEED, email_id)).encode("utf-8")).hexdigest()


def draw(group, count):
    """The `count` emails of a source+category group that come first in SHA-256 order."""
    return group.assign(_key=group["id"].map(order_key)).sort_values("_key").head(count).drop(columns="_key")


def build_sample(table):
    """(train sample, validation sample) from the train and validation rows of cleaned.parquet."""
    train = table[table["split"] == "train"]
    validation = table[table["split"] == "validation"]
    train_sample = pd.concat([draw(group, SAMPLE_PER_GROUP) for _, group in train.groupby(["source", "category"])])
    sizes = validation.groupby(["source", "category"]).size()
    quota = {key: min(int(sizes[key]), max(MIN_PER_GROUP_VALIDATION, int(round(VALIDATION_SAMPLE * sizes[key] / sizes.sum())))) for key in sizes.index}
    validation_sample = pd.concat([draw(group, quota[key]) for key, group in validation.groupby(["source", "category"])])
    return train_sample, validation_sample


def to_n1_frame(sample):
    return pd.DataFrame({"id": sample["id"].astype(str).to_numpy(), "source": sample["source"].to_numpy(), "category": sample["category"].to_numpy(), "split": sample["split"].to_numpy(),
                         "is_attack": sample["is_attack"].astype(bool).to_numpy(), "has_url": sample["has_url"].astype(bool).to_numpy(),
                         "text_raw": [clip(t) for t in sample["body_clean"]], "text_redacted": [clip(t) for t in sample["body_redacted"]]})


def counts_table(frame):
    rows = []
    for (split, source, category), part in frame.groupby(["split", "source", "category"]):
        rows.append({"split": split, "source": source, "category": category, "emails": len(part), "attacks": int(part["is_attack"].sum()), "with_a_link": int(part["has_url"].sum()),
                     "link_share_pct": round(100 * float(part["has_url"].mean()), 1)})
    return pd.DataFrame(rows)


def main():
    table = pd.read_parquet(paths.CLEANED_PARQUET, columns=COLUMNS, filters=[("split", "in", ["train", "validation"])]).reset_index(drop=True)
    if set(table["split"]) - {"train", "validation"}:
        raise SystemExit("a row of another split was loaded")
    train_sample, validation_sample = build_sample(table)
    frame = pd.concat([to_n1_frame(train_sample), to_n1_frame(validation_sample)], ignore_index=True)
    assert set(frame["split"]) == {"train", "validation"} and frame["id"].is_unique
    paths.N1_DATA_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(paths.N1_DATA_PARQUET, index=False)
    counts = counts_table(frame)
    paths.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(paths.RESULTS_DIR / "n1_data_counts.csv", index=False)
    print("N1 training sample: %d emails (%d attacks, %.1f%% with a link); validation sample: %d emails (%d attacks)" % (
        (frame["split"] == "train").sum(), frame[frame["split"] == "train"]["is_attack"].sum(), 100 * frame[frame["split"] == "train"]["has_url"].mean(),
        (frame["split"] == "validation").sum(), frame[frame["split"] == "validation"]["is_attack"].sum()))
    print(counts.to_string(index=False))
    print("\nWrote %s and %s. Upload n1_data.parquet to the 'pretextguard' folder of Google Drive (it holds full email text and is not committed)." % (
        paths.relative(paths.N1_DATA_PARQUET), paths.relative(paths.RESULTS_DIR / "n1_data_counts.csv")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
