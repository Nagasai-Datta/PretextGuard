"""Phase 8: run the header and request verifiers over the train split (and, in the final run, the validation split).

Run from the project root (after Phases 2, 3 and 7; needs the spaCy model of requirements.txt):
    python -m src.verifiers.selftest                          # hand-made emails and crafted input only (no data needed)
    python -m src.verifiers.build --train-only --limit 6000   # a quick development run (about 4 minutes the first time)
    python -m src.verifiers.build --train-only --limit 6000 --diagnose affiliation_external,authority
                                                # also print up to 25 contradictions found in ham and what passes in attacks (never saved)
    python -m src.verifiers.build --train-only --limit 6000 --show-rules hv_ext_unknown_freemail,hv_sig_other_domain
                                                # also print up to 25 examples of each named rule, from any category (never saved)
    python -m src.verifiers.build --train-only --workers 4    # every train email; --workers makes the claim extraction (the slow part, first time only) run in 4 processes
    python -m src.verifiers.build --train-only                # every train email (about 20 minutes the first time, 1 minute with the cache)
    python -m src.verifiers.build                             # the final run of a frozen rule version: also reads the validation emails, once

Reads  data/processed/cleaned.parquet     id, source, category, split, body_redacted, signature and the end of body_clean
                                          (the TRAIN rows; validation rows only in the final run; test rows never)
       data/processed/headers.parquet     the Phase 3 header fields and evidence of those emails
Writes data/processed/claims_cache/       the claims the Phase 7 extractor found, per split, so later runs and Phases 10 and 13
                                          do not repeat its 20 minutes (ignored by Git; rebuilt automatically when the pattern
                                          version or the spaCy model changes)
       results/verifier_rates.csv         per split, group (all, category, source, source and category) and claim type: how many
                                          claims were contradicted, consistent or not checkable, by severity (counts only)
       results/verifier_rule_hits.csv     per rule: how many rows it produced, per category (also rules that never fired)
       results/verifier_checks.csv        PASS/FAIL checks, rule version, pattern version and run details

WHAT THIS CAN AND CANNOT SAY. There are no contradiction labels: nobody marked which emails contain a contradicted claim. So
the verifiers are checked in three ways, none of which is a precision or recall:
 1. the self-test (hand-made emails, expected rows);
 2. contradiction rates per category and per source on the train split: an attack should show more contradictions than ordinary
    mail, and the contradictions found in ham are printed, to read. CAUTION: attacks and ham come from different corpora, and
    each corpus carries different header evidence (master document Section 8.11), so a difference between categories is partly
    a difference between corpora. The per-source rows show it; "not checkable" is never counted as "no contradiction";
 3. one read of the frozen rules on the validation emails (final run): the same rates, to see whether the train pattern holds.
How much contradictions add to detection is the N3 ablation of Phase 13.

Rules are written from the definitions and revised only after reading TRAIN results. `--train-only` never loads a validation
email; the final run reads validation once per frozen RULES_VERSION. The test split is used in Phase 13.
Claim labels are LLM labels from one model family, and the claims come from a rule-based extractor with recall 0.13 on
affiliation_internal: a missing claim is never evidence of honesty.
"""

import argparse
import concurrent.futures
import json
import multiprocessing
import time
from collections import defaultdict

import pandas as pd
import spacy
from tqdm import tqdm

from src.claims.extractor import MODEL_NAME, extract_many, load_nlp
from src.claims.patterns import KNOWN_ORGS, PATTERN_VERSION
from src.data.paths import (
    CLAIMS_CACHE_DIR, CLEANED_PARQUET, HEADERS_PARQUET, RESULTS_DIR, VERIFIER_CHECKS_CSV, VERIFIER_RATES_CSV, VERIFIER_RULE_HITS_CSV, relative,
)
from src.headers.domains import FREEMAIL, registered_domain
from src.models.dataset import model_text
from src.verifiers.brands import ALIASES, BRAND_DOMAINS, NO_DOMAINS_YET
from src.verifiers.facts import CONTACT_CHARS
from src.verifiers.rows import ROUTES, check_row
from src.verifiers.selftest import run_crafted, self_test
from src.verifiers.verify import ALL_RULES, RULES_VERSION, VERSION_LOG, verify_claims

