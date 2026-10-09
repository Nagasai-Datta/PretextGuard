"""Phase 9: the self-test of the thread verifier. Hand-made threads, and the rows they must give.

Run from the project root:   python -m src.thread.selftest

Each case is a small thread written by hand and the rules its last message must (and must not) fire. The expected rows come from
the rule definitions in thread_verifier.py and master document Section 4.3, not from any real thread: no real thread had been
read when they were written. They cover each of the four signals, the hijack variants of the benchmark (account takeover with
copied sending details, look-alike domain swap, forged thread), the calm thread that must stay silent, a thread without Message-IDs
(raw Enron), the single-email mode and the prior_relationship claim. A last check makes sure every rule is exercised by at least
one case, so a rule cannot be added without a test.

The last part feeds crafted input (50 messages of 200,000 characters, 100 References, floods of '>', 100,000 'Re:' prefixes,
a cyclic In-Reply-To chain, a 200-message thread) and checks that every case finishes in under two seconds and every row
passes check_row.
"""

import sys
import time

from src.thread import signals as sig
from src.thread import builder
from src.thread.builder import normalise_subject
from src.verifiers.rows import check_row
from src.verifiers.thread_verifier import CONTRADICTION_RULES, RULES, scan_thread, verify_thread_message
from src.verifiers.verify import verify_claims

CRAFTED_LIMIT = 2.0           # seconds one crafted input may take

PARAGRAPHS = [
    "Thanks for the invoice 77 and the delivery schedule. We will review the numbers with the team this week and confirm the dates for the second shipment on Friday.",
    "The warehouse confirmed that the pallets left on Tuesday and should reach your site by Thursday morning. Please let me know if the customs paperwork is complete on your side.",
    "Good news from the quality team: the sample batch passed every test and the supplier agreed to keep the current price for the next quarter. I attach nothing new this time.",
    "I went through the contract draft and only two clauses need a change, the delivery penalty and the notice period. Could you ask legal to look at both before the meeting on Monday?",
    "Following the call with the plant manager we moved the installation to next week. The engineers will need access to the east building and a parking permit for the two vans.",
    "Here is the updated project plan with the revised milestones. The testing phase now ends on the twentieth and the training sessions for the staff start right after that.",
]
CALM_TACTICS = {"authority": 0.08, "urgency": 0.12, "scarcity": 0.05, "secrecy": 0.02}
HOT_TACTICS = {"authority": 0.80, "urgency": 0.95, "scarcity": 0.10, "secrecy": 0.97}
IBAN_A, IBAN_B = "DE89 3704 0044 0532 0130 00", "GB82 WEST 1234 5698 7654 32"


def claim(kind, confidence=0.9, claim_id="c1"):
    return {"claim_id": claim_id, "type": kind, "text": kind, "span": [0, 1], "confidence": confidence, "attributes": {}}


def wrap(text, width=9):
    """Re-wrap and quote a text the way a mail program does: '> ' in front of short lines."""
    words = text.split()
    return "\n".join("> " + " ".join(words[i:i + width]) for i in range(0, len(words), width))


def thread(count=4, ids=True, **common):
    """A calm thread of `count` messages between two people, each replying to the one before and quoting it."""
    messages = []
    for i in range(count):
        who = "john" if i % 2 == 0 else "mary"
        message = {
            "key": "m%d" % i, "message_id": ("<m%d@acme.example>" % i) if ids else None,
            "in_reply_to": ("<m%d@acme.example>" % (i - 1)) if ids and i else None,
            "references": ["<m%d@acme.example>" % j for j in range(i)] if ids else [],
            "from_addr": "%s.%s@acme.com" % (who, "park" if who == "john" else "lee"), "from_name": "%s %s" % (who.title(), "Park" if who == "john" else "Lee"),
            "from_domain": "acme.com", "subject": ("Re: " if i else "") + "Invoice 77", "origin_ip": "203.0.113.%d" % (5 if who == "john" else 6),
            "mailer": "Apple Mail (2.3774.600.%d)" % (62 + i), "text": PARAGRAPHS[i % len(PARAGRAPHS)],
            "quoted": ("On Monday someone wrote:\n" + wrap(PARAGRAPHS[(i - 1) % len(PARAGRAPHS)])) if i else "",
            "tactics": dict(CALM_TACTICS), "claims": [],
        }
        message.update(common)
        messages.append(message)
    return messages


