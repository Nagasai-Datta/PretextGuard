"""Phase 9: rebuild real threads from raw Enron and from the Apache mailing lists.

    from src.thread.builder import enron_threads, apache_threads, split_message, normalise_subject

A thread is a list of message dictionaries in time order (the fields are described in src/thread/signals.py). This file
makes them. build.py runs it over the real data and saves data/processed/threads.parquet.

TWO WAYS TO FIND A THREAD
Apache keeps the headers mail programs use to thread a conversation, so its threads are rebuilt exactly as a mail program
does it:
    Message-ID     the name of one message, "<abc123@host>"
    In-Reply-To    the Message-ID of the message this one answers
    References     the Message-IDs of ALL its ancestors, oldest first
Messages that name each other are one thread (a union-find: two messages join a group when one names the other, and groups
join transitively, so a cycle or a missing parent cannot break anything).

Raw Enron has none of these headers (0% In-Reply-To, References, Received or X-Mailer, results/header_coverage.csv), so its
threads are guessed from what is left, the way old mail clients did:
    1. the subject with every "Re:" / "Fw:" prefix removed ("RE: Re: Budget" and "Budget" are one conversation);
    2. messages of one subject are cut into runs: a gap of more than 14 days starts a new run (the weekly "Update" mail);
    3. inside a run, two messages join when they share a participant (the sender or a To address);
    4. a thread needs at least 3 distinct messages, at least 2 senders, at least 2 reply-prefixed subjects, and at most
       50 messages (a bigger group is an announcement list, not a conversation).
Every message of Enron also exists in several folders (inbox, all_documents, sent ...) and the copies carry different Message-IDs, so a copy is
recognised by the same date, sender and subject.

THE TEXT OF A MESSAGE. split_message cuts a body exactly as Phase 2 does (HTML to text, list footer off, quoted history off)
and keeps BOTH halves: `text` is what the sender wrote new, `quoted` is the history the message quotes. The thread
verifier needs the quotation (it checks it against the earlier messages), which Phase 2 threw away.

SPLITS. A thread is the unit of the benchmark split, so no thread straddles train, validation and test: the split of a thread
comes from the SHA-256 of the seed and the thread id (70/15/15), the same method as Phase 1.

Security. Everything read here is attacker-written: files are read up to 300,000 bytes, a Subject is cut at 300 characters before
its prefixes are removed (a subject of 100,000 'Re:' cannot make the loop long), a thread has at most 50 messages and each text
at most 200,000 characters, and no regular expression runs over email text here. Attachments are never decoded.
"""

import email
import hashlib
import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import getaddresses

from src.headers.evidence import header_evidence
from src.headers.parser import body_text, parse_header_fields, split_headers
from src.preprocess.clean import MAX_BODY_CHARS, QUOTE_MARKERS, html_to_text, looks_like_html, normalise_whitespace, split_quoted, strip_list_footer
from src.preprocess.redact import redact
from src.thread.signals import MAX_MESSAGES
from src.verifiers.facts import FACT_KEYS

SEED = 42
MIN_THREAD = 3               # messages
MIN_SENDERS = 2              # different From addresses
MIN_REPLIES = 2              # Enron: subjects that start with a reply prefix
GAP_DAYS = 14                # Enron: a longer gap between two messages of one subject starts a new run
MAX_FILE_BYTES = 300_000     # bytes read from one raw file
MAX_SUBJECT_CHARS = 300
MAX_PREFIXES = 20            # reply prefixes removed from one subject
MAX_PARTICIPANTS = 20        # To addresses read per message
MAX_QUOTED_CHARS = 20_000    # the quoted history is kept up to this length
MAX_FULL_CHARS = 60_000      # the whole cleaned body is kept up to this length (the thread code reads no more than that)
PREFIXES = ("re", "fw", "fwd", "aw", "sv", "antw")


# ----------------------------------------------------------------------------------------------- text of a message

