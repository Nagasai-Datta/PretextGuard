"""Phase 4: run the keyword baseline over the training split and check the word lists.

Run from the project root (after the Phase 2 script):
    python -m src.baseline.build

Reads  data/processed/cleaned.parquet, TRAIN SPLIT ONLY. The Parquet filter never loads validation
       or test rows, so nothing in them can influence the word lists (leakage guard).
Writes results/keyword_hit_rates.csv    % of emails where each tactic fires, for all emails, per
                                        category and per source / category
       results/keyword_phrase_hits.csv  how many emails contain each phrase, per category (every
                                        phrase of the lexicon, also the ones that never matched)
       results/keyword_checks.csv       the sanity checks below, plus lexicon version and run details

Tactic labels do not exist before Phase 5, so Phase 4 cannot measure precision, recall or F1 (that is
Phase 13). What this script can show is whether the lists behave sensibly: secrecy phrases should
fire more on fraud than on ordinary mail, urgency and scarcity more on phishing, and so on. It
prints the hit-rate tables, the most common phrases per tactic, PASS/FAIL checks, and a few ordinary
(ham) emails where a tactic fired, which are the false positives to read.

The lists may be revised after reading this output, but only by looking at the train split. Each
revision changes LEXICON_VERSION in lexicon.py, and the version is saved in keyword_checks.csv.
The results files hold counts only, never email text; the ham examples are printed, not saved.
"""

import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.baseline.keywords import DEFAULT_THRESHOLD, INDEX, normalise, score_tactics
from src.baseline.lexicon import LEXICON_VERSION, STRONG_WEIGHT, TACTICS
from src.data.paths import (
    CLEANED_PARQUET,
    KEYWORD_CHECKS_CSV,
    KEYWORD_HIT_RATES_CSV,
    KEYWORD_PHRASE_HITS_CSV,
    RESULTS_DIR,
    SPLIT_COUNTS_CSV,
    relative,
)

CATEGORIES = ["ham", "spam", "phishing", "fraud"]
COLUMNS = list(TACTICS) + ["any_tactic"]  # any_tactic: at least one of the seven fires
MIN_FIRED = 20          # a tactic that fires on fewer train emails is too rare to evaluate
DOMINANT_SHARE = 0.5    # no phrase should account for more than half of its tactic's hits
MIN_RATIO = 2.0         # an attack category must fire at least this many times as often as ham
TOP_PHRASES = 5
EXAMPLES_PER_TACTIC = 3
EXAMPLE_SEED = 42
SNIPPET_CHARS = 70

# Where each tactic is expected to fire clearly more often than on ordinary mail.
EXPECTED_HIGHER = [
    ("secrecy", "fraud"), ("secrecy", "phishing"),
    ("urgency", "phishing"), ("scarcity", "phishing"),
    ("authority", "phishing"), ("liking", "fraud"),
]


def load_train():
    """Read only the train rows of cleaned.parquet. Validation and test rows are never loaded."""
    table = pd.read_parquet(
        CLEANED_PARQUET,
        columns=["id", "source", "category", "split", "body_redacted"],
        filters=[("split", "==", "train")],
    )
    assert set(table["split"].unique()) == {"train"}, "a non-train row was loaded"
    return table.reset_index(drop=True)


def expected_train_rows():
    """The train total Phase 1 recorded in results/split_counts.csv, or None if that file is missing."""
    if not SPLIT_COUNTS_CSV.exists():
        return None
    counts = pd.read_csv(SPLIT_COUNTS_CSV)
    return int(counts.loc[counts["source"] == "total", "train"].iloc[0])


def score_all(bodies):
    """Score every body. Returns a (rows x 7) DataFrame of scores and, per row, the (tactic, phrase) matches."""
    scores = np.zeros((len(bodies), len(TACTICS)))
    matches = []
    for row, body in enumerate(tqdm(bodies, desc="  scoring", unit=" emails")):
        result = score_tactics(body)
        for col, tactic in enumerate(TACTICS):
            scores[row, col] = result[tactic]["score"]
        matches.append([(tactic, phrase) for tactic in TACTICS for phrase in result[tactic]["phrases"]])
    return pd.DataFrame(scores, columns=list(TACTICS)), matches


def hit_rate_rows(fired, any_hit, means, groups, group_type):
    """Long-format rows: for each group and column, the % of emails that fire, the % with any match, the mean score."""
    sizes = groups.value_counts()
    fired_pct = fired.groupby(groups).mean() * 100
    any_pct = any_hit.groupby(groups).mean() * 100
    mean_score = means.groupby(groups).mean()
    rows = []
    for group in fired_pct.index:
        for column in COLUMNS:
            rows.append({
                "group_type": group_type, "group": group, "emails": int(sizes[group]), "tactic": column,
                "fired_pct": round(float(fired_pct.at[group, column]), 2),
                "any_hit_pct": round(float(any_pct.at[group, column]), 2),
                "mean_score": round(float(mean_score.at[group, column]), 3),
            })
    return rows