def extend(base, **overrides):
    """base plus one more message (a copy of the last, then changed): the message the verifier will judge."""
    last = dict(base[-1])
    i = len(base)
    last.update({"key": "m%d" % i, "message_id": "<m%d@acme.example>" % i if last["message_id"] else None,
                 "in_reply_to": "<m%d@acme.example>" % (i - 1) if last["message_id"] else None,
                 "references": ["<m%d@acme.example>" % j for j in range(i)] if last["message_id"] else [],
                 "text": PARAGRAPHS[i % len(PARAGRAPHS)], "quoted": "On Monday someone wrote:\n" + wrap(base[-1]["text"]),
                 "tactics": dict(CALM_TACTICS), "claims": []})
    last.update(overrides)
    return base + [last]


def rules_of(rows, contradictions_only=False):
    return {r["rule"] for r in rows if r["contradiction"] or not contradictions_only}


EXERCISED = set()


def case(name, messages, must=(), must_not=(), index=None, all_rules=(), claims_must=()):
    """One case: judge messages[index] (default the last). `must` and `must_not` are rules that must / must not be CONTRADICTIONS,
    `all_rules` rules that must appear with any outcome. Returns (name, passed, detail)."""
    index = len(messages) - 1 if index is None else index
    rows = verify_thread_message(messages, index)
    EXERCISED.update(rules_of(rows))
    fired = rules_of(rows, contradictions_only=True)
    appeared = rules_of(rows)
    problems = [p for row in rows for p in check_row(row, RULES)]
    missing = [r for r in must if r not in fired]
    unwanted = [r for r in must_not if r in fired]
    absent = [r for r in all_rules if r not in appeared]
    passed = not (missing or unwanted or absent or problems)
    detail = "" if passed else "missing %s, unwanted %s, absent %s, row problems %s, fired %s" % (missing, unwanted, absent, problems, sorted(fired))
    return name, passed, detail


