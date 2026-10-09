"""Phase 8: the self-test of the verifiers. Hand-made emails with real header blocks, and the ledger rows they must give.

Run from the project root:   python -m src.verifiers.selftest

Each case is a header block (parsed by the real Phase 3 parser and evidence code, so the whole chain is tested, not only
the verifiers), hand-made claims in the form the claim extractor returns, and the rows expected: (rule, severity), in
claim order. The cases are the ones of master document Section 6.7 (the David email from gmail.com, and the exact-domain
spoof), the examples of Section 6.5, and the situations the Phase 3 and Phase 7 notes warn about (a newsletter whose SPF
fails, mailing-list mail, a display name that shows another address, a look-alike domain, collector mailboxes). Nothing
here was read from a real email: the expected rows come from the rule definitions.

The last part feeds crafted input (60,000-character fields, thousands of '@' signs, IBAN-shaped words, markup in a claimed
organisation) and checks that every case finishes in under two seconds and every row passes check_row.
"""

import json
import sys
import time

from src.headers.build import organisation_domain
from src.headers.evidence import header_evidence
from src.headers.parser import parse_header_fields
from src.verifiers.bank import bank_detail_keys, find_bank_details, valid_iban
from src.verifiers.brands import BRAND_DOMAINS, NO_DOMAINS_YET
from src.verifiers.facts import find_addresses, prepare_facts, similar_domain
from src.verifiers.header_verifier import find_brand
from src.verifiers.rows import check_row
from src.verifiers.verify import ALL_RULES, RULES_VERSION, verify_claims

GOOD_IBAN = "DE89 3704 0044 0532 0130 00"
CRAFTED_LIMIT = 2.0          # seconds one crafted input may take


def claim(claim_type, text, organisation=None, department=None, confidence=0.9, pattern="selftest"):
    """A claim dictionary in the form of src/claims/schema.py (the claim id is set by `claims`)."""
    return {"claim_id": "", "type": claim_type, "text": text, "span": [0, len(text)], "confidence": confidence,
            "attributes": {"person": None, "organisation": organisation, "department": department, "pattern": pattern, "zone": "body"}}


def claims(*items):
    for number, item in enumerate(items, start=1):
        item["claim_id"] = "c%d" % number
    return list(items)


def facts_from(block):
    """Parse a header block with the Phase 3 code and return the merged fields and evidence a verifier receives."""
    fields, _ = parse_header_fields(block)
    evidence = header_evidence(fields, organisation_domain(fields.get("to_domain")))
    return {**fields, **evidence}


def auth(server, spf, dkim, dmarc, domain, dkim_domain=None):
    """An Authentication-Results line as the receiving server writes it."""
    return ("Authentication-Results: %s; spf=%s smtp.mailfrom=%s; dkim=%s header.d=%s; dmarc=%s header.from=%s\n"
            % (server, spf, domain, dkim, dkim_domain or domain, dmarc, domain))


# Header blocks, written once and reused.
DAVID_GMAIL = ("From: David Chen <david.chen.acme@gmail.com>\nTo: Maria Lopez <maria@acmecorp.com>\nReply-To: david.finance@protonmail.com\n"
               + auth("mx.acmecorp.com", "pass", "pass", "pass", "gmail.com") + "Subject: Urgent\n")
SPOOF = ('From: "David Chen" <d.chen@acmecorp.com>\nTo: Maria Lopez <maria@acmecorp.com>\n'
         + auth("mx.acmecorp.com", "fail", "none", "fail", "acmecorp.com") + "Subject: Wire\n")
HONEST = ("From: David Chen <david@acmecorp.com>\nTo: Maria Lopez <maria@acmecorp.com>\n"
          + auth("mx.acmecorp.com", "pass", "pass", "pass", "acmecorp.com") + "Subject: Budget\n")
NEWSLETTER = ("From: Shop News <news@shop-example.com>\nTo: Maria Lopez <maria@acmecorp.com>\n"
              + auth("mx.acmecorp.com", "fail", "none", "none", "shop-example.com") + "Subject: Sale\n")
