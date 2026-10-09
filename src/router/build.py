"""Phase 10: score the emails and threads, calibrate the risk score on the validation split, and check the work.

Run from the project root (after Phases 2, 3, 6, 7, 8 and 9; needs the tactic model and spaCy):
    python -m src.router.selftest                          # hand-made emails and threads only (no data, no model)
    python -m src.router.build --train-only --limit 6000   # development: a random 6,000 train emails (about 5 minutes the first time)
    python -m src.router.build --train-only                # development: every train email (about an hour the first time: the classifier reads 69,542 emails)
    python -m src.router.build --weights-only              # the reliability of every rule from EVERY train email, no classifier (about 3 minutes); saves score_rule_weights.csv
    python -m src.router.build --weights-only --write-reliability   # the same, and writes src/router/reliability.json (the file the score reads)
    python -m src.router.build --calibrate                 # the calibration: the grid of points on the VALIDATION split, the choice, nothing else saved but the grid
    python -m src.router.build                             # the final run of a frozen version: rule weights (train), validation emails and threads, benchmark check, checks
    python -m src.router.build --parity 300                # also run the real analyze() on 300 validation emails and compare with the batch scores

Reads  data/processed/cleaned.parquet, headers.parquet      the emails, their evidence and their redacted bodies (train rows; validation rows in --calibrate and the final run; never test)
       data/processed/claims_cache/                         the claims of Phase 7 (built by Phase 8)
       data/processed/threads.parquet, thread_features/     the real threads of Phase 9 and their cached features
       data/threads/                                        the hijack benchmark of Phase 9
       artifacts/tactic_model/                              the classifier (only for emails whose probabilities are not cached yet)
Writes data/processed/tactic_probs/                         tactic probabilities per email and split, cached (never committed)
       src/router/reliability.json                          with --write-reliability only: the reliability factor of each noisy rule (committed; the score reads it)
       results/score_rule_weights.csv                       per rule: how often it fires on ordinary real mail, and the reliability factor that follows
       results/score_grid.csv                               the grid of points tried, the budgets, the choice
       results/score_config.csv                             the frozen score configuration and the budgets
       results/score_distribution.csv                       emails per band, per category and source (counts and shares)
       results/score_budget.csv                             the false-alarm budget per source of ordinary mail and per source of real threads
       results/score_benchmark_check.csv                    the hijack benchmark scored with the frozen numbers, with and without the thread verifier
       results/score_checks.csv                             PASS/FAIL checks, versions and run details

WHAT THIS CAN AND CANNOT SAY. Nobody labelled which emails contain a contradicted claim, so the score has no precision or recall here. What the
data CAN say, and what is calibrated:
  - the false-alarm side: how many ordinary emails (ham and spam, per source) and how many unmodified messages of real threads reach Suspicious
    or High risk. The budget (High risk at most 1%, Suspicious or above at most 5%, per source with 20 or more checked emails) is declared in this file
    before the validation emails are read; a policy, not something the data decide.
  - the shape of the formula is fixed by its meaning (a lone high is Suspicious, a lone high with urgency or secrecy is High risk, a lone medium is
    Suspicious, a lone low is not): the grid keeps only the points that satisfy that, then picks the one closest to the initial numbers that also meets the
    budget on validation. If none does, the finding is that the rules are too noisy, and the run says so.
  - a RELIABILITY factor per rule from train: a rule that would breach the budget on its own (it fires on more than 5% of the ordinary mail of a source,
    with 20 or more hits) counts half; above 10% it counts nothing.
What it CANNOT say: how good the score is at finding attacks. Attack emails and ordinary emails come from different corpora with different header
evidence, so the share of phishing or fraud emails that reach each band is reported per source and is a description, not a recall. The hijack benchmark is
synthetic and built to trigger the rules, so it is a check of the wiring (does a rule that fires reach the right band, with and without the thread
verifier), never a fitting target. The attack and benchmark numbers are NOT used to choose any number.

Discipline: `--train-only` never loads a validation email. `--calibrate` and the final run read validation (the calibration IS the use of validation for this
score version); the test split is never read here (Phase 13). A change to any number of the score is a new SCORE_VERSION with a line in SCORE_LOG.
"""

import argparse
import json
import time
from collections import Counter

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.claims.patterns import PATTERN_VERSION
from src.data.label_schema import TACTICS
from src.data.paths import (
    HIJACK_CASES_CSV, HIJACK_INJECTIONS_CSV, RESULTS_DIR, SCORE_BENCHMARK_CHECK_CSV, SCORE_BUDGET_CSV, SCORE_CHECKS_CSV, SCORE_CONFIG_CSV, SCORE_DISTRIBUTION_CSV,
    RELIABILITY_JSON, SCORE_GRID_CSV, SCORE_RULE_WEIGHTS_CSV, STAGED_PARQUET, TACTIC_MODEL_DIR, TACTIC_PROBS_DIR, TACTIC_RUN_INFO_JSON, THREAD_SIGNAL_RATES_CSV, THREADS_PARQUET, relative,
)
from src.data.hijack_benchmark import VARIANTS, candidate_message, case_thread
from src.models.dataset import model_text
from src.router import selftest as router_selftest
from src.router.ledger import KNOWN_RULES, RULE_TYPE, RULE_VERIFIER
from src.router.score import SCORE_LOG, SCORE_VERSION, band_of, fired_tactics, make_config, score_ledger
from src.router import score as score_module
from src.thread import builder
from src.thread.evaluate import SEED, metric_row
from src.thread.features import attach_features
from src.verifiers.build import FACT_COLUMNS, get_claims, load_split
from src.verifiers.rows import check_row
from src.verifiers.thread_verifier import THREAD_RULES_VERSION, verify_thread_message
from src.verifiers.verify import RULES_VERSION, verify_claims

SCORE_FILES = {"rule_weights": SCORE_RULE_WEIGHTS_CSV, "grid": SCORE_GRID_CSV, "config": SCORE_CONFIG_CSV, "distribution": SCORE_DISTRIBUTION_CSV, "budget": SCORE_BUDGET_CSV,
               "benchmark_check": SCORE_BENCHMARK_CHECK_CSV, "checks": SCORE_CHECKS_CSV}

