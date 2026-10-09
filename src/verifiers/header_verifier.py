"""Phase 8: the header verifier (N3, the core novelty). It checks what an email CLAIMS about its sender against what its
headers can PROVE.

    from src.verifiers.facts import prepare_facts
    from src.verifiers.header_verifier import verify_header_claim

    row = verify_header_claim(claim, prepare_facts({**fields, **evidence}), contact_text)     # one ledger row

Five claim types come here (master document Sections 4.4 and 6.4); each gets a ledger row (rows.py) that is a
contradiction, consistent, or not checkable:

    affiliation_internal   "this is David from Finance": the sender belongs to the reader's own organisation
    affiliation_external   "PayPal Security Team": the sender represents an outside organisation
    authority              "As CFO I need this today": a rank claimed by the sender
    reply_direction        "reply to me directly": replies should go somewhere
    signature_contact      a signature with an address or phone number

THE POINT OF N3 IS THE CONDITIONING. Three domains are involved, and a contradiction is a mismatch between them that
the claim makes meaningful:
    the From domain             what the reader sees
    the authenticated domain    what SPF, DKIM or DMARC actually vouched for
    the claimed domain          what the body says (the organisation domain, or a brand's real domains)
The same header values mean different things under different claims. dmarc=pass for gmail.com is normal for a Gmail
user and a contradiction for someone who claims to be Acme's Finance Director; spf=fail on a message that claims nothing
is no finding at all (no claim, no row). This is why authentication is never a learned feature: it enters only
through the rules below, each of which names the claim it belongs to.

Every rule is written from the claim definitions and master document Sections 4.4 and 6.5, not tuned on data. Severities
are labels of rule strength ("high": hard to explain innocently; "medium": suspicious, has innocent explanations;
"low": weak); Phase 10 turns them into points. Thresholds are fixed numbers: look-alike score 80 (facts.py).

Not checkable, never guessed: no organisation domain (internal claims), no From address, no authentication verdict where a
rule needs one, a claim that names no organisation, an organisation with no known domain, a signature without an address,
mailing-list mail (its recipient domain belongs to the list, not to an employer).

Security: claim text and display names are attacker-written, so every string put into a reason or into the evidence goes
through clean_text or clean_domain (rows.py). Signature addresses are read by a bounded scanner (facts.find_addresses).
"""

from src.headers.domains import is_freemail
from src.verifiers.brands import ALIASES, BRAND_DOMAINS
from src.verifiers.facts import best_similarity, find_addresses, similar_domain
from src.verifiers.rows import clean_text, consistent_row, contradiction_row, unchecked_row

HEADER = "header"

