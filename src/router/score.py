"""Phase 10: the 0 to 100 Pretext Risk Score, the verdict band and the recommended action.

    from src.router.score import score_ledger, band_of, action_for

    detail = score_ledger(rows, fired_tactics)          # rows: the verdict ledger (src/router/ledger.py)
    detail["score"], detail["band"]                      # 62, "Suspicious"
    action_for(detail["band"], detail)                   # fixed text, never text from the email

THE FORMULA (master document Section 6.6, version 0.1 until Phase 10 freezes it):

    1. Only contradictions add points. A consistent row adds nothing and takes nothing away, and a row that is not
       checkable adds nothing. Missing evidence is neither a contradiction nor proof of honesty, and a check that passed
       for gmail.com says nothing about who the person is. (How many claims could not be checked is reported by the
       ledger as coverage.)
    2. Points come from the SEVERITY of the row, not from the type of its claim: the severities of Phases 8 and 9 already say
       how strong each rule is. high 60, medium 35, low 5. Each rule also has a RELIABILITY factor (1, 0.5 or 0), set
       from how often the rule fires on ordinary real mail (a rule that cries wolf counts less). Absent means 1. The factors
       are data, in src/router/reliability.json.
    3. One claim counts once. Rows are grouped by (claim id, claim type); each thread signal (tactic onset, request drift,
       sending path, thread integrity, single email) is its own group because its claim id is 'thread'. Only the
       strongest row of a group counts: one claim contradicted by two rules is still one claim.
    4. A saturating sum. The groups are sorted by points and the k-th counts half as much as the one before it:
       C = p0 + 0.5 p1 + 0.25 p2 + ... A second independent finding is strong evidence; a tenth adds almost nothing.
    5. Pressure tactics multiply. If urgency or secrecy fired, C is multiplied by 1 + 0.25 for each. A tactic raises the
       weight of a contradiction found with it; it never creates one (no contradiction, nothing to multiply).
    6. Small tactic points: authority, urgency, scarcity and secrecy that fired add 4 points each, at most 12.
       Reciprocity, social proof and liking are shown but not scored (Phase 6: fewer than 10 real positives, none found).
    7. score = round(C x multiplier + tactic points), capped at 100. Bands: 0-34 Low risk, 35-69 Suspicious, 70-100 High risk.

Worked values (the self-test checks them): a lone medium 35, a lone high 60, a lone high with urgency 75, two highs 90,
twelve lows about 10.

WHY THESE SHAPES. Severities are labels of rule strength, not probabilities, so they are not multiplied together as
probabilities would be. The discount makes the score grow with independent evidence but saturate, which is what the 0 to 100 scale
needs; the cap is a safety net, not the main limit. A pressure tactic is a modifier because it cannot be proved or disproved from
headers (master document Section 4.4): it matters only next to a contradiction.

CALIBRATION. There are no contradiction labels. The shape above is fixed by its meaning; Phase 10 sets the scale on the validation split
(src/router/build.py): the points are chosen so that ordinary validation mail stays inside a false-alarm budget declared before the
validation emails were read. Attacks, the hijack benchmark and the labelled tactics are reported against the chosen numbers, never fitted.

Security. The action text is fixed here; nothing from an email reaches it. Every number is a plain value from this file.
"""

import copy
import json

from src.data.label_schema import TACTICS
from src.data.paths import RELIABILITY_JSON
from src.models.dataset import MAIN_TACTICS

SCORE_VERSION = "0.2"
SCORE_LOG = [
    ("0.1", "First version: the shape of Section 6.6 and initial numbers (high 60, medium 35, low 5; each further claim counts half; urgency and secrecy "
            "multiply by 0.25 each; 4 points per fired main tactic up to 12; bands at 35 and 70). No reliability factors yet. No real email had been scored"),
    ("0.2", "Reliability factors added (src/router/reliability.json). The development run on 6,000 train emails scored the initial numbers: the budget held on every source, "
            "and two low rules cried wolf on ordinary real mail: hv_sig_other_domain (a signature address on another domain than the sender's: 29 of 68 checked SpamAssassin "
            "emails) and tv_path_origin (a new server address in a thread: 299 of 1,243 Apache messages). Both count 0. Points, discount, pressure, tactic points and bands unchanged"),
]