ORDINARY = ("ham", "spam")                    # not labelled as an attack
BUDGET_HIGH = 0.01                            # High risk may be at most this share of the checked ordinary emails of a source
BUDGET_SUSPICIOUS = 0.05                      # Suspicious or above may be at most this share
MIN_GROUP = 20                                # fewer checked emails than this in a source and the budget is not judged
MIN_HITS = 20                                 # fewer hits than this and a rule is not called noisy
HALF_RATE, ZERO_RATE = BUDGET_SUSPICIOUS, 2 * BUDGET_SUSPICIOUS     # reliability 0.5 above the first, 0 above the second
INITIAL = (60, 35, 0.25)                      # high points, medium points, pressure step: the numbers of score version 0.1
GRID = [(h, m, s) for h in (50, 60, 70) for m in (25, 35, 45) for s in (0.15, 0.25, 0.35)]
CHUNK = 400                                   # emails per classifier call (and per save of the probabilities cache)


# ---------------------------------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------------------------------

def wilson(hits, n, z=1.96):
    """95% Wilson interval of hits/n (hand-written): (low, high); (None, None) for n = 0."""
    if n == 0:
        return None, None
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def pct(value):
    return None if value is None else round(100 * value, 2)


def shown(path):
    """A path relative to the project for printing; any other path (the build self-test uses a temporary folder) as it is."""
    try:
        return relative(path)
    except ValueError:
        return path


def fmt(value):
    """A number for printing; a missing one (a group too small for a rate) as a dash."""
    return "-" if value is None or (isinstance(value, float) and value != value) else value


def read_thresholds_file(model_dir=TACTIC_MODEL_DIR):
    """The seven thresholds from thresholds.json next to the weights (no torch needed)."""
    with open(model_dir / "thresholds.json", encoding="utf-8") as handle:
        data = json.load(handle)
    if set(data) != set(TACTICS):
        raise SystemExit("thresholds.json must hold the seven tactics %s" % list(TACTICS))
    return {t: float(data[t]) for t in TACTICS}


def run_stamp():
    """What the cached probabilities depend on: the finish time of the Colab training run."""
    if TACTIC_RUN_INFO_JSON.exists():
        with open(TACTIC_RUN_INFO_JSON, encoding="utf-8") as handle:
            return {"tactic_run": json.load(handle).get("finished_utc")}
    return {"tactic_run": None}


def get_probs(table, split, classifier_factory, stamp):
    """Tactic probabilities (rows in the order of table, columns in TACTICS order, rounded to 4 decimals), from the cache where possible.

    The classifier is created (and the weights loaded) only if some email is not in the cache. The cache is saved after every chunk."""
    TACTIC_PROBS_DIR.mkdir(parents=True, exist_ok=True)
    path, side = TACTIC_PROBS_DIR / ("probs_%s.parquet" % split), TACTIC_PROBS_DIR / ("probs_%s.json" % split)
    cached = {}
    if path.exists() and side.exists():
        with open(side, encoding="utf-8") as handle:
            if json.load(handle) == stamp:
                frame = pd.read_parquet(path)
                cached = {i: row for i, row in zip(frame["id"], frame[list(TACTICS)].to_numpy())}
    missing = [i for i in table["id"] if i not in cached]
    if missing:
        classifier = classifier_factory()
        bodies = dict(zip(table["id"], table["body_redacted"]))
        print("  %d of %d %s emails need tactic probabilities (the rest come from the cache)" % (len(missing), len(table), split))
        for start in tqdm(range(0, len(missing), CHUNK), desc="  classifier", unit=" x%d emails" % CHUNK):
            part = missing[start:start + CHUNK]
            probs = classifier.probabilities([bodies[i] if isinstance(bodies[i], str) else "" for i in part])
            for i, row in zip(part, probs):
                cached[i] = np.round(np.asarray(row, dtype=float), 4)
            frame = pd.DataFrame({"id": list(cached)})
            for k, tactic in enumerate(TACTICS):
                frame[tactic] = [float(cached[i][k]) for i in frame["id"]]
            frame.to_parquet(path, index=False)
            with open(side, "w", encoding="utf-8") as handle:
                json.dump(stamp, handle)
    return np.array([cached[i] for i in table["id"]], dtype=float)


# ---------------------------------------------------------------------------------------------------------------------
# Units: one per email or per thread message, with only what the score needs
# ---------------------------------------------------------------------------------------------------------------------

def lite(row):
    return {"claim_id": row["claim_id"], "claim_type": row["claim_type"], "verifier": row["verifier"], "rule": row["rule"],
            "severity": row["severity"], "contradiction": True, "reason": ""}


def make_unit(uid, kind, group, category, rows, fired, extra=None):
    """A unit for scoring: its contradictions (the only rows the score reads), the tactics that fired, and whether any claim could be checked at all."""
    contradictions = [lite(r) for r in rows if r["contradiction"] is True]
    unit = {"id": uid, "kind": kind, "group": group, "category": category, "checked": any(r["contradiction"] is not None for r in rows),
            "fired": list(fired), "rows": contradictions, "rules": {r["rule"] for r in contradictions}}
    unit.update(extra or {})
    return unit


def email_units(split, limit, workers, classifier_factory, thresholds, stamp, with_tactics=True):
    """(units, problems found by check_row, claims extracted now) for the emails of one split.

    with_tactics=False skips the classifier (no email has a fired tactic): enough for the reliability of the rules, which needs the rows only."""
    table = load_split(split, limit)
    claim_lists, extracted = get_claims(table, split, workers)
    probs = get_probs(table, split, classifier_factory, stamp) if with_tactics else np.zeros((len(table), len(TACTICS)))
    facts_rows = table[FACT_COLUMNS].to_dict("records")
    units, problems = [], []
    columns = zip(table["id"], table["source"], table["category"], table["body_redacted"], table["contact"])
    for position, (uid, source, category, body, contact) in enumerate(tqdm(columns, total=len(table), desc="  verifying %s" % split, unit=" emails")):
        claims = claim_lists[position]
        rows = verify_claims(claims, facts_rows[position], contact if isinstance(contact, str) else "", model_text(body) if isinstance(body, str) else "") if claims else []
        for row in rows:
            problems += check_row(row, KNOWN_RULES)
        units.append(make_unit(uid, "email", source, category, rows, fired_tactics(probs[position], thresholds), {"split": split}))
    return units, problems, extracted