# Rule id -> (claim type, reads authentication, one-line meaning). "Reads authentication" means the rule reaches its
# verdict (contradiction or consistent) from the SPF, DKIM or DMARC result, so it must never fire when there is none.
# build.py lists every rule, also the ones that never fire, and checks that.
RULES = {
    "hv_int_list": ("affiliation_internal", False, "mailing-list mail: the recipient domain is the list's, not an employer's"),
    "hv_int_no_org": ("affiliation_internal", False, "no organisation domain is known for the recipient"),
    "hv_int_no_from": ("affiliation_internal", False, "no usable From address"),
    "hv_int_freemail": ("affiliation_internal", False, "claims to be internal, sent from a free mailbox provider"),
    "hv_int_lookalike": ("affiliation_internal", False, "claims to be internal, sent from a look-alike of the organisation's domain"),
    "hv_int_suffix": ("affiliation_internal", False, "claims to be internal, sent from the organisation's name under another suffix"),
    "hv_int_other_domain": ("affiliation_internal", False, "claims to be internal, sent from an unrelated domain (weak: the recipient domain may be a list or a partner)"),
    "hv_int_spoof": ("affiliation_internal", True, "From shows the organisation's own domain but DMARC failed (exact-domain spoof)"),
    "hv_int_auth_other": ("affiliation_internal", True, "From shows the organisation's domain, authentication vouched for another domain"),
    "hv_int_spf_fail": ("affiliation_internal", True, "From shows the organisation's domain, SPF failed"),
    "hv_int_no_pass": ("affiliation_internal", True, "From shows the organisation's domain, no check passed"),
    "hv_int_ok_auth": ("affiliation_internal", True, "From shows the organisation's domain and authentication passed for it"),
    "hv_int_no_auth": ("affiliation_internal", False, "From shows the organisation's domain, but no authentication verdict exists"),
    "hv_ext_no_from": ("affiliation_external", False, "no usable From address"),
    "hv_ext_no_org": ("affiliation_external", False, "the claim names no organisation"),
    "hv_ext_reference": ("affiliation_external", False, "names an organisation without saying the sender is that organisation (your PayPal account)"),
    "hv_ext_brand_spoof": ("affiliation_external", True, "From shows the brand's domain but DMARC failed"),
    "hv_ext_brand_auth_other": ("affiliation_external", True, "From shows the brand's domain, authentication vouched for another domain"),
    "hv_ext_brand_spf_fail": ("affiliation_external", True, "From shows the brand's domain, SPF failed"),
    "hv_ext_brand_no_pass": ("affiliation_external", True, "From shows the brand's domain, no check passed"),
    "hv_ext_brand_ok": ("affiliation_external", True, "From shows the brand's domain and authentication passed for it"),
    "hv_ext_brand_no_auth": ("affiliation_external", False, "From shows the brand's domain, but no authentication verdict exists"),
    "hv_ext_signed_by_brand": ("affiliation_external", True, "the brand's own domain authenticated the message"),
    "hv_ext_freemail": ("affiliation_external", False, "claims a known organisation, sent from a free mailbox provider"),
    "hv_ext_lookalike": ("affiliation_external", False, "claims a known organisation, sent from a look-alike of its domain"),
    "hv_ext_name_spoof": ("affiliation_external", False, "claims a known organisation, display name shows another address"),
    "hv_ext_suffix": ("affiliation_external", False, "claims a known organisation, sent from its name under another suffix"),
    "hv_ext_other_domain": ("affiliation_external", False, "claims a known organisation, sent from an unrelated domain"),
    "hv_ext_unknown_freemail": ("affiliation_external", False, "claims an organisation with no known domain, sent from a free mailbox provider (weak: the name comes from a name recogniser)"),
    "hv_ext_unknown_org": ("affiliation_external", False, "the claimed organisation has no known domain"),
    "hv_auth_no_from": ("authority", False, "no usable From address"),
    "hv_auth_name_address": ("authority", False, "rank claimed, display name shows another address"),
    "hv_auth_lookalike": ("authority", False, "rank claimed from a look-alike of the organisation's domain"),
    "hv_auth_dmarc_fail": ("authority", True, "rank claimed, DMARC failed"),
    "hv_auth_freemail": ("authority", False, "rank claimed from a free mailbox provider"),
    "hv_auth_spf_fail": ("authority", True, "rank claimed, SPF failed"),
    "hv_auth_no_pass": ("authority", True, "rank claimed, no authentication check passed"),
    "hv_auth_ok": ("authority", True, "rank claimed from a domain that authenticated as itself"),
    "hv_auth_no_evidence": ("authority", False, "rank claimed, nothing to compare it with"),
    "hv_reply_diverges": ("reply_direction", False, "Reply-To points to another domain"),
    "hv_reply_ok": ("reply_direction", False, "Reply-To is the sender's own domain or was set by a mailing list"),
    "hv_reply_no_header": ("reply_direction", False, "no Reply-To header to compare"),
    "hv_sig_no_from": ("signature_contact", False, "no usable From address"),
    "hv_sig_not_contact": ("signature_contact", False, "a postal address, disclaimer, copyright line or sign-off name is not a contact address to compare"),
    "hv_sig_no_address": ("signature_contact", False, "the signature holds no e-mail address"),
    "hv_sig_ok": ("signature_contact", False, "a signature address belongs to the sender's domain"),
    "hv_sig_lookalike": ("signature_contact", False, "a signature address is a look-alike of the sender's domain"),
    "hv_sig_freemail_sender": ("signature_contact", False, "company address in the signature, sent from a free mailbox provider"),
    "hv_sig_other_domain": ("signature_contact", False, "no signature address belongs to the sender's domain"),
}