CATEGORIES = ["ham", "spam", "phishing", "fraud"]
TYPES = list(ROUTES)
CHUNK = 2000
FLUSH_EVERY = 1                       # chunks between saves of the claims cache (a slow run must not lose its work)
FACT_COLUMNS = [
    "from_name", "from_addr", "from_registered_domain", "reply_to", "spf", "dkim", "dmarc", "auth_source", "authenticated_domain",
    "auth_aligned", "freemail", "name_has_address", "list_mail", "reply_to_divergence", "envelope_mismatch", "org_domain",
    "org_checkable", "from_matches_org", "org_lookalike_score", "to_domain",
]
MIN_CHECKABLE = 20                    # fewer checkable claims than this in a group and no contrast is judged
MIN_RATIO = 2.0                       # an attack's contradiction rate should be at least this many times the ham rate
MIN_FIRED = 20
DOMINANT_SHARE = 0.5
EXAMPLES = 3                          # examples printed per type and kind
DIAGNOSE_LINES = 25
SHOW_RULE_LINES = 25                  # examples printed per rule named with --show-rules
SNIPPET = 70
# Where a claim type is expected to be contradicted clearly more often than in ordinary mail (rates of checkable claims).
EXPECTED_HIGHER = [
    ("affiliation_external", "phishing"), ("authority", "fraud"), ("credential_request", "phishing"),
    ("payment_request", "fraud"), ("data_request", "fraud"), ("signature_contact", "phishing"),
]
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------------------------------------------
# Loading: emails, headers and claims
# ---------------------------------------------------------------------------------------------------------------

def load_split(split, limit=0):
    """The emails of one split with their header evidence. Only this split's rows are read from cleaned.parquet."""
    cleaned = pd.read_parquet(CLEANED_PARQUET, columns=["id", "source", "category", "split", "body_redacted", "signature", "body_clean"],
                              filters=[("split", "==", split)])
    if set(cleaned["split"].unique()) - {split}:
        raise SystemExit("a row of another split was loaded")
    cleaned = cleaned.reset_index(drop=True)
    if limit and limit < len(cleaned):
        cleaned = cleaned.sample(limit, random_state=42).reset_index(drop=True)
    # The block the signature rule reads: the signature column, or the end of the cleaned body when there is none.
    cleaned["contact"] = [sig if isinstance(sig, str) and sig.strip() else (body[-CONTACT_CHARS:] if isinstance(body, str) else "")
                          for sig, body in zip(cleaned["signature"], cleaned["body_clean"])]
    cleaned = cleaned.drop(columns="body_clean")
    headers = pd.read_parquet(HEADERS_PARQUET, columns=["id"] + FACT_COLUMNS, filters=[("id", "in", list(cleaned["id"]))])
    return cleaned.merge(headers, on="id", how="left")


def cache_file(split):
    return CLAIMS_CACHE_DIR / ("claims_%s.parquet" % split)


def read_cache(split, model_version):
    """{id: claims as JSON text} for a split, if the cache was built with this pattern version and spaCy model."""
    path = cache_file(split)
    if not path.exists():
        return {}
    cache = pd.read_parquet(path)
    cache = cache[(cache["pattern_version"] == PATTERN_VERSION) & (cache["model_version"] == model_version)]
    return dict(zip(cache["id"], cache["claims"]))


def write_cache(split, model_version, store):
    CLAIMS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"id": list(store), "claims": list(store.values())})
    frame["pattern_version"], frame["model_version"] = PATTERN_VERSION, model_version
    path = cache_file(split)
    temp = path.with_name(path.name + ".part")
    frame.to_parquet(temp, index=False)
    temp.replace(path)                                  # the finished file appears in one step


def extract_chunk(job):
    """The claims of one chunk of emails as JSON texts. Runs in the main process or in a worker (each loads the spaCy model once)."""
    bodies, signatures = job
    found, _ = extract_many(bodies, signatures)
    return [json.dumps(claims) for claims in found]