def cases():
    calm = thread(4)
    out = []
    out.append(case("a calm thread: the next reply fires nothing at all", extend(calm), must_not=sorted(CONTRADICTION_RULES),
                    all_rules=["tv_onset_steady", "tv_who_same_address", "tv_path_same", "tv_int_ids_ok", "tv_quote_ok"]))

    takeover = extend(calm, tactics=dict(HOT_TACTICS), text="Please change the payment now. Use IBAN %s from today and keep this between us." % IBAN_A,
                      claims=[claim("payment_change")])
    out.append(case("account takeover with copied sending details: content signals fire, path and integrity stay silent", takeover,
                    must=["tv_onset_many", "tv_bank_new", "tv_req_change_new"],
                    must_not=["tv_who_lookalike", "tv_who_suffix", "tv_path_origin_mailer", "tv_path_origin", "tv_path_mailer", "tv_int_ids_unknown", "tv_quote_mismatch"],
                    all_rules=["tv_who_same_address", "tv_path_same", "tv_int_ids_ok", "tv_quote_ok"]))
    out.append(case("one tactic starting is medium (tv_onset_one)", extend(calm, tactics=dict(CALM_TACTICS, urgency=0.80)), must=["tv_onset_one"], must_not=["tv_onset_many"]))
    hot_start = thread(4, tactics=dict(HOT_TACTICS))
    out.append(case("a thread that was urgent from the start does not start urgency again", extend(hot_start, tactics=dict(HOT_TACTICS)), must_not=["tv_onset_one", "tv_onset_many"], all_rules=["tv_onset_steady"]))
    out.append(case("a rare tactic (liking) never counts", extend(calm, tactics=dict(CALM_TACTICS, liking=0.99)), must_not=["tv_onset_one", "tv_onset_many"]))
    out.append(case("one earlier message is not enough history for tactic onset", extend(thread(1), tactics=dict(HOT_TACTICS)), all_rules=["tv_onset_no_history"], must_not=["tv_onset_one"]))

    with_bank = thread(3)
    with_bank[1]["text"] += " Our account is IBAN %s." % IBAN_A
    out.append(case("a different IBAN than the thread used before is high (tv_bank_changed)", extend(with_bank, text="Please use IBAN %s instead." % IBAN_B),
                    must=["tv_bank_changed"], must_not=["tv_bank_new"]))
    out.append(case("the same IBAN again is consistent (tv_bank_seen)", extend(with_bank, text="As before, IBAN %s." % IBAN_A), must_not=["tv_bank_changed", "tv_bank_new"], all_rules=["tv_bank_seen"]))
    quoted_only = thread(3)
    out.append(case("an IBAN only in the quoted history of this message is not counted", extend(quoted_only, quoted="On Monday someone wrote:\n" + wrap("Use IBAN %s please" % IBAN_A)),
                    must_not=["tv_bank_new", "tv_bank_changed"]))

    swap = extend(calm, from_addr="john.park@acrne.com", from_domain="acrne.com")
    out.append(case("look-alike domain swap (acme.com -> acrne.com) under an earlier sender's name is high", swap, must=["tv_who_lookalike"], must_not=["tv_path_origin"]))
    suffix = extend(calm, from_addr="john.park@acme.co", from_domain="acme.co")
    out.append(case("the same domain name under another suffix is medium", suffix, must=["tv_who_suffix"], must_not=["tv_who_lookalike"]))
    other = extend(calm, from_addr="john.park@gmail.com", from_domain="gmail.com")
    out.append(case("the same person from an unrelated domain is only low", other, must=["tv_who_other_domain"], must_not=["tv_who_lookalike", "tv_who_suffix"]))
    out.append(case("another address at the same domain is consistent", extend(calm, from_addr="john.p@acme.com"), must_not=["tv_who_lookalike", "tv_who_other_domain"], all_rules=["tv_who_same_domain"]))
    out.append(case("a stranger joining the thread: nothing to compare", extend(calm, from_addr="tom.stone@other.org", from_name="Tom Stone", from_domain="other.org"),
                    all_rules=["tv_who_new_sender"], must_not=["tv_who_lookalike"]))
    out.append(case("no From address", extend(calm, from_addr=None, from_name=None, from_domain=None), all_rules=["tv_who_no_from"]))

    out.append(case("same address, new server and new mail program is medium", extend(calm, origin_ip="198.51.100.9", mailer="Outlook Express 6"), must=["tv_path_origin_mailer"]))
    out.append(case("same address, new server only is low", extend(calm, origin_ip="198.51.100.9"), must=["tv_path_origin"], must_not=["tv_path_origin_mailer", "tv_path_mailer"]))
    out.append(case("same address, new mail program only is low", extend(calm, mailer="Outlook Express 6"), must=["tv_path_mailer"], must_not=["tv_path_origin"]))
    out.append(case("a mail program upgrade (new version number) is not a change", extend(calm, mailer="Apple Mail (2.9999.1.1)"), must_not=["tv_path_mailer", "tv_path_origin_mailer"], all_rules=["tv_path_same"]))
    out.append(case("no server or mail program known: path not checkable", extend(calm, origin_ip=None, mailer=None), all_rules=["tv_path_no_data"]))

    forged = extend(calm, in_reply_to="<fake1@evil.example>", references=["<fake0@evil.example>", "<fake1@evil.example>"],
                    quoted="On Monday someone wrote:\n" + wrap("The board approved the confidential acquisition last night and the lawyers need the first transfer wired before the market opens tomorrow morning so please prepare it quietly"))
    out.append(case("forged thread: unknown IDs and a fabricated quotation", forged, must=["tv_int_ids_unknown", "tv_quote_mismatch"], must_not=["tv_path_origin", "tv_who_lookalike"]))
    half = extend(calm, in_reply_to="<fake1@evil.example>", references=["<m0@acme.example>", "<m1@acme.example>", "<fake1@evil.example>"])
    out.append(case("the direct parent is missing but older ancestors are in the thread: low", half, must=["tv_int_parent_missing"], must_not=["tv_int_ids_unknown"]))
    no_ids = thread(4, ids=False)
    out.append(case("a thread without Message-IDs (raw Enron): IDs not checkable, the quote still is", extend(no_ids), all_rules=["tv_int_no_ids", "tv_quote_ok"], must_not=["tv_int_ids_unknown"]))
    enron_forged = extend(no_ids, quoted="On Monday someone wrote:\n" + wrap("Per our earlier call please prepare the transfer to the new account today and delete this message after reading it carefully"))
    out.append(case("a thread without IDs: the fabricated quotation is still caught", enron_forged, must=["tv_quote_mismatch"]))
    out.append(case("a short quotation cannot be judged", extend(calm, quoted="Re: hello thanks"), all_rules=["tv_quote_none"], must_not=["tv_quote_mismatch"]))

    two_requests = thread(3)
    for m in two_requests:
        m["claims"] = [claim("payment_request")]
    out.append(case("a payment request again in a payment thread is consistent", extend(two_requests, claims=[claim("payment_request")]), must_not=["tv_req_payment_new"], all_rules=["tv_req_seen"]))
    out.append(case("the first credential request in the thread is medium", extend(calm, claims=[claim("credential_request")]), must=["tv_req_credential_new"]))
    out.append(case("a weak credential claim lowers it one step (low)", extend(calm, claims=[claim("credential_request", confidence=0.6)]), must=["tv_req_credential_new"]))
    out.append(case("first gift-card request", extend(calm, claims=[claim("gift_card")]), must=["tv_req_gift_card_new"]))
    out.append(case("first payment request is low", extend(calm, claims=[claim("payment_request")]), must=["tv_req_payment_new"]))
    out.append(case("first data request is low", extend(calm, claims=[claim("data_request")]), must=["tv_req_data_new"]))
    out.append(case("request drift cannot be judged when earlier claims are missing", extend(thread(3, claims=None), claims=[claim("gift_card")]), all_rules=["tv_req_no_history"]))

    prior = [claim("prior_relationship")]
    out.append(case("prior_relationship: this sender wrote earlier in the thread", extend(calm, claims=prior), all_rules=["tv_prior_ok"], must_not=["tv_prior_stranger"]))
    stranger = extend(calm, from_addr="tom.stone@other.org", from_name="Tom Stone", from_domain="other.org", claims=prior)
    out.append(case("prior_relationship: a stranger in a longer thread is low", stranger, must=["tv_prior_stranger"]))
    out.append(case("prior_relationship: one earlier message shows no conversation", extend(thread(1), from_addr="tom.stone@other.org", from_name="Tom Stone", from_domain="other.org", claims=prior), all_rules=["tv_prior_few"]))
    out.append(case("prior_relationship: the earlier sender used another domain", extend(calm, from_addr="john.park@gmail.com", from_domain="gmail.com", claims=prior), must=["tv_prior_other_address"]))
    out.append(case("prior_relationship: no From address", extend(calm, from_addr=None, from_name=None, from_domain=None, claims=prior), all_rules=["tv_prior_no_from"]))
    out.append(case("prior_relationship in the first message: no thread", [dict(calm[0], claims=prior)], index=0, all_rules=["tv_prior_no_thread"]))

    first = dict(calm[0], subject="Re: Invoice 77", quoted=wrap(PARAGRAPHS[1] + " " + PARAGRAPHS[2]), in_reply_to=None, references=[])
    out.append(case("single email: a reply with quoted history but no reply headers is low", [first], index=0, must=["tv_single_no_reply_ids"]))
    out.append(case("single email: a reply that carries In-Reply-To is consistent", [dict(first, in_reply_to="<x@y.example>")], index=0, all_rules=["tv_single_ids_present"], must_not=["tv_single_no_reply_ids"]))
    out.append(case("single email: not a reply", [dict(first, subject="Invoice 77")], index=0, all_rules=["tv_single_not_reply"]))
    out.append(case("single email: a reply with no quoted history", [dict(first, quoted="")], index=0, all_rules=["tv_single_no_quote"]))
    return out


