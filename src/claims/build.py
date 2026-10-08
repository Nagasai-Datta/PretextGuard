"""Phase 7: run the claim extractor over the training split and score it against the Phase 5 claim labels.

Run from the project root (after Phases 2, 5 and 6; needs the spaCy model of requirements.txt):
    python -m src.claims.build --train-only --limit 6000    # a quick development run (about 3 minutes)
    python -m src.claims.build --train-only --limit 6000 --diagnose signature_contact,payment_request
                                            # also print, for labelled TRAIN emails, the claims the extractor misses and
                                            # the ones it finds that nobody labelled, with a little context (never saved)
    python -m src.claims.build --train-only # all train emails, about 20 minutes; validation is never loaded
    python -m src.claims.build              # the final run of a frozen version: also scores the validation emails (once)

Reads  data/processed/cleaned.parquet   TRAIN rows for the hit rates, plus the labelled train and validation emails
       data/labelled/labels.csv         the claim labels (spans and types) of the 690 labelled real emails
       data/synthetic/synthetic.csv     the synthetic emails and their required claims
Writes results/claim_hit_rates.csv      % of train emails where each claim type is found, per category (committed, counts only)
       results/claim_pattern_hits.csv   how many train emails each pattern fires on, per category
       results/claim_scores.csv         precision, recall and F1 per claim type on labelled emails, real and synthetic apart
       results/claim_checks.csv         PASS/FAIL checks, plus pattern version, spaCy version and run details

The three parts, and what each can and cannot say:
 1. Hit rates on ALL train emails (no labels needed). A claim type should fire far more often on the attacks it
    belongs to (credential requests on phishing, authority and reply directions on fraud) than on ordinary mail,
    and the printed ham examples are the false positives to read. Written to results as counts only.
 2. Scores on the labelled real emails (train and validation; the TEST split is never loaded here): does the
    email contain a claim of this type, as the annotators say? Plus, for the types that have enough labels, whether the
    found words overlap the labelled span (the Phase 5 overlap rule). A type with fewer than 10 positives in a set is
    reported as counts, never as an F1 (src/eval/metrics.py). Two operating points: all claims, and strong claims only.
 3. Scores on the synthetic train and validation emails, always apart from the real ones. Their labels list only the
    claims the generator was required to include, so precision there is a lower bound.

The patterns may be revised after reading part 1 and the train rows of parts 2 and 3, never after looking at validation
or test emails; every revision changes PATTERN_VERSION, which is saved in claim_checks.csv. That is what --train-only is
for: it never loads a validation email or label. The full run reads validation once per frozen version; a revision made
because of those scores is tuning on validation, and is logged as that.
The labels are LLM labels from one model family (Phase 5): every score is agreement with those labels.
"""

import argparse
import json
import time
from collections import Counter, defaultdict

import pandas as pd
import spacy
from tqdm import tqdm

from src.claims.extractor import MODEL_NAME, crafted_inputs, extract_claims, extract_many, load_nlp
from src.claims.patterns import PATTERN_VERSION, PHRASES, STRONG
from src.claims.schema import CLAIM_TYPES, MAX_CLAIMS, MAX_PER_TYPE, check_claim
from src.data.agreement import spans_overlap
from src.data.paths import (
    CLAIM_CHECKS_CSV, CLAIM_HIT_RATES_CSV, CLAIM_PATTERN_HITS_CSV, CLAIM_SCORES_CSV, CLEANED_PARQUET, LABELS_CSV, RESULTS_DIR,
    SYNTHETIC_CSV, relative,
)
from src.eval.metrics import macro_f1, tactic_rows