def get_claims(table, split, workers=1):
    """The claims of every email in table (a list of lists), from the cache where possible. Returns (claims, extracted now).

    With workers above 1 the missing emails are cut into chunks of 2,000 and extracted by that many processes at once; the
    claims are the same, only the waiting is shorter. The cache is saved after every chunk, so an interrupted run loses nothing.
    """
    model_version = load_nlp().meta["version"]
    store = read_cache(split, model_version)
    missing = table.index[~table["id"].isin(store)]
    if len(missing):
        print("  extracting claims for %d of %d %s emails (%d are in the cache), %d worker(s)" % (len(missing), len(table), split, len(table) - len(missing), workers))
        parts = [table.loc[missing[start:start + CHUNK]] for start in range(0, len(missing), CHUNK)]
        jobs = [(part["body_redacted"].tolist(), [s if isinstance(s, str) else "" for s in part["signature"]]) for part in parts]
        if workers > 1:
            pool = concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
            results = pool.map(extract_chunk, jobs)
        else:
            pool, results = None, map(extract_chunk, jobs)
        for number, (part, texts) in enumerate(zip(parts, tqdm(results, total=len(jobs), desc="  extracting", unit=" x%d emails" % CHUNK)), start=1):
            for row_id, text in zip(part["id"], texts):
                store[row_id] = text
            if number % FLUSH_EVERY == 0:
                write_cache(split, model_version, store)
        if pool is not None:
            pool.shutdown()
        write_cache(split, model_version, store)
    return [json.loads(store[row_id]) for row_id in table["id"]], len(missing)


# ---------------------------------------------------------------------------------------------------------------
# Running the verifiers
# ---------------------------------------------------------------------------------------------------------------

class Examples:
    """Rows to read: contradictions found in ordinary mail, and (with --diagnose) what attacks pass. Printed, never saved."""

    def __init__(self, diagnose_types, show_rules=()):
        self.diagnose = set(diagnose_types)
        self.items = defaultdict(list)
        self.show_rules = set(show_rules)
        self.by_rule = defaultdict(list)

    def add_rule(self, category, text, row, source):
        """Up to 25 examples, any category, of each rule named with --show-rules."""
        if row["rule"] in self.show_rules and len(self.by_rule[row["rule"]]) < SHOW_RULE_LINES:
            self.by_rule[row["rule"]].append((category, row["claim_type"], row["severity"], text[:SNIPPET], source, row["evidence"].get("from_domain"), row["reason"][:170]))

    def add(self, kind, claim_type, text, row, source):
        limit = DIAGNOSE_LINES if claim_type in self.diagnose else EXAMPLES
        if kind == "attack_consistent" and claim_type not in self.diagnose:
            return
        if len(self.items[(kind, claim_type)]) < limit:
            self.items[(kind, claim_type)].append((row["rule"], row["severity"], text[:SNIPPET], source, row["evidence"].get("from_domain"), row["reason"][:170]))


def verify_table(table, claim_lists, split, examples):
    """Run the verifiers over every email. Returns (ledger table with one record per row, problems found by check_row)."""
    records, problems = [], []
    facts_rows = table[FACT_COLUMNS].to_dict("records")
    columns = zip(table["id"], table["source"], table["category"], table["body_redacted"], table["contact"])
    for position, (row_id, source, category, body, contact) in enumerate(tqdm(columns, total=len(table), desc="  verifying %s" % split, unit=" emails")):
        claims = claim_lists[position]
        if not claims:
            continue
        texts = {c["claim_id"]: c["text"] for c in claims}
        rows = verify_claims(claims, facts_rows[position], contact if isinstance(contact, str) else "", model_text(body) if isinstance(body, str) else "")
        for row in rows:
            problems += check_row(row, ALL_RULES)
            status = {True: "contradiction", False: "consistent", None: "not_checkable"}[row["contradiction"]]
            evidence = row["evidence"]
            examples.add_rule(category, texts.get(row["claim_id"], ""), row, source)
            records.append({"id": row_id, "split": split, "source": source, "category": category, "claim_type": row["claim_type"],
                            "verifier": row["verifier"], "rule": row["rule"], "status": status, "severity": row["severity"],
                            "weak": evidence.get("claim_strength") == "weak", "auth_state": evidence.get("auth_state"),
                            "org_known": bool(evidence.get("org_domain")), "list_mail": bool(evidence.get("list_mail"))})
            if status == "contradiction" and category == "ham":
                examples.add("ham_contradiction", row["claim_type"], texts.get(row["claim_id"], ""), row, source)
            elif status == "contradiction":
                examples.add("attack_contradiction", row["claim_type"], texts.get(row["claim_id"], ""), row, source)
            elif status == "consistent" and category in ("phishing", "fraud"):
                examples.add("attack_consistent", row["claim_type"], texts.get(row["claim_id"], ""), row, source)
    ledger = pd.DataFrame.from_records(records, columns=["id", "split", "source", "category", "claim_type", "verifier", "rule", "status", "severity",
                                                         "weak", "auth_state", "org_known", "list_mail"])
    return ledger, problems


