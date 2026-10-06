"""Phase 2: add clean and redacted bodies to every staged email.

Run from the project root (after the Phase 1 scripts):
    python -m src.preprocess.build

Reads  data/processed/staged.parquet (never modified)
Writes data/processed/cleaned.parquet  = every staged column plus
           has_url        the original email contained a link (text or hidden in HTML)
           body_clean     readable text, quotes and list footers removed, links kept
           body_redacted  body_clean with [URL] [EMAIL] [FILE] [DOMAIN] placeholders
           signature      the signature block found in body_clean ('' if none)
       results/preprocess_summary.csv  per-source counts (committed)

What it prints is the check that Phase 2 worked: per-source counts, a search
for anything link-like left in body_redacted, how often Kaggle's own urls
column disagrees with the text, how many attacks are naturally link-free,
and a few before/after examples.
"""

import pandas as pd
from tqdm import tqdm

from src.data.paths import (
    CLEANED_PARQUET,
    KAGGLE_DIR,
    PREPROCESS_SUMMARY_CSV,
    RAW_DIR,
    RESULTS_DIR,
    STAGED_PARQUET,
    relative,
)
from src.preprocess.clean import clean_body
from src.preprocess.redact import EMAIL, URL, contains_url, redact

# Kaggle files that have a "urls" column (Enron.csv and Ling.csv do not).
KAGGLE_URL_FILES = ["CEAS_08.csv", "Nigerian_Fraud.csv"]
PLACEHOLDERS = ["url", "email", "file", "domain"]
EXAMPLE_SEED = 42


def kaggle_url_flags():
    """Map raw_ref -> True/False from Kaggle's own urls column (the same raw_ref format as loaders.py)."""
    flags = {}
    for file_name in KAGGLE_URL_FILES:
        path = KAGGLE_DIR / "phish_no_more" / file_name
        column = pd.read_csv(path, usecols=["urls"], dtype=str, keep_default_na=False)["urls"]
        ref_prefix = path.relative_to(RAW_DIR).as_posix()
        for row_number, value in enumerate(column):
            flags[f"{ref_prefix}#row={row_number}"] = value.strip() not in ("", "0")
    return flags


def process(table):
    """Clean and redact every body. Returns a DataFrame of new columns (same index as table)."""
    records = []
    for raw in tqdm(table["body_raw"], desc="  cleaning", unit=" emails"):
        cleaned = clean_body(raw)
        redacted, counts = redact(cleaned["body_clean"])
        cleaned["body_redacted"] = redacted
        cleaned["text_has_url"] = contains_url(raw)
        for name in PLACEHOLDERS:
            cleaned[f"n_{name}"] = counts[name]
        records.append(cleaned)
    return pd.DataFrame.from_records(records, index=table.index)


def summary_table(table, new):
    """Per-source counts and percentages for the report."""
    data = pd.concat([table[["source"]], new], axis=1)
    data["empty_after_clean"] = data["body_clean"].str.len() == 0
    data["has_signature"] = data["signature"].str.len() > 0
    grouped = data.groupby("source")
    summary = pd.DataFrame({
        "rows": grouped.size(),
        "html_pct": grouped["was_html"].mean() * 100,
        "has_url_pct": grouped["has_url"].mean() * 100,
        "quote_removed_pct": grouped["quote_removed"].mean() * 100,
        "footer_removed_pct": grouped["footer_removed"].mean() * 100,
        "signature_pct": grouped["has_signature"].mean() * 100,
        "empty_after_clean": grouped["empty_after_clean"].sum(),
        "truncated": grouped["truncated"].sum(),
    })
    for name in PLACEHOLDERS:
        summary[f"{name}_placeholders"] = grouped[f"n_{name}"].sum()
    return summary.round(1)


def leftover_check(redacted):
    """Count redacted bodies that still contain anything link-like."""
    checks = {
        "a URL pattern": redacted.map(lambda t: URL.search(t) is not None),
        "an email pattern": redacted.map(lambda t: EMAIL.search(t) is not None),
        "'http'": redacted.str.contains("http", case=False, regex=False),
        "'www.'": redacted.str.contains("www.", case=False, regex=False),
        "'@'": redacted.str.contains("@", regex=False),
    }
    for label, hits in checks.items():
        print(f"  rows with {label:<16} {int(hits.sum()):>7,}")
    sample = redacted[checks["'http'"]].head(3)
    for text in sample:
        at = text.lower().find("http")
        print(f"    e.g. ...{text[max(0, at - 40):at + 60]!r}...")


def print_examples(table, new):
    """Show a few before/after examples: HTML attack emails from the training split."""
    pool = table[(table["split"] == "train") & table["is_attack"] & new["was_html"]]
    for index in pool.sample(n=min(3, len(pool)), random_state=EXAMPLE_SEED).index:
        print(f"\n  [{table.at[index, 'source']}] {table.at[index, 'raw_ref']}")
        print(f"    raw      : {table.at[index, 'body_raw'][:250]!r}")
        print(f"    clean    : {new.at[index, 'body_clean'][:250]!r}")
        print(f"    redacted : {new.at[index, 'body_redacted'][:250]!r}")
        print(f"    signature: {new.at[index, 'signature'][:120]!r}")


def main():
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)

    table = pd.read_parquet(STAGED_PARQUET)
    print(f"Read {relative(STAGED_PARQUET)}: {len(table):,} emails")
    new = process(table)

    # has_url: a link in the raw text, or Kaggle's own urls column says the original had one.
    kaggle_flag = table["raw_ref"].map(kaggle_url_flags())  # NaN for rows outside the two files
    new["kaggle_url_flag"] = kaggle_flag
    new["has_url"] = new["text_has_url"] | kaggle_flag.fillna(False).astype(bool)

    out = table.copy()
    for column in ["has_url", "body_clean", "body_redacted", "signature"]:
        out[column] = new[column]
    temp = CLEANED_PARQUET.with_name(CLEANED_PARQUET.name + ".part")
    out.to_parquet(temp, index=False)
    temp.replace(CLEANED_PARQUET)  # the finished file appears in one step

    summary = summary_table(table, new)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(PREPROCESS_SUMMARY_CSV)

    print("\nPer source (percentages of that source's emails)")
    print(summary.to_string())

    print("\nLeftover check on body_redacted (should be close to 0)")
    leftover_check(new["body_redacted"])

    print("\nKaggle urls column vs links found in the text (CEAS-08 and Nigerian Fraud)")
    has_flag = kaggle_flag.notna()
    print(pd.crosstab(
        new.loc[has_flag, "kaggle_url_flag"].astype(bool).rename("kaggle says link"),
        new.loc[has_flag, "text_has_url"].rename("link in text"),
    ).to_string())

    print("\nNaturally link-free emails (has_url is False), by split")
    link_free = ~new["has_url"]
    print(pd.crosstab(
        [table["is_attack"].rename("is_attack"), link_free.rename("link_free")],
        table["split"],
    )[["train", "validation", "test"]].to_string())

    print("\nExamples (HTML attack emails, training split)")
    print_examples(table, new)

    print(f"\nSaved {relative(CLEANED_PARQUET)}")
    print(f"Saved {relative(PREPROCESS_SUMMARY_CSV)}")


if __name__ == "__main__":
    main()
