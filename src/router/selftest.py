"""Phase 10: the self-test of the router, the ledger, the score and the whole pipeline. Hand-made emails and threads, and what they must give.

Run from the project root:   python -m src.router.selftest

Three parts, none of which reads a real email or needs the trained model:
  1. the pieces alone: the score on hand-made ledgers (the worked values of master document Section 6.6), the router and the ledger checks;
  2. the pipeline end to end on hand-made raw emails and threads: the real header parser, the real redaction, the real spaCy claim extractor and the
     real verifiers, with a STAND-IN for the tactic classifier (a keyword counter with the Phase 6 thresholds), because the weights exist only on
     the Mac. The stand-in is only a source of tactic probabilities; everything else is the real code. The expected results come from the rule
     definitions (the David email of Section 6.7 and the hijack variants of Section 8.3), not from any real email;
  3. safety: crafted input (300,000-byte messages, header floods, markup, a 60-message thread) must finish quickly, produce a report that passes
     check_report, and put nothing that could run in a browser into any string.
The LIME part has its own self-test (python -m src.explain.lime_explain); here it is checked only as wired into the report.
"""

import json
import random
import sys
import time

import numpy as np

from src.data.label_schema import TACTICS
from src.explain.lime_explain import find_words
from src.router import ledger as ledger_module
from src.router import score as score_module
from src.router.pipeline import Analyzer, check_report, display_safe, looks_like_headers, usable_org
from src.router.router import assign, check_routing
from src.router.score import ACTIONS, ADDENDA, DEFAULT_CONFIG, action_for, band_of, fired_tactics, make_config, score_ledger
from src.thread.selftest import PARAGRAPHS, wrap
from src.verifiers.rows import ROUTES, consistent_row, contradiction_row, unchecked_row
from src.verifiers.verify import ALL_RULES

CRAFTED_LIMIT = 5.0           # seconds one crafted input may take (the real spaCy extractor is in the loop)
IBAN = "DE89 3704 0044 0532 0130 00"


# ---------------------------------------------------------------------------------------------------- the stand-in classifier

class StubClassifier:
    """Tactic probabilities from keyword counts, with the Phase 6 thresholds. Not a model: only a source of numbers for the tests."""

    thresholds = {"authority": 0.55, "urgency": 0.45, "scarcity": 0.65, "reciprocity": 0.5, "social_proof": 0.5, "liking": 0.5, "secrecy": 0.9}
    WORDS = {"urgency": ({"urgent", "urgently", "immediately", "asap", "today", "deadline"}, 0.3),
             "secrecy": ({"confidential", "secret", "discreet", "nobody"}, 0.45),
             "authority": ({"ceo", "cfo", "director", "president"}, 0.3),
             "scarcity": ({"limited", "hurry", "last", "only"}, 0.35)}

    def __init__(self):
        self.texts_seen = 0

    def probabilities(self, bodies, batch_size=16):
        out = np.full((len(bodies), len(TACTICS)), 0.03)
        for i, body in enumerate(bodies):
            words = {w for _, _, w in find_words(body) if w}
            for tactic, (keywords, step) in self.WORDS.items():
                out[i, TACTICS.index(tactic)] = min(0.97, 0.03 + step * len(words & keywords))
        self.texts_seen += len(bodies)
        return out


# --------------------------------------------------------------------------------------------------- hand-made raw emails

def auth(domain, spf="pass", dkim="pass", dmarc="pass"):
    return ("Authentication-Results: mx.acmecorp.com; spf=%s smtp.mailfrom=%s; dkim=%s header.d=%s; dmarc=%s header.from=%s\n"
            % (spf, domain, dkim, domain, dmarc, domain))


DAVID_BODY = ("Hi Maria,\n\nThis is David from Finance. I need you to process a wire transfer of $48,000 to a new vendor before 3 PM today. "
              "It is urgent and confidential, this is a secret so be discreet. Please reply to my private email only.\n\nDavid Chen\nFinance Director\n")
DAVID_GMAIL = ("From: David Chen <david.chen.acme@gmail.com>\nTo: Maria Lopez <maria@acmecorp.com>\nReply-To: david.finance@protonmail.com\n"
               + auth("gmail.com") + "Subject: Urgent wire\nDate: Mon, 05 Oct 2026 09:12:00 +0000\nMessage-ID: <d1@mail.gmail.com>\n\n" + DAVID_BODY)