def thread_units(threads, thresholds, split):
    """Units for the messages with a past of real, unmodified threads (every contradiction there is a false alarm). threads: {thread id: messages with features}."""
    units = []
    for tid, messages in threads.items():
        for i in range(1, len(messages)):
            m = messages[i]
            claim_rows = verify_claims(m["claims"] or [], m["facts"], "", model_text(m["redacted"]), thread=(messages, i))
            signals = [r for r in verify_thread_message(messages, i, thresholds) if r["claim_id"] == "thread"]
            units.append(make_unit("%s|%d" % (tid, i), "thread", m["source"], "real_thread", claim_rows + signals, fired_tactics(m["tactics"], thresholds),
                                   {"split": split, "thread": tid}))
    return units


def load_real_threads(split, featurize):
    """{thread id: messages with tactic probabilities and claims} for the real threads of a split (features from the Phase 9 cache)."""
    table = pd.read_parquet(THREADS_PARQUET)
    part = table[table["split"] == split]
    threads = builder.table_to_threads(part)
    featurize([m for t in threads.values() for m in t], split)
    return threads


# ---------------------------------------------------------------------------------------------------------------------
# Reliability of the rules (from train)
# ---------------------------------------------------------------------------------------------------------------------

def read_thread_rates():
    """{rule: [(source, hits, messages with a past)]} for the thread rules on the TRAIN threads, from the Phase 9 results (counts only)."""
    rates = pd.read_csv(THREAD_SIGNAL_RATES_CSV)
    rates = rates[rates["split"] == "train"]
    past = {r.source: int(r.rows) for r in rates[rates["rule"] == "(all rules)"].itertuples()}
    out = {}
    for r in rates[rates["rule"] != "(all rules)"].itertuples():
        out.setdefault(r.rule, []).append((r.source, int(r.contradiction), past.get(r.source, 0)))
    return out


def proposed_reliability(judged_rates):
    """1, 0.5 or 0 from the highest rate among the groups where the rule had enough hits to be judged."""
    worst = max(judged_rates, default=0.0)
    return 0.0 if worst > ZERO_RATE else 0.5 if worst > HALF_RATE else 1.0


def rule_weight_table(train_units, thread_rates, current):
    """One row per rule and group: how often the rule fires on ordinary real mail, and the reliability that follows (the same for all rows of a rule)."""
    denominator, hits_by = {}, {}
    for u in train_units:
        if u["category"] in ORDINARY and u["checked"]:
            denominator[u["group"]] = denominator.get(u["group"], 0) + 1
            for rule in u["rules"]:
                hits_by[(u["group"], rule)] = hits_by.get((u["group"], rule), 0) + 1
    rows = []
    for rule in sorted(KNOWN_RULES):
        verifier = RULE_VERIFIER[rule]
        if verifier == "thread":
            if rule == "tv_needs_thread":
                continue
            groups = [("train real thread messages with a past", source, den, hits) for source, hits, den in thread_rates.get(rule, [])]
        else:
            groups = [("train ordinary mail (ham and spam) with a checked claim", source, den, hits_by.get((source, rule), 0)) for source, den in sorted(denominator.items())]
        judged = [hits / den for _, _, den, hits in groups if den and hits >= MIN_HITS]
        reliability = proposed_reliability(judged)
        for basis, source, den, hits in groups:
            rows.append({"rule": rule, "verifier": verifier, "claim_type": RULE_TYPE.get(rule, ""), "basis": basis, "group": source, "denominator": den, "hits": hits,
                         "rate_pct": pct(hits / den) if den else None, "judged": bool(den and hits >= MIN_HITS), "proposed_reliability": reliability,
                         "current_reliability": current.get(rule, 1.0)})
    return pd.DataFrame(rows, columns=["rule", "verifier", "claim_type", "basis", "group", "denominator", "hits", "rate_pct", "judged", "proposed_reliability", "current_reliability"])


def reliability_from(weights):
    """{rule: factor} for the rules whose proposed reliability is below 1 (the content of reliability.json)."""
    proposed = weights.groupby("rule")["proposed_reliability"].first()
    return {rule: float(factor) for rule, factor in sorted(proposed.items()) if factor < 1.0}


def write_reliability(factors, basis, path=None):
    """Write reliability.json for the current score version."""
    path = path or RELIABILITY_JSON
    data = {"for_score_version": SCORE_VERSION, "basis": basis,
            "rule": "A rule that fires on more than %g%% of the checked ordinary mail of a source (or of the real thread messages of a source), with %d or more hits, counts 0.5; "
                    "above %g%% it counts 0. A rule that is not listed counts 1." % (100 * HALF_RATE, MIN_HITS, 100 * ZERO_RATE),
            "reliability": factors}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


# ---------------------------------------------------------------------------------------------------------------------
# Scores, budgets, the grid
# ---------------------------------------------------------------------------------------------------------------------

def scored(units, config):
    """Attach score and band to every unit (in place) and return the units."""
    for u in units:
        detail = score_ledger(u["rows"], u["fired"], config)
        u["score"], u["band"] = detail["score"], detail["band"]
        top = next((g for g in detail["groups"] if g["counted"] > 0), None)
        u["top_rule"] = top["rule"] if top else ""
    return units