def print_rates(rates, group_type, order=None):
    """Print the share of emails where each tactic fires, one row per group."""
    part = rates[rates["group_type"] == group_type]
    wide = part.pivot(index="group", columns="tactic", values="fired_pct")[COLUMNS]
    wide.insert(0, "emails", part.drop_duplicates("group").set_index("group")["emails"])
    print(wide.reindex(order if order else sorted(wide.index)).to_string())


def phrase_hit_table(categories, matches, any_hit):
    """One row per lexicon phrase: strength, emails containing it (total and per category), share of its tactic's hits."""
    counts = defaultdict(Counter)
    for category, pairs in zip(categories, matches):
        for key in pairs:
            counts[key][category] += 1
    tactic_hits = {tactic: int(any_hit[tactic].sum()) for tactic in TACTICS}
    rows = []
    for entries in INDEX.values():
        for entry in entries:
            per_category = counts.get((entry.tactic, entry.phrase), Counter())
            total = sum(per_category.values())
            row = {
                "tactic": entry.tactic, "phrase": entry.phrase,
                "strength": "strong" if entry.weight == STRONG_WEIGHT else "weak", "emails": total,
            }
            row.update({category: per_category.get(category, 0) for category in CATEGORIES})
            hits = tactic_hits[entry.tactic]
            row["share_of_tactic_hits_pct"] = round(100 * total / hits, 1) if hits else 0.0
            rows.append(row)
    table = pd.DataFrame(rows)
    table["tactic"] = pd.Categorical(table["tactic"], categories=list(TACTICS), ordered=True)
    return table.sort_values(["tactic", "emails", "phrase"], ascending=[True, False, True]).reset_index(drop=True)


def add_check(checks, check, item, value, expected, passed):
    """Record one sanity check and print it. passed=None means information only."""
    status = "info" if passed is None else ("PASS" if passed else "FAIL")
    checks.append({"check": check, "item": item, "value": value, "expected": expected, "status": status})
    print(f"  {status:<5} {item}: {value}" + (f"   (needs {expected})" if expected else ""))


def sanity_checks(rates, fired, phrases, checks):
    category_rates = rates[rates["group_type"] == "category"].pivot(index="group", columns="tactic", values="fired_pct")

    print("\nCheck 1: each tactic fires clearly more often on the attack category it belongs to than on ham")
    for tactic, category in EXPECTED_HIGHER:
        attack, ham = category_rates.at[category, tactic], category_rates.at["ham", tactic]
        add_check(checks, "attack_vs_ham", f"{tactic} on {category}", f"{attack:.2f}% vs ham {ham:.2f}%",
                  f">= {MIN_RATIO:.0f}x ham and above 0", attack > 0 and attack >= MIN_RATIO * ham)

    print("\nCheck 2: each tactic fires on enough train emails to be evaluated later")
    for tactic in TACTICS:
        count = int(fired[tactic].sum())
        add_check(checks, "tactic_coverage", tactic, f"fires on {count:,} emails", f">= {MIN_FIRED} emails", count >= MIN_FIRED)

    print("\nCheck 3: no single phrase accounts for most of its tactic's hits")
    for tactic in TACTICS:
        part = phrases[phrases["tactic"] == tactic]
        top = part.iloc[0]
        if part["emails"].sum() < MIN_FIRED:
            add_check(checks, "dominant_phrase", tactic, "too few matches to judge", "", None)
            continue
        add_check(checks, "dominant_phrase", f"{tactic}: '{top['phrase']}'", f"{top['share_of_tactic_hits_pct']:.1f}% of its hits",
                  f"<= {DOMINANT_SHARE * 100:.0f}%", top["share_of_tactic_hits_pct"] <= DOMINANT_SHARE * 100)


def print_top_phrases(phrases):
    """The most common phrases per tactic, and how many phrases never matched."""
    for tactic in TACTICS:
        part = phrases[phrases["tactic"] == tactic]
        never = int((part["emails"] == 0).sum())
        top = ", ".join(f"{row.phrase} ({row.strength[0]}) {row.emails:,}" for row in part.head(TOP_PHRASES).itertuples() if row.emails)
        print(f"  {tactic:<13} {len(part) - never:>3} of {len(part)} phrases matched | top: {top or 'none'}")