def scan_cases():
    """Flip-index cases: scan_thread must find the first message with a medium or high contradiction."""
    calm = thread(5)
    flip_at_3 = calm[:3] + [dict(calm[3], origin_ip="198.51.100.9", mailer="Outlook Express 6")] + calm[4:]
    sc = scan_thread(flip_at_3)
    forged_at_2 = calm[:2] + [dict(calm[2], in_reply_to="<fake@evil.example>", references=["<fake@evil.example>"])] + calm[3:]
    return [
        ("scan: a calm thread never flips", scan_thread(calm)["flip_index"] is None, ""),
        ("scan: the flip is the first message with a medium contradiction (index 3)", sc["flip_index"] == 3, "got %s" % sc["flip_index"]),
        ("scan: a low contradiction alone does not flip", scan_thread(calm[:3] + [dict(calm[3], origin_ip="198.51.100.9")] + calm[4:])["flip_index"] is None, ""),
        ("scan: a forged reply at index 2 flips at 2", scan_thread(forged_at_2)["flip_index"] == 2, "got %s" % scan_thread(forged_at_2)["flip_index"]),
        ("scan: message 0 has no past and never flips", scan_thread(calm)["messages"][0]["worst"] in (None,), ""),
    ]


def helper_checks():
    quote = " ".join(PARAGRAPHS[0:2])
    words, share = sig.quote_overlap(wrap(quote), [PARAGRAPHS[0], PARAGRAPHS[1]])
    unrelated = sig.quote_overlap(wrap(PARAGRAPHS[4]), [PARAGRAPHS[0], PARAGRAPHS[1]])[1]
    cut = normalise_subject("RE: Re: FW: Re[2]: Budget   plan ")
    return [
        ("words_of ignores punctuation and case", sig.words_of("Hello, WORLD! It's 5pm.") == ["hello", "world", "it", "s", "5pm"]),
        ("shingles of 4 words with size 2", sig.shingles(["a", "b", "c", "d"], 2) == {"a b", "b c", "c d"}),
        ("a re-wrapped, '>'-quoted copy of two messages matches its sources (only the 4 shingles over the join are missing)", share is not None and share > 0.9),
        ("an unrelated quotation shares (almost) no shingles", unrelated is not None and unrelated < 0.05),
        ("a quotation under 20 words cannot be judged", sig.quote_overlap("only a few words here", [PARAGRAPHS[0]])[1] is None),
        ("mailer_family drops versions", sig.mailer_family("Apple Mail (2.3774.600.62)") == "apple mail"),
        ("mailer_family keeps the first three words", sig.mailer_family("Microsoft Outlook Express Mail 6.0.2800") == "microsoft outlook express"),
        ("mailer_family of nothing is None", sig.mailer_family(None) is None and sig.mailer_family("123 456") is None),
        ("normalise_subject removes every prefix", cut == "budget plan"),
        ("two names of 5+ letters identify a person", sig.same_person({"from_name": "John Park", "from_addr": "a@x.com"}, {"from_name": "john park", "from_addr": "b@y.com"})),
        ("a short name does not", not sig.same_person({"from_name": "Bob", "from_addr": "bob@x.com"}, {"from_name": "Bob", "from_addr": "bob@y.com"})),
        ("rules registered: every contradiction rule has an entry", CONTRADICTION_RULES <= set(RULES)),
    ]