# ---------------------------------------------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------------------------------------------

def tally(sub):
    """Counts for one set of ledger records."""
    status, severity = sub["status"], sub["severity"]
    contradicted = status == "contradiction"
    high = contradicted & (severity == "high")
    return {"claims": len(sub), "emails": sub["id"].nunique(), "contradiction": int(contradicted.sum()),
            "consistent": int((status == "consistent").sum()), "not_checkable": int((status == "not_checkable").sum()),
            "high": int(high.sum()), "medium": int((contradicted & (severity == "medium")).sum()), "low": int((contradicted & (severity == "low")).sum()),
            "emails_with_contradiction": int(sub.loc[contradicted, "id"].nunique()), "emails_with_high": int(sub.loc[high, "id"].nunique())}


def rate_table(ledger, table, split):
    """Counts and rates per group (all, category, source, source and category) and claim type ('any' = all types together)."""
    rows = []
    for group_by, column in (("all", None), ("category", "category"), ("source", "source"), ("source_category", ["source", "category"])):
        if column is None:
            pieces = [("all", ledger, len(table))]
        else:
            sizes = table.groupby(column).size()
            pieces = [(key if isinstance(key, str) else "/".join(key), sub, int(sizes.loc[key])) for key, sub in ledger.groupby(column)]
        for label, sub, size in pieces:
            for claim_type in ["any"] + TYPES:
                part = sub if claim_type == "any" else sub[sub["claim_type"] == claim_type]
                if part.empty:
                    continue
                row = {"split": split, "group_by": group_by, "group": label, "claim_type": claim_type, "group_emails": size, **tally(part)}
                checkable = row["contradiction"] + row["consistent"]
                row["checkable_pct"] = round(100 * checkable / row["claims"], 2)
                row["contradiction_pct_of_checkable"] = round(100 * row["contradiction"] / checkable, 2) if checkable else None
                row["contradiction_email_pct"] = round(100 * row["emails_with_contradiction"] / size, 2) if size else None
                rows.append(row)
    return pd.DataFrame(rows)


def rule_table(ledger, split):
    """One row per rule (also the ones that never fired): rows by status and by category."""
    verifier_rows = ledger.groupby("verifier").size().to_dict()
    rows = []
    for rule, info in ALL_RULES.items():
        sub = ledger[ledger["rule"] == rule]
        rows.append({"split": split, "rule": rule, "verifier": info["verifier"], "claim_type": info["claim_type"], "reads_authentication": info["reads_auth"],
                     "meaning": info["meaning"], "rows": len(sub), "emails": sub["id"].nunique(),
                     "contradiction": int((sub["status"] == "contradiction").sum()), "consistent": int((sub["status"] == "consistent").sum()),
                     "not_checkable": int((sub["status"] == "not_checkable").sum()),
                     **{c: int((sub["category"] == c).sum()) for c in CATEGORIES},
                     "share_of_verifier_rows_pct": round(100 * len(sub) / verifier_rows[info["verifier"]], 2) if verifier_rows.get(info["verifier"]) else 0.0})
    return pd.DataFrame(rows)