LIST_MAIL = ("From: Alice <alice@gmail.com>\nTo: dev@kafka.apache.org\nReply-To: dev@kafka.apache.org\nList-Id: <dev.kafka.apache.org>\n"
             + auth("mx1.apache.org", "none", "pass", "none", "gmail.com") + "Subject: [DISCUSS] change\n")
PAYPAL_NAME = 'From: "service@paypal.com" <x@evil-mail.ru>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Your account\n'
PAYPAL_LOOKALIKE = "From: PayPal <service@paypa1.com>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Your account\n"
PAYPAL_REAL = ("From: PayPal <service@paypal.com>\nTo: someone@gmail.com\n" + auth("mx.google.com", "pass", "pass", "pass", "paypal.com")
               + "Subject: Receipt\n")
PAYPAL_VIA_MAILER = ("From: PayPal <paypal@mail.payments-example.net>\nTo: someone@gmail.com\n"
                     "Authentication-Results: mx.google.com; spf=pass smtp.mailfrom=bounce.sender-example.net; dkim=pass header.d=paypal.com; dmarc=none\n"
                     "Subject: Receipt\n")
AMAZON_OTHER = "From: Amazon Support <support@order-help-center.com>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Order\n"
LOOKALIKE_ORG = 'From: "Finance Director" <fd@acme-corp.co>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Payment\n'
REPLY_HIJACK = ("From: John Park <john@acmecorp.com>\nTo: Maria Lopez <maria@acmecorp.com>\nReply-To: john.park@gmail.com\n"
                + auth("mx.acmecorp.com", "pass", "pass", "pass", "acmecorp.com") + "Subject: Hello\n")
GMAIL_SENDER = "From: Accounts <accounts.team@gmail.com>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Update\n"
COLLECTOR = "From: Alex <alex@gmail.com>\nTo: jose@monkey.org\nSubject: Hello\n"
NO_FROM = "To: Maria Lopez <maria@acmecorp.com>\nSubject: Hello\n"
NO_AUTH = "From: David Chen <david@acmecorp.com>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Budget\n"
UNRELATED = "From: Sam Rivera <sam@partner-example.org>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Ticket\n"
BARE_NAME = 'From: "Amazon.com" <store@mailer-example.net>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Your order\n'
TENANT = "From: Payroll <payroll@acme-payroll.onmicrosoft.com>\nTo: Maria Lopez <maria@acmecorp.com>\nSubject: Payroll\n"