def budget_rows(units, config, split):
    """Per group (source of emails, source of threads) of CHECKED ORDINARY units: how many, how many High risk, how many Suspicious or above, and the verdict."""
    scored(units, config)
    groups = {}
    for u in units:
        if u["category"] in ORDINARY + ("real_thread",) and u["checked"]:
            groups.setdefault((u["kind"], u["group"]), []).append(u)
    rows = []
    for (kind, group), members in sorted(groups.items()):
        n = len(members)
        high = sum(1 for u in members if u["band"] == "High risk")
        susp = sum(1 for u in members if u["band"] != "Low risk")
        low_h, high_h = wilson(high, n)
        low_s, high_s = wilson(susp, n)
        judged = n >= MIN_GROUP
        ok = (high / n <= BUDGET_HIGH and susp / n <= BUDGET_SUSPICIOUS) if judged else None
        behind = Counter(u["top_rule"] for u in members if u["band"] != "Low risk")
        rows.append({"split": split, "kind": kind, "group": group, "checked_n": n, "high_n": high, "high_pct": pct(high / n) if n >= 10 else None,
                     "high_ci_low": pct(low_h) if n >= 10 else None, "high_ci_high": pct(high_h) if n >= 10 else None,
                     "suspicious_or_high_n": susp, "suspicious_or_high_pct": pct(susp / n) if n >= 10 else None,
                     "suspicious_ci_low": pct(low_s) if n >= 10 else None, "suspicious_ci_high": pct(high_s) if n >= 10 else None,
                     "budget": "info (fewer than %d)" % MIN_GROUP if ok is None else "PASS" if ok else "FAIL",
                     "top_rules": "; ".join("%s:%d" % (rule, count) for rule, count in behind.most_common(4))})
    return pd.DataFrame(rows)


DEFAULT_CUTS = score_module.CUTS


def meaning_ok(high, medium, step, low=5):
    """The shape fixed by the meaning of Section 6.6: a lone high is Suspicious (not High), a lone medium is Suspicious, a lone low is not, and a lone high
    with one pressure tactic is High risk (its 4 tactic points included)."""
    c = DEFAULT_CUTS
    return (c[0] <= medium < c[1] and c[0] <= high < c[1] and low < c[0] and medium < high and high * (1 + step) + score_module.TACTIC_POINTS >= c[1])


def distance(point):
    h, m, s = point
    return abs(h - INITIAL[0]) / 10 + abs(m - INITIAL[1]) / 10 + abs(s - INITIAL[2]) / 0.1


def grid_table(units, split, reliability):
    """Try every point of GRID on the units: the budget verdict, the worst group and whether the meaning holds."""
    rows = []
    for h, m, s in GRID:
        config = make_config(points={"high": h, "medium": m, "low": 5}, pressure={"urgency": s, "secrecy": s}, reliability=reliability)
        table = budget_rows(units, config, split)
        judged = table[table["budget"].isin(["PASS", "FAIL"])]
        rows.append({"split": split, "high_points": h, "medium_points": m, "pressure_step": s, "meaning_ok": meaning_ok(h, m, s),
                     "groups_judged": len(judged), "groups_failing": int((judged["budget"] == "FAIL").sum()),
                     "worst_high_pct": float((100 * judged["high_n"] / judged["checked_n"]).max()) if len(judged) else None,
                     "worst_suspicious_or_high_pct": float((100 * judged["suspicious_or_high_n"] / judged["checked_n"]).max()) if len(judged) else None,
                     "budget_ok": (int((judged["budget"] == "FAIL").sum()) == 0) if len(judged) else None,
                     "distance_from_initial": round(distance((h, m, s)), 2), "chosen": False})
    return pd.DataFrame(rows)


def choose(grid):
    """The row of the grid to keep: meaning holds, budget met, closest to the initial numbers (ties: fewer total points, then smaller step). None if no row qualifies."""
    ok = grid[grid["meaning_ok"] & (grid["budget_ok"] == True)]       # noqa: E712 (a pandas comparison, not a Python one)
    if ok.empty:
        return None
    ok = ok.sort_values(["distance_from_initial", "high_points", "medium_points", "pressure_step"])
    return ok.iloc[0]


def current_point():
    c = score_module.DEFAULT_CONFIG
    return (c["points"]["high"], c["points"]["medium"], c["pressure"]["urgency"])


def distribution_table(units, config, split):
    """Emails per band for all emails, per category, per source and per source and category (counts and shares), overall and among emails with a checked claim."""
    scored(units, config)
    frame = pd.DataFrame([{"category": u["category"], "source": u["group"], "checked": u["checked"], "band": u["band"], "score": u["score"]} for u in units])
    rows = []
    for group_by, columns in (("all", []), ("category", ["category"]), ("source", ["source"]), ("source_category", ["source", "category"])):
        pieces = [("all", frame)] if not columns else [("/".join(map(str, key)) if isinstance(key, tuple) else str(key), sub) for key, sub in frame.groupby(columns)]
        for label, sub in pieces:
            checked = sub[sub["checked"]]
            row = {"split": split, "group_by": group_by, "group": label, "emails": len(sub), "checked_emails": len(checked), "score_mean": round(float(sub["score"].mean()), 2)}
            for band, key in zip(score_module.BANDS, ("low", "suspicious", "high")):
                row[key] = int((sub["band"] == band).sum())
                row["checked_" + key] = int((checked["band"] == band).sum())
            row["suspicious_or_high_pct"] = pct((row["suspicious"] + row["high"]) / len(sub)) if len(sub) >= 10 else None
            row["high_pct"] = pct(row["high"] / len(sub)) if len(sub) >= 10 else None
            row["checked_suspicious_or_high_pct"] = pct((row["checked_suspicious"] + row["checked_high"]) / len(checked)) if len(checked) >= 10 else None
            row["checked_high_pct"] = pct(row["checked_high"] / len(checked)) if len(checked) >= 10 else None
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------------
# The hijack benchmark, scored (a check of the wiring, never a fitting target)
# ---------------------------------------------------------------------------------------------------------------------

