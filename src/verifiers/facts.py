"""Phase 8: the facts the verifiers read, cleaned and combined, plus the two small tools both verifiers share.

prepare_facts(raw) takes one email's header evidence, a dictionary with the keys that Phase 3's
header_evidence(fields, org_domain) returns, plus the parsed fields it does not repeat (from_name, from_addr,
reply_to). The API merges them as {**fields, **evidence}; build.py gets the same keys from a row of headers.parquet.
It returns plain Python values (a missing value or pandas' NA becomes None) and adds three derived facts:

    auth_state   what authentication proved about the sender, in one word:
                   aligned       a check passed for the From domain itself (the strongest good sign)
                   failed        DMARC failed (the From domain was forged, or the sender is not allowed to use it)
                   spf_failed    SPF failed or softfailed and nothing passed
                   other_domain  something passed, but for another domain than the From domain
                   no_pass       verdicts exist but none passed (dkim=none, spf=neutral ...)
                   list_relayed  mailing-list mail whose signature belongs to the list: says nothing about the author
                   unknown       no verdict at all (old corpora, or no Authentication-Results header)
    external     the sender is outside the recipient's organisation (None when the organisation domain is unknown)
    reply_domain the registered domain of the Reply-To address
    recipient_domain the registered domain of the To address (an address on it in a footer is usually the reader's own)
    name_address the display name holds an e-mail ADDRESS (with an @) on another domain than the sender's: '"service@paypal.com" <x@evil.ru>'
    name_domain  the display name holds only a bare domain name that is not the sender's ("Amazon.com" <store@mailer.net>): brands write
                 their own name like this and send through mailers, so it is a much weaker sign than an address

Authentication tells a verifier WHICH DOMAIN sent the message, never WHO the person is. That is why the verifiers
read it only against a claim: "authenticated for gmail.com" is normal for a Gmail user and a contradiction for
someone who claims to be Acme's Finance Director.

similar_domain(a, b) says how alike two registered domains are, find_addresses(text) reads e-mail addresses out of
a signature block. Both are written for attacker-controlled input: bounded loops, no regular expressions.
"""

from src.headers.domains import is_freemail, lookalike_score, registered_domain, skeleton, split_domain
from src.verifiers.rows import clean_domain

FACT_KEYS = (
    "spf", "dkim", "dmarc", "auth_source", "authenticated_domain", "auth_aligned", "from_registered_domain", "freemail",
    "name_has_address", "list_mail", "reply_to_divergence", "envelope_mismatch", "org_domain", "org_checkable",
    "from_matches_org", "org_lookalike_score", "from_name", "from_addr", "reply_to", "to_domain",
)
VERDICTS = {"pass", "fail", "softfail", "neutral", "none", "temperror", "permerror", "policy", "other", "unknown"}
BOOLEAN_KEYS = ("auth_aligned", "freemail", "name_has_address", "list_mail", "reply_to_divergence", "envelope_mismatch",
                "org_checkable", "from_matches_org")

LOOKALIKE_MIN = 80.0       # rapidfuzz ratio (0 to 100) from which two registered names count as look-alikes
MIN_NAME_LENGTH = 6        # below this, two different names are too easily alike by chance (visa / vista)
CONTACT_CHARS = 1000       # the signature block is cut here, as in Phase 7
MAX_ADDRESSES = 8          # addresses read from one signature
MAX_AT_SIGNS = 40          # '@' characters examined in one signature


def missing_to_none(value):
    """None for None, NaN and pandas' NA; every other value unchanged."""
    if value is None:
        return None
    try:
        if value != value:                      # NaN is the only value that differs from itself
            return None
    except (TypeError, ValueError):             # pandas' NA cannot be turned into a yes/no
        pass
    if type(value).__name__ in ("NAType", "NaTType"):
        return None
    return value


def truth(value):
    """True, False or None, whatever type a table gave (numpy and pandas booleans included)."""
    value = missing_to_none(value)
    return None if value is None else bool(value)


def auth_state(f):
    """One word for what authentication proved about the sender (see the module text); f is a prepared fact dictionary."""
    if all(f[m] in ("unknown", None) for m in ("spf", "dkim", "dmarc")):
        return "unknown"
    if f["dmarc"] == "fail":
        return "failed"
    if f["auth_aligned"] is True:
        return "aligned"
    if f["list_mail"]:
        return "list_relayed"           # a list re-signs the author's mail with its own domain: not evidence either way
    if f["authenticated_domain"] and f["auth_aligned"] is False:
        return "other_domain"
    if f["spf"] in ("fail", "softfail"):
        return "spf_failed"
    return "no_pass"