# (name, header block, claims, contact_text, body_text, expected [(rule, severity), ...] in claim order)
CASES = [
    ("David from gmail.com (Section 6.7): internal claim, payment request, reply redirect", DAVID_GMAIL,
     claims(claim("affiliation_internal", "this is David from Finance", department="Finance"), claim("payment_request", "process the wire transfer"),
            claim("reply_direction", "reply to my private email")), "", "",
     [("hv_int_freemail", "high"), ("rv_freemail", "high"), ("hv_reply_diverges", "medium")]),
    ("exact-domain spoof (Section 6.7 variant): DMARC fails for the organisation's own domain", SPOOF,
     claims(claim("affiliation_internal", "this is David from Finance", department="Finance"), claim("payment_request", "process the wire transfer")), "", "",
     [("hv_int_spoof", "high"), ("rv_auth_fail", "high")]),
    ("honest internal mail: authentication passes for the organisation's own domain", HONEST,
     claims(claim("affiliation_internal", "this is David from Finance", department="Finance"), claim("payment_request", "please pay the invoice"),
            claim("authority", "As the CFO"), claim("signature_contact", "David Chen Finance", None)),
     "David Chen\nFinance\ndavid@acmecorp.com +1 555 0100", "",
     [("hv_int_ok_auth", "none"), ("rv_ok", "none"), ("hv_auth_ok", "none"), ("hv_sig_ok", "none")]),
    ("newsletter with spf=fail and no identity claim gives no row at all", NEWSLETTER, [], "", "", []),
    ("the same failed SPF under a payment request is a finding", NEWSLETTER,
     claims(claim("payment_request", "your invoice is overdue")), "", "", [("rv_spf_fail", "medium")]),
    ("the same failed SPF under a rank claim is a finding", NEWSLETTER,
     claims(claim("authority", "As the manager")), "", "", [("hv_auth_spf_fail", "medium")]),
    ("bank details raise a payment request by one step", NEWSLETTER,
     claims(claim("payment_request", "please pay the invoice")), "", "Pay to " + GOOD_IBAN, [("rv_spf_fail", "high")]),
    ("mailing list: a list-set Reply-To is fine and the list domain is no employer", LIST_MAIL,
     claims(claim("reply_direction", "reply to me directly"), claim("affiliation_internal", "I am from the Kafka team")), "", "",
     [("hv_reply_ok", "none"), ("hv_int_list", "not_checkable")]),
    ("display name shows paypal.com, sent from evil-mail.ru", PAYPAL_NAME,
     claims(claim("affiliation_external", "PayPal Security Team", organisation="PayPal"), claim("credential_request", "verify your account")), "", "",
     [("hv_ext_name_spoof", "high"), ("rv_name_address", "medium")]),
    ("look-alike domain paypa1.com", PAYPAL_LOOKALIKE,
     claims(claim("affiliation_external", "PayPal Security Team", organisation="PayPal"), claim("credential_request", "sign in to your PayPal account")), "", "",
     [("hv_ext_lookalike", "high"), ("rv_lookalike", "high")]),
    ("genuine PayPal mail authenticates as paypal.com", PAYPAL_REAL,
     claims(claim("affiliation_external", "PayPal Security Team", organisation="PayPal"), claim("credential_request", "log in to your PayPal account")), "", "",
     [("hv_ext_brand_ok", "none"), ("rv_ok", "none")]),
    ("brand mail through a third-party mailer, signed by the brand's own domain", PAYPAL_VIA_MAILER,
     claims(claim("affiliation_external", "PayPal Customer Service", organisation="PayPal")), "", "", [("hv_ext_signed_by_brand", "none")]),
    ("known brand from an unrelated domain is medium, never high", AMAZON_OTHER,
     claims(claim("affiliation_external", "Amazon Support", organisation="Amazon")), "", "", [("hv_ext_other_domain", "medium")]),
    ("an organisation with no domain on file cannot be compared", AMAZON_OTHER,
     claims(claim("affiliation_external", "Acme Widgets Support", organisation="Acme Widgets")), "", "", [("hv_ext_unknown_org", "not_checkable")]),
    ("a cue with no organisation has nothing to check", AMAZON_OTHER,
     claims(claim("affiliation_external", "Security Team")), "", "", [("hv_ext_no_org", "not_checkable")]),
    ("rank and internal claim from acme-corp.co (look-alike of acmecorp.com)", LOOKALIKE_ORG,
     claims(claim("authority", "As the CFO"), claim("affiliation_internal", "this is the Finance department", department="Finance")), "", "",
     [("hv_auth_lookalike", "high"), ("hv_int_lookalike", "high")]),
    ("Reply-To hijack: the organisation's mail, replies to a free mailbox", REPLY_HIJACK,
     claims(claim("reply_direction", "reply to me directly")), "", "", [("hv_reply_diverges", "high")]),
    ("signature shows the company address, message sent from gmail.com", DAVID_GMAIL,
     claims(claim("signature_contact", "David Chen Finance Director")), "David Chen, Finance Director\nAcme Corp\ndavid.chen@acmecorp.com | +1 555 0100", "",
     [("hv_sig_freemail_sender", "medium")]),
    ("a signature with a phone number only cannot be compared", HONEST,
     claims(claim("signature_contact", "Tel: 555 0100")), "David Chen\nTel: +1 555 0100", "", [("hv_sig_no_address", "not_checkable")]),
    ("payment change with a valid IBAN from a free mailbox, bank details masked", GMAIL_SENDER,
     claims(claim("payment_change", "new bank details")), "", "Please use our new bank details: IBAN " + GOOD_IBAN, [("rv_freemail", "high")]),
    ("gift cards requested by a stranger on a free mailbox", GMAIL_SENDER,
     claims(claim("gift_card", "buy gift cards")), "", "", [("rv_freemail", "high")]),
    ("a data request from a free mailbox is one step lower", GMAIL_SENDER,
     claims(claim("data_request", "send your passport")), "", "", [("rv_freemail", "medium")]),
    ("collector mailbox: no organisation domain, so an internal claim is not checkable", COLLECTOR,
     claims(claim("affiliation_internal", "IT help desk", department="IT")), "", "", [("hv_int_no_org", "not_checkable")]),
    ("no From address: every claim is not checkable", NO_FROM,
     claims(claim("affiliation_internal", "IT help desk"), claim("affiliation_external", "PayPal Team", organisation="PayPal"), claim("authority", "As the CFO"),
            claim("payment_request", "pay the invoice"), claim("signature_contact", "Tel"), claim("reply_direction", "reply to me")), "", "",
     [("hv_int_no_from", "not_checkable"), ("hv_ext_no_from", "not_checkable"), ("hv_auth_no_from", "not_checkable"), ("rv_no_from", "not_checkable"),
      ("hv_sig_no_from", "not_checkable"), ("hv_reply_no_header", "not_checkable")]),
    ("a weak claim lowers the severity by one step", DAVID_GMAIL,
     claims(claim("affiliation_internal", "finance", department="Finance", confidence=0.6)), "", "", [("hv_int_freemail", "medium")]),
    ("organisation's own domain but no authentication verdict: not checkable, never consistent", NO_AUTH,
     claims(claim("affiliation_internal", "this is David from Finance", department="Finance"), claim("payment_request", "please pay the invoice"),
            claim("authority", "As the CFO")), "", "",
     [("hv_int_no_auth", "not_checkable"), ("rv_no_proof", "not_checkable"), ("hv_auth_no_evidence", "not_checkable")]),
    ("a bank-detail change from an authenticated sender still needs the thread", HONEST,
     claims(claim("payment_change", "new bank details")), "", "IBAN " + GOOD_IBAN, [("rv_change_needs_thread", "not_checkable")]),
    ("open-platform tenant acme-payroll.onmicrosoft.com counts as a free mailbox", TENANT,
     claims(claim("affiliation_internal", "this is Payroll", department="Payroll")), "", "", [("hv_int_freemail", "high")]),
    ("a reference to a brand ('your Microsoft account') is not a claim of identity", AMAZON_OTHER,
     claims(claim("affiliation_external", "Microsoft account", organisation="Microsoft", pattern="ae_org_cue")), "", "", [("hv_ext_reference", "not_checkable")]),
    ("the nearest organisation is not the claim's organisation: nothing to compare", AMAZON_OTHER,
     claims(claim("affiliation_external", "the Financial Services Authority", organisation="Lloyds TSB", pattern="ae_org_cue")), "", "", [("hv_ext_no_org", "not_checkable")]),
    ("a footer 'copyright Amazon' counts as the sender speaking", AMAZON_OTHER,
     claims(claim("affiliation_external", "Amazon", organisation="Amazon", pattern="ae_copyright")), "", "", [("hv_ext_other_domain", "medium")]),
    ("an unknown organisation from a free mailbox is only low", GMAIL_SENDER,
     claims(claim("affiliation_external", "Standard Bank Customer Service", organisation="Standard Bank")), "", "", [("hv_ext_unknown_freemail", "low")]),
    ("an internal claim from an unrelated domain is only low (the recipient domain may be a list)", UNRELATED,
     claims(claim("affiliation_internal", "IT help desk", department="IT")), "", "", [("hv_int_other_domain", "low")]),
    ("a bare domain in the display name (Amazon.com) is only a low signal under a request", BARE_NAME,
     claims(claim("credential_request", "log in to your account")), "", "", [("rv_name_domain", "low")]),
    ("a copyright line is no contact address to compare, even when the footer holds one", GMAIL_SENDER,
     claims(claim("signature_contact", "(c) 2008", pattern="sc_copyright")), "Acme Corp\nsales@acmecorp.com", "", [("hv_sig_not_contact", "not_checkable")]),
    ("prior_relationship goes to the thread verifier, tactics have no verifier", HONEST,
     claims(claim("prior_relationship", "as we discussed on the call"), claim("urgency", "right now")), "", "", [("tv_needs_thread", "not_checkable")]),
]