def benchmark_detail(cases, threads_by_id, injections, thresholds, config, featurize):
    """One row per case: the score of the candidate message with the thread verifier in the ledger (full) and with the Phase 8 verifiers alone."""
    candidates = []
    for case in cases.to_dict("records"):
        messages = threads_by_id[case["thread"]]
        candidate, facts = candidate_message(case["variant"], messages, int(case["index"]), injections[case["thread"]])
        candidates.append((case, messages, candidate, facts))
    featurize([c for case, _, c, _ in candidates if case["variant"] != "neg_real"], "hijack")
    rows = []
    for case, messages, candidate, facts in candidates:
        k = int(case["index"])
        thread = case_thread(case["variant"], messages, k, candidate)
        p8_rows = verify_claims(candidate["claims"] or [], facts, "", model_text(candidate["redacted"]))
        full_claims = verify_claims(candidate["claims"] or [], facts, "", model_text(candidate["redacted"]), thread=(thread, k))
        signals = [r for r in verify_thread_message(thread, k, thresholds) if r["claim_id"] == "thread"]
        fired = fired_tactics(candidate["tactics"], thresholds)
        full, without = score_ledger(full_claims + signals, fired, config), score_ledger(p8_rows, fired, config)
        rows.append({"case_id": case["case_id"], "thread": case["thread"], "split": case["split"], "source": case["source"], "variant": case["variant"],
                     "label": int(case["label"]), "score_full": full["score"], "band_full": full["band"], "score_phase8": without["score"], "band_phase8": without["band"]})
    return pd.DataFrame(rows)


def benchmark_table(detail):
    rng = np.random.default_rng(SEED)
    rows = []
    for (split, source), part in detail.groupby(["split", "source"]):
        for variant in [v for v in VARIANTS if (part["variant"] == v).any()] + ["attacks (A+B+C)"]:
            sub = part[part["label"] == 1] if variant.startswith("attacks") else part[part["variant"] == variant]
            clusters = sub["thread"].tolist()
            for metric, column, band in (("suspicious_or_high_full", "band_full", None), ("high_full", "band_full", "High risk"),
                                         ("suspicious_or_high_phase8", "band_phase8", None), ("high_phase8", "band_phase8", "High risk")):
                hits = [(b == band) if band else (b != "Low risk") for b in sub[column]]
                rows.append(metric_row(split, source, variant, metric, hits, clusters, rng, "negatives: these are false alarms" if variant.startswith("neg_") else ""))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------------
# Parity: the batch score and the real analyze() must agree
# ---------------------------------------------------------------------------------------------------------------------

MIME_HEADERS = ("content-type:", "content-transfer-encoding:", "content-disposition:", "mime-version:")


def strip_mime_headers(block):
    """The header block without the MIME headers and their continuation lines.

    staged.parquet keeps the body already decoded (Phase 1), so the original Content-Type (a multipart boundary, base64) no longer describes it; a rebuilt email
    that kept it would be read as an empty multipart. Without them the body is plain text, as the batch code read it."""
    kept, skipping = [], False
    for line in str(block).replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t"):
            if not skipping:
                kept.append(line)
            continue
        skipping = line.lower().startswith(MIME_HEADERS)
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def parity_check(units, n, analyzer_factory):
    """Run the real analyze() on n random validation emails (rebuilt from staged.parquet) and compare with the batch scores. Returns (rows, agree_band, agree_score)."""
    rng = np.random.default_rng(SEED)
    email_units_ = [u for u in units if u["kind"] == "email"]
    picked = [email_units_[i] for i in rng.choice(len(email_units_), size=min(n, len(email_units_)), replace=False)]
    ids = [u["id"] for u in picked]
    staged = pd.read_parquet(STAGED_PARQUET, columns=["id", "raw_headers", "body_raw"], filters=[("id", "in", ids)]).set_index("id")
    analyzer = analyzer_factory()
    rows = []
    for u in tqdm(picked, desc="  parity", unit=" emails"):
        raw = ("%s\n\n%s" % (strip_mime_headers(staged.at[u["id"], "raw_headers"]), staged.at[u["id"], "body_raw"])).encode("utf-8", errors="replace")
        report = analyzer.analyze(raw, explain=False)
        rows.append({"id": u["id"], "group": u["group"], "batch_score": u["score"], "analyze_score": report["score"], "batch_band": u["band"], "analyze_band": report["verdict"]})
    frame = pd.DataFrame(rows)
    return frame, float((frame["batch_band"] == frame["analyze_band"]).mean()), float((frame["batch_score"] == frame["analyze_score"]).mean())


# ---------------------------------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------------------------------

