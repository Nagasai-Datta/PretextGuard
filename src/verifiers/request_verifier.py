"""Phase 8: the request verifier. It answers one question for every request an email makes: WHO IS ASKING?

    from src.verifiers.facts import prepare_facts
    from src.verifiers.request_verifier import verify_request_claim

    row = verify_request_claim(claim, prepare_facts({**fields, **evidence}), body_text)     # one ledger row

Five claim types come here (master document Section 6.4): payment_request ("process the wire transfer"),
payment_change ("we have changed our bank details"), credential_request ("verify your account"), gift_card and
data_request ("send me a copy of your passport"). A request is not false the way a claim of identity can be false, so
the verifier does not ask "is the request true?" but "is the asker the kind of sender who makes this request
honestly?". It looks for these signals about the asker, each written from the definitions in master document
Section 6.5:

    lookalike       the sender's domain is a look-alike of the recipient organisation's domain, or of the brand the
                    request names ("sign in to your PayPal account" from paypa1.com)          high
    auth_fail       DMARC failed: the From domain was forged                                   high
    freemail        a free mailbox provider anyone can use                                      medium (high when the
                    sender is outside the recipient's organisation: the asker is a stranger)
    reply_redirect  the Reply-To header sends the answer to another domain                      medium
    name_address    the display name shows a different e-mail ADDRESS from the one that sent it medium
    name_domain     the display name shows only a bare domain ("Amazon.com"), which brands write   low
    spf_fail        SPF failed and nothing passed                                               medium
    no_pass         verdicts exist but none passed                                              low

The strongest signal sets the severity; then four adjustments move it one step (it stays between low and high):
payment_change and gift_card +1 (a bank-detail change or a gift-card request from a stranger is the classic fraud),
data_request -1 (many honest forms ask for data), valid bank details in a payment message +1 (the message really
carries account numbers: bank.py), weak claim -1 (rows.py). These are initial severities set from definitions;
Phase 10 calibrates weights on validation, never on test.

No signal is not the same as "safe":
    consistent      authentication passed for the sender's own domain, the sender is not a free mailbox, nothing
                    redirects the reply: the asker is who the domain says (not that the request is honest)
    not checkable   nothing contradicts the asker, but nothing proves who they are either (no authentication verdict),
                    or it is a bank-detail change, which headers can never confirm: the thread verifier (Phase 9) compares
                    the new details with the earlier messages

Security: bank details are shown masked (bank.py), claim text never reaches a reason, and every domain goes through
clean_domain.
"""

from src.verifiers.bank import find_bank_details
from src.verifiers.facts import best_similarity
from src.verifiers.header_verifier import find_brand
from src.verifiers.brands import BRAND_DOMAINS
from src.verifiers.rows import SEVERITIES, consistent_row, contradiction_row, shift, unchecked_row

REQUEST = "request"

# Rule id -> (claim type, reads authentication, one-line meaning).
RULES = {
    "rv_no_from": ("any request", False, "no usable From address"),
    "rv_ok": ("any request", True, "the asker authenticated as its own domain, is no free mailbox and redirects nothing"),
    "rv_no_proof": ("any request", False, "nothing contradicts the asker, but nothing proves who they are"),
    "rv_change_needs_thread": ("payment_change", False, "a bank-detail change cannot be confirmed from headers"),
}
# The signal names, with their base severity, are rule ids too, so build.py can count each one.
SIGNALS = {
    "lookalike": ("high", False), "auth_fail": ("high", True), "freemail": ("medium", False), "reply_redirect": ("medium", False),
    "name_address": ("medium", False), "spf_fail": ("medium", True), "no_pass": ("low", True), "name_domain": ("low", False),
}
for _name, (_severity, _reads_auth) in SIGNALS.items():
    RULES["rv_" + _name] = ("any request", _reads_auth, "strongest signal: " + _name.replace("_", " "))

ADJUSTMENT = {"payment_change": 1, "gift_card": 1, "data_request": -1}
BANK_CLAIMS = ("payment_change", "payment_request")
ASKS = {
    "payment_request": "asks for a payment", "payment_change": "announces new payment details", "credential_request": "asks for login details",
    "gift_card": "asks for gift cards", "data_request": "asks for personal or company data",
}
SIGNAL_TEXT = {
    "lookalike": "the sender domain %(from_domain)s is a look-alike of %(near)s",
    "auth_fail": "DMARC failed for the From domain",
    "freemail": "it was sent from %(from_domain)s, a free mailbox provider anyone can use",
    "reply_redirect": "the Reply-To header sends replies to %(reply_domain)s",
    "name_address": "the display name shows a different address from the one that sent it",
    "name_domain": "the display name shows a domain name that is not the sender's",
    "spf_fail": "SPF failed",
    "no_pass": "no authentication check passed",
}


