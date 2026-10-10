"""Phase 13: one table per split with everything the email-level experiments need, built once and cached.

The N3 ablation, the architecture ablation, the risk-score tables and the paraphrase test all start from the same questions about every email: what did
the full system say (score, band, the contradictions behind it), and what did each simpler system see (text only, headers only, the flat vector of the
architecture ablation)? This module answers them once per split with the code the system itself runs (the claims of Phase 7, `verify_claims` of Phases 8 and 9,
the ledger and score of Phase 10), and saves the answer to data/processed/eval_features/. Nothing here is a model of its own; it is plumbing.

One row per email. Columns:
    id, source, category, checked (some claim could be checked), claims_found, claims_checked, score, band, top_rule,
    fired (JSON list of the tactics that fired), contradictions (JSON list of the contradiction rows the score read),
    flat__*  the flat vector of src/router/ledger.py (the architecture ablation reads these),
    txt__*   what the text alone shows: the seven tactic probabilities and how many claims of each type were found,
    hdr__*   what the headers alone show: authentication verdicts, free mailbox, look-alike of the organisation domain, Reply-To and so on,
             with NO claim in sight (the headers-only system of the N3 ablation).

A cached table is thrown away when the claim patterns, the rule versions, the score version or the tactic model's training run change.
"""

import json

import numpy as np
import pandas as pd

from src.claims.patterns import PATTERN_VERSION
from src.data import paths
from src.data.label_schema import CLAIM_TYPES, TACTICS
from src.models.dataset import model_text
from src.router.build import get_probs, make_unit, read_thresholds_file, run_stamp, scored
from src.router.ledger import FEATURE_NAMES, coverage, flat_features
from src.router.score import DEFAULT_CONFIG, SCORE_VERSION, fired_tactics
from src.verifiers.build import FACT_COLUMNS, get_claims, load_split
from src.verifiers.facts import prepare_facts, similar_domain
from src.verifiers.thread_verifier import THREAD_RULES_VERSION
from src.verifiers.verify import RULES_VERSION, verify_claims

BUCKETS = ("pass", "fail", "other", "unknown")
AUTH_STATES = ("aligned", "failed", "list_relayed", "other_domain", "spf_failed", "no_pass", "unknown")
FAIL_VERDICTS = {"fail", "softfail", "permerror", "temperror"}
UNKNOWN_VERDICTS = {"unknown", None}
TEXT_NAMES = ["txt__p_" + t for t in TACTICS] + ["txt__n_" + c for c in CLAIM_TYPES]
HEADER_NAMES = (["hdr__%s_%s" % (m, b) for m in ("spf", "dkim", "dmarc") for b in BUCKETS] + ["hdr__auth_" + s for s in AUTH_STATES]
                + ["hdr__freemail_yes", "hdr__freemail_no", "hdr__name_address", "hdr__name_domain", "hdr__list_mail", "hdr__reply_to_other_domain", "hdr__reply_to_present",
                   "hdr__envelope_mismatch", "hdr__org_known", "hdr__org_checkable", "hdr__from_is_org", "hdr__from_not_org", "hdr__org_same_name_other_suffix",
                   "hdr__org_lookalike", "hdr__org_lookalike_score", "hdr__has_from_domain"])
FLAT_NAMES = ["flat__" + n for n in FEATURE_NAMES]


def verdict_bucket(value):
    if value == "pass":
        return "pass"
    if value in FAIL_VERDICTS:
        return "fail"
    if value in UNKNOWN_VERDICTS:
        return "unknown"
    return "other"