SEVERITY_POINTS = {"high": 60, "medium": 35, "low": 5}
DISCOUNT = 0.5                                       # the k-th group counts DISCOUNT ** k
PRESSURE = {"urgency": 0.25, "secrecy": 0.25}        # multiplier = 1 + the sum over the pressure tactics that fired
SCORED_TACTICS = MAIN_TACTICS                        # authority, urgency, scarcity, secrecy
TACTIC_POINTS = 4
TACTIC_POINTS_MAX = 12
CUTS = (35, 70)                                      # first score of Suspicious, first score of High risk
BANDS = ("Low risk", "Suspicious", "High risk")


def load_reliability(path=RELIABILITY_JSON):
    """{rule id: 0.5 or 0.0} from the data file next to this module; a rule that is not in it counts 1.

    The file is written by `python -m src.router.build --weights-only --write-reliability` (from every train email and the Phase 9 thread rates) and committed,
    like thresholds.json next to the model weights. It names the score version it was written for; a file for another version is refused, so the numbers and the
    version cannot drift apart."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("for_score_version") != SCORE_VERSION:
        raise ValueError("%s was written for score version %s, this is %s: regenerate it with python -m src.router.build --weights-only --write-reliability" % (
            path, data.get("for_score_version"), SCORE_VERSION))
    factors = data.get("reliability")
    if not isinstance(factors, dict) or not all(isinstance(k, str) and v in (0, 0.0, 0.5) for k, v in factors.items()):
        raise ValueError("%s: 'reliability' must map rule ids to 0 or 0.5" % path)
    return {k: float(v) for k, v in factors.items()}


RELIABILITY = load_reliability()                     # rule id -> 0.5 or 0.0; a rule that is not here has factor 1

ACTIONS = {
    "Low risk": "No contradiction was found among the claims that could be checked. That is not a guarantee: read the list of what could not be checked.",
    "Suspicious": "Do not act on any request in this message until you have confirmed it another way, for example by calling a number you already have.",
    "High risk": "Do not act on this message. Do not reply, pay, change payment details or give out logins. Confirm with the person through a number from "
                 "your own directory and report the message to your security team.",
}
ADDENDA = {
    "payment_request": "Do not pay anything until the request is confirmed by phone, using a number you already have.",
    "payment_change": "Do not change any payment details until the vendor or colleague confirms them by phone, using a number you already have.",
    "credential_request": "Do not enter a password or follow a sign-in request from this message; open the site yourself instead.",
    "gift_card": "Do not buy gift cards or send their codes.",
    "data_request": "Do not send personal or company data until the sender is confirmed another way.",
    "affiliation_internal": "The sender may not belong to your organisation; look the person up in your company directory.",
    "affiliation_external": "The sender may not belong to the organisation named in the message; contact that organisation through its own website or a number you already have.",
    "authority": "The sender may not hold the rank claimed; confirm through your company directory.",
    "reply_direction": "Replies may be going to someone else; write to the person at an address you already have.",
    "signature_contact": "The contact details in the signature do not match the sender; use details you already have.",
    "prior_relationship": "Check whether the conversation the sender mentions really took place.",
    "tactic_onset": "This message differs from the rest of its thread, so the sender's account may have been taken over; contact the sender by another route.",
    "request_drift": "This message differs from the rest of its thread, so the sender's account may have been taken over; contact the sender by another route.",
    "sending_path": "This message differs from the rest of its thread, so the sender's account may have been taken over; contact the sender by another route.",
    "thread_integrity": "This message does not fit the thread it claims to belong to; contact the sender by another route.",
    "single_email": "Check that this is a real reply before acting on it.",
}


def make_config(**changes):
    """A copy of the default configuration with some entries replaced: points, discount, pressure, tactic_points, tactic_max, cuts, reliability.

    The calibration grid (build.py) uses it to try other numbers without touching the frozen ones."""
    config = {"points": dict(SEVERITY_POINTS), "discount": DISCOUNT, "pressure": dict(PRESSURE), "tactic_points": TACTIC_POINTS,
              "tactic_max": TACTIC_POINTS_MAX, "cuts": tuple(CUTS), "reliability": dict(RELIABILITY)}
    for key, value in changes.items():
        if key not in config:
            raise KeyError("unknown score setting %r" % key)
        config[key] = copy.deepcopy(value)
    return config


DEFAULT_CONFIG = make_config()


def band_of(score, cuts=None):
    """'Low risk', 'Suspicious' or 'High risk' for a score."""
    first, second = cuts or DEFAULT_CONFIG["cuts"]
    return BANDS[2] if score >= second else BANDS[1] if score >= first else BANDS[0]


def group_key(row):
    return (row["claim_id"], row["claim_type"])


def counted_groups(rows, config):
    """One entry per group with a contradiction: its strongest row, the points that row is worth, and the weight of its place in the sum.

    Returned strongest first. A group whose points are 0 (reliability 0) is listed but takes no place in the sum."""
    best = {}
    for row in rows:
        if row.get("contradiction") is not True:
            continue
        base = config["points"].get(row["severity"])
        if base is None:
            continue
        reliability = config["reliability"].get(row["rule"], 1.0)
        points = base * reliability
        key = group_key(row)
        if key not in best or points > best[key]["points"]:
            best[key] = {"claim_id": row["claim_id"], "claim_type": row["claim_type"], "verifier": row["verifier"], "rule": row["rule"],
                         "severity": row["severity"], "base": base, "reliability": reliability, "points": points, "reason": row["reason"]}
    groups = sorted(best.values(), key=lambda g: (-g["points"], g["claim_id"], g["claim_type"], g["rule"]))
    place = 0
    for group in groups:
        if group["points"] > 0:
            group["weight"] = config["discount"] ** place
            group["counted"] = round(group["points"] * group["weight"], 2)
            place += 1
        else:
            group["weight"], group["counted"] = 0.0, 0.0
    return groups


def score_ledger(rows, fired, config=None):
    """The score of a ledger (a list of rows) and the tactics that fired. Returns the detail dictionary the report carries as score_detail.

    Keys: version, score (0 to 100), band, contradiction_points (before the multiplier), multiplier, tactic_points, raw (before rounding and the cap),
    capped (True when the cap cut it), groups (the strongest row of each claim and what it counted), pressure (the tactics that multiplied),
    scored_tactics (the tactics whose points were added)."""
    config = config or DEFAULT_CONFIG
    fired = set(fired)
    groups = counted_groups(rows, config)
    total = sum(g["counted"] for g in groups)
    pressure = sorted(t for t in fired if t in config["pressure"])
    multiplier = 1.0 + sum(config["pressure"][t] for t in pressure)
    scored = [t for t in SCORED_TACTICS if t in fired]
    tactic_points = min(config["tactic_max"], config["tactic_points"] * len(scored))
    raw = total * multiplier + tactic_points
    score = min(100, int(raw + 0.5))
    return {"version": SCORE_VERSION, "score": score, "band": band_of(score, config["cuts"]), "contradiction_points": round(total, 2),
            "multiplier": round(multiplier, 2), "tactic_points": tactic_points, "raw": round(raw, 2), "capped": raw + 0.5 >= 101,
            "groups": groups, "pressure": pressure, "scored_tactics": scored}


def action_for(band, detail=None):
    """The recommended action: the text of the band, plus one sentence keyed on the claim type of the strongest counted finding (never for Low risk)."""
    text = ACTIONS[band]
    if band != BANDS[0] and detail:
        top = next((g for g in detail["groups"] if g["counted"] > 0), None)
        if top and top["claim_type"] in ADDENDA:
            text += " " + ADDENDA[top["claim_type"]]
    return text


def fired_tactics(probabilities, thresholds):
    """The names of the tactics that fired, in the classifier's order. probabilities: a dict or a list in TACTICS order.

    Probability and threshold are both rounded to 4 decimals first, so the report, the check on the report and the calibration run
    (which read the probabilities from a table of rounded numbers) always agree on which tactics fired."""
    if not isinstance(probabilities, dict):
        probabilities = dict(zip(TACTICS, probabilities))
    return [t for t in TACTICS if round(float(probabilities[t]), 4) >= round(float(thresholds[t]), 4)]