CATEGORIES = ["ham", "spam", "phishing", "fraud"]
CHUNK = 2000
# The claim types with 10 or more real positives in both validation and test (results/label_counts.csv): the only
# ones that can get an F1 on real emails.
SCOREABLE = ("affiliation_external", "affiliation_internal", "authority", "credential_request", "signature_contact")
OPERATING_POINTS = (0.0, STRONG)             # min_confidence: every claim, or strong claims only
MIN_FIRED = 20                               # a type that fires on fewer train emails is too rare to evaluate
DOMINANT_SHARE = 0.5
MIN_RATIO = 2.0
EXAMPLES_PER_TYPE = 3
DIAGNOSE_LINES = 25          # examples printed per kind and type by --diagnose
DIAGNOSE_TAIL = 90           # characters from the end of an email printed next to a missed claim
SNIPPET_CHARS = 70

# Where a claim type is expected to fire clearly more often than on ordinary mail.
EXPECTED_HIGHER = [
    ("credential_request", "phishing"), ("affiliation_external", "phishing"), ("reply_direction", "fraud"),
    ("authority", "fraud"), ("data_request", "fraud"),
]
# Rules in extractor.py that are not phrase patterns.
RULE_PATTERNS = [("affiliation_external", "ae_org_cue", STRONG), ("affiliation_external", "ae_org_mention", 0.6),
                 ("affiliation_external", "ae_copyright", STRONG),
                 ("signature_contact", "sc_name_contact", STRONG), ("signature_contact", "sc_contact", 0.6),
                 ("signature_contact", "sc_labelled_contact", STRONG), ("signature_contact", "sc_signoff_name", 0.6)]


def load_train(limit):
    """The TRAIN rows of cleaned.parquet (validation and test rows are never loaded here), optionally a random sample of limit rows."""
    table = pd.read_parquet(CLEANED_PARQUET, columns=["id", "source", "category", "split", "body_redacted", "signature"],
                            filters=[("split", "==", "train")])
    assert set(table["split"].unique()) == {"train"}, "a non-train row was loaded"
    table = table.reset_index(drop=True)
    return table.sample(limit, random_state=42).reset_index(drop=True) if limit and limit < len(table) else table


def load_labelled_text(ids):
    """body_redacted and signature of the labelled emails with these ids."""
    table = pd.read_parquet(CLEANED_PARQUET, columns=["id", "body_redacted", "signature"], filters=[("id", "in", list(ids))])
    return table.set_index("id")


def signatures_of(table):
    return [s if isinstance(s, str) else "" for s in table["signature"]]


# ---------------------------------------------------------------------------------------------------------------
# Part 1: hit rates on the train split
# ---------------------------------------------------------------------------------------------------------------

def hit_rates(train):
    """Run the extractor over every train email. Returns (types fired per email at each operating point, pattern hits, examples, problems)."""
    fired = {conf: [] for conf in OPERATING_POINTS}
    pattern_hits = defaultdict(Counter)               # (type, pattern) -> {category: emails}
    examples = defaultdict(list)                      # type -> claim texts found in ham
    problems, max_claims, max_per_type = [], 0, 0
    for start in tqdm(range(0, len(train), CHUNK), desc="  extracting", unit=" x%d emails" % CHUNK):
        part = train.iloc[start:start + CHUNK]
        claims, prepared = extract_many(part["body_redacted"].tolist(), signatures_of(part))
        for category, email_claims, (text, sig) in zip(part["category"], claims, prepared):
            max_claims = max(max_claims, len(email_claims))
            max_per_type = max(max_per_type, max(Counter(c["type"] for c in email_claims).values(), default=0))
            problems += [p for c in email_claims for p in check_claim(c, text, sig)]
            for conf in OPERATING_POINTS:
                fired[conf].append({c["type"] for c in email_claims if c["confidence"] >= conf})
            for key in {(c["type"], c["attributes"]["pattern"]) for c in email_claims}:
                pattern_hits[key][category] += 1
            if category == "ham":
                for c in email_claims:
                    if len(examples[c["type"]]) < EXAMPLES_PER_TYPE and c["confidence"] >= STRONG:
                        examples[c["type"]].append(c["text"][:SNIPPET_CHARS])
    return fired, pattern_hits, examples, problems, max_claims, max_per_type


