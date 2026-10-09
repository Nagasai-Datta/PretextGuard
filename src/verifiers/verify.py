"""Phase 8: send each claim to its verifier and collect the ledger rows. Phase 10's router builds on this.

    from src.verifiers.verify import verify_claims

    rows = verify_claims(claims, {**fields, **evidence}, contact_text, body_text)

claims        the list from src.claims.extractor.extract_claims
facts         the parsed header fields plus header_evidence(fields, org_domain), merged in one dictionary
contact_text  the UNREDACTED signature block (or the last 1,000 characters of body_clean when there is none): the
              redacted text has only the placeholder [EMAIL], and the signature rule compares real addresses
body_text     the text the claim extractor read (model_text(body_redacted)); the request verifier looks for bank details in it

Routing is the table of master document Section 6.4 (ROUTES in rows.py): affiliation, authority, reply and signature
claims go to the header verifier; the five request types go to the request verifier; prior_relationship goes to the
thread verifier (Phase 9), which does not exist yet, so its row says so ("not checkable: needs a thread"). The six
tactics have no verifier. Claims of an unknown type are skipped.

RULES_VERSION changes with every revision of any rule, threshold or severity; build.py saves it in
results/verifier_checks.csv, and VERSION_LOG records what each revision changed and why (the master document copies it).
"""

from src.verifiers.facts import prepare_facts
from src.verifiers.header_verifier import RULES as HEADER_RULES, verify_header_claim
from src.verifiers.request_verifier import RULES as REQUEST_RULES, verify_request_claim
from src.verifiers.rows import ROUTES, unchecked_row

RULES_VERSION = "0.2"
VERSION_LOG = [
    ("0.1", "First version: rules written from master document Sections 4.4 and 6.5, the Phase 3 and Phase 7 notes and the claim definitions; "
            "thresholds fixed (look-alike score 80, names of 6 or more letters); severities are initial labels. No real email had been read"),
    ("0.2", "Read off the first train run (6,000 emails): affiliation_external was contradicted in 98% to 100% of its checkable claims in every category, because "
            "claims that only MENTION a brand (your Microsoft account, SharePoint Services) were treated as claims of identity, and the claimed organisation was "
            "taken from the nearest organisation in the text (Lloyds next to the Financial Services Authority). Now an external claim is checked only if the claim's "
            "own words name the organisation and say the sender is that organisation (a team, department, support, security ... or a footer or 'on behalf of'); "
            "a mere reference is not checkable. An unrelated domain under an internal claim is low (in sources without a List-Id the recipient domain is often a "
            "mailing list, as in the opensuse.org and linux.ie ham examples); an unknown organisation from a free mailbox is low (the name comes from a name recogniser: "
            "'Hi team'). A display name that holds only a bare domain name (brands write their site name, such as Brand.com, in the display name and send through mailers) is now low; only a shown e-mail address is medium. signature_contact compares addresses only for "
            "contact claims, not for postal addresses, disclaimers, copyright lines or sign-off names. The attack-versus-ham check now compares the share of EMAILS with a "
            "contradicted claim, because the rate among checkable claims is close to 100% in every category when 'checkable' mostly means 'contradicted'"),
]

THREAD_RULE = "tv_needs_thread"
THREAD_RULES = {THREAD_RULE: ("prior_relationship", False, "claims an earlier conversation; only the thread verifier (Phase 9) can check it")}

# Every rule id with (claim type, reads authentication, meaning), and the verifier it belongs to.
ALL_RULES = {}
for _verifier, _rules in (("header", HEADER_RULES), ("request", REQUEST_RULES), ("thread", THREAD_RULES)):
    for _rule, (_type, _reads_auth, _meaning) in _rules.items():
        ALL_RULES[_rule] = {"verifier": _verifier, "claim_type": _type, "reads_auth": _reads_auth, "meaning": _meaning}


def thread_pending_row(claim):
    """The row for a prior_relationship claim: it can only be checked against a thread."""
    return unchecked_row("thread", claim, THREAD_RULE,
                         "Claims an earlier conversation with the reader. Only the thread verifier can check that, and it needs the earlier messages (not yet available here).",
                         {"needs": "thread"})


def verify_claims(claims, facts, contact_text="", body_text=""):
    """The ledger rows for the claims of one email (one row per routed claim, in claim order)."""
    f = prepare_facts(facts)
    rows = []
    for claim in claims:
        verifier = ROUTES.get(claim.get("type"))
        if verifier == "header":
            row = verify_header_claim(claim, f, contact_text)
        elif verifier == "request":
            row = verify_request_claim(claim, f, body_text)
        elif verifier == "thread":
            row = thread_pending_row(claim)
        else:
            row = None
        if row is not None:
            rows.append(row)
    return rows
