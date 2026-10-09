"""Phase 10: the verdict ledger. It collects the rows of every verifier, checks them, and says how much could be checked.

    from src.router.ledger import build_ledger, coverage, flat_features

    rows, problems = build_ledger(claims, assignments, claim_rows, signal_rows)
    summary = coverage(claims, rows, limits)

A LEDGER ROW is one verdict about one claim (master document Section 6.3, built in src/verifiers/rows.py):
    claim, evidence, contradiction (true / false / null), severity, rule, reason.
The ledger is the explanation of the report: it does not describe the score after the fact, the score is computed from it
(src/router/score.py). This is the fact-checking pipeline of Section 4.5: claim, evidence, verdict, reason.

Two kinds of rows go in:
    claim rows    from verify_claims: one per claim and verifier (header, request and, with a thread, thread). claim_id is the claim's.
    signal rows   from the thread verifier: tactic onset, request drift in bank details, sending path, thread integrity, single email.
                  They are not about one claim in the text but about the message against its thread; claim_id is 'thread'.

build_ledger returns the rows unchanged (they are exactly what the verifiers made) and a list of PROBLEMS, which must be empty:
a row that fails check_row, a rule that belongs to another verifier, a claim row that names no claim, a signal row that is not 'thread',
two rows for one claim and verifier, and any claim that was assigned to a verifier but got no row (router.check_routing).

coverage says how much of the email could be checked: of the claims found, how many were contradicted, consistent or not checkable,
and why checks could not run (no header block, no From, no authentication results, no organisation domain, a single email with no thread).
'Low risk' is only as good as that coverage, so the report always carries it.

flat_features gives the same signals as one fixed-length number vector WITHOUT the link between a claim and its evidence: which rules
fired (anywhere), the worst severity per verifier, the seven tactic probabilities and two counts. Phase 13 trains a plain classifier
on it and compares it with the claim-routed score (the architecture ablation of Section 11): same signals, different wiring.
"""

from collections import Counter

from src.data.label_schema import TACTICS
from src.router.router import check_routing
from src.verifiers.rows import SEVERITIES, check_row
from src.verifiers.thread_verifier import RULES as THREAD_RULES
from src.verifiers.verify import ALL_RULES

RULE_VERIFIER = {rule: info["verifier"] for rule, info in ALL_RULES.items()}
RULE_VERIFIER.update({rule: "thread" for rule in THREAD_RULES})
RULE_TYPE = {rule: info["claim_type"] for rule, info in ALL_RULES.items()}
RULE_TYPE.update({rule: meaning[0] for rule, meaning in THREAD_RULES.items()})
KNOWN_RULES = frozenset(RULE_VERIFIER)
SIGNAL_ID = "thread"

# Why some checks could not run. The codes are set by the pipeline; the sentences are fixed here (nothing from the email is printed).
LIMITS = {
    "headers_missing": "No header block was found in the text, only a body, so every check that compares a claim with the sender could not run.",
    "no_from": "The message has no usable From address, so claims about who the sender is could not be compared with anything.",
    "no_authentication": "No SPF, DKIM or DMARC result from the receiving server was found, so authentication was not used.",
    "no_org_domain": "No organisation domain was known for the reader, so claims to belong to the reader's own organisation could not be checked.",
    "org_domain_ignored": "The organisation domain you gave was not usable (empty, malformed or a free mailbox provider) and was ignored.",
    "single_email": "Only this message was given, so the checks against the history of its thread did not run.",
    "thread_truncated": "The thread was longer than 50 messages; only the last 50 were examined.",
    "thread_unordered": "Not every message has a usable Date, so the messages were taken in the order given.",
    "text_truncated": "The text was cut at the size limit before it was analysed.",
}


