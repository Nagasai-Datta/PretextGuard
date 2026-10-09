"""Phase 9: the four measurements of thread verification (N2). They measure; src/verifiers/thread_verifier.py judges.

A thread is a list of messages in time order. To check message i, the verifier looks at message i (`me`) and the messages
before it (`earlier`). Every function here takes those two things and returns plain numbers, sets and words, never a
verdict. That split is deliberate: a measurement can be tested with a hand-made thread and no model, and the rules that
turn measurements into findings (and their severities) live in one other file where they can be read and changed.

A message is a plain dictionary (the builder fills it, the API will fill it the same way):

    key          where the message came from (an id, or a file path)
    message_id   "<abc@host>" or None          in_reply_to   the parent's Message-ID or None
    references   list of Message-IDs           (at most 100 are kept)
    from_addr    lower case address or None    from_name     display name or None
    from_domain  registered domain of From     subject       the Subject text
    origin_ip    first public IP of the Received chain (the author's end) or None
    mailer       X-Mailer or User-Agent text or None
    text         the NEW text of this message (quoted history cut off)     quoted   the history it quotes
    tactics      {tactic: probability} from the Phase 6 classifier or None   claims   the Phase 7 claims or None

THE FOUR SIGNALS (master document Section 4.3), and what each measures
    tactic_onset    a manipulation tactic that crosses its Phase 6 threshold in this message although no earlier message did
    request_drift   bank details in this message that no earlier message had (a set difference), and request types that
                    appear for the first time in the thread
    sending_path    who the sender is compared with the earlier senders (same address, same name at a look-alike domain, ...)
                    and whether the same address now writes from another server or mail program
    integrity       whether In-Reply-To and References name messages that exist in the thread, and whether the history this
                    message quotes is really what the earlier messages said (5-word shingles, see quote_overlap)

Fixed numbers. Every threshold below is a definition, not a tuned value: Phase 6 thresholds for the tactics, 20 words of
quotation and a 30% match for the quote, a 5-word shingle. They were written down before any thread was read and are revised
only after reading TRAIN threads (the version log in thread_verifier.py).

Security. A thread is attacker-written input. At most 50 messages are examined, each text is cut at 60,000 characters and
5,000 words, at most 100 Message-IDs are read per message, and nothing here runs a regular expression over email text:
words are found by walking the characters once, so the cost grows with the length of the input and nothing else. A cyclic
In-Reply-To chain (A replies to B replies to A) cannot loop, because IDs are only looked up in a set, never followed.
"""

from functools import lru_cache

from src.models.dataset import MAIN_TACTICS
from src.verifiers.bank import bank_detail_keys, find_bank_details
from src.verifiers.facts import similar_domain

MAX_MESSAGES = 50            # messages examined in one thread (master document Section 10)
MAX_SCAN_CHARS = 60_000      # characters of one text that are read
MAX_WORDS = 5_000            # words of one text that are kept
MAX_IDS = 100                # Message-IDs read from one message
SHINGLE = 5                  # words in one shingle
MIN_QUOTE_WORDS = 20         # a shorter quotation says too little to compare
QUOTE_MATCH_MIN = 0.30       # below this share of matching shingles the quoted history is not what the thread said
MIN_HISTORY = 2              # earlier messages with tactic probabilities that tactic onset needs
ONSET_JUMP = 0.40            # a tactic starts only if its probability is this much above the average of the earlier messages (0.2: a small crossing is not an onset)
MIN_PERSON_LETTERS = 5       # a name or local part shorter than this is too common to identify a person
MAILER_WORDS = 3             # words of the mail program name that are compared (versions are dropped)

# The Phase 6 thresholds of the four tactics the classifier learned from real emails (artifacts/tactic_model/thresholds.json;
# results/tactic_validation_scores.csv). The other three tactics have fewer than 10 real positives and are never used here.
# build.py passes the real file's numbers; these are for the self-test and for callers that have no model folder.
DEFAULT_THRESHOLDS = {"authority": 0.55, "urgency": 0.45, "scarcity": 0.65, "secrecy": 0.90}
REQUEST_TYPES = ("payment_request", "payment_change", "credential_request", "gift_card", "data_request")


# ---------------------------------------------------------------------------------------------------------------- text

