"""Phase 10: the claim router. It decides which verifier checks which claim, and checks that none was dropped.

    from src.router.router import assign, check_routing

    assignments, skipped = assign(claims, has_thread=False)
    # [{"claim_id": "c1", "type": "affiliation_internal", "verifiers": ["header"]},
    #  {"claim_id": "c2", "type": "payment_request",      "verifiers": ["request"]}]      (and "thread" too when a thread is given)

The routing table is master document Section 6.4 and lives in src/verifiers/rows.py (ROUTES), where the verifiers also read it:

    affiliation_internal, affiliation_external, authority, reply_direction, signature_contact    ->  header verifier (N3)
    prior_relationship                                                                          ->  thread verifier (N2)
    payment_request, payment_change, credential_request, gift_card, data_request                ->  request verifier, and the thread
                                                                                                    verifier as well when a thread is present
    the seven tactics are NOT claims: the classifier gives them as probabilities, and they have no verifier. They are modifiers
    (src/router/score.py): they raise the weight of a contradiction found with them.

In JavaScript terms this is an Express route table: a lookup from the claim's type to the handler that can test it. The point of the
router is that a claim is checked by the verifier that holds the evidence for it, and that the report can say which one. The table is data;
the dispatch itself is src.verifiers.verify.verify_claims (frozen in Phases 8 and 9, so their numbers stay reproducible). What this
file adds is the CHECK that nothing falls through: every claim that was assigned to a verifier must come back as at least one ledger row
from that verifier (check_routing), and a claim of an unknown type is reported as skipped, never silently lost.
"""

from src.verifiers.rows import ROUTES

REQUEST_VERIFIER = "request"
THREAD_VERIFIER = "thread"


def assign(claims, has_thread=False):
    """(assignments, skipped claim ids). One assignment per claim of a routed type, in claim order."""
    assignments, skipped = [], []
    for claim in claims:
        verifier = ROUTES.get(claim.get("type"))
        if verifier is None:
            skipped.append(claim.get("claim_id", ""))
            continue
        verifiers = [verifier]
        if verifier == REQUEST_VERIFIER and has_thread:
            verifiers.append(THREAD_VERIFIER)          # request drift: is this the first such request in the thread?
        assignments.append({"claim_id": claim.get("claim_id", ""), "type": claim["type"], "verifiers": verifiers})
    return assignments, skipped


def check_routing(assignments, rows):
    """Problems with the routing (an empty list when every assigned claim got a row from every verifier it was assigned to).

    Also catches a row that names a claim nobody assigned, and a claim checked by a verifier it was not assigned to."""
    problems = []
    assigned = {(a["claim_id"], v) for a in assignments for v in a["verifiers"]}
    claim_ids = {a["claim_id"] for a in assignments}
    seen = {(r["claim_id"], r["verifier"]) for r in rows if r["claim_id"] != "thread"}
    for claim_id, verifier in sorted(assigned - seen):
        problems.append("claim %s was assigned to the %s verifier but got no row from it" % (claim_id, verifier))
    for claim_id, verifier in sorted(seen - assigned):
        reason = "was not assigned to it" if claim_id in claim_ids else "was not assigned to any verifier"
        problems.append("a %s row names claim %s, which %s" % (verifier, claim_id, reason))
    return problems
