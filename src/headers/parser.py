"""Read emails: split a raw email, decode its body, and parse its header fields.

1. split_headers, decode_part and body_text turn raw email bytes into a header
   block and readable body text. They moved here from src/data/loaders.py in
   Phase 3, so the dataset loaders and, later, the API use one copy.
2. parse_header_fields(header_block) turns a header block into plain fields
   (From, Reply-To, Return-Path, To, Date, Subject, Message-ID, In-Reply-To,
   References, List-Id, Received lines, mailer, authentication headers) for
   evidence.py.

Security: whoever sends an email writes its headers, so attackers control them.
The block is capped at MAX_HEADER_CHARS, at most MAX_RECEIVED Received lines are
kept, every field is parsed on its own (a broken field becomes None and is
counted; the others survive), and every pattern has bounded repeats (no ReDoS).
"""

import email
import email.utils
import re
from email.header import decode_header, make_header

MAX_HEADER_CHARS = 64 * 1024  # a header block longer than this is cut
MAX_RECEIVED = 50             # Received lines kept (a long chain is a warning sign itself)
MAX_FIELD_CHARS = 2000        # a single field longer than this is cut

MESSAGE_ID = re.compile(r"<[^<>\s]{1,250}>")
ANGLE_ADDRESS = re.compile(r"<\s{0,5}([^<>\s@]{1,64}@[^<>\s@]{1,255})\s{0,5}>")  # "<x@evil.ru>"


# ---------- Raw email: header block and body text ----------

def split_headers(raw):
    """Return the header block of a raw email as text: everything before the first blank line."""
    raw = raw.replace(b"\r\n", b"\n")  # Windows line endings -> Unix
    end = raw.find(b"\n\n")
    header_bytes = raw if end == -1 else raw[:end]
    return header_bytes.decode("utf-8", errors="replace")


def decode_part(part):
    """Return one MIME part as text: undo base64 or quoted-printable, then its character set."""
    payload = part.get_payload(decode=True)  # bytes, with the transfer encoding already undone
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):  # unknown or broken charset name, such as "x-unknown"
        return payload.decode("utf-8", errors="replace")


def body_text(message):
    """Return an email's text/plain parts, or its text/html parts if it has no plain text."""
    plain, html = [], []
    for part in message.walk():
        # Containers (multipart/...) hold no text themselves; attachments are never read.
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain.append(decode_part(part))
        elif content_type == "text/html":
            html.append(decode_part(part))
    text = "\n\n".join(t for t in plain if t.strip())
    if not text:
        text = "\n\n".join(t for t in html if t.strip())
    return text


# ---------- Header fields ----------

def decode_text(value):
    """Decode "=?utf-8?B?...?=" words, join folded lines and cut very long values."""
    try:
        value = str(make_header(decode_header(value)))
    except Exception:  # a badly encoded value is kept as written
        pass
    return " ".join(value.split())[:MAX_FIELD_CHARS]


def usable(addr):
    """The address in lower case if it looks like local@domain.tld, else None."""
    addr = addr.strip().lower()
    if addr.count("@") != 1 or "." not in addr.split("@")[1]:
        return None  # not a usable address, for example "undisclosed-recipients:;"
    return addr


def parse_address(value):
    """Return (display name, address) from a header value; the address is lower-case, or None.

    Python's parser is strict and gives up on display names with an unquoted "@",
    "," or ";", such as 'service@paypal.com <x@evil.ru>'. Those are common in
    attacks, so when it gives up, the last <...> address is taken as the address
    (mail apps send replies there) and the text before it as the name.
    """
    name, addr = email.utils.parseaddr(value)
    addr = usable(addr)
    if addr is None:
        found = list(ANGLE_ADDRESS.finditer(value[:MAX_FIELD_CHARS]))
        if found:
            addr = usable(found[-1].group(1))
            name = value[:found[-1].start()].strip(" \t\"'")
    return decode_text(name) or None, addr


def header_value(message, name):
    """The first value of a header as a string, or None if the header is missing."""
    value = message.get(name)
    return None if value is None else str(value)


def sender(message):
    """(display name, address) of the From header."""
    value = header_value(message, "From")
    return parse_address(value) if value else (None, None)


def first_address(message, name):
    """The address in a one-address header such as Reply-To or Return-Path."""
    value = header_value(message, name)
    return parse_address(value)[1] if value else None


def to_domain(message):
    """The domain of the first usable address in To."""
    values = [str(value) for value in message.get_all("To", [])[:5]]
    for _, addr in email.utils.getaddresses(values):
        addr = usable(addr)
        if addr:
            return addr.split("@")[1]
    for value in values:  # the strict parser gave up on all of them: try the <...> fallback
        _, addr = parse_address(value)
        if addr:
            return addr.split("@")[1]
    return None


def date_value(message):
    """The Date header as a datetime that keeps the sender's own time zone."""
    value = header_value(message, "Date")
    return email.utils.parsedate_to_datetime(value) if value else None


def text_value(message, *names):
    """The decoded text of the first of these headers that exists."""
    for name in names:
        value = header_value(message, name)
        if value:
            return decode_text(value)
    return None


def first_message_id(message, name):
    """The first <...> message ID in a header such as Message-ID or In-Reply-To."""
    found = MESSAGE_ID.findall(header_value(message, name) or "")
    return found[0] if found else None


def all_message_ids(message, name):
    """Every <...> message ID in a header such as References, space-separated."""
    return " ".join(MESSAGE_ID.findall(header_value(message, name) or "")[:100]) or None


def all_values(message, name, limit):
    """Every value of a repeated header (top first), each on one line, at most `limit`."""
    return [" ".join(str(value).split())[:MAX_FIELD_CHARS] for value in message.get_all(name, [])[:limit]]


# (field name, function, extra arguments). Each runs on its own, so one broken header
# costs only its own field.
FIELD_PARSERS = [
    ("sender", sender, ()),
    ("reply_to", first_address, ("Reply-To",)),
    ("return_path", first_address, ("Return-Path",)),
    ("to_domain", to_domain, ()),
    ("date", date_value, ()),
    ("subject", text_value, ("Subject",)),
    ("message_id", first_message_id, ("Message-ID",)),
    ("in_reply_to", first_message_id, ("In-Reply-To",)),
    ("references", all_message_ids, ("References",)),
    ("list_id", text_value, ("List-Id",)),
    ("mailer", text_value, ("X-Mailer", "User-Agent")),
    ("received", all_values, ("Received", MAX_RECEIVED)),
    ("auth_results", all_values, ("Authentication-Results", 10)),
    ("received_spf", text_value, ("Received-SPF",)),
]


def parse_header_fields(block):
    """Parse a header block into plain fields. Returns (fields, problems).

    problems lists the fields that could not be parsed; they are None in fields.
    """
    # The default (legacy) parser is the most forgiving with malformed headers.
    message = email.message_from_string(block[:MAX_HEADER_CHARS] + "\n\n")
    fields, problems = {}, []
    for name, function, args in FIELD_PARSERS:
        try:
            fields[name] = function(message, *args)
        except Exception:  # attacker-written input: a failure must not lose the other fields
            fields[name] = None
            problems.append(name)

    from_name, from_addr = fields.pop("sender") or (None, None)
    fields["from_name"] = from_name
    fields["from_addr"] = from_addr
    fields["from_domain"] = from_addr.split("@")[1] if from_addr else None
    return fields, problems