# ---------------------------------------------------------------------------------------------------------------
# Brand lookup: no regular expressions, a few word lists
# ---------------------------------------------------------------------------------------------------------------

MAX_WORDS = 60

# An organisation name next to one of these words is a SPEAKER ("PayPal Security Team writes to you"). Next to the others
# (account, online, services, bank, inc ...) it is a name or a reference ("your PayPal account", "SharePoint Services").
SPEAKER_CUES = frozenset(
    "team department dept security support customer helpdesk desk billing representative representatives notification notifications "
    "division office unit staff centre center promotions promotion".split())
SPEAKER_PATTERNS = ("ae_sent_by_org", "ae_on_behalf", "ae_copyright")      # "message from X", "on behalf of X", "(c) 2024 X"
# Signature rules of src/claims/patterns.py that find no contact address: a postal address, a disclaimer, a copyright line,
# a name after a closing word. Only the contact rules (sc_contact, sc_name_contact, sc_labelled_contact) are compared with From.
NON_CONTACT_PATTERNS = frozenset(("sc_street", "sc_street_zip", "sc_in_error", "sc_notify_sender", "sc_copyright", "sc_sent_by", "sc_receiving", "sc_signoff_name"))


def words_of(text):
    """Lower-case words of a short text (letters, digits and &), at most 60."""
    words, current = [], []
    for ch in text[:600]:
        if ch.isalnum() or ch == "&":
            current.append(ch.lower())
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words[:MAX_WORDS]


def build_index():
    """Lower-case word tuple -> brand key, for every brand name and alias."""
    index = {tuple(words_of(name)): name for name in BRAND_DOMAINS}
    index.update({tuple(words_of(alias)): brand for alias, brand in ALIASES.items()})
    return index


BRAND_INDEX = build_index()
LONGEST_NAME = max(len(key) for key in BRAND_INDEX)


def find_brand(*texts):
    """The brand key of the first known organisation named in these texts (the longest name at each position), or None."""
    for text in texts:
        if not isinstance(text, str):
            continue
        words = words_of(text)
        for start in range(len(words)):
            for length in range(min(LONGEST_NAME, len(words) - start), 0, -1):
                brand = BRAND_INDEX.get(tuple(words[start:start + length]))
                if brand:
                    return brand
    return None


def lies_within(name, text):
    """True if the words of name appear in a row in text (both cleaned to lower-case words)."""
    inner, outer = words_of(name), words_of(text)
    return bool(inner) and any(outer[i:i + len(inner)] == inner for i in range(len(outer) - len(inner) + 1))


def claimed_organisation(claim):
    """(brand key or None, organisation name or ''): the organisation the claim's OWN words name.

    attributes.organisation is the nearest organisation within six tokens of the claim, which can be another one
    ("the Financial Services Authority" next to "Lloyds TSB"), so it counts only if it lies inside the claim text.
    """
    text = claim.get("text") or ""
    named = clean_text(claim.get("attributes", {}).get("organisation") or "", 40)
    if named and not lies_within(named, text):
        named = ""
    brand = find_brand(text) or (find_brand(named) if named else None)
    return brand, named


def speaks_as_organisation(claim):
    """True if the claim says the sender IS the organisation (a team, a department, a footer, 'on behalf of'), not that it is mentioned."""
    if claim.get("attributes", {}).get("pattern") in SPEAKER_PATTERNS:
        return True
    return any(word in SPEAKER_CUES for word in words_of(claim.get("text") or ""))


# ---------------------------------------------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------------------------------------------