def hit_rate_table(train, fired):
    """Long-format rows: % of emails where each claim type is found, for all emails and per category."""
    rows = []
    groups = [("all", "all", pd.Series(True, index=train.index))] + [("category", c, train["category"] == c) for c in CATEGORIES]
    for group_type, group, mask in groups:
        indexes = list(train.index[mask])
        for claim_type in CLAIM_TYPES:
            row = {"group_type": group_type, "group": group, "emails": len(indexes), "claim_type": claim_type}
            for conf, name in zip(OPERATING_POINTS, ("fired_pct", "strong_pct")):
                hits = sum(claim_type in fired[conf][i] for i in indexes)
                row[name] = round(100 * hits / max(1, len(indexes)), 2)
            rows.append(row)
    return pd.DataFrame(rows)


def pattern_table(pattern_hits):
    """One row per pattern (also the ones that never fired): emails per category and the share of its type's hits."""
    entries = [(t, pid, s) for t, es in PHRASES.items() for pid, _, s in es] + RULE_PATTERNS
    totals = Counter()
    for (claim_type, _), counts in pattern_hits.items():
        totals[claim_type] += sum(counts.values())
    rows = []
    for claim_type, pid, strength in entries:
        counts = pattern_hits.get((claim_type, pid), Counter())
        total = sum(counts.values())
        rows.append({"claim_type": claim_type, "pattern": pid, "strength": "strong" if strength >= STRONG else "weak", "emails": total,
                     **{c: counts.get(c, 0) for c in CATEGORIES},
                     "share_of_type_hits_pct": round(100 * total / totals[claim_type], 1) if totals[claim_type] else 0.0})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------
# Parts 2 and 3: scores against labels
# ---------------------------------------------------------------------------------------------------------------

def truth_matrix(label_lists):
    """(emails x 11) yes/no matrix from lists of labelled claims."""
    return [[any(c["type"] == t for c in claims) for t in CLAIM_TYPES] for claims in label_lists]


def span_scores(label_lists, found_lists, claim_type):
    """Span-level precision and recall for one type: found spans that overlap a labelled span, labelled spans that a found span overlaps."""
    found_total = found_hit = label_total = label_hit = 0
    for labelled, found in zip(label_lists, found_lists):
        wanted = [c["span"] for c in labelled if c["type"] == claim_type]
        ours = [c["text"] for c in found if c["type"] == claim_type]
        found_total += len(ours)
        found_hit += sum(any(spans_overlap(o, w) for w in wanted) for o in ours)
        label_total += len(wanted)
        label_hit += sum(any(spans_overlap(o, w) for o in ours) for w in wanted)
    return (round(found_hit / found_total, 4) if found_total else None, round(label_hit / label_total, 4) if label_total else None)


def score_set(name, bodies, signatures, label_lists, note=""):
    """Score one labelled set at both operating points. Returns (rows, problems, claims per email, the texts that were read)."""
    claims, prepared = extract_many(bodies, signatures)
    problems = [p for email_claims, (text, sig) in zip(claims, prepared) for c in email_claims for p in check_claim(c, text, sig)]
    truth = truth_matrix(label_lists)
    rows = []
    for conf in OPERATING_POINTS:
        kept = [[c for c in email_claims if c["confidence"] >= conf] for email_claims in claims]
        predicted = [[any(c["type"] == t for c in email_claims) for t in CLAIM_TYPES] for email_claims in kept]
        for row in tactic_rows(truth, predicted, CLAIM_TYPES):
            claim_type = row.pop("tactic")
            row = {"data": name, "min_confidence": conf, "claim_type": claim_type, **row, "span_precision": None, "span_recall": None, "note": note}
            if row["f1"] is not None and claim_type in SCOREABLE and name.startswith("real"):
                row["span_precision"], row["span_recall"] = span_scores(label_lists, kept, claim_type)
            rows.append(row)
        rows.append({"data": name, "min_confidence": conf, "claim_type": "macro_scoreable5", "items": len(bodies),
                     "f1": round(macro_f1(truth, predicted, CLAIM_TYPES, SCOREABLE), 4), "reported": "mean F1 over " + ", ".join(SCOREABLE),
                     "note": note})
    return rows, problems, claims, prepared