def build_ledger(claims, assignments, claim_rows, signal_rows):
    """(rows, problems): claim rows followed by signal rows, and every way the ledger breaks its rules (empty when it is sound)."""
    rows = list(claim_rows) + list(signal_rows)
    problems = []
    claim_ids = {c.get("claim_id") for c in claims}
    for row in rows:
        for problem in check_row(row, KNOWN_RULES):
            problems.append("row %s: %s" % (row.get("rule") if isinstance(row, dict) else "?", problem))
        owner = RULE_VERIFIER.get(row.get("rule")) if isinstance(row, dict) else None
        if owner and row.get("verifier") != owner:
            problems.append("row %s says verifier %s but the rule belongs to %s" % (row["rule"], row.get("verifier"), owner))
    for row in claim_rows:
        if row["claim_id"] not in claim_ids:
            problems.append("claim row %s names claim %r, which was not extracted" % (row["rule"], row["claim_id"]))
    for row in signal_rows:
        if row["claim_id"] != SIGNAL_ID:
            problems.append("signal row %s has claim id %r instead of %r" % (row["rule"], row["claim_id"], SIGNAL_ID))
    for (claim_id, verifier), count in Counter((r["claim_id"], r["verifier"]) for r in claim_rows).items():
        if count > 1:
            problems.append("claim %s has %d rows from the %s verifier" % (claim_id, count, verifier))
    problems += check_routing(assignments, claim_rows)
    return rows, problems


def status_of_claim(rows):
    """'contradicted', 'consistent' or 'not_checkable' for the rows of one claim: a contradiction wins, then a passed check."""
    if any(r["contradiction"] is True for r in rows):
        return "contradicted"
    if any(r["contradiction"] is False for r in rows):
        return "consistent"
    return "not_checkable"


def coverage(claims, rows, limits=()):
    """How much could be checked: counts over the claims, counts over the thread signals, the limits that applied and one plain sentence.

    A claim counts once whatever the number of its rows (a payment request in a thread has two). Claims of a type no verifier handles are not counted."""
    by_claim = {}
    for row in rows:
        by_claim.setdefault(row["claim_id"], []).append(row)
    claim_status = {}
    for claim in claims:
        if claim["claim_id"] in by_claim:
            claim_status[claim["claim_id"]] = status_of_claim(by_claim[claim["claim_id"]])
    counts = Counter(claim_status.values())
    signals = by_claim.get(SIGNAL_ID, [])
    signal_counts = Counter(status_of_claim([r]) for r in signals)
    found = len(claim_status)
    checked = counts["contradicted"] + counts["consistent"]
    limits = [code for code in limits if code in LIMITS]
    if found == 0:
        sentence = "No claim of a type that can be checked was found in the text."
    else:
        sentence = "%d of %d claims could be checked and %d could not." % (checked, found, counts["not_checkable"])
    history = [r for r in signals if r["claim_type"] != "single_email"]
    if history:
        sentence += " %d of %d checks of the message against its thread ran." % (sum(1 for r in history if r["contradiction"] is not None), len(history))
    if limits:
        sentence += " " + " ".join(LIMITS[code] for code in limits)
    return {"claims": found, "checked": checked, "contradicted": counts["contradicted"], "consistent": counts["consistent"],
            "not_checkable": counts["not_checkable"], "signals": len(signals), "signals_contradicted": signal_counts["contradicted"],
            "signals_not_checkable": signal_counts["not_checkable"], "limits": limits, "note": sentence}


# ---------------------------------------------------------------------------------------------------- the flat vector

FEATURE_RULES = sorted(KNOWN_RULES)
VERIFIERS = ("header", "request", "thread")
FEATURE_NAMES = (["rule:" + r for r in FEATURE_RULES] + ["worst:" + v for v in VERIFIERS] + ["tactic:" + t for t in TACTICS]
                 + ["claims_found", "claims_checked"])


def flat_features(rows, tactic_probabilities, claims_found, claims_checked):
    """The same signals as one list of numbers in the order of FEATURE_NAMES, without which claim each row was about.

    rule:X       1 when rule X produced a contradiction anywhere in the ledger, else 0
    worst:V      0 none, 1 low, 2 medium, 3 high: the strongest contradiction of verifier V
    tactic:T     the classifier's probability of tactic T (tactic_probabilities: a dict or a list in TACTICS order)
    claims_*     how many claims were found and how many could be checked"""
    fired = {r["rule"] for r in rows if r["contradiction"] is True}
    worst = {v: 0 for v in VERIFIERS}
    for r in rows:
        if r["contradiction"] is True and r["verifier"] in worst:
            worst[r["verifier"]] = max(worst[r["verifier"]], SEVERITIES.index(r["severity"]) + 1)
    if isinstance(tactic_probabilities, dict):
        probabilities = [float(tactic_probabilities.get(t, 0.0)) for t in TACTICS]
    else:
        probabilities = [float(p) for p in tactic_probabilities]
    return ([1.0 if r in fired else 0.0 for r in FEATURE_RULES] + [float(worst[v]) for v in VERIFIERS] + probabilities
            + [float(claims_found), float(claims_checked)])