def auth_evidence(f):
    """The authentication facts every row carries (so a reader sees what the rule saw)."""
    return {"spf": f["spf"], "dkim": f["dkim"], "dmarc": f["dmarc"], "authenticated_domain": f["authenticated_domain"],
            "auth_state": f["auth_state"]}


def authentication_phrase(f):
    """A short sentence about what authentication proved, for the reason of a row."""
    state = f["auth_state"]
    if state == "aligned":
        return "Authentication passed for %s." % f["from_domain"]
    if state == "failed":
        return "DMARC failed."
    if state == "other_domain":
        return "Authentication vouched for %s, not for the sender's domain." % f["authenticated_domain"]
    if state == "spf_failed":
        return "SPF failed."
    if state == "no_pass":
        return "No authentication check passed."
    return "No authentication verdict is available."


def sender_vouched_for(f, claim, rules, owner, owner_domain, evidence):
    """The rows for a message whose From shows the claimed organisation's own domain: authentication decides.

    owner is the text for the reasons ("acmecorp.com" or "PayPal"); rules is the dictionary of rule ids to use for the
    states aligned, failed, other_domain, spf_failed, no_pass and unknown.
    """
    state = f["auth_state"]
    shows = "The From address shows %s's own domain (%s)" % (owner, owner_domain)
    if state == "failed":
        return contradiction_row(HEADER, claim, rules["failed"], "high",
                                 "%s, but its authentication failed (DMARC fail): the sender is using a domain they do not control." % shows, evidence)
    if state == "other_domain":
        return contradiction_row(HEADER, claim, rules["other_domain"], "medium",
                                 "%s, but authentication vouched for %s instead." % (shows, f["authenticated_domain"]), evidence)
    if state == "spf_failed":
        return contradiction_row(HEADER, claim, rules["spf_failed"], "medium",
                                 "%s, but SPF failed: the sending server is not allowed to use that domain." % shows, evidence)
    if state == "no_pass":
        return contradiction_row(HEADER, claim, rules["no_pass"], "low",
                                 "%s, but no authentication check passed for it." % shows, evidence)
    if state == "aligned":
        return consistent_row(HEADER, claim, rules["aligned"], "%s and authentication passed for that domain." % shows, evidence)
    return unchecked_row(HEADER, claim, rules["unknown"],
                         "%s, but there is no usable authentication verdict, so a forged From address cannot be ruled out." % shows, evidence)


# ---------------------------------------------------------------------------------------------------------------
# The five claim types
# ---------------------------------------------------------------------------------------------------------------

def internal_label(claim, f):
    department = clean_text(claim.get("attributes", {}).get("department") or "", 30)
    return "%s at %s" % (department, f["org_domain"]) if department else f["org_domain"]