def builder_checks():
    """Regression checks for two mistakes the first real run showed: References is ONE space-separated string in headers.parquet (Phase 3),
    and the copies of an Enron message carry different Message-IDs."""
    two = "<a@x.example> <b@y.example>"
    header = {"message_id": "<m3@l>", "in_reply_to": None, "references": "<m1@l> <m2@l>", "from_addr": "c@z.org", "subject": "Kafka", "date": "2025-03-04T10:00:00+00:00"}
    records = [builder.record_from_table("m%d" % i, "apache_x", dict(header, message_id="<m%d@l>" % i, in_reply_to=("<m%d@l>" % (i - 1)) if i == 2 else None,
                                                                    references={1: None, 2: "<m1@l>", 3: "<m1@l> <m2@l>"}[i],
                                                                    from_addr="p%d@z.org" % (i % 2), date="2025-03-0%dT10:00:00+00:00" % i), "Hello thread body %d" % i)
               for i in (1, 2, 3)]
    threads, _ = builder.apache_threads(records)
    index = [{"key": "k%d" % i, "message_id": "<id%d>" % i, "date": "2001-05-1%dT10:00:00-07:00" % (i % 3), "from_addr": ("a" if i % 2 == 0 else "b") + "@enron.com",
              "subject": ("RE: " if i else "") + "Budget plan", "people": ["a@enron.com", "b@enron.com"]} for i in range(3)]
    copies = [dict(row, key=row["key"] + "_copy", message_id=row["message_id"] + "_copy") for row in index]      # same second, sender and subject, new Message-ID
    candidates, counts = builder.enron_candidates(index + copies)
    return [
        ("decode_references reads the space-separated string of headers.parquet", builder.decode_references(two) == ["<a@x.example>", "<b@y.example>"]),
        ("decode_references reads the JSON list of threads.parquet, None and NaN", builder.decode_references('["<a@x>"]') == ["<a@x>"] and builder.decode_references(None) == []
         and builder.decode_references(float("nan")) == []),
        ("a message with References but no In-Reply-To still joins its thread", len(threads) == 1 and len(threads[0]) == 3),
        ("record_from_table turns the References string into a list", records[2]["references"] == ["<m1@l>", "<m2@l>"]),
        ("copies of an Enron message with other Message-IDs are removed", counts["distinct_messages"] == 3 and len(candidates) == 1 and len(candidates[0]) == 3),
    ]