def cell(row):
    """'34.5% of 120' for a rates row: the contradiction rate among checkable claims, and how many were checkable."""
    if row is None:
        return "-"
    checkable = row["contradiction"] + row["consistent"]
    if not checkable:
        return "none checkable (%d)" % row["claims"]
    return "%5.1f%% of %d" % (100 * row["contradiction"] / checkable, checkable)


def print_matrix(rates, split, group_by, groups, title):
    part = rates[(rates["split"] == split) & (rates["group_by"] == group_by)]
    lookup = {(r.group, r.claim_type): r._asdict() for r in part.itertuples()}
    print("\n%s (%s)" % (title, split))
    print("%-22s" % "claim type" + "".join("%-22s" % g[:21] for g in groups))
    for claim_type in ["any"] + TYPES:
        cells = [cell(lookup.get((g, claim_type))) for g in groups]
        if any(c != "-" for c in cells):
            print("%-22s" % claim_type + "".join("%-22s" % c for c in cells))


def print_email_matrix(rates, split, group_by, groups, title):
    """Share of the group's emails that hold at least one contradicted claim of the type (the number in brackets is how many emails)."""
    part = rates[(rates["split"] == split) & (rates["group_by"] == group_by)]
    lookup = {(r.group, r.claim_type): r for r in part.itertuples()}
    print("\n%s (%s)" % (title, split))
    print("%-22s" % "claim type" + "".join("%-22s" % g[:21] for g in groups))
    for claim_type in ["any"] + TYPES:
        cells = []
        for g in groups:
            r = lookup.get((g, claim_type))
            cells.append("-" if r is None else "%5.1f%% (%d)" % (r.contradiction_email_pct, r.emails_with_contradiction))
        if any(c != "-" for c in cells):
            print("%-22s" % claim_type + "".join("%-22s" % c for c in cells))


def print_rule_examples(examples):
    for rule, items in sorted(examples.by_rule.items()):
        print("\nExamples of rule %s (printed to read, never saved):" % rule)
        for category, claim_type, severity, text, source, from_domain, reason in items:
            print("  %-9s %-20s %-7s %-14s from %-24s %r" % (category, claim_type, severity, source[:14], str(from_domain)[:24], text))
            print("      %s" % reason)


def print_not_checkable(ledger, split):
    """Why claims could not be checked: the most common not-checkable rules per claim type."""
    part = ledger[(ledger["status"] == "not_checkable")]
    print("\nWhy claims were not checkable (%s): most common rules per claim type" % split)
    for claim_type in TYPES:
        sub = part[part["claim_type"] == claim_type]
        total = int((ledger["claim_type"] == claim_type).sum())
        if total:
            top = sub["rule"].value_counts().head(3)
            print("  %-22s %5d of %5d not checkable: %s" % (claim_type, len(sub), total, ", ".join("%s %d" % (r, n) for r, n in top.items()) or "-"))


def print_examples(examples, kinds):
    for kind, title in kinds:
        printed = False
        for (k, claim_type), items in sorted(examples.items.items()):
            if k != kind or not items:
                continue
            if not printed:
                print("\n%s (printed to read, never saved):" % title)
                printed = True
            for rule, severity, text, source, from_domain, reason in items:
                print("  %-22s %-24s %-7s %-14s from %-24s %r" % (claim_type, rule, severity, source[:14], str(from_domain)[:24], text))
                print("      %s" % reason)


# ---------------------------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------------------------

def brand_checks(add):
    domains = [d for ds in BRAND_DOMAINS.values() for d in ds]
    overlap = sorted(set(domains) & set(FREEMAIL))
    add("brands", "brand domains that are free mailbox domains", len(overlap), "0", "PASS" if not overlap else "FAIL")
    not_registered = [d for d in domains if registered_domain(d) != d]
    add("brands", "brand domains that are not a registered domain as written", len(not_registered), "0", "PASS" if not not_registered else "FAIL")
    covered = set(BRAND_DOMAINS) | set(ALIASES) | set(NO_DOMAINS_YET)
    unmapped = [name for name in KNOWN_ORGS if name not in covered]
    add("brands", "KNOWN_ORGS names with neither a domain list nor a reason", len(unmapped), "0", "PASS" if not unmapped else "FAIL")
    add("brands", "organisations with domains / domains / without domains yet", "%d / %d / %d" % (len(BRAND_DOMAINS), len(set(domains)), len(NO_DOMAINS_YET)), "", "info")