def verify_internal(claim, f):
    """affiliation_internal: does the sender belong to the recipient's organisation?"""
    evidence = {"from_domain": f["from_domain"], "org_domain": f["org_domain"], "freemail": f["freemail"],
                "list_mail": f["list_mail"], **auth_evidence(f)}
    if f["list_mail"]:
        return unchecked_row(HEADER, claim, "hv_int_list",
                             "Mailing-list mail: the recipient domain belongs to the list, not to an employer, so it cannot show which organisation the sender belongs to.", evidence)
    if not f["org_domain"]:
        return unchecked_row(HEADER, claim, "hv_int_no_org",
                             "Claims to be from the reader's own organisation, but no organisation domain is known for the recipient, so this cannot be checked.", evidence)
    if not f["from_domain"]:
        return unchecked_row(HEADER, claim, "hv_int_no_from",
                             "Claims to be from the reader's own organisation, but the message has no usable From address.", evidence)
    label = internal_label(claim, f)
    if f["from_matches_org"]:
        rules = {"failed": "hv_int_spoof", "other_domain": "hv_int_auth_other", "spf_failed": "hv_int_spf_fail",
                 "no_pass": "hv_int_no_pass", "aligned": "hv_int_ok_auth", "unknown": "hv_int_no_auth"}
        return sender_vouched_for(f, claim, rules, "the organisation", f["org_domain"], evidence)
    relation, _ = best_similarity(f["from_domain"], [f["org_domain"]])
    tail = "" if f["auth_state"] in ("unknown", "list_relayed") else " " + authentication_phrase(f)
    start = "Claims to be internal (%s), but the message comes from %s" % (label, f["from_domain"])
    if f["freemail"]:
        return contradiction_row(HEADER, claim, "hv_int_freemail", "high", "%s, a free mailbox provider anyone can use.%s" % (start, tail), evidence)
    if relation == "lookalike":
        return contradiction_row(HEADER, claim, "hv_int_lookalike", "high", "%s, a look-alike of %s.%s" % (start, f["org_domain"], tail), evidence)
    if relation == "suffix":
        return contradiction_row(HEADER, claim, "hv_int_suffix", "medium", "%s, the same name as %s under another suffix.%s" % (start, f["org_domain"], tail), evidence)
    return contradiction_row(HEADER, claim, "hv_int_other_domain", "low",
                             "%s, an unrelated domain (the recipient domain may be a list or a partner, so this is weak).%s" % (start, tail), evidence)


def verify_external(claim, f):
    """affiliation_external: does the sender belong to the outside organisation the email says it represents?"""
    brand, named = claimed_organisation(claim)
    evidence = {"from_domain": f["from_domain"], "claimed_organisation": brand or named or None, "freemail": f["freemail"],
                "name_address": f["name_address"], **auth_evidence(f)}
    if not f["from_domain"]:
        return unchecked_row(HEADER, claim, "hv_ext_no_from", "Claims to represent an outside organisation, but the message has no usable From address.", evidence)
    if not (brand or named):
        return unchecked_row(HEADER, claim, "hv_ext_no_org",
                             "The claim names no organisation (a cue such as Security Team on its own), so there is no domain to compare the sender with.", evidence)
    if not speaks_as_organisation(claim):
        return unchecked_row(HEADER, claim, "hv_ext_reference",
                             "Names %s, but does not say the sender is %s (a reference such as 'your account' or a service name), so it is not a claim of identity." % (brand or named, brand or named), evidence)
    if not brand:
        if f["freemail"]:
            return contradiction_row(HEADER, claim, "hv_ext_unknown_freemail", "low",
                                     "Claims to represent %s, but the message comes from %s, a free mailbox provider anyone can use." % (named, f["from_domain"]), evidence)
        return unchecked_row(HEADER, claim, "hv_ext_unknown_org",
                             "Claims to represent %s, which has no domain on file, so the sender domain %s cannot be compared with it." % (named, f["from_domain"]), evidence)
    domains = BRAND_DOMAINS[brand]
    evidence["brand_domains"] = list(domains[:4])
    if f["from_domain"] in domains:
        rules = {"failed": "hv_ext_brand_spoof", "other_domain": "hv_ext_brand_auth_other", "spf_failed": "hv_ext_brand_spf_fail",
                 "no_pass": "hv_ext_brand_no_pass", "aligned": "hv_ext_brand_ok", "unknown": "hv_ext_brand_no_auth"}
        return sender_vouched_for(f, claim, rules, brand, f["from_domain"], evidence)
    if f["authenticated_domain"] in domains:
        return consistent_row(HEADER, claim, "hv_ext_signed_by_brand",
                              "Claims to represent %s; the message is sent from %s, but %s itself authenticated it." % (brand, f["from_domain"], f["authenticated_domain"]), evidence)
    relation, near = best_similarity(f["from_domain"], domains)
    start = "Claims to represent %s, but the message comes from %s" % (brand, f["from_domain"])
    tail = "" if f["auth_state"] in ("unknown", "list_relayed") else " " + authentication_phrase(f)
    if f["freemail"]:
        return contradiction_row(HEADER, claim, "hv_ext_freemail", "high", "%s, a free mailbox provider anyone can use.%s" % (start, tail), evidence)
    if relation == "lookalike":
        return contradiction_row(HEADER, claim, "hv_ext_lookalike", "high", "%s, a look-alike of %s.%s" % (start, near, tail), evidence)
    if f["name_address"]:
        return contradiction_row(HEADER, claim, "hv_ext_name_spoof", "high",
                                 "%s, and the display name shows a different address from the one that sent it.%s" % (start, tail), evidence)
    if relation == "suffix":
        return contradiction_row(HEADER, claim, "hv_ext_suffix", "medium", "%s, the same name as %s under another suffix.%s" % (start, near, tail), evidence)
    return contradiction_row(HEADER, claim, "hv_ext_other_domain", "medium",
                             "%s, which is not one of its domains (brand mail sometimes goes through a third-party mailer).%s" % (start, tail), evidence)


