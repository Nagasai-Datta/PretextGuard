"""Phase 8: the ledger row that every verifier returns, and the helpers that build and check it.

A ledger row is one verdict about one claim, in the form of master document Section 6.3:

    {"claim_id": "c1",
     "claim_type": "affiliation_internal",
     "verifier": "header",                          "header", "request" or "thread"
     "rule": "hv_int_freemail",                     the rule that produced the row (every row can say why it exists)
     "evidence": {"from_domain": "gmail.com", "org_domain": "acmecorp.com", "freemail": true, ...},
     "contradiction": true,                         true, false or null
     "severity": "high",
     "reason": "Claims to be internal (Finance at acmecorp.com), but the message comes from gmail.com, a free mailbox provider."}

THREE VALUES, NEVER TWO. A row says one of three things, and the severity says which:

    contradiction  true   severity "high", "medium" or "low"   the evidence disagrees with the claim
    consistent     false  severity "none"                      the evidence was there and agrees (or at least does not disagree)
    not checkable  null   severity "not_checkable"             the evidence needed for this claim is missing

Missing evidence is never turned into "no contradiction": a source that has no authentication verdicts gets
"not checkable" rows for every rule that needs one. In JavaScript terms the three values are true, false and null.

Severity is only a label of how strong the rule is. It is not a probability and it is not a score: Phase 10 turns
severities into points and calibrates them on the validation split. A weak claim (confidence 0.6) lowers its row's
severity by one step, because a weak claim may be an ordinary sentence.

Security: reasons and evidence are built from validated values only. Anything that came from the email (a
claimed organisation, a display name, a domain) goes through clean_text or clean_domain first, so a reason can never
carry markup, control characters or a very long string. The interface must still escape reasons when it shows them
(Phase 12); this is the second line of defence.
"""

import json

from src.claims.patterns import STRONG

SEVERITIES = ("low", "medium", "high")
VERIFIERS = ("header", "request", "thread")
ROW_KEYS = {"claim_id", "claim_type", "verifier", "rule", "evidence", "contradiction", "severity", "reason"}
MAX_REASON = 400
MAX_EVIDENCE_JSON = 2000
MAX_STRING = 80
MAX_LIST = 6

# Which verifier handles which claim type: the routing table of master document Section 6.4.
# The six manipulation tactics have no verifier: they are modifiers that Phase 10 uses to raise a contradiction's weight.
ROUTES = {
    "affiliation_internal": "header", "affiliation_external": "header", "authority": "header",
    "reply_direction": "header", "signature_contact": "header",
    "prior_relationship": "thread",
    "payment_request": "request", "payment_change": "request", "credential_request": "request",
    "gift_card": "request", "data_request": "request",
}

TEXT_OK = set(" .,-_'&()")


def clean_text(value, limit=MAX_STRING):
    """Text that came from an email, made safe to print: letters, digits, spaces and . , - _ ' & ( ) only, cut at limit."""
    if not isinstance(value, str):
        return ""
    kept = "".join(ch if (ch.isalnum() or ch in TEXT_OK) else " " for ch in value[:limit * 3])
    return " ".join(kept.split())[:limit]


def clean_domain(value):
    """A domain from a header, lower case, letters, digits, dots and hyphens only; None if nothing usable is left."""
    if not isinstance(value, str):
        return None
    kept = "".join(ch for ch in value[:200].lower() if ch.isalnum() or ch in ".-").strip(".-")
    return kept[:MAX_STRING] or None


def shift(severity, steps):
    """Move a severity up (+1) or down (-1) the ladder low, medium, high; it never leaves the ladder."""
    index = min(len(SEVERITIES) - 1, max(0, SEVERITIES.index(severity) + steps))
    return SEVERITIES[index]


def clean_evidence(evidence):
    """Evidence with only simple values: None, booleans, numbers, short cleaned strings and short lists of those."""
    out = {}
    for key, value in evidence.items():
        if isinstance(value, (list, tuple)):
            out[str(key)] = [simple(v) for v in list(value)[:MAX_LIST]]
        else:
            out[str(key)] = simple(value)
    return out


def simple(value):
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 1)
    return clean_text(str(value))


def make_row(verifier, claim, rule, contradiction, severity, reason, evidence):
    """Build one ledger row. contradiction is True, False or None and must agree with severity (check_row verifies it)."""
    if contradiction and claim.get("confidence", STRONG) < STRONG:
        severity = shift(severity, -1)                 # a weak claim may be an ordinary sentence: one step lower
        evidence = dict(evidence, claim_strength="weak")
    return {"claim_id": claim.get("claim_id", ""), "claim_type": claim.get("type", ""), "verifier": verifier, "rule": rule,
            "evidence": clean_evidence(evidence), "contradiction": contradiction, "severity": severity,
            "reason": " ".join(reason.split())[:MAX_REASON]}


def contradiction_row(verifier, claim, rule, severity, reason, evidence):
    return make_row(verifier, claim, rule, True, severity, reason, evidence)


def consistent_row(verifier, claim, rule, reason, evidence):
    return make_row(verifier, claim, rule, False, "none", reason, evidence)


def unchecked_row(verifier, claim, rule, reason, evidence):
    return make_row(verifier, claim, rule, None, "not_checkable", reason, evidence)


def status_of(row):
    """'contradiction', 'consistent' or 'not_checkable'."""
    return {True: "contradiction", False: "consistent", None: "not_checkable"}[row["contradiction"]]


def check_row(row, rules=None):
    """A list of problems with one ledger row (empty when it is valid). rules, if given, is the set of known rule ids."""
    problems = []
    if not isinstance(row, dict) or set(row) != ROW_KEYS:
        return ["keys are %s" % (sorted(row) if isinstance(row, dict) else type(row).__name__)]
    if row["verifier"] not in VERIFIERS:
        problems.append("verifier %r" % row["verifier"])
    if rules is not None and row["rule"] not in rules:
        problems.append("unknown rule %r" % row["rule"])
    expected = {True: SEVERITIES, False: ("none",), None: ("not_checkable",)}
    if row["contradiction"] not in expected:
        problems.append("contradiction %r" % row["contradiction"])
    elif row["severity"] not in expected[row["contradiction"]]:
        problems.append("severity %r does not fit contradiction %r" % (row["severity"], row["contradiction"]))
    reason = row["reason"]
    if not isinstance(reason, str) or not 10 <= len(reason) <= MAX_REASON:
        problems.append("reason length")
    elif any(ch in reason for ch in "<>`") or not reason.isprintable():
        problems.append("reason holds markup or control characters")
    if not isinstance(row["evidence"], dict):
        problems.append("evidence is not a dictionary")
    else:
        try:
            if len(json.dumps(row["evidence"])) > MAX_EVIDENCE_JSON:
                problems.append("evidence too long")
        except (TypeError, ValueError):
            problems.append("evidence is not plain data")
    return problems