def make_checks(ctx):
    checks = []

    def add(check, item, value, expected, status):
        checks.append({"check": check, "item": item, "value": value, "expected": expected, "status": status})

    from src.explain import lime_explain
    passed, total = router_selftest.self_test(verbose=False)
    add("selftest", "router, ledger, score and pipeline self-test", "%s of %d" % ("all" if passed else "NOT all", total), "all pass", "PASS" if passed else "FAIL")
    passed, total = lime_explain.self_test(verbose=False)
    add("selftest", "LIME self-test", "%s of %d" % ("all" if passed else "NOT all", total), "all pass", "PASS" if passed else "FAIL")
    add("rows_valid", "verifier rows that fail check_row", len(ctx["problems"]), "0", "PASS" if not ctx["problems"] else "FAIL")
    units = ctx["scored_units"]
    bad = [u for u in units if not (isinstance(u["score"], int) and 0 <= u["score"] <= 100)]
    add("score_range", "units whose score is not a whole number from 0 to 100", len(bad), "0", "PASS" if not bad else "FAIL")
    wrong = [u for u in units if u["band"] != band_of(u["score"], ctx["config"]["cuts"])]
    add("bands", "units whose band does not fit their score", len(wrong), "0", "PASS" if not wrong else "FAIL")
    no_evidence = [u for u in units if not u["checked"] and u["kind"] == "email" and any(u["rows"])]
    add("evidence_discipline", "emails with a contradiction but no checked claim", len(no_evidence), "0", "PASS" if not no_evidence else "FAIL")
    add("leakage_guard", "splits read", "+".join(ctx["splits"]), "train only (--train-only) or train and validation; never test",
        "PASS" if set(ctx["splits"]) <= {"train", "validation"} else "FAIL")
    add("validation_read", "this run read the validation emails", "no (--train-only)" if ctx["train_only"] else "yes", "yes in --calibrate and the final run", "info" if ctx["train_only"] else "PASS")
    for row in ctx["budget"].itertuples():
        status = row.budget if not ctx["train_only"] else ("info (development, train)" if row.budget in ("PASS", "FAIL") else row.budget)
        summary = "%d checked; High risk %s%%, Suspicious or above %s%%" % (row.checked_n, fmt(row.high_pct), fmt(row.suspicious_or_high_pct))
        add("budget", "%s %s (%s)" % (row.split, row.group, row.kind), summary, "High risk <= %g%%, Suspicious or above <= %g%%" % (100 * BUDGET_HIGH, 100 * BUDGET_SUSPICIOUS),
            status if status in ("PASS", "FAIL") else "info")
    judged = ctx["budget"][ctx["budget"]["budget"].isin(["PASS", "FAIL"])]
    add("budget", "groups with enough checked emails to be judged", len(judged), ">= 1", "PASS" if len(judged) else ("info" if ctx["train_only"] else "FAIL"))
    if ctx["grid"] is not None:
        pick = choose(ctx["grid"])
        if pick is None:
            add("calibration", "a grid point that keeps the meaning and meets the budget", "none", "one", "info" if ctx["train_only"] else "FAIL")
        else:
            point = (int(pick["high_points"]), int(pick["medium_points"]), float(pick["pressure_step"]))
            add("calibration", "chosen point (high, medium, pressure step) on %s" % ctx["grid"]["split"].iloc[0], str(point), "", "info")
            if not ctx["train_only"]:
                add("calibration", "the frozen numbers equal the chosen point", "%s vs %s" % (current_point(), point), "equal", "PASS" if current_point() == point else "FAIL")
    if ctx.get("weights") is not None:
        proposed, current = reliability_from(ctx["weights"]), dict(ctx["config"]["reliability"])
        full = not ctx["train_only"] and not ctx["limit"]
        add("calibration", "reliability.json equals the factors computed from %s" % ("every train email" if full else "this sample of train emails"),
            "same" if proposed == current else "proposed %s, file %s" % (proposed or "none", current or "none"), "same",
            ("PASS" if proposed == current else "FAIL") if full else "info")
    if ctx.get("parity") is not None:
        add("parity", "validation emails scored by analyze() and by the batch code: same band / same score", "%.1f%% / %.1f%% of %d" % (100 * ctx["parity"][1], 100 * ctx["parity"][2], len(ctx["parity"][0])),
            ">= 95% same band", "PASS" if ctx["parity"][1] >= 0.95 else "FAIL")
    if ctx.get("benchmark") is not None:
        bench = ctx["benchmark"]
        for source in sorted(bench["source"].unique()):
            neg = bench[(bench["source"] == source) & (bench["variant"] == "neg_real") & (bench["metric"] == "suspicious_or_high_full")]
            if not neg.empty and pd.notna(neg.iloc[0]["rate"]):
                add("benchmark", "%s %s: real next reply reaching Suspicious or above (a false alarm)" % (neg.iloc[0]["split"], source), "%.1f%% of %d" % (100 * neg.iloc[0]["rate"], neg.iloc[0]["n"]),
                    "<= %g%% (a finding if not)" % (100 * BUDGET_SUSPICIOUS), "PASS" if neg.iloc[0]["rate"] <= BUDGET_SUSPICIOUS else "info")
    add("run", "score version / rules version / thread rules version / claim patterns", "%s / %s / %s / %s" % (SCORE_VERSION, RULES_VERSION, THREAD_RULES_VERSION, PATTERN_VERSION), "", "info")
    add("run", "tactic model run", str(ctx["stamp"].get("tactic_run")), "", "info")
    for name, count in ctx["counts"].items():
        add("run", name, count, "", "info")
    add("run", "--limit (0 means every train email)", ctx["limit"], "0 in the final run", "info" if ctx["limit"] else "PASS")
    add("run", "seconds", round(time.time() - ctx["started"]), "", "info")
    return pd.DataFrame(checks)


# ---------------------------------------------------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------------------------------------------------

def print_distribution(dist, split):
    pd.set_option("display.width", 230)
    part = dist[(dist["split"] == split) & (dist["group_by"].isin(["category", "source_category"]))]
    print("\nBands per category and source (%s): emails | of them with a checked claim: Low risk / Suspicious / High risk" % split)
    for r in part.itertuples():
        print("  %-34s %6d emails | %5d checked: %5d / %4d / %4d   (Suspicious or above %s%%, High risk %s%% of the checked)" % (
            r.group, r.emails, r.checked_emails, r.checked_low, r.checked_suspicious, r.checked_high, fmt(r.checked_suspicious_or_high_pct), fmt(r.checked_high_pct)))


def print_budget(budget):
    print("\nFalse-alarm budget (High risk <= %g%%, Suspicious or above <= %g%% of the checked ordinary emails / real thread messages of a source, judged from %d):" % (
        100 * BUDGET_HIGH, 100 * BUDGET_SUSPICIOUS, MIN_GROUP))
    for r in budget.itertuples():
        print("  %-10s %-24s %6d checked   High risk %5s%% [%s, %s]   Suspicious or above %5s%% [%s, %s]   %s" % (
            r.kind, r.group, r.checked_n, fmt(r.high_pct), fmt(r.high_ci_low), fmt(r.high_ci_high), fmt(r.suspicious_or_high_pct), fmt(r.suspicious_ci_low), fmt(r.suspicious_ci_high), r.budget))
        if r.top_rules:
            print("             rules behind Suspicious or above (strongest finding of each email or message): %s" % r.top_rules)


def print_grid(grid):
    pick = choose(grid)
    print("\nGrid (split %s): points high / medium / pressure step -> meaning, budget, worst source" % grid["split"].iloc[0])
    for r in grid.itertuples():
        mark = "  <== CHOSEN" if pick is not None and (r.high_points, r.medium_points, r.pressure_step) == (pick["high_points"], pick["medium_points"], pick["pressure_step"]) else ""
        print("  %3d / %3d / %.2f   meaning %-5s budget %-5s worst High risk %5s%% worst Suspicious or above %5s%%  distance %.2f%s" % (
            r.high_points, r.medium_points, r.pressure_step, r.meaning_ok, r.budget_ok, None if r.worst_high_pct is None else round(r.worst_high_pct, 2),
            None if r.worst_suspicious_or_high_pct is None else round(r.worst_suspicious_or_high_pct, 2), r.distance_from_initial, mark))
    if pick is None:
        print("  NO grid point keeps the meaning and meets the budget: the rules are too noisy for these budgets (a finding; see score_budget.csv).")


