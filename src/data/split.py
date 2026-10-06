"""Give every staged email a fixed train / validation / test label (70 / 15 / 15).

Run from the project root (after stage.py):
    python -m src.data.split

Rules (master document, Section 8.6):
- Stratified: the 70/15/15 cut is made separately inside every
  (source, category) stratum, so each split has the same mix of sources
  and categories.
- Grouped by subject: inside a stratum, emails whose subjects match after
  removing "Re:"/"Fwd:" prefixes (a thread, or one spam campaign) always go
  to the same split. Replies quote earlier messages and campaigns reuse text,
  so separating them would put near-copies of training emails into the test set.
- Capped: a subject shared by more than 2% of its stratum (and more than 25
  emails) is too common to be one thread, for example "hello", and keeping it
  together would wreck the 70/15/15 ratio. Such groups are split email by
  email, and the script reports how many emails that affected.
- Fixed: each group's place in the order comes from a SHA-256 hash of the
  seed and the group key, not from a random number generator, so the split is
  identical on every machine, every run and every library version.
The test split is not used again until the final evaluation in Phase 13.

Writes:
    data/processed/staged.parquet  the same table with a "split" column added
    results/split_counts.csv       rows per source, category and split (committed)
Run it again whenever stage.py has been run again.
"""

import email.errors
import hashlib
import re
from email.header import decode_header, make_header

import pandas as pd

from src.data.paths import RESULTS_DIR, SPLIT_COUNTS_CSV, STAGED_PARQUET, relative

SEED = 42
TRAIN_END = 0.70       # groups whose middle row falls before 70% of the stratum -> train
VALIDATION_END = 0.85  # 70% to 85% -> validation; the rest (15%) -> test
SPLITS = ["train", "validation", "test"]
GROUP_CAP_SHARE = 0.02  # a group may hold at most 2% of its stratum...
MIN_GROUP_CAP = 25      # ...but groups of up to 25 emails are always kept together

# The Subject header, including any continuation lines (which start with a space or tab).
SUBJECT_LINE = re.compile(r"^Subject:(.*(?:\n[ \t].*)*)", re.MULTILINE | re.IGNORECASE)
# One or more reply/forward prefixes at the start: "Re:", "RE: Fwd:", "Re[2]:", German "AW:", ...
REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv|antw)\s*(\[\d+\])?\s*:\s*)+", re.IGNORECASE)


def subject_of(header_block):
    """Return the decoded Subject of a header block, or '' if it has none."""
    match = SUBJECT_LINE.search(header_block)
    if not match:
        return ""
    value = " ".join(match.group(1).split())  # join continuation lines
    try:
        value = str(make_header(decode_header(value)))  # "=?utf-8?B?...?=" -> readable text
    except (LookupError, ValueError, email.errors.HeaderParseError):
        pass  # a badly encoded subject is used as it is
    return value


def thread_key(subject):
    """The subject without reply prefixes, in lower case, letters and digits only."""
    without_prefix = REPLY_PREFIX.sub("", subject)
    return re.sub(r"[\W_]+", "", without_prefix.lower())


def group_keys(table):
    """One group key per row: source|category|thread key, or the row id when the subject is empty."""
    keys = table["raw_headers"].map(lambda block: thread_key(subject_of(block)))
    keys = keys.where(keys != "", "id:" + table["id"])  # no subject: the email is its own group
    return table["source"] + "|" + table["category"] + "|" + keys


def break_up_big_groups(table):
    """Split groups bigger than the cap into single emails.

    Returns the new group keys and the number of emails whose group was split up.
    """
    stratum_size = table.groupby(["source", "category"])["id"].transform("size")
    group_size = table.groupby("group")["id"].transform("size")
    cap = (stratum_size * GROUP_CAP_SHARE).clip(lower=MIN_GROUP_CAP)
    too_big = group_size > cap
    new_keys = table["group"].where(~too_big, table["group"] + "|" + table["id"])
    return new_keys, int(too_big.sum())


def position(group):
    """A fixed number between 0 and 1 for a group, taken from the SHA-256 of seed and key."""
    digest = hashlib.sha256(f"{SEED}|{group}".encode("utf-8")).hexdigest()
    return int(digest[:15], 16) / 16**15


def assign_splits(table):
    """Return the split of every row: groups are cut 70/15/15 inside each stratum."""
    parts = []
    for _, stratum in table.groupby(["source", "category"]):
        sizes = stratum.groupby("group").size()
        total = len(stratum)
        done = 0
        group_split = {}
        for group in sorted(sizes.index, key=position):
            middle = (done + sizes[group] / 2) / total  # where the group's middle row falls
            done += sizes[group]
            if middle < TRAIN_END:
                group_split[group] = "train"
            elif middle < VALIDATION_END:
                group_split[group] = "validation"
            else:
                group_split[group] = "test"
        parts.append(stratum["group"].map(group_split))
    return pd.concat(parts)


def main():
    pd.set_option("display.width", 140)

    table = pd.read_parquet(STAGED_PARQUET)
    table = table.drop(columns=["split"], errors="ignore")  # safe to rerun
    table["group"] = group_keys(table)
    table["group"], broken_up = break_up_big_groups(table)
    table["split"] = assign_splits(table)

    # Safety check: no group may be spread over two splits.
    if (table.groupby("group")["split"].nunique() > 1).any():
        raise SystemExit("A group landed in two splits; nothing was saved.")

    # Write to a temporary file first, then replace the old table in one step.
    temp = STAGED_PARQUET.with_name(STAGED_PARQUET.name + ".part")
    table.drop(columns=["group"]).to_parquet(temp, index=False)
    temp.replace(STAGED_PARQUET)

    counts = pd.crosstab(
        [table["source"], table["category"]], table["split"], margins=True, margins_name="total"
    ).reindex(columns=SPLITS + ["total"], fill_value=0)  # fixed column order; 0 if a split is empty
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(SPLIT_COUNTS_CSV)

    sizes = table.groupby("group").size()
    print(f"Rows: {len(table):,} in {len(sizes):,} groups")
    print(f"Rows that share a group with others: {sizes[sizes > 1].sum():,}")
    print(f"Rows whose subject group was too big to keep together, split one by one: {broken_up:,}")
    print("Largest groups kept together:")
    print(sizes.sort_values(ascending=False).head(5).to_string())

    shares = table["split"].value_counts(normalize=True).reindex(SPLITS, fill_value=0) * 100
    print("\nOverall: " + ", ".join(f"{name} {share:.1f}%" for name, share in shares.items()))
    attack_shares = table.loc[table["is_attack"], "split"].value_counts(normalize=True).reindex(SPLITS, fill_value=0) * 100
    print("Attacks: " + ", ".join(f"{name} {share:.1f}%" for name, share in attack_shares.items()))

    print("\nRows per source, category and split")
    print(counts.to_string())
    print(f"\nSaved {relative(STAGED_PARQUET)} (split column added)")
    print(f"Saved {relative(SPLIT_COUNTS_CSV)}")


if __name__ == "__main__":
    main()