def run_case(name, block, claim_list, contact, body, expected):
    """Returns (passed, detail) for one case."""
    rows = verify_claims(claim_list, facts_from(block), contact, body)
    got = [(r["rule"], r["severity"]) for r in rows]
    problems = [p for r in rows for p in check_row(r, ALL_RULES)]
    ok = got == expected and not problems
    return ok, "" if ok else "got %s expected %s %s" % (got, expected, problems)


def helper_checks():
    """(name, passed) for the small tools."""
    out = []
    out.append(("valid IBAN examples pass the checksum", all(valid_iban(v) for v in ("GB82WEST12345698765432", "DE89370400440532013000", "FR1420041010050500013M02606"))))
    out.append(("a changed digit fails the checksum", not valid_iban("DE89370400440532013001") and not valid_iban("GB82WEST12345698765433")))
    details = find_bank_details("Account number 12345678, routing 021000021, sort code 12-34-56, SWIFT DEUTDEFF500, call 5551234567, order number 87654321")
    out.append(("labelled numbers found, unlabelled numbers ignored", [d["kind"] for d in details] == ["account", "routing", "routing", "swift"]))
    out.append(("bank detail keys compare as sets", bank_detail_keys("IBAN " + GOOD_IBAN) == bank_detail_keys("iban DE89370400440532013000.")))
    out.append(("an IBAN is masked in the details", find_bank_details(GOOD_IBAN)[0]["masked"] == "DE**3000"))
    out.append(("paypa1.com is a look-alike of paypal.com", similar_domain("paypa1.com", "paypal.com") == "lookalike"))
    out.append(("paypal.net is the same name under another suffix", similar_domain("paypal.net", "paypal.com") == "suffix"))
    out.append(("visa.com and vista.com are not look-alikes (names too short)", similar_domain("vista.com", "visa.com") is None))
    out.append(("acme-corp.co is a look-alike of acmecorp.com", similar_domain("acme-corp.co", "acmecorp.com") == "lookalike"))
    out.append(("unrelated domains are not alike", similar_domain("example.org", "paypal.com") is None))
    out.append(("brand lookup finds the longest name and aliases", find_brand("Wells Fargo Bank team") == "Wells Fargo" and find_brand("Office 365 admin") == "Microsoft"
                and find_brand("nobody here") is None))
    out.append(("signature addresses are read by registered domain", find_addresses("Call me. John <john.doe@mail.acmecorp.com>; also j@gmail.com, x@@bad") == ["acmecorp.com", "gmail.com"]))
    f = prepare_facts({"spf": float("nan"), "dmarc": "pass", "freemail": None, "list_mail": None, "from_registered_domain": "gmail.com"})
    out.append(("missing and NaN values become unknown, never pass", f["spf"] == "unknown" and f["dkim"] == "unknown" and f["auth_state"] == "no_pass" and f["list_mail"] is False))
    brand_overlap = [d for domains in BRAND_DOMAINS.values() for d in domains if d in __import__("src.headers.domains", fromlist=["FREEMAIL"]).FREEMAIL]
    out.append(("no brand domain is a free mailbox domain", not brand_overlap))
    out.append(("rules are listed with their verifier", len(ALL_RULES) >= 50 and "Yahoo" in NO_DOMAINS_YET))
    bad = {"claim_id": "c1", "claim_type": "authority", "verifier": "header", "rule": "hv_auth_ok", "evidence": {}, "contradiction": True,
           "severity": "none", "reason": "A reason that is long enough."}
    out.append(("check_row rejects a contradiction with severity none", bool(check_row(bad))))
    return out


