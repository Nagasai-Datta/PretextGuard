"""Header coverage table: which sources carry which headers.

Run from the project root (after stage.py):
    python -m src.data.coverage

For every source in the staged table, plus raw Enron, it reports the share of
messages (in %) that carry each header in HEADERS. This decides where each
header signal can be scored: a source with 0% Authentication-Results never
has its SPF, DKIM or DMARC results read, so those signals are recorded as
unknown there, never as pass (master document, Section 6.5).

It also answers the open Enron question: does raw Enron keep In-Reply-To,
References, Received and X-Mailer? If not, Phase 9 rebuilds Enron threads
from subjects and quoted text instead of reply headers.

Kaggle rows have no original headers: their header block was rebuilt from
CSV columns (From, To, Date, Subject), so full_headers is False for them.

Writes results/header_coverage.csv (committed; a table for the report).
"""

import re

import pandas as pd
from tqdm import tqdm

from src.data.loaders import split_headers
from src.data.paths import ENRON_DIR, HEADER_COVERAGE_CSV, RESULTS_DIR, STAGED_PARQUET, relative

HEADERS = [
    "Message-ID",              # unique ID; threads link to it
    "Date",
    "Reply-To",                # where replies really go (N3 reply-direction check)
    "Return-Path",             # envelope sender
    "Received",                # one line per mail server on the way (N2 sending path)
    "Authentication-Results",  # SPF, DKIM and DMARC verdicts (N3)
    "Received-SPF",            # older, SPF-only verdict header
    "DKIM-Signature",
    "In-Reply-To",             # thread links (N2 thread integrity)
    "References",
    "X-Mailer",                # mail program (N2 sending path)
    "User-Agent",              # mail program, another common header for it
    "List-Id",                 # set by mailing lists
    "X-Original-From",         # original sender when a list rewrites From
]

# A header starts at the beginning of a line with its name and a colon.
# Continuation lines start with a space or tab, so they never match.
HEADER_NAME = re.compile(r"^([A-Za-z0-9-]+):", re.MULTILINE)

ENRON_MAILDIR = ENRON_DIR / "enron_mail_20150507" / "maildir"
HEAD_BYTES = 64 * 1024  # headers sit at the top of a file; read at most this much


def header_names(block):
    """Return the set of header names in a header block, in lower case."""
    return {name.lower() for name in HEADER_NAME.findall(block)}


def coverage_row(header_blocks):
    """Return the message count and, per header in HEADERS, the % of blocks that carry it."""
    counts = dict.fromkeys(HEADERS, 0)
    total = 0
    for block in header_blocks:
        total += 1
        names = header_names(block)
        for header in HEADERS:
            if header.lower() in names:
                counts[header] += 1
    row = {"messages": total}
    for header in HEADERS:
        row[header] = round(100 * counts[header] / total, 1) if total else 0.0
    return row


def enron_header_blocks():
    """Yield the header block of every raw Enron message (one file per message)."""
    paths = [p for p in ENRON_MAILDIR.rglob("*") if p.is_file()]
    for path in tqdm(paths, desc="  enron_raw", unit=" files"):
        with open(path, "rb") as f:
            yield split_headers(f.read(HEAD_BYTES))


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)

    staged = pd.read_parquet(STAGED_PARQUET, columns=["source", "has_full_headers", "raw_headers"])
    rows = []
    for source, group in staged.groupby("source"):
        row = {"source": source, "full_headers": bool(group["has_full_headers"].all())}
        row.update(coverage_row(group["raw_headers"]))
        rows.append(row)

    print("Reading raw Enron headers (about 517,000 files; a few minutes)")
    row = {"source": "enron_raw", "full_headers": True}
    row.update(coverage_row(enron_header_blocks()))
    rows.append(row)

    table = pd.DataFrame(rows).set_index("source")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(HEADER_COVERAGE_CSV)

    # Printed with headers as rows and sources as columns, so it fits a terminal.
    print("\n% of messages carrying each header")
    print(table.T.to_string())

    enron = table.loc["enron_raw"]
    print(
        "\nRaw Enron thread and routing headers: "
        f"In-Reply-To {enron['In-Reply-To']}%, References {enron['References']}%, "
        f"Received {enron['Received']}%, X-Mailer {enron['X-Mailer']}%"
    )
    print(f"\nSaved {relative(HEADER_COVERAGE_CSV)}")


if __name__ == "__main__":
    main()
