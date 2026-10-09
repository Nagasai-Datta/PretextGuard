"""Phase 9: the thread verifier (N2). It judges one message against the earlier messages of its own thread.

    from src.verifiers.thread_verifier import verify_thread_message, scan_thread

    rows = verify_thread_message(messages, index)        # the ledger rows for messages[index]
    result = scan_thread(messages)                       # every message in turn, and the index where the thread flipped

`messages` is a list of the dictionaries described in src/thread/signals.py, in time order. A message with no earlier
messages gets only the one rule that needs no history (single-email mode, below). The rows have the shape of master document
Section 6.3 (rows.py), with verifier "thread"; rule ids start with tv_.

WHY IT EXISTS. N3 and the request verifier read the headers of ONE email. A hijacked account sends through the real provider
with the real credentials, so SPF, DKIM and DMARC all pass for the real domain and every Phase 8 rule says 'consistent'.
What gives the attacker away is not the message but the change: the thread was about a project and now asks for a new bank
account, or the same address suddenly writes from another server, or the 'earlier conversation' it quotes never happened.
That is what the four signals measure (src/thread/signals.py) and this file turns into findings:

    tactic_onset       urgency, secrecy ... start here and nowhere before                       tv_onset_*
    request_drift      new or changed bank details; a request type that is new to the thread    tv_bank_*  tv_req_*
    sending_path       the name of an earlier sender at a look-alike domain; the same address
                       from a new server and mail program                                      tv_who_*  tv_path_*
    thread_integrity   In-Reply-To / References that name no message of the thread; a
                       quotation that is not what the thread said                              tv_int_*  tv_quote_*
    prior_relationship "as we discussed on the call": did this sender take part earlier?        tv_prior_*

Three values, as in Phase 8: a finding is a contradiction (high, medium or low), consistent, or not checkable. Missing
evidence is never 'no contradiction': a thread without Message-IDs (raw Enron) gets 'not checkable' from the ID rule, not a pass.

THE FLIP POINT. scan_thread judges message 1, 2, 3 ... each against its own past. The thread 'flipped' at the first message
with a contradiction of medium or high severity. That is change-point detection in its simplest form: the thread is normal until
one message breaks the pattern, and the index of that message is the answer.

SINGLE-EMAIL MODE. With no earlier messages the history signals cannot run. The one thing that can is the check master
document Section 4.3 promises: a message that calls itself a reply ('Re:' subject, quoted history) but carries no In-Reply-To
or References. Many real messages lack the headers, so it is low severity; build.py prints its rate on real mail.

NOT PROOF. A hijacker who has read the mailbox can copy real Message-IDs, sending details and wording; then only the content
signals can catch the message, and if the attacker also keeps the content calm, nothing here can (the report says so). A thread
verifier that says 'consistent' means 'nothing in the thread contradicts this message', never 'this message is safe'.

Severities are initial labels (the strength of the rule, not a probability); Phase 10 turns them into points and calibrates
them on validation. Rules are written from the definitions and revised only after reading TRAIN threads (THREAD_VERSION_LOG).

Security. Reasons are built from fixed templates and validated values only: tactic names come from a fixed list, domains go
through clean_domain, bank details are shown masked (bank.py), and nothing else from the email is printed. check_row rejects a
reason with markup.
"""

from src.claims.patterns import STRONG
from src.thread import signals as sig
from src.verifiers.rows import SEVERITIES, clean_domain, consistent_row, contradiction_row, unchecked_row

VERIFIER = "thread"
THREAD_RULES_VERSION = "0.1"
THREAD_VERSION_LOG = [
    ("0.1", "First version: rules written from master document Sections 4.3 and 6.4 and the Phase 3, 7 and 8 notes. Fixed numbers: the Phase 6 "
            "thresholds, a quotation of 20 words matched by 30% of its 5-word shingles, a person identified by 5 letters of name or local part. "
            "Severities are initial labels. No real thread had been read"),
]