def api_checks():
    """verify_claims: unchanged without a thread, thread-aware with one."""
    calm = thread(4)
    prior = [dict(claim("prior_relationship"), claim_id="c1"), dict(claim("payment_request"), claim_id="c2")]
    alone = verify_claims(prior, {}, "", "")
    with_thread = verify_claims(prior, {}, "", "", thread=(extend(calm), len(calm)))
    rules_alone = [r["rule"] for r in alone]
    rules_thread = [r["rule"] for r in with_thread]
    return [
        ("verify_claims without a thread keeps the Phase 8 placeholder", rules_alone[0] == "tv_needs_thread" and len(alone) == 2),
        ("verify_claims with a thread replaces it with tv_prior_*", rules_thread[0] == "tv_prior_ok"),
        ("a request claim gets the request verifier's row and then the thread's", len(with_thread) == 3 and with_thread[2]["verifier"] == "thread" and with_thread[1]["verifier"] == "request"),
    ]


def crafted():
    """(name, thread) pairs of hostile input; see the module text."""
    big = "word " * 40_000          # 200,000 characters
    base = thread(3)
    out = []
    out.append(("50 messages of 200,000 characters, each quoting the one before", [dict(m, text=big + str(i), quoted=big) for i, m in enumerate(thread(50))]))
    out.append(("a message that names 100 References", extend(base, references=["<r%d@x.example>" % i for i in range(100)])))
    out.append(("a quotation that is 10,000 lines of '>'", extend(base, quoted=">\n" * 10_000)))
    out.append(("a subject of 100,000 'Re:' prefixes", extend(base, subject="Re: " * 100_000)))
    cyc = thread(50)
    for i, m in enumerate(cyc):
        m["in_reply_to"], m["references"] = "<m%d@acme.example>" % ((i + 1) % 50), ["<m%d@acme.example>" % ((i + 1) % 50)]
    out.append(("a cyclic In-Reply-To chain across 50 messages", cyc))
    out.append(("60,000 '@' signs and IBAN-shaped words in the text", extend(base, text="@" * 30_000 + " DE12 " * 6_000)))
    out.append(("one 60,000-character word", extend(base, text="A1" * 30_000, quoted="B2" * 30_000)))
    out.append(("a mailer and a display name of 60,000 characters", extend(base, mailer="x" * 60_000, from_name="y" * 60_000)))
    out.append(("a thread of 200 messages (only 50 are examined)", thread(200)))
    return out


def run_crafted():
    """Run the crafted inputs. Returns a list of (name, seconds, number of row problems, number of rows)."""
    results = []
    for name, messages in crafted():
        sig.text_shingles.cache_clear()
        started = time.time()
        result = scan_thread(messages)
        seconds = time.time() - started
        rows = [row for entry in result["messages"] for row in entry["rows"]]
        results.append((name, seconds, sum(len(check_row(r, RULES)) for r in rows), len(rows)))
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

    EXERCISED.clear()
    check("thread rules", True, "(%d rules)" % len(RULES))
    for name, passed, detail in cases():
        check(name, passed, detail)
    for name, passed, detail in scan_cases():
        check(name, passed, detail)
    for name, passed in helper_checks():
        check(name, passed)
    for name, passed in builder_checks():
        check(name, passed)
    for name, passed in api_checks():
        check(name, passed)
    unexercised = sorted(set(RULES) - EXERCISED)
    check("every rule is exercised by at least one case", not unexercised, "(not exercised: %s)" % unexercised if unexercised else "")
    for name, seconds, problems, produced in run_crafted():
        check("crafted input: %s" % name, seconds < CRAFTED_LIMIT and not problems and produced > 0,
              "(%.2f s, %d rows%s)" % (seconds, produced, ", %d problems" % problems if problems else ""))
    return ok, count


if __name__ == "__main__":
    print("Thread verifier self-test:")
    sys.exit(0 if self_test()[0] else 1)