def crafted():
    """(name, text-builder) for the crafted-input cases: each builds a header block and claims that try to make the verifiers slow or unsafe."""
    big = 60000
    return [
        ("display name of 60,000 characters", 'From: "%s" <x@evil.ru>\nTo: maria@acmecorp.com\n' % ("service@paypal.com " * (big // 19)), "x"),
        ("Reply-To of 60,000 characters", "From: a@acmecorp.com\nTo: maria@acmecorp.com\nReply-To: %s@gmail.com\n" % ("a" * big), "x"),
        ("signature of 60,000 '@' signs", GMAIL_SENDER, "@" * big),
        ("signature of 60,000 address-like words", GMAIL_SENDER, "a@b.c " * (big // 6)),
        ("body of IBAN-shaped words", GMAIL_SENDER, "DE12 " * (big // 5)),
        ("one 60,000-character word", GMAIL_SENDER, "A1" * (big // 2)),
        ("labels without numbers", GMAIL_SENDER, "account " * (big // 8)),
        ("markup in the claimed organisation", AMAZON_OTHER, "<script>alert(1)</script>"),
    ]


def run_crafted():
    """Run the crafted inputs. Returns a list of (name, seconds, number of problems, rows, claims asked)."""
    results = []
    for name, block, payload in crafted():
        organisation = payload if "markup" in name else "PayPal"
        claim_list = claims(claim("affiliation_internal", "IT help desk"), claim("affiliation_external", "PayPal Security Team", organisation=organisation),
                            claim("authority", "As the CFO"), claim("reply_direction", "reply to me"), claim("signature_contact", "Tel"),
                            claim("payment_request", "pay the invoice"), claim("payment_change", "new bank details"), claim("credential_request", "verify your account"),
                            claim("gift_card", "gift cards"), claim("data_request", "send your passport"))
        body = payload if "markup" not in name else ""
        started = time.time()
        rows = verify_claims(claim_list, facts_from(block), body, body)
        seconds = time.time() - started
        results.append((name, seconds, sum(len(check_row(r, ALL_RULES)) for r in rows), len(rows), len(claim_list)))
    return results


def self_test(verbose=True):
    """Run everything. Returns (passed, number of checks). With verbose=False only failures are printed."""
    ok, count = True, 0

    def check(name, passed, detail=""):
        nonlocal ok, count
        ok = ok and passed
        count += 1
        if verbose or not passed:
            print("  %-4s %s %s" % ("PASS" if passed else "FAIL", name, detail))

    check("rules version", True, "(%s, %d rules)" % (RULES_VERSION, len(ALL_RULES)))
    for name, block, claim_list, contact, body, expected in CASES:
        passed, detail = run_case(name, block, claim_list, contact, body, expected)
        check(name, passed, detail)
    for name, passed in helper_checks():
        check(name, passed)
    iban_case = next(case for case in CASES if case[0].startswith("payment change with a valid IBAN"))
    rows = verify_claims(iban_case[2], facts_from(iban_case[1]), "", iban_case[4])
    text = json.dumps(rows)
    check("the full IBAN never appears in a row", "DE89370400440532013000" not in text and GOOD_IBAN not in text and "DE**3000" in text)
    for name, seconds, problems, produced, asked in run_crafted():
        check("crafted input: %s" % name, seconds < CRAFTED_LIMIT and not problems and produced == asked,
              "(%.2f s, %d rows%s)" % (seconds, produced, ", %d problems" % problems if problems else ""))
    return ok, count


if __name__ == "__main__":
    print("Verifier self-test:")
    sys.exit(0 if self_test()[0] else 1)