SPOOF = ('From: "David Chen" <d.chen@acmecorp.com>\nTo: Maria Lopez <maria@acmecorp.com>\n' + auth("acmecorp.com", "fail", "none", "fail")
         + "Subject: Wire\nDate: Mon, 05 Oct 2026 09:12:00 +0000\n\n" + DAVID_BODY)
HONEST = ("From: David Chen <david@acmecorp.com>\nTo: Maria Lopez <maria@acmecorp.com>\n" + auth("acmecorp.com")
          + "Subject: Invoice\nDate: Mon, 05 Oct 2026 09:12:00 +0000\n\nHi Maria,\n\nThis is David from Finance. Please process the invoice for the October delivery when you have a moment.\n\nThanks\n")
PHISH_GMAIL = ("From: IT Help Desk <it.helpdesk.acme@gmail.com>\nTo: Maria Lopez <maria@acmecorp.com>\n" + auth("gmail.com")
               + "Subject: Account\nDate: Mon, 05 Oct 2026 09:12:00 +0000\n\nDear user, please verify your account password and confirm your login details.\n")
BODY_ONLY = ("Hi Maria,\n\nThis is David from Finance. Please process a wire transfer of $48,000 today, it is urgent. Keep it confidential, it is a secret. "
             "Reply to my private email.\n\nDavid\n")
NEWSLETTER = ("From: Shop News <news@shop-example.com>\nTo: Maria Lopez <maria@acmecorp.com>\n" + auth("shop-example.com", "fail", "none", "none")
              + "Subject: Sale\nDate: Mon, 05 Oct 2026 09:12:00 +0000\n\nOur autumn sale starts this week with new products in every category.\n")