# Rule id -> (claim type or signal, reads authentication, one-line meaning). No thread rule reads authentication: on list mail it
# belongs to the list (auth_state 'list_relayed'), and the sending-path rules compare the author's own server and program instead.
RULES = {
    "tv_onset_one": ("tactic_onset", False, "one tactic starts in this message that no earlier message had"),
    "tv_onset_many": ("tactic_onset", False, "two or more tactics start together in this message"),
    "tv_onset_steady": ("tactic_onset", False, "no tactic starts here that was absent before"),
    "tv_onset_no_history": ("tactic_onset", False, "fewer than two earlier messages with tactic probabilities"),
    "tv_bank_changed": ("request_drift", False, "bank details that differ from earlier details of the same kind"),
    "tv_bank_new": ("request_drift", False, "bank details in a thread that had none of this kind"),
    "tv_bank_seen": ("request_drift", False, "bank details the thread already used"),
    "tv_req_credential_new": ("credential_request", False, "the first request for login details in the thread"),
    "tv_req_gift_card_new": ("gift_card", False, "the first gift-card request in the thread"),
    "tv_req_change_new": ("payment_change", False, "the first announcement of new payment details in the thread"),
    "tv_req_payment_new": ("payment_request", False, "the first payment request in the thread"),
    "tv_req_data_new": ("data_request", False, "the first request for personal or company data in the thread"),
    "tv_req_seen": ("any request", False, "an earlier message made a request of the same type"),
    "tv_req_no_history": ("any request", False, "no earlier messages, or the claims of the thread are missing"),
    "tv_who_lookalike": ("sending_path", False, "an earlier sender's name from a look-alike of that sender's domain"),
    "tv_who_suffix": ("sending_path", False, "an earlier sender's name from the same domain name under another suffix"),
    "tv_who_other_domain": ("sending_path", False, "an earlier sender's name from an unrelated domain"),
    "tv_who_same_domain": ("sending_path", False, "the same person at another address of the same domain"),
    "tv_who_same_address": ("sending_path", False, "an earlier message came from this address"),
    "tv_who_new_sender": ("sending_path", False, "nobody who wrote earlier looks like this sender"),
    "tv_who_no_from": ("sending_path", False, "no usable From address"),
    "tv_path_origin_mailer": ("sending_path", False, "the same address from a new server and a new mail program"),
    "tv_path_origin": ("sending_path", False, "the same address from a new server"),
    "tv_path_mailer": ("sending_path", False, "the same address with a new mail program"),
    "tv_path_same": ("sending_path", False, "the same address from a known server and mail program"),
    "tv_path_no_data": ("sending_path", False, "no server or mail program to compare with"),
    "tv_int_ids_unknown": ("thread_integrity", False, "In-Reply-To and References name no message of the thread"),
    "tv_int_parent_missing": ("thread_integrity", False, "In-Reply-To names a message not in the thread, References name known ones"),
    "tv_int_ids_ok": ("thread_integrity", False, "the message answers a message of the thread"),
    "tv_int_no_ids": ("thread_integrity", False, "no IDs to compare (none named, or the thread has no Message-IDs)"),
    "tv_quote_mismatch": ("thread_integrity", False, "the quoted history is not what the earlier messages said"),
    "tv_quote_ok": ("thread_integrity", False, "the quoted history matches the earlier messages"),
    "tv_quote_none": ("thread_integrity", False, "no quotation long enough to compare"),
    "tv_prior_ok": ("prior_relationship", False, "an earlier message in the thread came from this sender"),
    "tv_prior_other_address": ("prior_relationship", False, "the sender who wrote earlier used another domain"),
    "tv_prior_stranger": ("prior_relationship", False, "this sender wrote none of the earlier messages of a longer thread"),
    "tv_prior_few": ("prior_relationship", False, "only one earlier message, which cannot show a conversation"),
    "tv_prior_no_thread": ("prior_relationship", False, "no earlier messages"),
    "tv_prior_no_from": ("prior_relationship", False, "no usable From address"),
    "tv_single_no_reply_ids": ("single_email", False, "a reply with quoted history but no In-Reply-To or References"),
    "tv_single_ids_present": ("single_email", False, "a reply that carries reply headers"),
    "tv_single_not_reply": ("single_email", False, "not a reply"),
    "tv_single_no_quote": ("single_email", False, "a reply without quoted history to check"),
}
# The rules that can produce a contradiction (the others give 'consistent' or 'not checkable'); build.py reports which ones never fire.
CONTRADICTION_RULES = frozenset({
    "tv_onset_one", "tv_onset_many", "tv_bank_changed", "tv_bank_new", "tv_req_credential_new", "tv_req_gift_card_new", "tv_req_change_new",
    "tv_req_payment_new", "tv_req_data_new", "tv_who_lookalike", "tv_who_suffix", "tv_who_other_domain", "tv_path_origin_mailer", "tv_path_origin",
    "tv_path_mailer", "tv_int_ids_unknown", "tv_int_parent_missing", "tv_quote_mismatch", "tv_prior_other_address", "tv_prior_stranger",
    "tv_single_no_reply_ids",
})
REQUEST_RULE = {"credential_request": "tv_req_credential_new", "gift_card": "tv_req_gift_card_new", "payment_change": "tv_req_change_new",
                "payment_request": "tv_req_payment_new", "data_request": "tv_req_data_new"}