def prepare_facts(raw):
    """Clean one email's evidence into the dictionary the verifiers read (keys: FACT_KEYS plus the derived facts)."""
    raw = raw or {}
    f = {key: missing_to_none(raw.get(key)) for key in FACT_KEYS}
    for key in BOOLEAN_KEYS:
        f[key] = truth(f[key])
    f["name_has_address"] = bool(f["name_has_address"])
    f["list_mail"] = bool(f["list_mail"])
    for key in ("spf", "dkim", "dmarc"):
        f[key] = f[key] if f[key] in VERDICTS else "unknown"
    f["from_domain"] = clean_domain(f["from_registered_domain"])
    # On mailing-list mail the recipient domain is the list's host (apache.org), not the employer of the reader or the sender,
    # so it is no organisation domain: every check that needs one is then not checkable (Phase 3 treats collectors alike).
    f["org_domain"] = None if f["list_mail"] else clean_domain(f["org_domain"])
    f["authenticated_domain"] = clean_domain(f["authenticated_domain"])
    # Derived again from the cleaned domains, so a caller that passes only a few keys still gets consistent facts.
    f["freemail"] = is_freemail(f["from_domain"]) if f["from_domain"] else None
    f["auth_aligned"] = (f["authenticated_domain"] == f["from_domain"]) if f["authenticated_domain"] and f["from_domain"] else None
    f["org_checkable"] = bool(f["org_domain"] and f["from_domain"])
    f["from_matches_org"] = (f["from_domain"] == f["org_domain"]) if f["org_checkable"] else None
    f["external"] = (not f["from_matches_org"]) if f["org_checkable"] else None
    f["recipient_domain"] = clean_domain(registered_domain(f["to_domain"])) if isinstance(f["to_domain"], str) else None
    reply = f["reply_to"] if isinstance(f["reply_to"], str) and f["reply_to"].count("@") == 1 else None
    f["reply_domain"] = clean_domain(registered_domain(reply.split("@")[1])) if reply else None
    f["auth_state"] = auth_state(f)
    # Phase 3's name_has_address also fires on bare domains ("eBay.com"), which brands write in their display names. The
    # verifiers separate a shown ADDRESS (strong) from a shown bare domain (weak) by reading the display name itself.
    shown = find_addresses(f["from_name"]) if isinstance(f["from_name"], str) else []
    f["name_address"] = bool(f["from_domain"] and any(d != f["from_domain"] for d in shown))
    f["name_domain"] = bool(f["name_has_address"] and not f["name_address"])
    return f


def similar_domain(domain, target):
    """How a sender's registered domain relates to another: 'same', 'suffix', 'lookalike' or None.

    same       the same registered domain
    suffix     the same name under another suffix (paypal.net for paypal.com): often a regional domain, sometimes a squat
    lookalike  the names differ only by look-alike characters (paypa1, a Cyrillic a, rn for m), or are alike enough:
               rapidfuzz ratio of 80 or more and both names at least 6 letters (shorter names are alike by chance)
    None       not alike
    """
    if not domain or not target:
        return None
    if domain == target:
        return "same"
    name_a, _ = split_domain(domain)
    name_b, _ = split_domain(target)
    if not name_a or not name_b:
        return None
    if name_a == name_b:
        return "suffix"
    if skeleton(name_a) == skeleton(name_b):
        return "lookalike"
    score = lookalike_score(domain, target)
    if score is not None and score >= LOOKALIKE_MIN and min(len(name_a), len(name_b)) >= MIN_NAME_LENGTH:
        return "lookalike"
    return None


def best_similarity(domain, targets):
    """The strongest relation of domain to any of targets: same, then lookalike, then suffix, else None; with the target."""
    best, best_target = None, None
    order = {"same": 3, "lookalike": 2, "suffix": 1, None: 0}
    for target in targets:
        relation = similar_domain(domain, target)
        if order[relation] > order[best]:
            best, best_target = relation, target
    return best, best_target


def find_addresses(text):
    """The registered domains of the e-mail addresses in a signature block (at most 8, in order, no repeats).

    Works by finding each '@' and walking left and right over the characters an address may hold, with a fixed
    limit in both directions, so the cost grows with the text length and cannot blow up.
    """
    if not isinstance(text, str):
        return []
    text = text[:CONTACT_CHARS]
    found, at, examined = [], text.find("@"), 0
    while at != -1 and examined < MAX_AT_SIGNS and len(found) < MAX_ADDRESSES:
        examined += 1
        left = at
        while left > 0 and at - left < 64 and (text[left - 1].isalnum() or text[left - 1] in "._%+-"):
            left -= 1
        right = at + 1
        while right < len(text) and right - at <= 255 and (text[right].isalnum() or text[right] in ".-"):
            right += 1
        domain = text[at + 1:right].strip(".-").lower()
        if left < at and "." in domain:
            registered = clean_domain(registered_domain(domain))
            if registered and registered not in found:
                found.append(registered)
        at = text.find("@", right)
    return found


__all__ = ["prepare_facts", "similar_domain", "best_similarity", "find_addresses", "is_freemail", "auth_state"]