def diagnose(claim_types, prepared, label_lists, claims):
    """Print the labelled train emails where a claim type is missed or found without a label (terminal only, never saved)."""
    for claim_type in claim_types:
        misses, extras = [], []
        for (text, sig), labelled, found in zip(prepared, label_lists, claims):
            wanted = [c["span"] for c in labelled if c["type"] == claim_type]
            ours = [c for c in found if c["type"] == claim_type]
            if wanted and not ours and len(misses) < DIAGNOSE_LINES:
                misses.append("labelled: %-70r end of the email: %r" % (wanted[0][:70], text[-DIAGNOSE_TAIL:]))
            if ours and not wanted and len(extras) < DIAGNOSE_LINES:
                claim = ours[0]
                source = text if claim["attributes"]["zone"] == "body" else sig
                start, end = claim["span"]
                around = source[max(0, start - 40):start] + "[[" + source[start:end][:80] + "]]" + source[end:end + 40]
                extras.append("%-16s %.1f  %r" % (claim["attributes"]["pattern"], claim["confidence"], around))
        print("\nDIAGNOSE %s (real train): %d missed, then %d found without a label" % (claim_type, len(misses), len(extras)))
        for line in misses:
            print("  MISS ", line)
        for line in extras:
            print("  EXTRA", line)


def print_scores(scores, name, conf):
    part = scores[(scores["data"] == name) & (scores["min_confidence"] == conf)]
    print("\n%s, min_confidence %.1f (items %d)" % (name, conf, int(part["items"].iloc[0])))
    print("%-22s %9s %6s %6s %6s %7s %7s %7s" % ("claim type", "positives", "tp", "fp", "fn", "prec", "recall", "F1"))
    for row in part.itertuples():
        if row.claim_type == "macro_scoreable5":
            print("%-22s %9s %6s %6s %6s %7s %7s %7.3f" % ("macro (5 scoreable)", "", "", "", "", "", "", row.f1))
        elif pd.notna(row.f1):
            print("%-22s %9d %6d %6d %6d %7.2f %7.2f %7.3f" % (row.claim_type, row.positives, row.tp, row.fp, row.fn, row.precision, row.recall, row.f1))
        else:
            print("%-22s %9d %6d %6d %6d %s" % (row.claim_type, row.positives, row.tp, row.fp, row.fn, "  counts only"))