def print_ham_examples(table, scores, matches):
    """A few ordinary emails where each tactic fired: false positives to read (printed, never saved)."""
    rng = np.random.RandomState(EXAMPLE_SEED)
    is_ham = (table["category"] == "ham").to_numpy()
    for tactic in TACTICS:
        rows = np.flatnonzero(is_ham & (scores[tactic].to_numpy() >= DEFAULT_THRESHOLD))
        shown = min(EXAMPLES_PER_TACTIC, len(rows))
        print(f"\n  {tactic}: fired on {len(rows):,} ham emails" + (f", {shown} shown" if shown else ""))
        for row in (rng.choice(rows, size=shown, replace=False) if shown else []):
            phrases = [phrase for t, phrase in matches[row] if t == tactic]
            text = normalise(table.at[row, "body_redacted"])
            where = max(text.find(phrases[0]), 0)
            snippet = text[max(0, where - SNIPPET_CHARS): where + len(phrases[0]) + SNIPPET_CHARS]
            print(f"    [{table.at[row, 'source']}] {phrases}  ...{snippet}...")


def main():
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)
    checks = []

    table = load_train()
    expected = expected_train_rows()
    print(f"Read {relative(CLEANED_PARQUET)}, train split only: {len(table):,} emails"
          + (f" (results/split_counts.csv says {expected:,}: {'match' if expected == len(table) else 'MISMATCH'})" if expected else ""))
    empty = int((table["body_redacted"].fillna("").str.strip() == "").sum())
    print(f"Lexicon version {LEXICON_VERSION}; {sum(len(v) for v in INDEX.values())} phrases; a tactic fires at score >= {DEFAULT_THRESHOLD}; "
          f"{empty:,} bodies are empty after cleaning (they score zero)")

    start = time.perf_counter()
    scores, matches = score_all(table["body_redacted"])
    seconds = time.perf_counter() - start
    print(f"Scored {len(table):,} emails in {seconds:.1f} s ({len(table) / seconds:,.0f} emails per second)")

    fired = scores >= DEFAULT_THRESHOLD
    any_hit = scores > 0
    means = scores.copy()
    means["any_tactic"] = fired.sum(axis=1)  # for any_tactic, the mean score is the mean number of tactics firing
    fired["any_tactic"] = fired[list(TACTICS)].any(axis=1)
    any_hit["any_tactic"] = any_hit[list(TACTICS)].any(axis=1)

    everyone = pd.Series("all", index=table.index)
    by_source = table["source"] + " / " + table["category"]
    rows = []
    for groups, group_type in [(everyone, "all"), (table["category"], "category"), (by_source, "source")]:
        rows += hit_rate_rows(fired, any_hit, means, groups, group_type)
    rates = pd.DataFrame(rows)

    print("\nShare of train emails where each tactic fires (%), per category. any_tactic: at least one of the seven")
    print_rates(rates, "category", CATEGORIES)
    print("\nSame, per source and category")
    print_rates(rates, "source")
    print("\nAll train emails")
    print_rates(rates, "all")
    print("\nMean number of tactics firing per email, by category:",
          {c: round(float(means.loc[table["category"] == c, "any_tactic"].mean()), 2) for c in CATEGORIES})

    phrases = phrase_hit_table(table["category"], matches, any_hit)
    print("\nPhrases that matched, and the most common ones (s = strong, w = weak; number = train emails)")
    print_top_phrases(phrases)

    print("\nSanity checks (they show the lists behave sensibly; accuracy needs the Phase 5 labels)")
    sanity_checks(rates, fired, phrases, checks)
    judged = [c for c in checks if c["status"] in ("PASS", "FAIL")]
    passed = sum(c["status"] == "PASS" for c in judged)
    print(f"\n{passed} of {len(judged)} checks passed" + ("" if passed == len(judged) else ": read the FAIL lines above and the tables, they are findings, not errors"))

    print("\nOrdinary (ham) emails where a tactic fired: read these for false positives")
    print_ham_examples(table, scores, matches)

    run_info = [("lexicon_version", LEXICON_VERSION), ("phrases", sum(len(v) for v in INDEX.values())),
                ("fire_threshold", DEFAULT_THRESHOLD), ("train_rows", len(table)),
                ("empty_bodies", empty), ("scoring_seconds", round(seconds, 1))]
    checks += [{"check": "run", "item": item, "value": value, "expected": "", "status": "info"} for item, value in run_info]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rates.to_csv(KEYWORD_HIT_RATES_CSV, index=False)
    phrases.to_csv(KEYWORD_PHRASE_HITS_CSV, index=False)
    pd.DataFrame(checks, columns=["check", "item", "value", "expected", "status"]).to_csv(KEYWORD_CHECKS_CSV, index=False)
    for path in (KEYWORD_HIT_RATES_CSV, KEYWORD_PHRASE_HITS_CSV, KEYWORD_CHECKS_CSV):
        print(f"Saved {relative(path)}")


if __name__ == "__main__":
    main()