REQUEST_SEVERITY = {"credential_request": "medium", "gift_card": "medium", "payment_change": "medium",
                    "payment_request": "low", "data_request": "low"}
ASKS = {"credential_request": "asks for login details", "gift_card": "asks for gift cards", "payment_change": "announces new payment details",
        "payment_request": "asks for a payment", "data_request": "asks for personal or company data"}
FLIP_SEVERITIES = ("medium", "high")


def signal(name):
    """The claim-shaped stand-in for a row that is about the thread, not about one claim in the text."""
    return {"claim_id": "thread", "type": name, "confidence": STRONG}


def pct(value):
    return "%.2f" % value


# ---------------------------------------------------------------------------------------------------- signal rows

def onset_row(earlier, me, thresholds):
    claim = signal("tactic_onset")
    m = sig.tactic_onset(earlier, me, thresholds)
    if not m["checkable"]:
        why = ("The message has no tactic probabilities." if m["why"] == "no_probabilities"
               else "Fewer than two earlier messages have tactic probabilities, so there is no pattern to compare with.")
        return unchecked_row(VERIFIER, claim, "tv_onset_no_history", why, {"why": m["why"]})
    new = m["new"]
    if not new:
        return consistent_row(VERIFIER, claim, "tv_onset_steady",
                              "No tactic reaches its threshold here that was below it in every earlier message.", {"new": []})
    evidence = {"new": new}
    for tactic in new:
        evidence["p_" + tactic], evidence["earlier_max_" + tactic] = m["probs"][tactic], m["earlier_max"][tactic]
    detail = ", ".join("%s %s (highest earlier %s)" % (t, pct(m["probs"][t]), pct(m["earlier_max"][t])) for t in new)
    rule, severity = ("tv_onset_one", "medium") if len(new) == 1 else ("tv_onset_many", "high")
    return contradiction_row(VERIFIER, claim, rule, severity,
                             "Manipulation starts in this message: %s. No earlier message in the thread reached that level." % detail, evidence)


def bank_row(earlier, me):
    d = sig.bank_drift(earlier, me)
    if not d["has_details"]:
        return None
    claim = signal("request_drift")
    evidence = {"changed": d["changed"], "new": d["new"], "seen": d["seen"], "details": d["masked"]}
    shown = ", ".join(d["masked"])
    if d["changed"]:
        return contradiction_row(VERIFIER, claim, "tv_bank_changed", "high",
                                 "Gives bank details (%s) that differ from the %s details the thread used before." % (shown, "/".join(d["changed"])), evidence)
    if d["new"]:
        return contradiction_row(VERIFIER, claim, "tv_bank_new", "medium",
                                 "Gives bank details (%s) of a kind that no earlier message in the thread mentioned." % shown, evidence)
    return consistent_row(VERIFIER, claim, "tv_bank_seen", "The bank details (%s) are the ones the thread already used." % shown, evidence)