def verify_authority(claim, f):
    """authority: a rank is claimed. Contradicted by a free mailbox, a look-alike, a display name that shows another
    address, or failed authentication. The rank itself can never be verified from headers; an authenticated sender is
    'consistent' only in the sense that nothing contradicts it."""
    evidence = {"from_domain": f["from_domain"], "org_domain": f["org_domain"], "freemail": f["freemail"],
                "name_address": f["name_address"], **auth_evidence(f)}
    if not f["from_domain"]:
        return unchecked_row(HEADER, claim, "hv_auth_no_from", "Claims a rank, but the message has no usable From address.", evidence)
    signals = []       # (severity rank, rule, text); the strongest decides the row, all go into the reason
    if f["name_address"]:
        signals.append((3, "high", "hv_auth_name_address", "the display name shows a different address from the one that sent it"))
    relation, _ = best_similarity(f["from_domain"], [f["org_domain"]]) if f["org_domain"] else (None, None)
    if relation == "lookalike" and not f["from_matches_org"]:
        signals.append((3, "high", "hv_auth_lookalike", "%s is a look-alike of the organisation's domain %s" % (f["from_domain"], f["org_domain"])))
    if f["auth_state"] == "failed":
        signals.append((3, "high", "hv_auth_dmarc_fail", "DMARC failed for the From domain"))
    if f["freemail"]:
        signals.append((2, "medium", "hv_auth_freemail", "%s is a free mailbox provider anyone can use" % f["from_domain"]))
    if f["auth_state"] == "spf_failed":
        signals.append((2, "medium", "hv_auth_spf_fail", "SPF failed"))
    if f["auth_state"] == "no_pass":
        signals.append((1, "low", "hv_auth_no_pass", "no authentication check passed"))
    if signals:
        signals.sort(key=lambda s: -s[0])
        _, severity, rule, _ = signals[0]
        evidence["signals"] = [s[2] for s in signals]
        reason = "Claims a position of authority, but " + "; ".join(s[3] for s in signals[:3]) + "."
        return contradiction_row(HEADER, claim, rule, severity, reason, evidence)
    if f["auth_state"] == "aligned":
        return consistent_row(HEADER, claim, "hv_auth_ok",
                              "Claims a position of authority; the message authenticates as its own domain (%s) and nothing contradicts it. The rank itself cannot be verified from headers." % f["from_domain"], evidence)
    return unchecked_row(HEADER, claim, "hv_auth_no_evidence",
                         "Claims a position of authority; the sender is not a free mailbox and no look-alike or failure was found, but nothing proves who they are.", evidence)