def lookalike_score(value):
    """The organisation look-alike score (0 to 100) as a number between 0 and 1; 0 when it is missing. Accepts any numeric type a table gives (numpy integers included)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number / 100.0 if number == number else 0.0


def text_vector(probabilities, claims):
    """Seven tactic probabilities, then the number of claims of each of the eleven types: all that the text alone shows."""
    counts = {c: 0 for c in CLAIM_TYPES}
    for claim in claims:
        if claim["type"] in counts:
            counts[claim["type"]] += 1
    return [float(p) for p in probabilities] + [float(counts[c]) for c in CLAIM_TYPES]


def header_vector(raw_facts):
    """The header evidence of one email as numbers, in the order of HEADER_NAMES. It never looks at a claim."""
    f = prepare_facts(raw_facts)
    out = []
    for method in ("spf", "dkim", "dmarc"):
        bucket = verdict_bucket(f[method])
        out += [1.0 if bucket == b else 0.0 for b in BUCKETS]
    out += [1.0 if f["auth_state"] == s else 0.0 for s in AUTH_STATES]
    relation = similar_domain(f["from_domain"], f["org_domain"]) if f["from_domain"] and f["org_domain"] else None
    reply_other = bool(f["reply_domain"] and f["from_domain"] and f["reply_domain"] != f["from_domain"])
    out += [1.0 if f["freemail"] is True else 0.0, 1.0 if f["freemail"] is False else 0.0, 1.0 if f["name_address"] else 0.0, 1.0 if f["name_domain"] else 0.0,
            1.0 if f["list_mail"] else 0.0, 1.0 if reply_other else 0.0, 1.0 if f["reply_domain"] else 0.0, 1.0 if f["envelope_mismatch"] else 0.0,
            1.0 if f["org_domain"] else 0.0, 1.0 if f["org_checkable"] else 0.0, 1.0 if f["from_matches_org"] is True else 0.0, 1.0 if f["from_matches_org"] is False else 0.0,
            1.0 if relation == "suffix" else 0.0, 1.0 if relation == "lookalike" else 0.0,
            lookalike_score(f["org_lookalike_score"]), 1.0 if f["from_domain"] else 0.0]
    return out


def world_stamp(limit):
    return {"pattern_version": PATTERN_VERSION, "rules_version": RULES_VERSION, "thread_rules_version": THREAD_RULES_VERSION, "score_version": SCORE_VERSION,
            "tactic_run": run_stamp().get("tactic_run"), "limit": limit, "columns": len(FLAT_NAMES) + len(TEXT_NAMES) + len(HEADER_NAMES)}


def build_from_table(table, name, classifier_factory, thresholds=None, stamp=None, workers=1, config=None):
    """The world table for the emails of `table` (columns of verifiers.build.load_split). `name` names the claim and probability caches."""
    thresholds = thresholds or read_thresholds_file()
    stamp = stamp if stamp is not None else run_stamp()
    config = config or DEFAULT_CONFIG
    claim_lists, _ = get_claims(table, name, workers)
    probabilities = get_probs(table, name, classifier_factory, stamp)
    facts_rows = table[FACT_COLUMNS].to_dict("records")
    n = len(table)
    flat, text, header = np.zeros((n, len(FLAT_NAMES)), dtype=np.float32), np.zeros((n, len(TEXT_NAMES)), dtype=np.float32), np.zeros((n, len(HEADER_NAMES)), dtype=np.float32)
    records = []
    columns = zip(table["id"], table["source"], table["category"], table["body_redacted"], table["contact"])
    for i, (uid, source, category, body, contact) in enumerate(columns):
        claims = claim_lists[i]
        rows = verify_claims(claims, facts_rows[i], contact if isinstance(contact, str) else "", model_text(body) if isinstance(body, str) else "") if claims else []
        fired = fired_tactics(probabilities[i], thresholds)
        unit = make_unit(uid, "email", source, category, rows, fired)
        detail = scored([unit], config)[0]
        cover = coverage(claims, rows)
        flat[i] = flat_features(rows, probabilities[i], cover["claims"], cover["checked"])
        text[i] = text_vector(probabilities[i], claims)
        header[i] = header_vector(facts_rows[i])
        records.append({"id": uid, "source": source, "category": category, "checked": bool(unit["checked"]), "claims_found": int(cover["claims"]),
                        "claims_checked": int(cover["checked"]), "score": int(detail["score"]), "band": detail["band"], "top_rule": detail["top_rule"],
                        "fired": json.dumps(list(fired)), "contradictions": json.dumps(unit["rows"])})
    frame = pd.DataFrame(records)
    return pd.concat([frame, pd.DataFrame(flat, columns=FLAT_NAMES), pd.DataFrame(text, columns=TEXT_NAMES), pd.DataFrame(header, columns=HEADER_NAMES)], axis=1)


def load_world(split, limit=0, workers=1, classifier_factory=None, thresholds=None):
    """The world table of a split, from the cache when its stamp is current. `limit` takes a random sample (for rehearsals); the cache is kept per limit."""
    folder = paths.EVAL_FEATURES_DIR
    suffix = "_n%d" % limit if limit else ""
    table_path, stamp_path = folder / ("world_%s%s.parquet" % (split, suffix)), folder / ("world_%s%s.json" % (split, suffix))
    stamp = world_stamp(limit)
    if table_path.is_file() and stamp_path.is_file() and json.loads(stamp_path.read_text(encoding="utf-8")) == stamp:
        return pd.read_parquet(table_path)
    print("  building the per-email table of the %s split (cached in %s afterwards)" % (split, table_path.parent.name))
    world = build_from_table(load_split(split, limit), split, classifier_factory, thresholds, workers=workers)
    folder.mkdir(parents=True, exist_ok=True)
    world.to_parquet(table_path, index=False)
    stamp_path.write_text(json.dumps(stamp), encoding="utf-8")
    return world


def matrix(world, names):
    """The columns `names` of a world table as a float matrix."""
    return world[names].to_numpy(dtype=np.float64)


def units_from(world, split):
    """Scoring units (the shape src/router/build.py uses) rebuilt from a world table, for the budget and distribution tables."""
    units = []
    for r in world[["id", "source", "category", "checked", "fired", "contradictions"]].itertuples(index=False):
        rows = json.loads(r.contradictions)
        units.append({"id": r.id, "kind": "email", "group": r.source, "category": r.category, "checked": bool(r.checked), "fired": json.loads(r.fired), "rows": rows,
                      "rules": {x["rule"] for x in rows}, "split": split})
    return units