def print_weights(weights):
    changed = weights[weights["proposed_reliability"] < 1.0]
    print("\nRules whose reliability would be lowered (fire on > %g%% of the ordinary mail of a source or of real thread messages, with >= %d hits):" % (100 * HALF_RATE, MIN_HITS))
    if changed.empty:
        print("  none")
    for rule, sub in changed.groupby("rule"):
        worst = sub[sub["judged"]].sort_values("rate_pct", ascending=False).iloc[0]
        print("  %-26s -> %.1f   worst %s %s%% (%d of %d)" % (rule, sub["proposed_reliability"].iloc[0], worst["group"], worst["rate_pct"], worst["hits"], worst["denominator"]))
    near = weights[(weights["proposed_reliability"] == 1.0) & weights["judged"] & (weights["rate_pct"] > 100 * BUDGET_HIGH)]
    for r in near.sort_values("rate_pct", ascending=False).head(8).itertuples():
        print("  (kept at 1.0, fires on %s%% of %s: %s, %d of %d)" % (r.rate_pct, r.group, r.rule, r.hits, r.denominator))


# ---------------------------------------------------------------------------------------------------------------------

def run(args, classifier=None, featurize=attach_features, analyzer_factory=None):
    """The whole run. classifier and featurize can be replaced (the self-test of the build does); on the Mac the defaults are the real ones."""
    started = time.time()
    if args.limit and not args.train_only:
        raise SystemExit("--limit is for development runs: use it with --train-only.")
    if args.calibrate and args.train_only:
        raise SystemExit("--calibrate reads the validation split; --train-only never does. Use one of them.")
    if args.write_reliability and not args.weights_only:
        raise SystemExit("--write-reliability goes with --weights-only.")
    if args.weights_only and (args.train_only or args.calibrate or args.limit or args.parity):
        raise SystemExit("--weights-only reads every train email and nothing else: do not combine it with --train-only, --calibrate, --limit or --parity.")
    stamp = run_stamp()

    def classifier_factory():
        nonlocal classifier
        if classifier is None:
            from src.models.predict import TacticClassifier
            classifier = TacticClassifier()
        return classifier

    thresholds = getattr(classifier, "thresholds", None) or read_thresholds_file()
    config = score_module.DEFAULT_CONFIG
    print("Score version %s (rules %s, thread rules %s, claim patterns %s); tactic run %s" % (SCORE_VERSION, RULES_VERSION, THREAD_RULES_VERSION, PATTERN_VERSION, stamp.get("tactic_run")))
    counts, problems = {}, []
    ctx = {"started": started, "stamp": stamp, "train_only": args.train_only, "limit": args.limit, "config": config, "counts": counts, "problems": problems,
           "grid": None, "benchmark": None, "parity": None, "weights": None}
    results = {}

    # ---- the reliability of every rule from every train email (no classifier, no validation)
    if args.weights_only:
        train_units, train_problems, extracted = email_units("train", 0, max(1, args.workers), classifier_factory, thresholds, stamp, with_tactics=False)
        weights = rule_weight_table(train_units, read_thread_rates(), config["reliability"])
        print_weights(weights)
        factors = reliability_from(weights)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        weights.to_csv(SCORE_FILES["rule_weights"], index=False)
        print("\nFrom every train email (%d scored, %d claims extracted now) the factors below 1 are: %s" % (len(train_units), extracted, factors or "none"))
        print("The current file holds: %s -> %s" % (dict(config["reliability"]) or "none", "the same" if factors == dict(config["reliability"]) else "DIFFERENT"))
        if args.write_reliability:
            write_reliability(factors, "Computed by python -m src.router.build --weights-only --write-reliability from every train email (%d) and the Phase 9 thread rates on the train threads "
                                       "(results/score_rule_weights.csv)" % len(train_units))
            print("Wrote %s and %s (commit both). If the factors changed, restart the score checks: --calibrate next." % (shown(RELIABILITY_JSON), shown(SCORE_FILES["rule_weights"])))
        else:
            print("Wrote %s. Add --write-reliability to write %s." % (shown(SCORE_FILES["rule_weights"]), shown(RELIABILITY_JSON)))
        if train_problems:
            print("%d verifier rows failed check_row" % len(train_problems))
        return 1 if train_problems else 0

    # ---- the units of the split that the calibration reads: train (development) or validation
    unit_split = "train" if args.train_only else "validation"
    splits = ["train"] if args.train_only else (["validation"] if args.calibrate else ["train", "validation"])
    ctx["splits"] = splits
    weights_units = []
    if "train" in splits:
        train_units, train_problems, extracted = email_units("train", args.limit, max(1, args.workers), classifier_factory, thresholds, stamp, with_tactics=args.train_only)
        problems += train_problems
        counts["train emails scored / claims extracted now"] = "%d / %d" % (len(train_units), extracted)
        weights_units = train_units
    if unit_split == "validation":
        val_units, val_problems, extracted = email_units("validation", 0, max(1, args.workers), classifier_factory, thresholds, stamp)
        problems += val_problems
        counts["validation emails scored / claims extracted now"] = "%d / %d" % (len(val_units), extracted)
    else:
        val_units = []
    units = weights_units if unit_split == "train" else val_units

    # ---- real threads of the same split
    threads = load_real_threads(unit_split, featurize)
    units = units + thread_units(threads, thresholds, unit_split)
    counts["%s real thread messages with a past scored" % unit_split] = sum(1 for u in units if u["kind"] == "thread")

    # ---- reliability of the rules (train rows) and the grid
    if not args.calibrate:
        weights = rule_weight_table(weights_units, read_thread_rates(), config["reliability"])
        results["rule_weights"] = weights
        ctx["weights"] = weights
        print_weights(weights)
    grid = grid_table(units, unit_split, config["reliability"])
    pick = choose(grid)
    if pick is not None:
        grid.loc[(grid["high_points"] == pick["high_points"]) & (grid["medium_points"] == pick["medium_points"]) & (grid["pressure_step"] == pick["pressure_step"]), "chosen"] = True
    ctx["grid"] = grid
    results["grid"] = grid
    print_grid(grid)

    # ---- the current numbers on the units: distribution, budget
    email_only = [u for u in units if u["kind"] == "email"]
    budget = budget_rows(units, config, unit_split)
    print_budget(budget)
    ctx["budget"], ctx["scored_units"] = budget, units
    if not args.calibrate:
        dist = distribution_table(email_only, config, unit_split)
        results["distribution"], results["budget"] = dist, budget
        print_distribution(dist, unit_split)

        # ---- the hijack benchmark, scored with the frozen numbers (a check, not a fit)
        cases = pd.read_csv(HIJACK_CASES_CSV)
        cases = cases[(cases["split"] == unit_split) & cases["thread"].isin(set(threads))]
        injections = pd.read_csv(HIJACK_INJECTIONS_CSV).set_index("thread").to_dict("index")
        detail = benchmark_detail(cases, threads, injections, thresholds, config, featurize)
        bench = benchmark_table(detail)
        results["benchmark_check"] = bench
        ctx["benchmark"] = bench
        counts["%s hijack benchmark cases scored" % unit_split] = len(detail)
        print("\nHijack benchmark (%s cases), scored with the frozen numbers: share reaching Suspicious or above / High risk, with the thread verifier in the ledger and without it" % unit_split)
        show = bench[bench["variant"].isin(["neg_real", "A", "B", "C"])]
        for (source, variant), sub_table in show.groupby(["source", "variant"]):
            cells = {r.metric: ("%.0f%%" % (100 * r.rate) if pd.notna(r.rate) else "count %d/%d" % (r.hits, r.n)) for r in sub_table.itertuples()}
            print("  %-8s %-9s n=%-3d  with thread verifier: %s / %s    without: %s / %s" % (source, variant, sub_table["n"].iloc[0], cells["suspicious_or_high_full"], cells["high_full"],
                                                                                    cells["suspicious_or_high_phase8"], cells["high_phase8"]))
        if args.parity and not args.train_only:
            ctx["parity"] = parity_check(email_only, args.parity, analyzer_factory or default_analyzer_factory(classifier_factory))
            print("\nParity: %.1f%% of %d emails get the same band from analyze() and from the batch code, %.1f%% the same score" % (100 * ctx["parity"][1], len(ctx["parity"][0]), 100 * ctx["parity"][2]))
            for r in ctx["parity"][0][ctx["parity"][0]["batch_score"] != ctx["parity"][0]["analyze_score"]].head(8).itertuples():
                print("    differs: %s %s batch %d (%s) analyze %d (%s)" % (r.id, r.group, r.batch_score, r.batch_band, r.analyze_score, r.analyze_band))

    # ---- write
    if not args.calibrate:
        results["config"] = config_table(config)
        checks = make_checks(ctx)
        results["checks"] = checks
        print("\nChecks:")
        for r in checks.itertuples():
            print("  %-4s %-20s %-78s %s%s" % (r.status, r.check, str(r.item)[:78], r.value, "  (expected %s)" % r.expected if r.expected else ""))
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for name, frame in results.items():
            frame.to_csv(SCORE_FILES[name], index=False)
        print("\nWrote %s" % ", ".join(str(shown(SCORE_FILES[n])) for n in results))
        failed = int((checks["status"] == "FAIL").sum())
        print("%d checks failed" % failed if failed else "No check failed (info rows are findings, not failures)")
    else:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        grid.to_csv(SCORE_FILES["grid"], index=False)
        print("\nWrote %s (the calibration reads the validation split; nothing else is saved in this mode)" % shown(SCORE_FILES["grid"]))
        failed = 0
    if args.limit:
        print("NOTE: this was a quick run (--limit %d); rerun without --limit before committing the results." % args.limit)
    print("Score version %s: %s" % (SCORE_LOG[-1][0], SCORE_LOG[-1][1][:150]))
    return failed


