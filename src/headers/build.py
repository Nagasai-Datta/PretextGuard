"""Phase 3: parse every email's headers and turn them into evidence.

Run from the project root (after Phase 2):
    python -m src.headers.build

Reads  data/processed/cleaned.parquet (never modified)
Writes data/processed/headers.parquet   one row per email: id plus the header fields and evidence
       results/header_evidence_summary.csv  per-source percentages (committed)
       results/header_top_domains.csv       most common sender and recipient domains per source (committed)

headers.parquet joins to cleaned.parquet on id. What this prints is the check
that Phase 3 worked: per-source evidence, fields that could not be parsed, the
most common sender and recipient domains (to spot missing freemail providers and
collector addresses), and two examples.
"""

import pandas as pd
from tqdm import tqdm

from src.data.paths import (
    CLEANED_PARQUET,
    HEADER_EVIDENCE_SUMMARY_CSV,
    HEADER_TOP_DOMAINS_CSV,
    HEADERS_PARQUET,
    RESULTS_DIR,
    relative,
)
from src.headers.domains import registered_domain
from src.headers.evidence import header_evidence
from src.headers.parser import parse_header_fields

# Recipient domains that say nothing about the recipient's organisation: the corpus
# collector's own mailbox. Emails sent to them get no organisation domain (not checkable).
COLLECTOR_DOMAINS = {"monkey.org"}  # every Nazario message was delivered to jose@monkey.org

FIELD_COLUMNS = [
    "from_name", "from_addr", "from_domain", "reply_to", "return_path", "to_domain", "subject",
    "message_id", "in_reply_to", "references", "list_id", "mailer",
]
BOOLEAN_COLUMNS = ["auth_aligned", "freemail", "name_has_address", "list_mail", "reply_to_divergence",
                   "envelope_mismatch", "org_checkable", "from_matches_org"]


def organisation_domain(to_domain):
    """The recipient organisation's registered domain, or None for collectors and missing To."""
    org = registered_domain(to_domain) if to_domain else None
    return None if org in COLLECTOR_DOMAINS else org


def process(table):
    """Parse and evaluate every header block. Returns one row per email."""
    rows = []
    for row_id, block in tqdm(zip(table["id"], table["raw_headers"]), total=len(table), desc="  headers", unit=" emails"):
        fields, problems = parse_header_fields(block)
        evidence = header_evidence(fields, organisation_domain(fields.get("to_domain")))
        row = {"id": row_id}
        row.update({column: fields.get(column) for column in FIELD_COLUMNS})
        date = fields.get("date")
        row["date"] = date.isoformat() if date is not None else None  # keeps the sender's own time zone
        row.update(evidence)
        row["parse_problems"] = ",".join(problems) or None
        rows.append(row)
    out = pd.DataFrame.from_records(rows)
    for column in BOOLEAN_COLUMNS:
        out[column] = out[column].astype("boolean")  # True / False / unknown
    for column in ["send_hour", "received_hops"]:
        out[column] = out[column].astype("Int64")    # whole numbers that may be unknown
    return out


def percent(series):
    """Share of rows where the value is True (unknown counts as not True), in %."""
    return round(series.fillna(False).astype(bool).mean() * 100, 1)


def summary_table(data):
    """Per-source percentages of each kind of evidence."""
    rows = {}
    for source, group in data.groupby("source"):
        rows[source] = {
            "rows": len(group),
            "from_parsed_pct": percent(group["from_addr"].notna()),
            "auth_known_pct": percent(group["auth_source"] != "none"),
            "spf_pass_pct": percent(group["spf"] == "pass"),
            "spf_fail_pct": percent(group["spf"].isin(["fail", "softfail"])),
            "dkim_pass_pct": percent(group["dkim"] == "pass"),
            "dmarc_pass_pct": percent(group["dmarc"] == "pass"),
            "dmarc_fail_pct": percent(group["dmarc"] == "fail"),
            "authenticated_domain_pct": percent(group["authenticated_domain"].notna()),
            "auth_aligned_pct": percent(group["auth_aligned"]),
            "freemail_pct": percent(group["freemail"]),
            "name_has_address_pct": percent(group["name_has_address"]),
            "list_mail_pct": percent(group["list_mail"]),
            "reply_to_divergence_pct": percent(group["reply_to_divergence"]),
            "envelope_mismatch_pct": percent(group["envelope_mismatch"]),
            "org_checkable_pct": percent(group["org_checkable"]),
            "send_hour_pct": percent(group["send_hour"].notna()),
            "origin_ip_pct": percent(group["origin_ip"].notna()),
            "rows_with_parse_problems": int(group["parse_problems"].notna().sum()),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def top_domains(data):
    """The 8 most common sender and 5 most common recipient registered domains per source."""
    records = []
    data = data.assign(to_registered=data["to_domain"].map(registered_domain, na_action="ignore"))
    for source, group in data.groupby("source"):
        for kind, column, n in [("from", "from_registered_domain", 8), ("to", "to_registered", 5)]:
            for domain, count in group[column].value_counts().head(n).items():
                records.append({"source": source, "kind": kind, "domain": domain, "count": int(count)})
    return pd.DataFrame(records)


def print_examples(data):
    """Show the evidence for one phishing_pot attack and one Apache list message."""
    columns = ["from_addr", "reply_to", "spf", "dkim", "dmarc", "authenticated_domain", "auth_aligned",
               "freemail", "list_mail", "reply_to_divergence", "envelope_mismatch", "received_hops",
               "origin_ip", "send_hour", "org_domain", "org_lookalike_score"]
    for source in ["phishing_pot", "apache_tomcat_users"]:
        pool = data[(data["source"] == source) & (data["auth_source"] != "none")]
        if len(pool):
            row = pool.sample(n=1, random_state=42).iloc[0]
            print(f"\n  [{source}] {row['id']}")
            for column in columns:
                print(f"    {column:<22} {row[column]}")


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)

    table = pd.read_parquet(CLEANED_PARQUET, columns=["id", "source", "raw_headers"])
    print(f"Read {relative(CLEANED_PARQUET)}: {len(table):,} emails")
    out = process(table)

    temp = HEADERS_PARQUET.with_name(HEADERS_PARQUET.name + ".part")
    out.to_parquet(temp, index=False)
    temp.replace(HEADERS_PARQUET)  # the finished file appears in one step

    data = out.merge(table[["id", "source"]], on="id")
    summary = summary_table(data)
    domains = top_domains(data)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(HEADER_EVIDENCE_SUMMARY_CSV, index_label="source")
    domains.to_csv(HEADER_TOP_DOMAINS_CSV, index=False)

    print("\nPer source (% of that source's emails)")
    print(summary.T.to_string())

    print("\nFields that could not be parsed (rows)")
    problems = out["parse_problems"].dropna().str.split(",").explode().value_counts()
    print(problems.to_string() if len(problems) else "  none")

    print("\nMost common sender (from) and recipient (to) domains")
    for (source, kind), group in domains.groupby(["source", "kind"], sort=True):
        listed = ", ".join(f"{d} {c}" for d, c in zip(group["domain"], group["count"]))
        print(f"  {source:<22} {kind:<4} {listed}")

    print("\nExamples")
    print_examples(data)

    print(f"\nSaved {relative(HEADERS_PARQUET)}")
    print(f"Saved {relative(HEADER_EVIDENCE_SUMMARY_CSV)}")
    print(f"Saved {relative(HEADER_TOP_DOMAINS_CSV)}")


if __name__ == "__main__":
    main()