def verify_reply(claim, f):
    """reply_direction: the email asks to be answered somewhere. Contradicted when the Reply-To header sends replies to
    another domain (mailing-list Reply-To excluded, Phase 3)."""
    evidence = {"from_domain": f["from_domain"], "reply_domain": f["reply_domain"], "list_mail": f["list_mail"],
                "reply_to_divergence": f["reply_to_divergence"]}
    if f["reply_to_divergence"] is True:
        severity, how = "medium", "a different domain"
        if f["reply_domain"] and is_freemail(f["reply_domain"]) and not f["freemail"]:
            severity, how = "high", "a free mailbox provider"
        elif f["reply_domain"] and similar_domain(f["reply_domain"], f["from_domain"]) == "lookalike":
            severity, how = "high", "a look-alike of the sender's own domain"
        return contradiction_row(HEADER, claim, "hv_reply_diverges", severity,
                                 "Asks the reader to reply, but the Reply-To header sends replies to %s (%s) instead of the sender's own domain (%s)." % (
                                     f["reply_domain"] or "another address", how, f["from_domain"]), evidence)
    if f["reply_to_divergence"] is False and f["reply_to"]:
        why = "was set by the mailing list" if f["list_mail"] else "is the sender's own domain"
        return consistent_row(HEADER, claim, "hv_reply_ok", "The Reply-To header %s, so replies are not redirected by the headers." % why, evidence)
    return unchecked_row(HEADER, claim, "hv_reply_no_header",
                         "Asks the reader to reply elsewhere, but there is no Reply-To header (or no usable sender domain) to compare, and the body's own address is redacted.", evidence)


def verify_signature(claim, f, contact_text):
    """signature_contact: the signature block shows contact details. Contradicted when none of its e-mail addresses is on
    the From domain. contact_text is the UNREDACTED signature block (redacted text only has the placeholder [EMAIL])."""
    pattern = claim.get("attributes", {}).get("pattern")
    addresses = find_addresses(contact_text)
    evidence = {"from_domain": f["from_domain"], "signature_domains": addresses, "freemail": f["freemail"], "list_mail": f["list_mail"], "pattern": pattern}
    if pattern in NON_CONTACT_PATTERNS:
        return unchecked_row(HEADER, claim, "hv_sig_not_contact",
                             "The claim is a postal address, disclaimer, copyright line or sign-off name; it holds no contact address, and addresses elsewhere in the footer say nothing about it.", evidence)
    if not f["from_domain"]:
        return unchecked_row(HEADER, claim, "hv_sig_no_from", "The signature shows contact details, but the message has no usable From address.", evidence)
    if not addresses:
        return unchecked_row(HEADER, claim, "hv_sig_no_address", "The signature holds no e-mail address (phone numbers and postal addresses cannot be compared with the sender).", evidence)
    if f["from_domain"] in addresses:
        return consistent_row(HEADER, claim, "hv_sig_ok", "An address in the signature belongs to the sender's domain (%s)." % f["from_domain"], evidence)
    relation, near = best_similarity(f["from_domain"], addresses)
    shown = ", ".join(addresses[:3])
    start = "The signature shows %s, but the message was sent from %s" % (shown, f["from_domain"])
    if relation == "lookalike":
        row = contradiction_row(HEADER, claim, "hv_sig_lookalike", "high", "%s, and %s looks like the sender's domain." % (start, near), evidence)
    elif f["freemail"] and any(not is_freemail(d) for d in addresses):
        row = contradiction_row(HEADER, claim, "hv_sig_freemail_sender", "medium", "%s, a free mailbox provider." % start, evidence)
    else:
        row = contradiction_row(HEADER, claim, "hv_sig_other_domain", "low", "%s." % start, evidence)
    if f["list_mail"] and row["severity"] != "high":
        row["severity"] = "low"                 # list members often sign with a work address while writing from a personal one
    return row


def verify_header_claim(claim, f, contact_text=""):
    """The ledger row for one claim of the five header types, or None for any other type. f comes from prepare_facts."""
    claim_type = claim.get("type")
    if claim_type == "affiliation_internal":
        return verify_internal(claim, f)
    if claim_type == "affiliation_external":
        return verify_external(claim, f)
    if claim_type == "authority":
        return verify_authority(claim, f)
    if claim_type == "reply_direction":
        return verify_reply(claim, f)
    if claim_type == "signature_contact":
        return verify_signature(claim, f, contact_text)
    return None