# ---------------------------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Claim extractor: train hit rates and scores against labels (Phase 7).")
    parser.add_argument("--diagnose", default="", help="comma-separated claim types: print the misses and the unlabelled finds on labelled train emails")
    parser.add_argument("--train-only", action="store_true", help="never load validation emails or labels (use while writing patterns)")
    parser.add_argument("--limit", type=int, default=0, help="a random sample of N train emails for the hit rates (a quick run)")
    args = parser.parse_args()
    pd.set_option("display.width", 220)
    started = time.time()
    nlp = load_nlp()
    print("Pattern version %s, spaCy %s, model %s %s" % (PATTERN_VERSION, spacy.__version__, MODEL_NAME, nlp.meta["version"]))

    # ---- part 1 --------------------------------------------------------------------------------------------------
    train = load_train(args.limit)
    print("Part 1: hit rates on %d train emails" % len(train))
    fired, pattern_hits, examples, problems, max_claims, max_per_type = hit_rates(train)
    rates = hit_rate_table(train, fired)
    patterns = pattern_table(pattern_hits)
    wide = rates.pivot(index="claim_type", columns="group", values="fired_pct")[["all"] + CATEGORIES]
    print("\n% of train emails where the claim type is found (all claims), per category:")
    print(wide.reindex(CLAIM_TYPES).to_string())
    strong = rates.pivot(index="claim_type", columns="group", values="strong_pct")[["all"] + CATEGORIES]
    print("\n% of train emails where a STRONG claim of the type is found:")
    print(strong.reindex(CLAIM_TYPES).to_string())
    print("\nStrong claims found in ordinary (ham) train emails, the false positives to read (printed, never saved):")
    for claim_type in CLAIM_TYPES:
        for text in examples.get(claim_type, []):
            print("  %-22s %r" % (claim_type, text))

    # ---- parts 2 and 3 -------------------------------------------------------------------------------------------
    labels = pd.read_csv(LABELS_CSV, dtype={"id": str})
    diagnose_types = [t for t in args.diagnose.split(",") if t]
    unknown = [t for t in diagnose_types if t not in CLAIM_TYPES]
    if unknown:
        raise SystemExit("--diagnose: unknown claim types %s" % unknown)
    splits = ("train",) if args.train_only else ("train", "validation")
    labels = labels[labels["split"].isin(splits)]                           # the test labels are never used here
    assert not (labels["split"] == "test").any()
    text = load_labelled_text(labels["id"])
    synthetic = pd.read_csv(SYNTHETIC_CSV, dtype={"id": str})
    synthetic = synthetic[synthetic["split"].isin(splits)]
    rows, labelled_problems, claim_counts = [], [], []
    for split in splits:
        part = labels[labels["split"] == split]
        sigs = [s if isinstance(s, str) else "" for s in text.loc[part["id"], "signature"]]
        label_lists = [json.loads(c) for c in part["claims"]]
        result, found_problems, claims, prepared = score_set("real_" + split, text.loc[part["id"], "body_redacted"].tolist(), sigs, label_lists)
        rows += result
        labelled_problems += found_problems
        claim_counts += [len(c) for c in claims]
        if split == "train" and diagnose_types:
            diagnose(diagnose_types, prepared, label_lists, claims)
        part = synthetic[synthetic["split"] == split]
        result, found_problems, claims, _ = score_set("synthetic_" + split, part["body_redacted"].tolist(), None,
                                                   [json.loads(c) for c in part["claims"]],
                                                   note="labels list only the claims the generator was required to include: precision is a lower bound")
        rows += result
        labelled_problems += found_problems
    scores = pd.DataFrame(rows)[["data", "min_confidence", "claim_type", "items", "positives", "predicted", "tp", "fp", "fn",
                                 "precision", "recall", "f1", "reported", "span_precision", "span_recall", "note"]]
    for split in splits:
        for kind in ("real_", "synthetic_"):
            for conf in OPERATING_POINTS:
                print_scores(scores, kind + split, conf)
    print("\nReal train scores are a development set (the patterns were written while reading train data); validation is the first unbiased read of this version.")
    print("All scores are agreement with LLM labels from one model family. Synthetic precision is a lower bound.")

    # ---- checks --------------------------------------------------------------------------------------------------
    checks = []

    def add(check, item, value, expected, status):
        checks.append({"check": check, "item": item, "value": value, "expected": expected, "status": status})

    add("patterns", "phrases compile; ids unique; every word is one token", sum(len(v) for v in PHRASES.values()), "all valid", "PASS")
    for claim_type, group in EXPECTED_HIGHER:
        ham = float(rates[(rates["group"] == "ham") & (rates["claim_type"] == claim_type)]["fired_pct"].iloc[0])
        other = float(rates[(rates["group"] == group) & (rates["claim_type"] == claim_type)]["fired_pct"].iloc[0])
        add("attack_vs_ham", "%s on %s" % (claim_type, group), "%.2f%% vs ham %.2f%%" % (other, ham), ">= %gx ham and above 0" % MIN_RATIO,
            "PASS" if other > 0 and other >= MIN_RATIO * ham else "FAIL")
    all_problems = problems + labelled_problems
    add("claims_valid", "claims whose text is not the slice of their span, or with a bad type, zone or confidence", len(all_problems), "0",
        "PASS" if not all_problems else "FAIL")
    add("claims_capped", "most claims in one email / most of one type", "%d / %d" % (max_claims, max_per_type),
        "<= %d / <= %d" % (MAX_CLAIMS, MAX_PER_TYPE), "PASS" if max_claims <= MAX_CLAIMS and max_per_type <= MAX_PER_TYPE else "FAIL")
    slowest = 0.0
    for _, crafted in crafted_inputs():
        began = time.time()
        extract_claims(crafted, crafted)
        slowest = max(slowest, time.time() - began)
    add("crafted_inputs", "slowest of 8 crafted 200,000-character inputs", "%.2f s" % slowest, "< 2 s", "PASS" if slowest < 2.0 else "FAIL")
    add("leakage_guard", "splits read for hit rates", "+".join(sorted(train["split"].unique())), "train only", "PASS")
    add("leakage_guard", "splits read for scoring", "+".join(sorted(labels["split"].unique())), "train and validation only (train only with --train-only)",
        "PASS" if set(labels["split"]) <= set(splits) else "FAIL")
    add("validation_scored", "this run scored the validation emails", "no (--train-only)" if args.train_only else "yes",
        "yes in the final run of a frozen version", "info" if args.train_only else "PASS")
    all_fired = fired[OPERATING_POINTS[0]]
    for claim_type in CLAIM_TYPES:
        count = sum(claim_type in f for f in all_fired)
        add("coverage", claim_type, "fires on %d emails" % count, ">= %d (a finding if not)" % MIN_FIRED, "PASS" if count >= MIN_FIRED else "info")
    for claim_type in CLAIM_TYPES:
        part = patterns[patterns["claim_type"] == claim_type]
        top = part.sort_values("share_of_type_hits_pct", ascending=False).iloc[0]
        add("dominant_pattern", "%s: %s" % (claim_type, top["pattern"]), "%.1f%% of its hits" % top["share_of_type_hits_pct"],
            "<= %d%% (a finding if not)" % (100 * DOMINANT_SHARE), "PASS" if top["share_of_type_hits_pct"] <= 100 * DOMINANT_SHARE else "info")
    add("run", "pattern_version", PATTERN_VERSION, "", "info")
    add("run", "phrases", sum(len(v) for v in PHRASES.values()), "", "info")
    add("run", "spacy / model", "%s / %s %s" % (spacy.__version__, MODEL_NAME, nlp.meta["version"]), "", "info")
    add("run", "train_emails", len(train), "", "info")
    add("run", "labelled real emails scored (train / validation)", "%d / %d" % ((labels["split"] == "train").sum(), (labels["split"] == "validation").sum()), "", "info")
    add("run", "--limit (0 means every train email)", args.limit, "0 in the final run", "info" if args.limit else "PASS")
    add("run", "mean claims per labelled real email", round(sum(claim_counts) / max(1, len(claim_counts)), 2), "", "info")
    add("run", "seconds", round(time.time() - started), "", "info")
    checks_frame = pd.DataFrame(checks)
    print("\nChecks:")
    for row in checks_frame.itertuples():
        print("  %-4s %-16s %-60s %s%s" % (row.status, row.check, row.item[:60], row.value, "  (expected %s)" % row.expected if row.expected else ""))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rates.to_csv(CLAIM_HIT_RATES_CSV, index=False)
    patterns.to_csv(CLAIM_PATTERN_HITS_CSV, index=False)
    scores.to_csv(CLAIM_SCORES_CSV, index=False)
    checks_frame.to_csv(CLAIM_CHECKS_CSV, index=False)
    print("\nWrote %s, %s, %s and %s" % tuple(relative(p) for p in (CLAIM_HIT_RATES_CSV, CLAIM_PATTERN_HITS_CSV, CLAIM_SCORES_CSV, CLAIM_CHECKS_CSV)))
    failed = int((checks_frame["status"] == "FAIL").sum())
    print("%d checks failed" % failed if failed else "No check failed (info rows are findings, not failures)")
    if args.limit:
        print("NOTE: this was a quick run (--limit %d); rerun without --limit before committing the results." % args.limit)


if __name__ == "__main__":
    main()
