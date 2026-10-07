"""Turn parsed header fields into the evidence the N3 header verifier checks claims against.

header_evidence(fields, org_domain) returns one flat dict:
    spf, dkim, dmarc        the receiving server's verdicts, or "unknown" when there is no verdict
    auth_source             where they came from: "authentication-results", "received-spf" or "none"
    authenticated_domain    the domain authentication actually vouched for (gmail.com for the fake David)
    auth_aligned            the authenticated domain is the From domain's registered domain
    received_hops, origin_ip, send_hour
    freemail, name_has_address, list_mail, reply_to_divergence, envelope_mismatch
    org_domain, org_checkable, from_matches_org, org_lookalike_score

Missing evidence is recorded as unknown (None or "unknown"), never as pass.

Security: only the topmost Authentication-Results header is trusted, because the
receiving server adds it at the top; an attacker can write a fake
"dmarc=pass" lower in the header (RFC 8601 says to ignore results a receiver did
not add itself). All patterns have bounded repeats (no ReDoS).
"""

import ipaddress
import re

from src.headers.domains import is_freemail, lookalike_score, registered_domain

RESULTS = {"pass", "fail", "softfail", "neutral", "none", "temperror", "permerror", "policy"}
SYNONYMS = {"hardfail": "fail", "bestguesspass": "pass"}

COMMENT = re.compile(r"\([^()]{0,500}\)")  # "(google.com: domain of ... designates ...)"
METHOD_RESULT = re.compile(r"\b(spf|dkim|dmarc)\s{0,5}=\s{0,5}([a-z]{1,20})", re.IGNORECASE)
PROPERTY = re.compile(r"\b(smtp\.mailfrom|header\.from|header\.d|header\.i)\s{0,5}=\s{0,5}([^\s;]{1,255})", re.IGNORECASE)
IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
ADDRESS_OR_DOMAIN = re.compile(r"\b[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){1,8}\b", re.IGNORECASE)


def normal_result(word):
    """Map a verdict word to one of RESULTS ('hardfail' -> 'fail'); anything else is 'other'."""
    word = SYNONYMS.get(word.lower(), word.lower())
    return word if word in RESULTS else "other"


def domain_part(value):
    """'x@paypal.com' or '@paypal.com' or 'paypal.com' -> 'paypal.com' (lower-case, quotes stripped)."""
    value = value.strip("\"'<>").lower()
    return value.rsplit("@", 1)[-1] or None


def parse_auth_results(value):
    """Read one Authentication-Results value into verdicts and the domains they are about.

    Example: "mx.google.com; spf=pass smtp.mailfrom=x@y.com; dkim=pass header.d=y.com;
    dmarc=pass header.from=y.com" -> spf/dkim/dmarc = pass, with domains y.com.
    """
    verdicts = {}  # method -> (result, domain)
    for clause in COMMENT.sub(" ", value).split(";")[1:]:  # the part before the first ";" names the checker
        match = METHOD_RESULT.search(clause)
        if not match:
            continue
        method, result = match.group(1).lower(), normal_result(match.group(2))
        domain = None
        for key, prop_value in PROPERTY.findall(clause):
            key = key.lower()
            if (method, key) in {("spf", "smtp.mailfrom"), ("dmarc", "header.from"),
                                 ("dkim", "header.d"), ("dkim", "header.i")}:
                domain = domain_part(prop_value)
                break
        # A message can carry several DKIM signatures: keep a pass if there is one.
        if method not in verdicts or (result == "pass" and verdicts[method][0] != "pass"):
            verdicts[method] = (result, domain)
    return verdicts


def authentication(fields):
    """spf, dkim, dmarc, auth_source and authenticated_domain from the topmost verdict header."""
    out = {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown", "auth_source": "none", "authenticated_domain": None}
    verdicts = {}
    if fields.get("auth_results"):
        verdicts = parse_auth_results(fields["auth_results"][0])  # topmost only: added by the receiving server
        out["auth_source"] = "authentication-results"
    elif fields.get("received_spf"):
        words = fields["received_spf"].split()
        if words:
            verdicts = {"spf": (normal_result(words[0]), None)}
            out["auth_source"] = "received-spf"
    for method, (result, _) in verdicts.items():
        out[method] = result
    # The domain authentication vouched for: DMARC's From domain, else DKIM's, else SPF's.
    for method in ("dmarc", "dkim", "spf"):
        result, domain = verdicts.get(method, (None, None))
        if result == "pass" and domain:
            out["authenticated_domain"] = registered_domain(domain)
            break
    return out


def origin_ip(received):
    """The first public IPv4 address, reading the Received lines from the bottom (the sender's end) up."""
    for line in reversed(received or []):
        for candidate in IPV4.findall(line):
            try:
                if ipaddress.ip_address(candidate).is_global:  # skip 10.x, 192.168.x, 127.x and similar
                    return candidate
            except ValueError:  # not a real address, for example 999.1.1.1
                continue
    return None


def name_has_address(from_name, from_registered):
    """True if the display name shows an address or domain that is not the sender's own.

    '"service@paypal.com" <x@evil.ru>' -> True; '"PayPal" <service@paypal.com>' -> False.
    """
    if not from_name:
        return False
    for token in ADDRESS_OR_DOMAIN.findall(from_name):
        shown = registered_domain(token)
        if shown and shown != from_registered:
            return True
    return False


def header_evidence(fields, org_domain=None):
    """All evidence for one email. org_domain is the recipient organisation's domain, or None if unknown."""
    from_registered = registered_domain(fields.get("from_domain"))
    evidence = authentication(fields)
    authenticated = evidence["authenticated_domain"]
    evidence["auth_aligned"] = None if not (authenticated and from_registered) else authenticated == from_registered

    received = fields.get("received") or []
    evidence["received_hops"] = len(received)
    evidence["origin_ip"] = origin_ip(received)
    date = fields.get("date")
    evidence["send_hour"] = date.hour if date is not None else None  # on the sender's own clock

    evidence["from_registered_domain"] = from_registered
    evidence["freemail"] = is_freemail(from_registered) if from_registered else None
    evidence["name_has_address"] = name_has_address(fields.get("from_name"), from_registered)
    evidence["list_mail"] = fields.get("list_id") is not None

    reply_registered = registered_domain(fields.get("reply_to").split("@")[1]) if fields.get("reply_to") else None
    if not reply_registered or not from_registered:
        evidence["reply_to_divergence"] = False if not fields.get("reply_to") else None
    else:
        # A Reply-To set by a mailing list is how lists work, not a redirection.
        evidence["reply_to_divergence"] = reply_registered != from_registered and not evidence["list_mail"]

    bounce_registered = registered_domain(fields.get("return_path").split("@")[1]) if fields.get("return_path") else None
    evidence["envelope_mismatch"] = (bounce_registered != from_registered) if (bounce_registered and from_registered) else None

    org = registered_domain(org_domain) if org_domain else None
    evidence["org_domain"] = org
    evidence["org_checkable"] = org is not None and from_registered is not None
    evidence["from_matches_org"] = (from_registered == org) if evidence["org_checkable"] else None
    evidence["org_lookalike_score"] = lookalike_score(from_registered, org) if evidence["org_checkable"] else None
    return evidence