def who_row(earlier, me):
    """The sender compared with the earlier senders. Also returns the status, so the caller knows whether to compare paths."""
    claim = signal("sending_path")
    s = sig.sender_identity(earlier, me)
    status, mine, theirs = s["status"], clean_domain(me.get("from_domain")), clean_domain(s.get("earlier_domain"))
    evidence = {"status": status, "from_domain": mine, "earlier_domain": theirs}
    if status == "no_from":
        return unchecked_row(VERIFIER, claim, "tv_who_no_from", "The message has no usable From address.", evidence), status
    if status == "same_address":
        return consistent_row(VERIFIER, claim, "tv_who_same_address", "An earlier message in the thread came from this same address.", evidence), status
    if status == "same_domain":
        return consistent_row(VERIFIER, claim, "tv_who_same_domain", "The same person wrote earlier from another address at %s." % mine, evidence), status
    if status == "lookalike":
        return contradiction_row(VERIFIER, claim, "tv_who_lookalike", "high",
                                 "Writes under the name of an earlier sender, but from %s, a look-alike of the %s that sender used before." % (mine, theirs), evidence), status
    if status == "suffix":
        return contradiction_row(VERIFIER, claim, "tv_who_suffix", "medium",
                                 "Writes under the name of an earlier sender, but from %s, the same name as the %s that sender used before under another suffix." % (mine, theirs), evidence), status
    if status == "other_domain":
        return contradiction_row(VERIFIER, claim, "tv_who_other_domain", "low",
                                 "Writes under the name of an earlier sender, but from %s, unrelated to the %s that sender used before." % (mine, theirs), evidence), status
    return unchecked_row(VERIFIER, claim, "tv_who_new_sender", "Nobody who wrote earlier looks like this sender, so there is no earlier sending path to compare with.", evidence), status


def path_row(earlier, me):
    claim = signal("sending_path")
    d = sig.path_drift(earlier, me)
    if not d["checkable"]:
        return unchecked_row(VERIFIER, claim, "tv_path_no_data", "No server address or mail program is known for this address in both this message and an earlier one.", {})
    evidence = {"new_ip": d["new_ip"], "new_mailer": d["new_mailer"], "ip_compared": d["ip_compared"], "mailer_compared": d["mailer_compared"]}
    if d["new_ip"] and d["new_mailer"]:
        return contradiction_row(VERIFIER, claim, "tv_path_origin_mailer", "medium",
                                 "The same address now writes from a server and a mail program it never used earlier in the thread.", evidence)
    if d["new_ip"]:
        return contradiction_row(VERIFIER, claim, "tv_path_origin", "low", "The same address now writes from a server it never used earlier in the thread.", evidence)
    if d["new_mailer"]:
        return contradiction_row(VERIFIER, claim, "tv_path_mailer", "low", "The same address now writes with a mail program it never used earlier in the thread.", evidence)
    return consistent_row(VERIFIER, claim, "tv_path_same", "The same address writes from a server and mail program it used earlier in the thread.", evidence)


def ids_row(earlier, me):
    claim = signal("thread_integrity")
    d = sig.id_integrity(earlier, me)
    if not d["checkable"]:
        return unchecked_row(VERIFIER, claim, "tv_int_no_ids", "The message names no earlier message, or the thread has no Message-IDs to compare with.",
                             {"named": d["named"], "history_ids": d["history_ids"]})
    evidence = {"parent_found": d["parent_found"], "known": d["known"], "total": d["total"]}
    if d["known"] == 0:
        return contradiction_row(VERIFIER, claim, "tv_int_ids_unknown", "medium",
                                 "Says it answers %d message(s), but none of them is a message of this thread." % d["total"], evidence)
    if d["parent_found"] is False:
        return contradiction_row(VERIFIER, claim, "tv_int_parent_missing", "low",
                                 "The message it replies to directly is not in the thread, although %d of the %d messages it names are." % (d["known"], d["total"]), evidence)
    return consistent_row(VERIFIER, claim, "tv_int_ids_ok", "The message answers a message of the thread (%d of %d named messages are in it)." % (d["known"], d["total"]), evidence)