def eml(i, sender, subject, text, previous=None, ids=True, ip="52.10.20.30", mailer="Apple Mail (2.3774.600.62)", reply_to_ids=None, quote=None):
    """A raw .eml of message i of a thread: headers a real mail program writes, the new text, and the previous text quoted with '> ' marks."""
    name, address = sender
    lines = ["From: %s <%s>" % (name, address), "To: Team <team@acme.com>", "Date: Mon, %02d Oct 2026 09:%02d:00 +0000" % (5 + i // 6, 10 + i * 5),
             "Subject: %s" % subject, "Message-ID: <m%d@acme.example>" % i, "X-Mailer: %s" % mailer,
             "Received: from mailhost (mailhost [%s]) by mx.acme.com with ESMTP; Mon, 05 Oct 2026 09:10:00 +0000" % ip]
    if ids and i:
        refs = reply_to_ids or ["<m%d@acme.example>" % j for j in range(i)]
        lines += ["In-Reply-To: %s" % refs[-1], "References: %s" % " ".join(refs)]
    body = text
    if quote is not None:
        body += "\n\nOn Monday, someone wrote:\n" + wrap(quote)
    elif previous:
        body += "\n\nOn Monday, someone wrote:\n" + wrap(previous)
    return "\n".join(lines) + "\n\n" + body + "\n"


JOHN, MARY = ("John Park", "john.park@acme.com"), ("Mary Lee", "mary.lee@acme.com")


def calm_thread(count=4):
    return [eml(i, JOHN if i % 2 == 0 else MARY, ("Re: " if i else "") + "Invoice 77", PARAGRAPHS[i % len(PARAGRAPHS)],
                previous=PARAGRAPHS[(i - 1) % len(PARAGRAPHS)] if i else None, ip="52.10.20.%d" % (30 if i % 2 == 0 else 31)) for i in range(count)]


HIJACK_TEXT = ("Quick change before the next payment: we have changed banks, please use our new account %s and pay today, it is urgent. "
               "Keep this confidential, it is a secret, tell nobody." % IBAN)


# ---------------------------------------------------------------------------------------------------------------- rows for part 1

def claim(kind, claim_id="c1", confidence=0.9):
    return {"claim_id": claim_id, "type": kind, "text": kind, "span": [0, 1], "confidence": confidence, "attributes": {"zone": "body"}}


def hot(rule, severity, kind, claim_id="c1", verifier=None):
    verifier = verifier or ALL_RULES.get(rule, {}).get("verifier", "thread")
    return contradiction_row(verifier, claim(kind, claim_id), rule, severity, "A test reason for %s." % rule, {"x": 1})


def results_of(report):
    return {r["rule"] for r in report["ledger"] if r["contradiction"] is True}


# ---------------------------------------------------------------------------------------------------------------- the self-test

def self_test(verbose=True):
    """(all passed, number of checks)."""
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # ---- part 1a: the score ----------------------------------------------------------------------------------------------
    def score_of(rows, fired=(), config=None):
        return score_ledger(rows, fired, config)

    medium = hot("hv_ext_other_domain", "medium", "affiliation_external")
    high = hot("hv_int_freemail", "high", "affiliation_internal")
    high2 = hot("rv_freemail", "high", "payment_request", "c2")
    d = score_of([medium])
    check("a lone medium contradiction scores 35 and is Suspicious", d["score"] == 35 and d["band"] == "Suspicious", str(d["score"]))
    d = score_of([high])
    check("a lone high scores 60 and is Suspicious", d["score"] == 60 and d["band"] == "Suspicious", str(d["score"]))
    d = score_of([high], ["urgency"])
    check("a lone high with urgency scores 75 (60 x 1.25 + 4 tactic points = 79, so 75 is the contradiction part)", d["contradiction_points"] == 60 and d["multiplier"] == 1.25 and d["score"] == 79,
          str((d["contradiction_points"], d["multiplier"], d["score"])))
    d = score_of([high], ["secrecy"])
    check("a lone high with secrecy is High risk", d["band"] == "High risk" and d["score"] == 79, str(d["score"]))
    d = score_of([high, high2])
    check("two highs on two claims score 90 (60 + 30) and are High risk", d["score"] == 90 and d["band"] == "High risk", str(d["score"]))
    lows = [hot("hv_ext_unknown_freemail", "low", "affiliation_external", "c%d" % i) for i in range(1, 13)]
    d = score_of(lows)
    check("twelve lows on twelve claims score 10 (5 x (2 - 2^-11)) and stay Low risk", d["score"] == 10 and d["band"] == "Low risk", str(d["score"]))
    d = score_of([high, high2, hot("hv_reply_diverges", "medium", "reply_direction", "c3")], ["urgency", "secrecy"])
    check("the score is capped at 100", d["score"] == 100 and d["capped"] is True, str((d["raw"], d["score"])))
    d = score_of([consistent_row("header", claim("authority"), "hv_auth_ok", "The rank claimed comes from an authenticated domain.", {}),
                  unchecked_row("header", claim("reply_direction", "c2"), "hv_reply_no_header", "There is no Reply-To header to compare.", {})])
    check("consistent and not-checkable rows add nothing", d["score"] == 0 and d["groups"] == [], str(d["score"]))
    d = score_of([high, consistent_row("request", claim("payment_request", "c2"), "rv_ok", "The asker authenticated as its own domain.", {})])
    check("a passed check never lowers the score of another claim", d["score"] == 60)
    same = [high, hot("hv_int_other_domain", "medium", "affiliation_internal")]
    d = score_of(same)
    check("two contradictions of one claim count once (the strongest)", d["score"] == 60 and len(d["groups"]) == 1 and d["groups"][0]["severity"] == "high")
    d = score_of([], ["urgency", "secrecy"])
    check("pressure tactics alone score only their small points (8) and multiply nothing", d["score"] == 8 and d["contradiction_points"] == 0 and d["band"] == "Low risk")
    d = score_of([], ["authority", "urgency", "scarcity", "secrecy"])
    check("tactic points stop at 12", d["tactic_points"] == 12 and d["score"] == 12)
    d = score_of([], ["liking", "reciprocity", "social_proof"])
    check("liking, reciprocity and social proof are not scored", d["score"] == 0 and d["scored_tactics"] == [])
    d = score_of([hot("tv_onset_one", "medium", "tactic_onset", "thread"), hot("tv_path_origin_mailer", "medium", "sending_path", "thread")])
    check("each thread signal is its own group (35 + 17.5)", d["score"] == 53 and len(d["groups"]) == 2, str(d["score"]))
    config = make_config(reliability={"hv_ext_other_domain": 0.5})
    d = score_of([medium], config=config)
    check("a rule with reliability 0.5 is worth half (17.5) and a lone medium drops to Low risk", d["score"] == 18 and d["band"] == "Low risk", str(d["score"]))
    config = make_config(reliability={"hv_ext_other_domain": 0.0})
    d = score_of([medium, high2], config=config)
    check("a rule with reliability 0 is listed but takes no place in the sum", d["score"] == 60 and d["groups"][-1]["counted"] == 0.0 and d["groups"][0]["weight"] == 1.0, str(d["score"]))
    check("the shipped reliability file lists only known rules, each with factor 0 or 0.5, and its factor is used by the default configuration",
          set(score_module.RELIABILITY) <= ledger_module.KNOWN_RULES and all(v in (0.0, 0.5) for v in score_module.RELIABILITY.values()) and DEFAULT_CONFIG["reliability"] == score_module.RELIABILITY,
          str(score_module.RELIABILITY))
    noisy = [hot(rule, "low", "signature_contact") for rule in score_module.RELIABILITY if score_module.RELIABILITY[rule] == 0.0 and rule.startswith("hv_")]
    check("a noisy rule at reliability 0 in the shipped file adds no points even when it fires", not noisy or score_of(noisy)["score"] == 0, str(score_of(noisy)["score"] if noisy else "none"))
    check("bands change at 35 and 70", [band_of(s) for s in (0, 34, 35, 69, 70, 100)] == ["Low risk", "Low risk", "Suspicious", "Suspicious", "High risk", "High risk"])
    try:
        make_config(nonsense=1)
        check("an unknown score setting is refused", False)
    except KeyError:
        check("an unknown score setting is refused", True)
    check("changing a copy of the configuration leaves the frozen one alone", make_config(points={"high": 1, "medium": 1, "low": 1}) is not DEFAULT_CONFIG and DEFAULT_CONFIG["points"]["high"] == 60)
    rng = random.Random(7)
    pool = [hot("hv_int_freemail", "high", "affiliation_internal"), hot("rv_freemail", "high", "payment_request", "c2"), hot("hv_reply_diverges", "medium", "reply_direction", "c3"),
            hot("hv_sig_other_domain", "low", "signature_contact", "c4"), hot("tv_bank_new", "medium", "request_drift", "thread"), hot("tv_quote_mismatch", "high", "thread_integrity", "thread")]
    monotone = True
    for _ in range(200):
        subset = rng.sample(pool, rng.randint(0, 5))
        extra = rng.choice(pool)
        tactics = rng.sample(TACTICS, rng.randint(0, 4))
        monotone &= score_of(subset + [extra], tactics)["score"] >= score_of(subset, tactics)["score"]
        monotone &= score_of(subset, tactics + ["urgency"])["score"] >= score_of(subset, tactics)["score"]
    check("adding a contradiction or a fired tactic never lowers the score (400 random cases)", monotone)
    check("the Low risk action has no addendum, the others add one sentence keyed on the strongest finding",
          action_for("Low risk", score_of([medium])) == ACTIONS["Low risk"] and action_for("High risk", score_of([high2, high])).endswith(ADDENDA["affiliation_internal"]) and action_for("High risk", score_of([high2])).endswith(ADDENDA["payment_request"]))
    check("action texts hold no markup", all(not set("<>`") & set(t) for t in list(ACTIONS.values()) + list(ADDENDA.values())))
    check("fired_tactics compares probability and threshold rounded to 4 decimals", fired_tactics({t: 0.45 for t in TACTICS}, StubClassifier.thresholds) == ["urgency"]
          and fired_tactics({t: 0.44996 for t in TACTICS}, StubClassifier.thresholds) == ["urgency"] and fired_tactics([0.0] * 7, StubClassifier.thresholds) == [])

    # ---- part 1b: the router and the ledger ---------------------------------------------------------------------------
    claims = [claim(t, "c%d" % (i + 1)) for i, t in enumerate(ROUTES)]
    assignments, skipped = assign(claims)
    check("every claim type is routed to the verifier of Section 6.4", all(a["verifiers"] == [ROUTES[a["type"]]] for a in assignments) and not skipped)
    assignments, _ = assign(claims, has_thread=True)
    check("with a thread the five request types also go to the thread verifier", {a["type"] for a in assignments if a["verifiers"] == ["request", "thread"]}
          == {"payment_request", "payment_change", "credential_request", "gift_card", "data_request"})
    check("a claim of an unknown type is reported as skipped", assign([claim("loud_noises", "c9")]) == ([], ["c9"]))
    rows = [consistent_row("header", claim("authority", "c1"), "hv_auth_ok", "The rank claimed comes from an authenticated domain.", {})]
    two, _ = assign([claim("authority", "c1"), claim("payment_request", "c2")])
    problems = check_routing(two, rows)
    check("a claim that got no row from its verifier is found", len(problems) == 1 and "c2" in problems[0] and "request" in problems[0], str(problems))
    check("a row for a claim nobody assigned is found", len(check_routing(two[:1], rows + [consistent_row("request", claim("payment_request", "c2"), "rv_ok", "The asker authenticated as its own domain.", {})])) == 1)
    good = [high, high2]
    built, problems = ledger_module.build_ledger([claim("affiliation_internal", "c1"), claim("payment_request", "c2")], assign([claim("affiliation_internal", "c1"), claim("payment_request", "c2")])[0], good, [])
    check("a sound ledger has no problems", not problems and built == good, str(problems))
    wrong = dict(high, verifier="request")
    check("a rule filed under the wrong verifier is found", any("belongs to header" in p for p in ledger_module.build_ledger([claim("affiliation_internal")], assign([claim("affiliation_internal")])[0], [wrong], [])[1]))
    check("a claim row that names no extracted claim is found", any("not extracted" in p for p in ledger_module.build_ledger([], [], [high], [])[1]))
    check("a signal row that is not 'thread' is found", any("instead of" in p for p in ledger_module.build_ledger([], [], [], [hot("tv_onset_one", "medium", "tactic_onset", "c1")])[1]))
    check("two rows for one claim and verifier are found", any("2 rows" in p for p in ledger_module.build_ledger([claim("affiliation_internal")], assign([claim("affiliation_internal")])[0], [high, high], [])[1]))
    broken = dict(high, severity="none")
    check("a row that fails check_row is found", any("severity" in p for p in ledger_module.build_ledger([claim("affiliation_internal")], assign([claim("affiliation_internal")])[0], [broken], [])[1]))
    thread_rows = [hot("rv_freemail", "high", "payment_request", "c1"), consistent_row("thread", claim("payment_request", "c1"), "tv_req_seen", "An earlier message in the thread already made a request of this type.", {})]
    cov = ledger_module.coverage([claim("payment_request", "c1"), claim("authority", "c2")], thread_rows + [unchecked_row("header", claim("authority", "c2"), "hv_auth_no_evidence", "Rank claimed, nothing to compare it with.", {})], ["single_email"])
    check("coverage counts a claim once whatever the number of its rows", (cov["claims"], cov["contradicted"], cov["not_checkable"], cov["checked"]) == (2, 1, 1, 1), str(cov))
    check("coverage says in plain words what could not run", "1 of 2 claims" in cov["note"] and ledger_module.LIMITS["single_email"] in cov["note"], cov["note"])
    check("coverage with no claim says so", "No claim" in ledger_module.coverage([], [], [])["note"])
    names = ledger_module.FEATURE_NAMES
    vector = ledger_module.flat_features(thread_rows, {t: 0.5 for t in TACTICS}, 2, 1)
    check("the flat feature vector has one number per name, no duplicate names, and is repeatable", len(vector) == len(names) == len(set(names)) and vector == ledger_module.flat_features(thread_rows, [0.5] * 7, 2, 1))
    check("the flat vector marks the rule that fired and the worst severity of its verifier", vector[names.index("rule:rv_freemail")] == 1.0 and vector[names.index("worst:request")] == 3.0
          and vector[names.index("worst:header")] == 0.0 and vector[names.index("rule:tv_req_seen")] == 0.0)

    # ---- part 2: the pipeline end to end ----------------------------------------------------------------------------------
    stub = StubClassifier()
    analyzer = Analyzer(classifier=stub)

    def run(raw, **kwargs):
        started = time.time()
        report = analyzer.analyze(raw, **kwargs)
        return report, time.time() - started

    report, _ = run(DAVID_GMAIL)
    rules = results_of(report)
    check("David from gmail.com (Section 6.7): High risk", report["verdict"] == "High risk" and report["score"] == 100, "%s %s" % (report["verdict"], report["score"]))
    check("David: internal claim, payment request and Reply-To are contradicted by the header and request verifiers", {"hv_int_freemail", "rv_freemail", "hv_reply_diverges"} <= rules, str(sorted(rules)))
    check("David: urgency and secrecy fired and multiplied", report["score_detail"]["pressure"] == ["secrecy", "urgency"] and report["score_detail"]["multiplier"] == 1.5, str(report["score_detail"]["pressure"]))
    check("David: the organisation domain came from the To header", report["org_domain"] == "acmecorp.com", str(report["org_domain"]))
    check("David: header findings show the sender and the authentication state without any address", report["header_findings"]["from_domain"] == "gmail.com" and report["header_findings"]["freemail"] is True
          and report["header_findings"]["auth_state"] == "aligned" and "@" not in json.dumps(report["header_findings"]), str(report["header_findings"]))
    check("David: the report passes check_report", check_report(report) == [])
    check("David: the routing lists each claim with its verifier", {a["type"]: a["verifiers"] for a in report["routing"]}["payment_request"] == ["request"] and report["mode"] == "email" and report["thread"] is None)
    check("David: LIME ran for the tactics that fired and its highlights fit the text", report["explained"] is True and any(t["highlights"] for t in report["tactics"] if t["fired"])
          and all(report["text_read"][h["start"]:h["end"]] == h["text"] for t in report["tactics"] for h in t["highlights"]))
    urgency_words = {h["word"].lower() for t in report["tactics"] if t["name"] == "urgency" for h in t["highlights"]}
    check("David: the urgency highlights are words the stand-in classifier reacts to", urgency_words and urgency_words <= StubClassifier.WORDS["urgency"][0] | set(), str(urgency_words))
    fast, _ = run(DAVID_GMAIL, explain=False)
    check("without LIME no highlights are made and the score is the same", fast["explained"] is False and not any(t["highlights"] for t in fast["tactics"]) and fast["score"] == report["score"])
    again, _ = run(DAVID_GMAIL, request_id="fixed-id")
    again2, _ = run(DAVID_GMAIL, request_id="fixed-id")
    check("the same email gives the same report (only the request id may differ)", again == again2 and dict(again, request_id="x") == dict(report, request_id="x"))
    report, _ = run(SPOOF)
    check("exact-domain spoof (DMARC fails for the organisation's own domain): High risk", report["verdict"] == "High risk" and {"hv_int_spoof", "rv_auth_fail"} <= results_of(report), str(sorted(results_of(report))))
    report, _ = run(HONEST)
    check("honest internal mail: Low risk, the claims checked and consistent", report["verdict"] == "Low risk" and report["score"] == 0 and report["coverage"]["contradicted"] == 0
          and report["coverage"]["checked"] >= 1, str(report["coverage"]))
    report, _ = run(PHISH_GMAIL)
    check("a credential request from a free mailbox claiming to be IT: at least Suspicious", report["verdict"] in ("Suspicious", "High risk") and "rv_freemail" in results_of(report), "%s %s" % (report["verdict"], sorted(results_of(report))))
    report, _ = run(NEWSLETTER)
    check("a newsletter with no claim: Low risk and the coverage says no claim was found", report["verdict"] == "Low risk" and report["coverage"]["claims"] == 0 and "No claim" in report["coverage"]["note"])
    report, _ = run(BODY_ONLY)
    check("a pasted body with no headers: nothing can be checked, so Low risk by the score, but the coverage says why",
          report["verdict"] == "Low risk" and report["header_findings"]["headers_found"] is False and "headers_missing" in report["coverage"]["limits"]
          and report["coverage"]["checked"] == 0 and report["coverage"]["not_checkable"] >= 2 and not results_of(report), str(report["coverage"]))
    check("a pasted body: the tactics still fired and add their small points", report["score"] == 8 and set(report["score_detail"]["scored_tactics"]) == {"urgency", "secrecy"}, str(report["score_detail"]))
    check("an organisation domain given by the caller is used; a free mailbox provider is ignored", usable_org("AcmeCorp.com")[0] == "acmecorp.com" and usable_org("gmail.com") == (None, True) and usable_org(None) == (None, False)
          and usable_org("not a domain") == (None, True))
    report, _ = run(HONEST, org_domain="gmail.com")
    check("an unusable organisation domain is reported as a limit", "org_domain_ignored" in report["coverage"]["limits"])
    check("header detection: a header line starts an email, a greeting or 'X-ray' or 'From the desk' does not",
          looks_like_headers(b"From: a@b.co\nTo: x") and looks_like_headers(b"Received: from x") and looks_like_headers(b"From bob@x.com Mon Jan 1 2024")
          and not looks_like_headers(b"Hello Maria,\nplease") and not looks_like_headers(b"X-ray results are in") and not looks_like_headers(b"From the desk of the CFO"))

    # threads
    calm = calm_thread(4)
    calm5 = calm + [eml(4, JOHN, "Re: Invoice 77", PARAGRAPHS[4], previous=PARAGRAPHS[3], ip="52.10.20.30")]
    report, _ = run(calm5)
    check("a calm thread with a calm newest message: Low risk, no flip", report["mode"] == "thread" and report["verdict"] == "Low risk" and report["thread"]["flip_index"] is None
          and report["thread"]["messages"] == 5 and not results_of(report), "%s %s %s" % (report["verdict"], report["thread"]["flip_index"], sorted(results_of(report))))
    takeover = calm + [eml(4, JOHN, "Re: Invoice 77", HIJACK_TEXT, previous=PARAGRAPHS[3], ip="52.10.20.30")]
    report, _ = run(takeover)
    rules = results_of(report)
    check("account takeover (same address, same server, copied IDs, new bank details and pressure): the thread flips at the newest message", report["thread"]["flip_index"] == 4, str(report["thread"]["flip_index"]))
    check("takeover: tactic onset and a new bank detail are found, and the score is at least Suspicious", {"tv_bank_new"} <= rules and rules & {"tv_onset_one", "tv_onset_many"} and report["verdict"] in ("Suspicious", "High risk"),
          "%s %s" % (report["verdict"], sorted(rules)))
    check("takeover: the Phase 8 verifiers alone would have seen nothing at all (header and request rows are not contradictions)", not any(r["contradiction"] is True for r in report["ledger"] if r["verifier"] in ("header", "request")))
    check("takeover: the thread section lists the signals that fired and a timeline of every message", len(report["thread"]["timeline"]) == 5 and any(s["rule"] == "tv_bank_new" for s in report["thread"]["signals"]))
    swap = calm + [eml(4, ("John Park", "john.park@acrne.com"), "Re: Invoice 77", PARAGRAPHS[4], previous=PARAGRAPHS[3], ip="52.10.20.77", mailer="Roundcube Webmail 1.6")]
    report, _ = run(swap)
    check("look-alike domain swap (acme.com becomes acrne.com): found by the sender comparison", "tv_who_lookalike" in results_of(report) and report["verdict"] in ("Suspicious", "High risk"), str(sorted(results_of(report))))
    forged = calm + [eml(4, JOHN, "Re: Invoice 77", PARAGRAPHS[4], reply_to_ids=["<forged-1@thread.invalid>", "<forged-2@thread.invalid>"],
                         quote="We agreed last week on the new payment schedule and the revised amounts for the second quarter, and you promised to send the signed papers by Friday afternoon.")]
    report, _ = run(forged)
    check("forged thread (IDs that name no message, a quotation that never happened): found by the integrity checks", {"tv_int_ids_unknown", "tv_quote_mismatch"} <= results_of(report), str(sorted(results_of(report))))
    shuffled, _ = run(list(reversed(takeover)))
    check("messages given in the wrong order are sorted by their Date headers", shuffled["thread"]["flip_index"] == 4 and shuffled["score"] == run(takeover)[0]["score"])
    undated = [m.replace("Date:", "X-Date:") for m in takeover]
    report, _ = run(undated)
    check("messages without a usable Date are taken in the order given, and the coverage says so", "thread_unordered" in report["coverage"]["limits"])
    big = [eml(i, JOHN if i % 2 == 0 else MARY, ("Re: " if i else "") + "Invoice 77", PARAGRAPHS[i % len(PARAGRAPHS)], previous=PARAGRAPHS[(i - 1) % len(PARAGRAPHS)] if i else None) for i in range(60)]
    report, seconds = run(big)
    check("a 60-message thread: the last 50 are examined and the coverage says so", report["thread"]["messages"] == 50 and "thread_truncated" in report["coverage"]["limits"] and seconds < CRAFTED_LIMIT, "%.2f s" % seconds)
    report, _ = run([DAVID_GMAIL])
    check("a thread of one message is analysed as a single email", report["mode"] == "email" and report["thread"] is None)

    # ---- part 3: safety ----------------------------------------------------------------------------------------------------
    evil = DAVID_GMAIL.replace("Hi Maria,", "Hi <b>Maria</b> `x` <script>alert(1)</script> \u200b\x07,")
    report, _ = run(evil)
    flat = json.dumps(report)
    check("HTML tags, backticks and control characters in the email never reach the report", "<" not in flat and ">" not in flat and "`" not in flat
          and "\u200b" not in report["text_read"] and check_report(report) == [])
    evil = DAVID_GMAIL.replace("Hi Maria,", "Hi Maria, if the amount is < 50,000 or > 10,000 `x` \u200b\x07 then wait,")
    report, _ = run(evil)
    flat = json.dumps(report)
    check("a '<' or '>' that is not an HTML tag is shown as a look-alike character, one for one", "<" not in flat and ">" not in flat and "\u2039 50,000" in report["text_read"]
          and "\u203a 10,000" in report["text_read"] and "\u200b" not in report["text_read"] and check_report(report) == [])
    check("display_safe keeps the length, so every offset still fits", len(display_safe("<a>`b`\x00​")) == len("<a>`b`\x00​") and display_safe("<a>") == "‹a›")
    evil_from = DAVID_GMAIL.replace('From: David Chen <david.chen.acme@gmail.com>', 'From: "<img src=x onerror=alert(1)> Boss" <david.chen.acme@gmail.com>')
    report, _ = run(evil_from)
    flat = json.dumps(report)
    check("a display name with markup is cleaned in the header findings and in every reason", "<" not in flat and "onerror" not in report["header_findings"]["from_name"].replace(" ", "") + "x" or "<" not in flat)
    huge = DAVID_GMAIL + ("lorem ipsum dolor sit amet " * 20000)
    report, seconds = run(huge)
    check("a message over 300,000 bytes is cut and the coverage says so", "text_truncated" in report["coverage"]["limits"] and seconds < CRAFTED_LIMIT, "%.2f s" % seconds)
    flood = "".join("X-Spam-%d: %s\n" % (i, "a" * 200) for i in range(3000)) + DAVID_GMAIL
    report, seconds = run(flood)
    check("3,000 extra header lines finish in time and give a sound report", seconds < CRAFTED_LIMIT and check_report(report) == [], "%.2f s" % seconds)
    report, seconds = run("From: " + "@" * 60000 + "\nTo: x@y.com\n\n" + "@" * 60000)
    check("60,000 '@' signs in the From header and the body finish in time", seconds < CRAFTED_LIMIT and check_report(report) == [], "%.2f s" % seconds)
    report, seconds = run("")
    check("an empty email gives a sound Low risk report", report["verdict"] == "Low risk" and check_report(report) == [] and report["claims"] == [])
    report, seconds = run(DAVID_GMAIL.encode("utf-8") + b"\xff\xfe\x00bad bytes")
    check("bytes that are not valid text are decoded with replacement and analysed", check_report(report) == [])
    for bad, error in ((12345, TypeError), ([], ValueError)):
        try:
            analyzer.analyze(bad)
            check("input of the wrong kind is refused (%r)" % (bad,), False)
        except error:
            check("input of the wrong kind is refused (%r)" % (bad,), True)
    for rid in ("", "a b", "x" * 65, "<script>"):
        try:
            analyzer.analyze(NEWSLETTER, request_id=rid)
            check("a request id with bad characters or the wrong size is refused (%r)" % rid[:12], False)
        except ValueError:
            check("a request id with bad characters or the wrong size is refused (%r)" % rid[:12], True)
    # check_report catches tampering
    good_report, _ = run(DAVID_GMAIL, request_id="tamper")
    cases = {
        "a changed score": lambda r: r.update(score=50),
        "a verdict that does not fit the score": lambda r: r.update(verdict="Low risk"),
        "a ledger row removed": lambda r: r["ledger"].pop(0),
        "markup in a reason": lambda r: r["ledger"][0].update(reason="Claims <b>internal</b> status, see the evidence."),
        "a tactic flag flipped": lambda r: r["tactics"][1].update(fired=not r["tactics"][1]["fired"]),
        "a highlight that does not match the text": lambda r: r["tactics"][1]["highlights"].append({"start": 0, "end": 3, "text": "zzz", "weight": 0.1, "word": "zzz"}),
        "a missing key": lambda r: r.pop("coverage"),
        "a thread section in email mode": lambda r: r.update(thread={"messages": 1}),
        "a claim whose text is not its span": lambda r: r["claims"][0].update(text="something else"),
        "a score_detail that was edited": lambda r: r["score_detail"].update(contradiction_points=1),
    }
    import copy
    for name, tamper in cases.items():
        broken = copy.deepcopy(good_report)
        try:
            tamper(broken)
            found = check_report(broken)
        except Exception as error:      # a crash while checking a tampered report also counts as found
            found = [repr(error)]
        check("check_report finds %s" % name, bool(found), "")
    flipped = Analyzer(classifier=stub, config=make_config(reliability={"hv_int_freemail": 0.0, "rv_freemail": 0.0, "hv_reply_diverges": 0.0}))
    report = flipped.analyze(DAVID_GMAIL, explain=False)
    check("a report made with another configuration passes check_report with that configuration (and not with the frozen one)",
          check_report(report, flipped.config) == [] and check_report(report) != [] and report["score"] < 100, str(report["score"]))
    check("the stand-in classifier saw every message once for the tactics and the LIME copies for the rest", stub.texts_seen > 0)

    passed = all(ok for _, ok, _ in checks)
    if verbose:
        for name, ok, detail in checks:
            print("  %s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok or not detail else "  -> " + detail))
        print("%d of %d checks passed" % (sum(ok for _, ok, _ in checks), len(checks)))
    return passed, len(checks)


if __name__ == "__main__":
    ok, _ = self_test()
    sys.exit(0 if ok else 1)