def make_checks(ledger, rates, rules, problems, splits, args, started, counts):
    checks = []

    def add(check, item, value, expected, status):
        checks.append({"check": check, "item": item, "value": value, "expected": expected, "status": status})

    passed, total = self_test(verbose=False)
    add("selftest", "hand-made cases, helper checks and crafted inputs", "%s of %d" % ("all" if passed else "NOT all", total), "all pass", "PASS" if passed else "FAIL")
    brand_checks(add)
    add("rows_valid", "ledger rows that fail check_row (keys, severity fits contradiction, known rule, safe reason)", len(problems), "0", "PASS" if not problems else "FAIL")
    broken = rates[rates["claims"] != rates["contradiction"] + rates["consistent"] + rates["not_checkable"]]
    add("three_valued", "groups where contradiction + consistent + not checkable differ from the claims", len(broken), "0", "PASS" if broken.empty else "FAIL")
    reads = {rule for rule, info in ALL_RULES.items() if info["reads_auth"]}
    blind = ledger[ledger["rule"].isin(reads) & ledger["auth_state"].isin(["unknown", "list_relayed"])]
    add("evidence_discipline", "rows from a rule that reads authentication where there was no usable verdict", len(blind), "0", "PASS" if blind.empty else "FAIL")
    internal = ledger[ledger["claim_type"] == "affiliation_internal"]
    guessed = internal[(~internal["org_known"] | internal["list_mail"]) & (internal["status"] != "not_checkable")]
    add("evidence_discipline", "internal-affiliation rows checked without an organisation domain, or on mailing-list mail", len(guessed), "0", "PASS" if guessed.empty else "FAIL")
    weak_high = ledger[ledger["weak"] & (ledger["severity"] == "high")]
    add("severity", "weak-claim contradictions with severity high", len(weak_high), "0", "PASS" if weak_high.empty else "FAIL")
    train = rates[(rates["split"] == "train") & (rates["group_by"] == "category")]
    for claim_type, group in EXPECTED_HIGHER:
        ham = train[(train["group"] == "ham") & (train["claim_type"] == claim_type)]
        attack = train[(train["group"] == group) & (train["claim_type"] == claim_type)]
        item = "%s: emails with a contradicted claim, %s against ham" % (claim_type, group)
        # The rate among CHECKABLE claims is no fair measure: where the only way to be checkable is to be contradicted it is near 100%
        # in every category (first train run). The share of EMAILS is what a detector would see; the confound with the corpus remains.
        if attack.empty or (attack.iloc[0]["contradiction"] + attack.iloc[0]["consistent"]) < MIN_CHECKABLE:
            add("attack_vs_ham", item, "fewer than %d checkable claims on %s" % (MIN_CHECKABLE, group), "judged only with enough checkable claims", "info")
            continue
        ham_rate = float(ham.iloc[0]["contradiction_email_pct"]) if not ham.empty else 0.0
        attack_rate = float(attack.iloc[0]["contradiction_email_pct"])
        value = "%.1f%% vs ham %.1f%%" % (attack_rate, ham_rate)
        if attack_rate > 0 and attack_rate >= MIN_RATIO * ham_rate:
            add("attack_vs_ham", item, value, ">= %gx ham and above 0" % MIN_RATIO, "PASS")
        elif attack_rate > ham_rate:
            # separates, but less than the expected factor: a finding for the report (low-severity rules may well do this), not a failure
            add("attack_vs_ham", item, value + " (%.1fx, above ham but below %gx)" % (attack_rate / ham_rate if ham_rate else float("inf"), MIN_RATIO),
                ">= %gx ham for a pass; above ham is a finding; not above ham fails" % MIN_RATIO, "info")
        else:
            add("attack_vs_ham", item, value, "above ham", "FAIL")
    slowest = max(seconds for _, seconds, _, _, _ in run_crafted())
    add("crafted_inputs", "slowest of the crafted inputs (60,000-character fields, '@' floods, IBAN-shaped words)", "%.2f s" % slowest, "< 2 s", "PASS" if slowest < 2.0 else "FAIL")
    add("leakage_guard", "splits read", "+".join(splits), "train only (--train-only) or train and validation; never test", "PASS" if set(splits) <= {"train", "validation"} else "FAIL")
    add("validation_scored", "this run read the validation emails", "no (--train-only)" if args.train_only else "yes", "yes in the final run of a frozen version", "info" if args.train_only else "PASS")
    train_rules = rules[rules["split"] == "train"]
    for claim_type in TYPES:
        sub = ledger[(ledger["split"] == "train") & (ledger["claim_type"] == claim_type)]
        add("coverage", claim_type, "%d claims, %d checkable" % (len(sub), int((sub["status"] != "not_checkable").sum())),
            ">= %d claims (a finding if not)" % MIN_FIRED, "PASS" if len(sub) >= MIN_FIRED else "info")
    for verifier in ("header", "request"):
        sub = train_rules[(train_rules["verifier"] == verifier) & (train_rules["contradiction"] > 0)]
        if sub.empty:
            continue
        top = sub.sort_values("contradiction", ascending=False).iloc[0]
        share = top["contradiction"] / sub["contradiction"].sum()
        add("dominant_rule", "%s verifier: %s" % (verifier, top["rule"]), "%.1f%% of its contradictions" % (100 * share), "<= %d%% (a finding if not)" % (100 * DOMINANT_SHARE),
            "PASS" if share <= DOMINANT_SHARE else "info")
    silent = [r for r in train_rules["rule"] if int(train_rules.loc[train_rules["rule"] == r, "rows"].iloc[0]) == 0]
    add("coverage", "rules that never fired on the train emails", "%d of %d" % (len(silent), len(train_rules)), "(a finding, not a failure)", "info")
    add("run", "rules_version", RULES_VERSION, "", "info")
    add("run", "claim pattern version", PATTERN_VERSION, "", "info")
    add("run", "spaCy / model", "%s / %s %s" % (spacy.__version__, MODEL_NAME, load_nlp().meta["version"]), "", "info")
    for split, (emails, extracted) in counts.items():
        add("run", "%s emails verified / claims extracted now (the rest came from the cache)" % split, "%d / %d" % (emails, extracted), "", "info")
    add("run", "ledger rows (all splits)", len(ledger), "", "info")
    add("run", "--limit (0 means every train email)", args.limit, "0 in the final run", "info" if args.limit else "PASS")
    add("run", "seconds", round(time.time() - started), "", "info")
    return pd.DataFrame(checks)