def words_of(text, limit=MAX_WORDS):
    """The lower-case words (runs of letters and digits) of a text, at most `limit`, found by one pass over the characters."""
    if not isinstance(text, str):
        return []
    found, current = [], []
    for ch in text[:MAX_SCAN_CHARS].lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            found.append("".join(current))
            current = []
            if len(found) >= limit:
                return found
    if current and len(found) < limit:
        found.append("".join(current))
    return found


def shingles(words, size=SHINGLE):
    """The set of overlapping runs of `size` words: ['a','b','c','d'] with size 2 gives {'a b', 'b c', 'c d'}."""
    return {" ".join(words[i:i + size]) for i in range(max(0, len(words) - size + 1))}


@lru_cache(maxsize=512)
def text_shingles(text):
    """The shingle set of one text, remembered: scanning a thread compares every message with all earlier ones."""
    return frozenset(shingles(words_of(text)))


def quote_overlap(quoted, earlier_texts):
    """(words in the quotation, share of its shingles found in the earlier texts or None when it cannot be judged).

    Why shingles. A reply quotes the message it answers, often re-wrapped, prefixed with '>' or with a header block in
    front. Comparing whole lines would break on every re-wrap, so both sides are cut into words and every run of five
    words is a shingle. A quotation that really comes from the thread shares almost all of its shingles with the earlier
    messages; a fabricated 'previous conversation' shares almost none. Short quotations (under 20 words) and threads
    with no earlier text cannot be judged and return None.
    """
    quote_words = words_of(quoted)
    if len(quote_words) < MIN_QUOTE_WORDS:
        return len(quote_words), None
    known = set()
    for text in earlier_texts[:2 * MAX_MESSAGES]:
        known |= text_shingles(text)
    mine = shingles(quote_words)
    if not known or not mine:
        return len(quote_words), None
    return len(quote_words), sum(1 for s in mine if s in known) / len(mine)


def letters_only(text):
    """Lower-case letters of a text with everything else removed ('Park, John' -> 'parkjohn')."""
    return "".join(ch for ch in text[:200].lower() if ch.isalpha()) if isinstance(text, str) else ""


def mailer_family(text):
    """The name of a mail program without its version: 'Apple Mail (2.3774.600.62)' -> 'apple mail'; None when empty.

    Versions change on every update, so comparing them would flag a harmless upgrade. The first three words of three or
    more letters are kept."""
    if not isinstance(text, str):
        return None
    tokens, current = [], []
    for ch in text[:200].lower():
        if ch.isalpha():
            current.append(ch)
            continue
        if len(current) >= 3:
            tokens.append("".join(current))
        current = []
        if len(tokens) >= MAILER_WORDS:
            break
    if len(current) >= 3 and len(tokens) < MAILER_WORDS:
        tokens.append("".join(current))
    return " ".join(tokens[:MAILER_WORDS]) or None


# ------------------------------------------------------------------------------------------------ 1. tactic onset