def quote_row(earlier, me):
    claim = signal("thread_integrity")
    words, share = sig.quote_integrity(earlier, me)
    if share is None:
        return unchecked_row(VERIFIER, claim, "tv_quote_none", "No quoted history of 20 words or more to compare with the earlier messages.", {"quoted_words": words})
    evidence = {"quoted_words": words, "match_share": round(share, 2)}
    if share < sig.QUOTE_MATCH_MIN:
        return contradiction_row(VERIFIER, claim, "tv_quote_mismatch", "high",
                                 "Quotes %d words of earlier conversation, but only %d%% of it appears in the earlier messages of the thread." % (words, round(100 * share)), evidence)
    return consistent_row(VERIFIER, claim, "tv_quote_ok", "The quoted history matches the earlier messages (%d%% of its word runs appear in them)." % round(100 * share), evidence)


def single_rows(me):
    """The one rule that needs no history: a reply that carries no reply headers."""
    claim = signal("single_email")
    if not sig.is_reply_subject(me.get("subject")):
        return [unchecked_row(VERIFIER, claim, "tv_single_not_reply", "The subject does not start with Re:, so this is not presented as a reply.", {})]
    words = len(sig.words_of(me.get("quoted") or ""))
    if words < sig.MIN_QUOTE_WORDS:
        return [unchecked_row(VERIFIER, claim, "tv_single_no_quote", "A reply without quoted history of 20 words or more: nothing to check.", {"quoted_words": words})]
    if sig.reply_ids(me):
        return [consistent_row(VERIFIER, claim, "tv_single_ids_present", "A reply with quoted history that carries In-Reply-To or References.", {"quoted_words": words})]
    return [contradiction_row(VERIFIER, claim, "tv_single_no_reply_ids", "low",
                              "Presented as a reply with %d words of quoted history, but carries no In-Reply-To or References header." % words, {"quoted_words": words})]


def signal_rows(earlier, me, thresholds=None):
    """The rows about the thread itself (no claim needed): tactic onset, request drift in bank details, sender and path, integrity."""
    if not earlier:
        return single_rows(me)
    rows = [onset_row(earlier, me, thresholds)]
    bank = bank_row(earlier, me)
    if bank is not None:
        rows.append(bank)
    who, status = who_row(earlier, me)
    rows.append(who)
    if status == "same_address":
        rows.append(path_row(earlier, me))
    rows += [ids_row(earlier, me), quote_row(earlier, me)]
    return rows


# ---------------------------------------------------------------------------------------------------- claim rows

def prior_row(claim, earlier, me):
    """A prior_relationship claim ('as we discussed on the call'): did this sender take part earlier in the thread?

    A thread cannot disprove a call that happened outside it, so the strongest answer is a low contradiction: the claim
    sits oddly in a longer thread in which this sender wrote nothing."""
    if not earlier:
        return unchecked_row(VERIFIER, claim, "tv_prior_no_thread", "Claims an earlier conversation, but there are no earlier messages to check it against.", {"earlier": 0})
    s = sig.sender_identity(earlier, me)
    status = s["status"]
    evidence = {"status": status, "earlier_messages": len(earlier)}
    if status == "no_from":
        return unchecked_row(VERIFIER, claim, "tv_prior_no_from", "Claims an earlier conversation, but the message has no usable From address.", evidence)
    if status in ("same_address", "same_domain"):
        return consistent_row(VERIFIER, claim, "tv_prior_ok", "Claims an earlier conversation, and an earlier message of the thread came from this sender.", evidence)
    if status in ("lookalike", "suffix", "other_domain"):
        return contradiction_row(VERIFIER, claim, "tv_prior_other_address", "low",
                                 "Claims an earlier conversation, but the sender who wrote earlier in the thread used the domain %s, not %s." % (
                                     clean_domain(s.get("earlier_domain")), clean_domain(me.get("from_domain"))), evidence)
    if len(earlier) < 2:
        return unchecked_row(VERIFIER, claim, "tv_prior_few", "Claims an earlier conversation, but the thread has only one earlier message, which shows no conversation.", evidence)
    return contradiction_row(VERIFIER, claim, "tv_prior_stranger", "low",
                             "Claims an earlier conversation, but this sender wrote none of the %d earlier messages in the thread. A call outside the thread cannot be checked." % len(earlier), evidence)