def asker_signals(claim, f):
    """The signals about the asker as a list of (name, severity, near), strongest first. See the module text."""
    found = []
    targets = [(f["org_domain"], "the recipient's domain")] if f["org_domain"] and f["from_domain"] and not f["from_matches_org"] else []
    brand = find_brand(claim.get("text"))
    if brand:
        targets += [(d, brand) for d in BRAND_DOMAINS[brand] if d != f["from_domain"]]
    if f["from_domain"] and not (brand and f["from_domain"] in BRAND_DOMAINS[brand]):
        for target, _ in targets:
            if best_similarity(f["from_domain"], [target])[0] == "lookalike":
                found.append(("lookalike", "high", target))
                break
    if f["auth_state"] == "failed":
        found.append(("auth_fail", "high", None))
    if f["freemail"]:
        found.append(("freemail", "high" if f["external"] else "medium", None))
    if f["reply_to_divergence"] is True:
        found.append(("reply_redirect", "medium", None))
    if f["name_address"]:
        found.append(("name_address", "medium", None))
    elif f["name_domain"]:
        found.append(("name_domain", "low", None))
    if f["auth_state"] == "spf_failed":
        found.append(("spf_fail", "medium", None))
    if f["auth_state"] == "no_pass":
        found.append(("no_pass", "low", None))
    found.sort(key=lambda s: -SEVERITIES.index(s[1]))
    return found


def verify_request(claim, f, body_text=""):
    """The ledger row for one request claim; body_text is the text the claim extractor read (for bank details)."""
    claim_type = claim.get("type")
    details = find_bank_details(body_text) if claim_type in BANK_CLAIMS else []
    has_iban = any(d["kind"] == "iban" for d in details)
    signals = asker_signals(claim, f)
    evidence = {"from_domain": f["from_domain"], "org_domain": f["org_domain"], "freemail": f["freemail"], "external": f["external"],
                "reply_domain": f["reply_domain"], "list_mail": f["list_mail"], "signals": [s[0] for s in signals],
                "bank_details": [d["masked"] for d in details[:4]], "auth_state": f["auth_state"],
                "spf": f["spf"], "dkim": f["dkim"], "dmarc": f["dmarc"]}
    if not f["from_domain"]:
        return unchecked_row(REQUEST, claim, "rv_no_from", "The message %s, but it has no usable From address, so the asker cannot be checked." % ASKS[claim_type], evidence)
    if signals:
        name, severity, near = signals[0]
        severity = shift(severity, ADJUSTMENT.get(claim_type, 0) + (1 if details and claim_type in BANK_CLAIMS else 0))
        reasons = []
        for signal, _, target in signals[:3]:
            reasons.append(SIGNAL_TEXT[signal] % {"from_domain": f["from_domain"], "reply_domain": f["reply_domain"] or "another domain", "near": target or ""})
        where = " from outside the recipient's organisation (%s)" % f["org_domain"] if f["external"] else ""
        extra = ""
        if details and claim_type in BANK_CLAIMS:
            extra = " The message carries bank details (%s)%s." % (", ".join(d["masked"] for d in details[:3]), ", including a valid IBAN" if has_iban else "")
        reason = "The message %s%s: %s.%s" % (ASKS[claim_type], where, "; ".join(reasons), extra)
        return contradiction_row(REQUEST, claim, "rv_" + name, severity, reason, evidence)
    if claim_type == "payment_change":
        return unchecked_row(REQUEST, claim, "rv_change_needs_thread",
                             "The message announces new payment details. Nothing about the sender contradicts it, but headers cannot confirm a change: "
                             "the thread verifier compares the new details with the earlier messages.", evidence)
    if f["auth_state"] == "aligned":
        return consistent_row(REQUEST, claim, "rv_ok",
                              "The message %s; it authenticates as its own domain (%s), is no free mailbox and redirects no reply. That shows who sent it, not that the request is honest." % (
                                  ASKS[claim_type], f["from_domain"]), evidence)
    return unchecked_row(REQUEST, claim, "rv_no_proof",
                         "The message %s. The sender is no free mailbox and nothing redirects the reply, but there is no usable authentication verdict to prove who they are." % ASKS[claim_type],
                         evidence)


def verify_request_claim(claim, f, body_text=""):
    """The ledger row for one claim of the five request types, or None for any other type. f comes from prepare_facts."""
    return verify_request(claim, f, body_text) if claim.get("type") in ASKS else None