def config_table(config):
    rows = [("score_version", SCORE_VERSION), ("points_high", config["points"]["high"]), ("points_medium", config["points"]["medium"]), ("points_low", config["points"]["low"]),
            ("discount_per_further_claim", config["discount"]), ("pressure_urgency", config["pressure"]["urgency"]), ("pressure_secrecy", config["pressure"]["secrecy"]),
            ("tactic_points_each", config["tactic_points"]), ("tactic_points_max", config["tactic_max"]), ("cut_suspicious", config["cuts"][0]), ("cut_high_risk", config["cuts"][1]),
            ("rules_with_reliability_below_1", len(config["reliability"])), ("budget_high_risk_share", BUDGET_HIGH), ("budget_suspicious_or_above_share", BUDGET_SUSPICIOUS),
            ("budget_judged_from_checked_emails", MIN_GROUP), ("reliability_half_above_rate", HALF_RATE), ("reliability_zero_above_rate", ZERO_RATE),
            ("reliability_judged_from_hits", MIN_HITS), ("initial_point_high_medium_step", str(INITIAL))]
    rows += [("reliability:" + rule, factor) for rule, factor in sorted(config["reliability"].items())]
    return pd.DataFrame(rows, columns=["setting", "value"])


def default_analyzer_factory(classifier_factory):
    def make():
        from src.router.pipeline import Analyzer
        return Analyzer(classifier=classifier_factory())
    return make


def main():
    parser = argparse.ArgumentParser(description="Score the emails and threads, calibrate the risk score on validation, and check the work (Phase 10).")
    parser.add_argument("--train-only", action="store_true", help="never load validation emails (development)")
    parser.add_argument("--limit", type=int, default=0, help="a random sample of N train emails (needs --train-only)")
    parser.add_argument("--calibrate", action="store_true", help="evaluate the grid on the validation split and print the choice (saves only score_grid.csv)")
    parser.add_argument("--parity", type=int, default=0, help="also run the real analyze() on N validation emails and compare (final run)")
    parser.add_argument("--weights-only", action="store_true", help="the reliability of every rule from every train email, no classifier (about 3 minutes)")
    parser.add_argument("--write-reliability", action="store_true", help="with --weights-only: write src/router/reliability.json")
    parser.add_argument("--workers", type=int, default=1, help="processes for the claim extraction if the cache is incomplete")
    args = parser.parse_args()
    failed = run(args)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