def request_row(claim, earlier, me):
    """A request claim compared with the requests earlier in the thread: is it the first of its type?"""
    novelty = sig.request_novelty(earlier, dict(me, claims=me.get("claims") if me.get("claims") is not None else [claim]))
    kind = claim.get("type")
    if novelty is None:
        return unchecked_row(VERIFIER, claim, "tv_req_no_history", "No earlier messages, or the claims of the earlier messages are missing, so request drift cannot be checked.", {})
    if novelty.get(kind):
        return contradiction_row(VERIFIER, claim, REQUEST_RULE[kind], REQUEST_SEVERITY[kind],
                                 "This message %s; no earlier message in the thread made a request of this type." % ASKS[kind], {"first_in_thread": True})
    return consistent_row(VERIFIER, claim, "tv_req_seen", "An earlier message in the thread already made a request of this type.", {"first_in_thread": False})


def claim_row(claim, earlier, me):
    """The thread verifier's row for one claim, or None if the claim is not routed to it."""
    kind = claim.get("type")
    if kind == "prior_relationship":
        return prior_row(claim, earlier, me)
    if kind in REQUEST_RULE:
        return request_row(claim, earlier, me)
    return None


def claim_rows(earlier, me):
    return [row for row in (claim_row(c, earlier, me) for c in (me.get("claims") or [])) if row is not None]


# -------------------------------------------------------------------------------------------- one message, a thread

def split_thread(messages, index):
    """(earlier messages, the message) for messages[index], with at most 49 earlier messages."""
    messages = messages[:sig.MAX_MESSAGES]
    if not 0 <= index < len(messages):
        raise IndexError("index %d is outside the thread of %d messages" % (index, len(messages)))
    return messages[max(0, index - (sig.MAX_MESSAGES - 1)):index], messages[index]


def verify_thread_message(messages, index, thresholds=None):
    """All thread-verifier rows for messages[index]: the signal rows plus one row per prior_relationship and request claim."""
    earlier, me = split_thread(messages, index)
    return signal_rows(earlier, me, thresholds) + claim_rows(earlier, me)


def worst_severity(rows):
    """The strongest severity among the contradictions of a list of rows, or None when none is a contradiction."""
    found = [r["severity"] for r in rows if r["contradiction"]]
    return max(found, key=SEVERITIES.index) if found else None


def scan_thread(messages, thresholds=None):
    """Judge every message against its own past. Returns {"flip_index": first message with a medium or high contradiction or None,
    "messages": [{"index", "worst", "rules", "rows"}, ...]}. Message 0 has no past and can only get the single-email rule."""
    messages = messages[:sig.MAX_MESSAGES]
    out, flip = [], None
    for index in range(len(messages)):
        rows = verify_thread_message(messages, index, thresholds)
        worst = worst_severity(rows)
        out.append({"index": index, "worst": worst, "rules": [r["rule"] for r in rows if r["contradiction"]], "rows": rows})
        if flip is None and index >= 1 and worst in FLIP_SEVERITIES:
            flip = index
    return {"flip_index": flip, "messages": out}