def split_message(raw_body):
    """{'text', 'quoted', 'full'} of one raw body.

    text    the new text, cut exactly as Phase 2 cuts it (everything before the first quote marker, minus lines starting with '>')
    quoted  the quotation proper: the lines marked with '>' and, when the first marker is an Outlook-style one ("-----Original Message-----",
            "From: ... Sent:", a forward), everything after that marker. After a Gmail or Thunderbird "On ... wrote:" line only the '>' lines
            count: people answer INLINE there, and their own answers between the quoted paragraphs are not quoted history
    full    the whole cleaned body, new text and quotation together: what a LATER reply may quote from this message (an inline answer
            written here is quoted back by the next reply, so the pool a quotation is compared with must hold it)
    """
    raw = raw_body.replace("\r\n", "\n").replace("\r", "\n")[:MAX_BODY_CHARS] if isinstance(raw_body, str) else ""
    text = html_to_text(raw)[0] if looks_like_html(raw) else html.unescape(raw)
    text, _ = strip_list_footer(text)
    main, _ = split_quoted(text)
    first = None
    for marker in QUOTE_MARKERS:
        found = marker.search(text)
        if found and (first is None or found.start() < first[0]):
            first = (found.start(), marker)
    parts = [line.lstrip().lstrip("> \t") for line in text.split("\n") if line.lstrip().startswith(">")]
    if first is not None and "wrote" not in first[1].pattern:        # Outlook style: no '>' marks, the history is everything after the marker
        parts.append(text[first[0]:])
    return {"text": normalise_whitespace(main), "quoted": " ".join(" ".join(parts).split())[:MAX_QUOTED_CHARS], "full": " ".join(text.split())[:MAX_FULL_CHARS]}


def strip_prefix(text):
    """(text without one leading reply prefix, True) or (text, False). Handles 're:', 'RE :', 'Re[2]:' and the other languages' forms."""
    lowered = text.lower()
    for prefix in PREFIXES:
        if not lowered.startswith(prefix):
            continue
        rest = text[len(prefix):].lstrip()
        if rest.startswith("["):
            end = rest.find("]")
            if 0 < end <= 6 and rest[1:end].isdigit():
                rest = rest[end + 1:].lstrip()
        if rest.startswith(":"):
            return rest[1:].lstrip(), True
    return text, False


def normalise_subject(subject):
    """The subject without its reply prefixes, lower case, one line: 'RE: Re: Budget  plan' -> 'budget plan'."""
    text = " ".join(str(subject or "").split())[:MAX_SUBJECT_CHARS]
    for _ in range(MAX_PREFIXES):
        text, removed = strip_prefix(text)
        if not removed:
            break
    return text.lower()


def has_reply_prefix(subject):
    return strip_prefix(" ".join(str(subject or "").split())[:MAX_SUBJECT_CHARS])[1]


# ---------------------------------------------------------------------------------------------------- thread ids

def thread_id(source, first_key):
    """A short stable name for a thread: the source and 12 hex characters of the SHA-256 of its first message's key."""
    return "%s_%s" % (source, hashlib.sha256(first_key.encode("utf-8")).hexdigest()[:12])


def hash_order(text):
    """A fixed pseudo-random sort key for a text: the SHA-256 of the seed and the text. Sorting by it picks the same items on every machine."""
    return hashlib.sha256(("%d|order|%s" % (SEED, text)).encode("utf-8")).hexdigest()


def split_of_thread(tid):
    """train / validation / test for a whole thread (70/15/15), fixed by the seed and the thread id."""
    bucket = int(hashlib.sha256(("%d|thread-split|%s" % (SEED, tid)).encode("utf-8")).hexdigest(), 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def timestamp(iso):
    """Seconds since 1970 (UTC) for an ISO date with or without a time zone, or None."""
    try:
        moment = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


# --------------------------------------------------------------------------------------------- the message record

def json_safe(value):
    """A plain Python value for a table cell: numpy and pandas scalars become ints, floats, bools; missing values become None."""
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict, str)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and value != value:
        return None
    if type(value).__name__ in ("NAType", "NaTType"):
        return None
    return value


def message_record(key, source, fields, evidence, body_raw):
    """One message dictionary from parsed header fields, header evidence and a raw body (the shape of src/thread/signals.py).

    `facts` keeps the header evidence the Phase 8 verifiers read (FACT_KEYS), so the benchmark can ask 'what would N3 have said?'."""
    parts = split_message(body_raw)
    merged = {**fields, **evidence}
    date = fields.get("date")
    references = decode_references(fields.get("references"))
    return {
        "key": key, "source": source,
        "message_id": fields.get("message_id"), "in_reply_to": fields.get("in_reply_to"), "references": references,
        "from_addr": fields.get("from_addr"), "from_name": fields.get("from_name"), "from_domain": evidence.get("from_registered_domain"),
        "subject": fields.get("subject") or "", "date": date.isoformat() if hasattr(date, "isoformat") else (date or None),
        "origin_ip": evidence.get("origin_ip"), "mailer": fields.get("mailer"), "received_hops": json_safe(evidence.get("received_hops")),
        "list_mail": bool(evidence.get("list_mail")),
        "text": parts["text"], "quoted": parts["quoted"], "full": parts["full"], "redacted": redact(parts["text"])[0],
        "facts": {k: json_safe(merged.get(k)) for k in FACT_KEYS},
        "tactics": None, "claims": None,
    }