def tactic_onset(earlier, me, thresholds=None):
    """Which of the four main tactics start in this message.

    A tactic 'starts' when (1) its probability reaches that tactic's Phase 6 threshold here, (2) it stayed below the threshold in every
    earlier message and (3) it is at least ONSET_JUMP (0.40) above the AVERAGE of the earlier messages. The third condition was added in
    version 0.2: the first real run showed urgency creeping over its threshold of 0.45 by a hair (0.46 after 0.45) in ordinary business
    mail; an attack jumps (0.1 to 0.9). A thread that was urgent from the start does not start urgency again. Needs at least two earlier
    messages that have tactic probabilities (one message is not a pattern).

    Returns {"checkable": False, "why": ...} or {"checkable": True, "new": [tactics], "probs": {...}, "earlier_mean": {...}}.
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    mine = me.get("tactics")
    if not mine:
        return {"checkable": False, "why": "no_probabilities"}
    before = [m["tactics"] for m in earlier if m.get("tactics")]
    if len(before) < MIN_HISTORY:
        return {"checkable": False, "why": "no_history"}
    new, probs, earlier_mean = [], {}, {}
    for tactic in MAIN_TACTICS:
        p = float(mine.get(tactic, 0.0))
        history = [float(h.get(tactic, 0.0)) for h in before]
        mean = sum(history) / len(history)
        probs[tactic], earlier_mean[tactic] = round(p, 2), round(mean, 2)
        if p >= thresholds[tactic] and all(h < thresholds[tactic] for h in history) and p - mean >= ONSET_JUMP:
            new.append(tactic)
    return {"checkable": True, "new": new, "probs": probs, "earlier_mean": earlier_mean}


# ----------------------------------------------------------------------------------------------- 2. request drift

def pool_text(message):
    """Everything a later reply may quote from a message: its whole cleaned body (`full`), or new text plus quotation when `full` is missing."""
    return message.get("full") or ((message.get("text") or "") + " " + (message.get("quoted") or ""))


def bank_drift(earlier, me):
    """Bank details of this message compared with everything the thread said before (a set difference).

    now - seen = the details nobody in the thread had mentioned. Each detail is a (kind, value) pair from bank.py (an IBAN,
    an account number, a routing or sort number, a SWIFT code). For every detail in this message:
        seen     the same detail appeared before (an invoice repeating the account)
        changed  an earlier message had a DIFFERENT detail of the same kind (the account number changed)
        new      no earlier message had any detail of this kind
    The earlier messages' quoted history counts as 'seen' too, so a thread that starts in the middle does not look new.
    Only the new text of THIS message counts: its own quotation repeats old details by definition.

    Returns {"has_details": bool, "changed": [kinds], "new": [kinds], "seen": [kinds], "masked": [masked values]}.
    """
    now = find_bank_details(me.get("text") or "")
    if not now:
        return {"has_details": False, "changed": [], "new": [], "seen": [], "masked": []}
    seen = set()
    for message in earlier:
        seen |= bank_detail_keys(message.get("text") or "") | bank_detail_keys(message.get("quoted") or "") | bank_detail_keys(pool_text(message))
    changed, new, same = [], [], []
    for detail in now:
        kind, key = detail["kind"], (detail["kind"], detail["value"])
        if key in seen:
            same.append(kind)
        elif any(k == kind for k, _ in seen):
            changed.append(kind)
        else:
            new.append(kind)
    return {"has_details": True, "changed": sorted(set(changed)), "new": sorted(set(new)), "seen": sorted(set(same)),
            "masked": [d["masked"] for d in now][:4]}


def request_novelty(earlier, me):
    """For each request type this message makes, whether it is the first time in the thread.

    Returns None when there is no earlier message or the claims of the thread are missing (the verifier then says
    'not checkable'), else
    {request type: True if no earlier message made a request of the same type}. payment_change counts only against earlier
    payment_change claims: a thread of ordinary payment requests that suddenly announces new details is the hijack pattern.
    """
    if not earlier or me.get("claims") is None or any(m.get("claims") is None for m in earlier):
        return None
    seen = {c.get("type") for m in earlier for c in m["claims"]}
    return {t: t not in seen for t in REQUEST_TYPES if any(c.get("type") == t for c in me["claims"])}


# ---------------------------------------------------------------------------------------------- 3. sending path

def same_person(a, b):
    """True when two messages name the same person: the display names match, or the part of the address before '@' does.

    Both must have at least 5 letters ('Bob' or 'info' would match strangers). It is a clue, not proof: the verifier uses it
    only to ask whether a NEW address or domain belongs to someone who already wrote in the thread."""
    name_a, name_b = letters_only(a.get("from_name")), letters_only(b.get("from_name"))
    if len(name_a) >= MIN_PERSON_LETTERS and name_a == name_b:
        return True
    local_a, local_b = local_part(a), local_part(b)
    return len(local_a) >= MIN_PERSON_LETTERS and local_a == local_b


def local_part(message):
    address = message.get("from_addr")
    return address.split("@")[0] if isinstance(address, str) and "@" in address else ""


def sender_identity(earlier, me):
    """How the sender of this message relates to the earlier senders.

    status is one of
        no_from        the message has no usable From address
        same_address   an earlier message came from this very address
        same_domain    the same person wrote earlier from another address at the same domain
        lookalike      the same person (name or local part) wrote earlier from a look-alike of this domain (paypa1 / paypal)
        suffix         ... from the same name under another suffix (acme.com / acme.co)
        other_domain   ... from an unrelated domain (a work address now, a free mailbox then)
        new_sender     nobody who wrote earlier looks like this sender
    earlier_domain is the domain the strongest match used earlier (for the reason text).
    """
    address = me.get("from_addr")
    if not address:
        return {"status": "no_from"}
    if any(m.get("from_addr") == address for m in earlier):
        return {"status": "same_address"}
    rank = {"lookalike": 3, "suffix": 2, "other_domain": 1, "same_domain": 0}
    best, best_domain = None, None
    for message in earlier:
        if not message.get("from_addr") or not same_person(me, message):
            continue
        relation = similar_domain(me.get("from_domain"), message.get("from_domain"))
        status = {"same": "same_domain", "lookalike": "lookalike", "suffix": "suffix"}.get(relation, "other_domain")
        if best is None or rank[status] > rank[best]:
            best, best_domain = status, message.get("from_domain")
    return {"status": best or "new_sender", "earlier_domain": best_domain}


def network_of(ip):
    """The network of an IP address, so that a rotating address of one provider is not a new server: the first three numbers of an IPv4
    address (a /24) or the first four groups of an IPv6 address (a /64). Anything else is returned unchanged."""
    if not isinstance(ip, str):
        return None
    if "." in ip and ip.count(".") == 3:
        return ".".join(ip.split(".")[:3])
    if ":" in ip:
        return ":".join(ip.split(":")[:4])
    return ip


def path_drift(earlier, me):
    """Whether the same address now writes from a server or mail program it never used before in this thread.

    Compared with the earlier messages from the same address only: the network of the first public IP of the Received chain (the author's
    end; a mailing list's later hops are not used; version 0.2 compares the /24 network, not the exact address, because a provider rotates its
    addresses) and the mail program's name (version dropped). Either can change for a
    harmless reason (a new phone, a trip), so one change alone is weak and both together are stronger.

    Returns {"checkable": False} when there is no earlier message from this address or nothing to compare, else
    {"checkable": True, "new_ip": bool, "new_mailer": bool, "ip_compared": bool, "mailer_compared": bool}.
    """
    address = me.get("from_addr")
    same = [m for m in earlier if address and m.get("from_addr") == address]
    if not same:
        return {"checkable": False}
    ips = {network_of(m["origin_ip"]) for m in same if m.get("origin_ip")}
    families = {f for f in (mailer_family(m.get("mailer")) for m in same) if f}
    my_ip, my_family = network_of(me.get("origin_ip")), mailer_family(me.get("mailer"))
    ip_compared, mailer_compared = bool(my_ip and ips), bool(my_family and families)
    if not (ip_compared or mailer_compared):
        return {"checkable": False}
    return {"checkable": True, "ip_compared": ip_compared, "mailer_compared": mailer_compared,
            "new_ip": bool(ip_compared and my_ip not in ips), "new_mailer": bool(mailer_compared and my_family not in families)}


# ------------------------------------------------------------------------------------------------- 4. integrity

def reply_ids(message):
    """The Message-IDs a message says it answers: In-Reply-To first, then References (at most 100 in all)."""
    ids = []
    for value in [message.get("in_reply_to")] + list(message.get("references") or [])[:MAX_IDS]:
        if isinstance(value, str) and value and value not in ids:
            ids.append(value)
    return ids[:MAX_IDS]


def id_integrity(earlier, me):
    """Do the IDs this message answers belong to messages of the thread?

    Returns {"checkable": False} when the message names no ID or no earlier message has a Message-ID (raw Enron has none),
    else {"checkable": True, "parent_found": True/False/None, "known": ids found, "total": ids named}. parent_found is None
    when the message has References but no In-Reply-To.
    """
    named = reply_ids(me)
    history = {m["message_id"] for m in earlier if m.get("message_id")}
    if not named or not history:
        return {"checkable": False, "named": len(named), "history_ids": len(history)}
    parent = me.get("in_reply_to")
    return {"checkable": True, "parent_found": (parent in history) if parent else None,
            "known": sum(1 for i in named if i in history), "total": len(named)}


def quote_integrity(earlier, me):
    """(words quoted, share of the quotation's shingles found in the earlier messages or None). See quote_overlap.

    The quotation of this message is compared with the WHOLE text of every earlier message, not only with their new text: a reply quotes
    what the earlier message said, and in an inline reply that includes the answers written between the quoted paragraphs."""
    return quote_overlap(me.get("quoted") or "", [pool_text(m) for m in earlier])


def is_forward_subject(subject):
    """True for a subject that starts with 'Fw:' or 'Fwd:' (any case): a forward quotes a message from outside the thread."""
    lowered = subject.lstrip().lower() if isinstance(subject, str) else ""
    return lowered.startswith("fw:") or lowered.startswith("fwd:")


def is_reply_subject(subject):
    """True for a subject that starts with 'Re:' (any case)."""
    return isinstance(subject, str) and subject.lstrip()[:3].lower() == "re:"