# ---------------------------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Header and request verifiers: contradiction rates and checks (Phase 8).")
    parser.add_argument("--train-only", action="store_true", help="never load validation emails (use while writing rules)")
    parser.add_argument("--limit", type=int, default=0, help="a random sample of N train emails (a quick run; needs --train-only)")
    parser.add_argument("--diagnose", default="", help="comma-separated claim types: print up to 25 contradictions found in ham and what passes in attacks")
    parser.add_argument("--workers", type=int, default=1, help="processes for the claim extraction (the first run over all train emails: try 4); the claims are the same")
    parser.add_argument("--show-rules", default="", help="comma-separated rule ids: print up to 25 examples of each, from any category (never saved)")
    args = parser.parse_args()
    if args.limit and not args.train_only:
        raise SystemExit("--limit is for development runs: use it with --train-only. The final run uses every email.")
    diagnose_types = [t for t in args.diagnose.split(",") if t]
    unknown = [t for t in diagnose_types if t not in ROUTES]
    if unknown:
        raise SystemExit("--diagnose: unknown claim types %s" % unknown)
    pd.set_option("display.width", 220)
    started = time.time()
    nlp = load_nlp()
    print("Rules version %s, claim pattern version %s, spaCy %s, model %s %s" % (RULES_VERSION, PATTERN_VERSION, spacy.__version__, MODEL_NAME, nlp.meta["version"]))

    splits = ["train"] if args.train_only else ["train", "validation"]
    show_rules = [r for r in args.show_rules.split(",") if r]
    bad_rules = [r for r in show_rules if r not in ALL_RULES]
    if bad_rules:
        raise SystemExit("--show-rules: unknown rules %s" % bad_rules)
    examples = Examples(diagnose_types, show_rules)
    ledgers, rate_frames, rule_frames, problems, counts = [], [], [], [], {}
    for split in splits:
        table = load_split(split, args.limit if split == "train" else 0)
        print("\n%s: %d emails (%s)" % (split, len(table), ", ".join("%s %d" % (c, n) for c, n in table["category"].value_counts().items())))
        claim_lists, extracted = get_claims(table, split, max(1, args.workers))
        counts[split] = (len(table), extracted)
        ledger, found_problems = verify_table(table, claim_lists, split, examples)
        problems += found_problems
        ledgers.append(ledger)
        rate_frames.append(rate_table(ledger, table, split))
        rule_frames.append(rule_table(ledger, split))
        sources = sorted(table["source"].unique())
        rates_now = rate_frames[-1]
        print("\n%s: %d claims routed to a verifier in %d emails" % (split, len(ledger), ledger["id"].nunique()))
        print_matrix(rates_now, split, "category", CATEGORIES, "Contradicted among CHECKABLE claims, per category")
        print_matrix(rates_now, split, "source", sources, "Contradicted among CHECKABLE claims, per source (a source without the evidence shows 'none checkable')")
        print_email_matrix(rates_now, split, "category", CATEGORIES, "Share of EMAILS with a contradicted claim of the type, per category")
        print_email_matrix(rates_now, split, "source", sources, "Share of EMAILS with a contradicted claim of the type, per source")
        print_not_checkable(ledger, split)
    all_ledger = pd.concat(ledgers, ignore_index=True)
    rates = pd.concat(rate_frames, ignore_index=True)
    rules = pd.concat(rule_frames, ignore_index=True)

    print_examples(examples, [("ham_contradiction", "Contradictions found in ordinary (ham) mail: the false alarms to read"),
                              ("attack_contradiction", "Contradictions found in attacks (phishing, fraud)"),
                              ("attack_consistent", "Claims in attacks the verifiers found consistent (--diagnose only): what slips through")])
    train_rules = rules[(rules["split"] == "train") & (rules["rows"] > 0)].sort_values("rows", ascending=False)
    print_rule_examples(examples)
    print("\nMost frequent rules on the train emails (rows: contradiction / consistent / not checkable; then rows in ham / spam / phishing / fraud):")
    for r in train_rules.head(24).itertuples():
        print("  %-26s %7d  %6d / %6d / %6d   %6d / %5d / %6d / %5d   %s" % (r.rule, r.rows, r.contradiction, r.consistent, r.not_checkable, r.ham, r.spam, r.phishing, r.fraud, r.meaning[:60]))

    checks = make_checks(all_ledger, rates, rules, problems, splits, args, started, counts)
    print("\nChecks:")
    for row in checks.itertuples():
        print("  %-4s %-20s %-70s %s%s" % (row.status, row.check, row.item[:70], row.value, "  (expected %s)" % row.expected if row.expected else ""))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rates.to_csv(VERIFIER_RATES_CSV, index=False)
    rules.to_csv(VERIFIER_RULE_HITS_CSV, index=False)
    checks.to_csv(VERIFIER_CHECKS_CSV, index=False)
    print("\nWrote %s, %s and %s" % tuple(relative(p) for p in (VERIFIER_RATES_CSV, VERIFIER_RULE_HITS_CSV, VERIFIER_CHECKS_CSV)))
    failed = int((checks["status"] == "FAIL").sum())
    print("%d checks failed" % failed if failed else "No check failed (info rows are findings, not failures)")
    if args.limit:
        print("NOTE: this was a quick run (--limit %d); rerun without --limit before committing the results." % args.limit)
    print("Rules version %s: %s" % (VERSION_LOG[-1][0], VERSION_LOG[-1][1][:150]))


if __name__ == "__main__":
    main()