def record_from_table(key, source, header, body_raw):
    """A message record from a row of headers.parquet (parsed in Phase 3; `header` is a dict) and the raw body from staged.parquet.

    Used for Apache: the headers were parsed once, in Phase 3, and are not parsed again."""
    parts = split_message(body_raw)
    references = decode_references(header.get("references"))
    return {
        "key": key, "source": source,
        "message_id": json_safe(header.get("message_id")), "in_reply_to": json_safe(header.get("in_reply_to")), "references": references,
        "from_addr": json_safe(header.get("from_addr")), "from_name": json_safe(header.get("from_name")),
        "from_domain": json_safe(header.get("from_registered_domain")), "subject": json_safe(header.get("subject")) or "",
        "date": json_safe(header.get("date")), "origin_ip": json_safe(header.get("origin_ip")), "mailer": json_safe(header.get("mailer")),
        "received_hops": json_safe(header.get("received_hops")), "list_mail": bool(json_safe(header.get("list_mail"))),
        "text": parts["text"], "quoted": parts["quoted"], "full": parts["full"], "redacted": redact(parts["text"])[0],
        "facts": {k: json_safe(header.get(k)) for k in FACT_KEYS},
        "tactics": None, "claims": None,
    }


def decode_references(value):
    """The list of Message-IDs from a table cell, at most 100.

    Three forms occur: the space-separated string Phase 3 writes to headers.parquet ("<a@x> <b@y>"; a Message-ID holds no space), the
    JSON list that threads.parquet uses, and nothing at all (None or NaN). A list or array is accepted as it is."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                value = json.loads(text)
            except ValueError:
                return []
        else:
            value = text.split()
    if value is None or isinstance(value, (str, dict)) or not hasattr(value, "__len__"):
        return []
    return [str(r) for r in value][:100]


def table_to_threads(table):
    """{thread_id: list of message dictionaries in order} from rows of threads.parquet (facts decoded; tactics and claims still None)."""
    out = defaultdict(list)
    for row in table.sort_values(["thread_id", "position"]).to_dict("records"):
        m = dict(row)
        m["facts"] = json.loads(m["facts"]) if isinstance(m["facts"], str) else m["facts"]
        m["references"] = decode_references(m.get("references"))
        for key in ("message_id", "in_reply_to", "from_addr", "from_name", "from_domain", "origin_ip", "mailer", "date", "received_hops"):
            m[key] = json_safe(m.get(key))
        m["list_mail"] = bool(json_safe(m.get("list_mail")))
        m["tactics"] = m["claims"] = None
        out[m["thread_id"]].append(m)
    return out


# ------------------------------------------------------------------------------------------------- union-find

class Groups:
    """Union-find over 0..n-1: join(i, j) puts two items in one group; roots() lists the groups. Iterative, so it cannot recurse deeply."""

    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, i, j):
        self.parent[self.find(i)] = self.find(j)

    def groups(self):
        out = {}
        for i in range(len(self.parent)):
            out.setdefault(self.find(i), []).append(i)
        return list(out.values())


def order_messages(messages):
    """Messages in time order (date, then key). Messages without a usable date are left out; returns (ordered, number left out)."""
    dated = [(timestamp(m["date"]), m["key"], m) for m in messages]
    kept = sorted((d for d in dated if d[0] is not None), key=lambda d: (d[0], d[1]))
    return [m for _, _, m in kept], len(dated) - len(kept)


# --------------------------------------------------------------------------------------------------------- Apache

def apache_threads(messages):
    """Threads of Apache list mail from Message-ID, In-Reply-To and References. messages: records from message_record.

    Returns (threads, counts) where counts says how many candidate groups were dropped and why."""
    index = {}
    for i, m in enumerate(messages):
        if m["message_id"] and m["message_id"] not in index:
            index[m["message_id"]] = i
    groups = Groups(len(messages))
    for i, m in enumerate(messages):
        for ref in ([m["in_reply_to"]] if m["in_reply_to"] else []) + list(m["references"]):
            j = index.get(ref)
            if j is not None and j != i:
                groups.join(i, j)
    return finish_threads(messages, groups.groups(), "apache", require_replies=False)


def finish_threads(messages, groups, label, require_replies):
    threads, counts = [], {"groups": len(groups), "single": 0, "too_short": 0, "too_long": 0, "one_sender": 0, "few_replies": 0, "no_date": 0, "kept": 0}
    for members in groups:
        if len(members) < 2:
            counts["single"] += 1
            continue
        ordered, undated = order_messages([messages[i] for i in members])
        counts["no_date"] += undated
        if len(ordered) < MIN_THREAD:
            counts["too_short"] += 1
        elif len(ordered) > MAX_MESSAGES:
            counts["too_long"] += 1
        elif len({m["from_addr"] for m in ordered if m["from_addr"]}) < MIN_SENDERS:
            counts["one_sender"] += 1
        elif require_replies and sum(has_reply_prefix(m["subject"]) for m in ordered) < MIN_REPLIES:
            counts["few_replies"] += 1
        else:
            tid = thread_id(label, ordered[0]["key"])
            for position, m in enumerate(ordered):
                m["thread_id"], m["position"] = tid, position
            threads.append(ordered)
            counts["kept"] += 1
    return threads, counts


# --------------------------------------------------------------------------------------------------------- Enron

def enron_index_row(path, relative_key):
    """One row for the Enron index: only what grouping needs (read from the first 8,000 bytes of the file)."""
    with open(path, "rb") as handle:
        head = handle.read(8000)
    block = split_headers(head)
    fields, _ = parse_header_fields(block)
    message = email.message_from_string(block + "\n\n")
    people = []
    for _, address in getaddresses([str(v) for v in message.get_all("To", [])[:3]])[:MAX_PARTICIPANTS]:
        if address and "@" in address:
            people.append(address.lower())
    date = fields.get("date")
    return {"key": relative_key, "message_id": fields.get("message_id"), "date": date.isoformat() if date is not None else None,
            "from_addr": fields.get("from_addr"), "subject": fields.get("subject") or "", "people": people}


def enron_candidates(index_rows):
    """Candidate Enron threads from index rows: lists of row dictionaries (copies of one message removed first).

    Returns (candidates, counts)."""
    seen, rows = set(), []
    for row in index_rows:
        # The same message sits in several folders (inbox, sent, all_documents ...). In this dump the copies carry DIFFERENT Message-IDs
        # (the first real run found 517,432 files and 517,432 distinct IDs), so a copy is recognised by what one message cannot have twice:
        # the same second, the same sender and the same subject.
        copy = (row["date"], row["from_addr"], row["subject"]) if row["date"] and row["from_addr"] else None
        if copy is not None:
            if copy in seen:
                continue
            seen.add(copy)
        rows.append(row)
    counts = {"files": len(index_rows), "distinct_messages": len(rows), "subject_groups": 0, "runs": 0, "candidates": 0}
    by_subject = {}
    for row in rows:
        subject = normalise_subject(row["subject"])
        if len(subject) >= 4 and timestamp(row["date"]) is not None:
            by_subject.setdefault(subject, []).append(row)
    counts["subject_groups"] = len(by_subject)
    candidates = []
    for subject, members in by_subject.items():
        members.sort(key=lambda r: (timestamp(r["date"]), r["key"]))
        runs, current = [], [members[0]]
        for row in members[1:]:
            if timestamp(row["date"]) - timestamp(current[-1]["date"]) > GAP_DAYS * 86400:
                runs.append(current)
                current = []
            current.append(row)
        runs.append(current)
        for run in runs:
            counts["runs"] += 1
            if len(run) < MIN_THREAD or len(run) > MAX_MESSAGES:
                continue
            groups, first_seen = Groups(len(run)), {}
            for i, row in enumerate(run):
                for person in ([row["from_addr"]] if row["from_addr"] else []) + list(row["people"]):
                    if person in first_seen:
                        groups.join(i, first_seen[person])
                    else:
                        first_seen[person] = i
            for members_of in groups.groups():
                if MIN_THREAD <= len(members_of) <= MAX_MESSAGES:
                    candidates.append([run[i] for i in members_of])
    counts["candidates"] = len(candidates)
    return candidates, counts


def read_enron_message(path, key, source="enron"):
    """The full message record of one raw Enron file (headers, evidence, text), or None when it cannot be read."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES)
    except OSError:
        return None
    fields, _ = parse_header_fields(split_headers(raw))
    evidence = header_evidence(fields, None)          # Enron has no organisation domain use here (internal affiliation is not N2's job)
    return message_record(key, source, fields, evidence, body_text(email.message_from_bytes(raw)))


def enron_threads(candidates, maildir, require_replies=True):
    """Full thread records for the candidate threads (a list of lists of index rows). Reads the files of those messages only."""
    messages, groups = [], []
    for candidate in candidates:
        members = []
        for row in candidate:
            record = read_enron_message(maildir / row["key"], row["key"])
            if record is not None:
                messages.append(record)
                members.append(len(messages) - 1)
        groups.append(members)
    return finish_threads(messages, groups, "enron", require_replies=require_replies)
