"""Turn a raw email body into clean, readable text.

clean_body(raw) is the one function other code calls. It runs, in order:
1. cap the length (MAX_BODY_CHARS), so huge bodies cannot stall the regexes;
2. HTML to text, keeping each link's hidden target next to its text;
3. remove a mailing-list footer ("To unsubscribe ...");
4. remove quoted earlier messages ("> ...", "On ... wrote:", "-----Original Message-----");
5. find the signature block (it stays in the text and is also returned separately);
6. collapse all whitespace to single spaces, so no source can be recognised by its spacing.

Links stay in body_clean: it is the "raw" view for N1's model A. redact.py
replaces them afterwards.

Security: the same functions run on attacker-written email in the API
(Phase 11). HTML is parsed as data only (never rendered, no scripts run,
nothing fetched), every regular expression is written so crafted input cannot
make it backtrack for minutes (ReDoS: bounded repeats, no look-ahead over long
text), and bodies are capped. Each defence was tested on 31 crafted inputs of
up to 200,000 characters; the slowest takes under two seconds.
"""

import html
import re

from bs4 import BeautifulSoup

MAX_BODY_CHARS = 200_000

# Tags that only appear in HTML; plain text that merely contains "<john@x.com>" does not match.
HTML_TAG = re.compile(r"<\s{0,10}/?\s{0,10}(html|head|body|div|p|br|table|tr|td|span|font|a|img|style|center|b|i|ul|li|h[1-6]|blockquote)\b", re.IGNORECASE)
# Tags whose contents are never visible text.
INVISIBLE_TAGS = ["script", "style", "head", "noscript", "title"]
# Opening or closing tags that start a new line when an email is displayed (<br>, </p>, <div ...>).
BLOCK_BOUNDARY = re.compile(r"<\s{0,10}/?\s{0,10}(?:br|p|div|tr|li|table|h[1-6]|blockquote)\b", re.IGNORECASE)
MAX_LINE_BREAKS = 3000  # more block tags than this: skip the line breaks (see html_to_text)
MAX_LINKS = 500         # annotate at most this many links per email

# Markers that start quoted or forwarded history. Text from the earliest marker on is removed.
# "(?:- ?)" also matches the spaced dashes of pre-tokenised text ("- - - - - original message").
QUOTE_MARKERS = [
    re.compile(r"(?:- ?){2,40}\s{0,5}Original Message", re.IGNORECASE),             # Outlook
    re.compile(r"(?:- ?){2,40}\s{0,5}Forwarded message", re.IGNORECASE),            # Gmail
    re.compile(r"(?:- ?){2,40}\s{0,5}Forwarded by\b", re.IGNORECASE),               # Lotus Notes (Enron)
    re.compile(r"(?:- ?){10,40}\s{0,5}(?:To|From) ?: ", re.IGNORECASE),             # forwarded header after a dash line
    re.compile(r"\bBegin forwarded message ?:", re.IGNORECASE),                     # Apple Mail
    re.compile(r"\bOn [^\n]{1,300}? wrote ?:"),                                     # "On Mon, 5 Aug, Bob wrote:"
    re.compile(r"\bFrom ?: [^\n]{1,200}?\bSent ?: ", re.IGNORECASE),                # Outlook reply header
    re.compile(r"\bcc ?: [^\n]{0,200}?\bSubject ?: ", re.IGNORECASE),               # header block of a forward
]
QUOTED_LINE = re.compile(r"^[ \t]*>")  # a line that starts with ">" quotes an earlier message

# A list footer: a separator (10+ of - _ = *) at most 300 characters before "unsubscribe" or
# "mailing list". The words are found first and the separator is searched only in the 300
# characters before them: a single pattern with a look-ahead backtracks for hours on 200,000 dashes.
FOOTER_WORDS = re.compile(r"\b(?:unsubscribe|mailing list)\b", re.IGNORECASE)
SEPARATOR = re.compile(r"[-_=*]{10,}")
FOOTER_WINDOW = 300      # the separator must be this close before the words
MAX_FOOTER_CHARS = 1500  # only a short tail counts as a footer

# Signature start: "-- " on its own line (the standard), or a closing line such as "Best regards,".
SIGNATURE_DASHES = re.compile(r"^-- ?$")
CLOSING_LINE = re.compile(
    r"^(best regards|kind regards|warm regards|regards|best|many thanks|thanks|thank you|cheers|"
    r"sincerely|yours sincerely|yours truly|yours faithfully)[ \t]*[,.!]?$",
    re.IGNORECASE,
)
SIGNATURE_SEARCH_LINES = 12  # a closing line must be within the last 12 lines
SIGNATURE_MAX_LINES = 8      # the signature is at most 8 lines after it


def looks_like_html(text):
    """True if the text contains real HTML tags."""
    return HTML_TAG.search(text) is not None


def html_to_text(raw_html):
    """Convert HTML to plain text. Returns (text, had_blockquote)."""
    # Put a line break in front of every block tag, so the text keeps the email's lines (needed
    # to find the signature). On a crafted email with thousands of nested tags those extra line
    # breaks make parsing slow (5 seconds for 20,000 nested <div> tags), so very tag-heavy HTML
    # is parsed without them; it only loses its line structure.
    if len(BLOCK_BOUNDARY.findall(raw_html)) <= MAX_LINE_BREAKS:
        raw_html = BLOCK_BOUNDARY.sub(r"\n\g<0>", raw_html)
    soup = BeautifulSoup(raw_html, "html.parser")  # Python's own parser: no network, no scripts
    for tag in soup.find_all(INVISIBLE_TAGS):
        tag.decompose()  # delete the tag and everything inside it
    # Gmail and Outlook put quoted replies in <blockquote>; remove them like "> " lines.
    blockquotes = soup.find_all("blockquote")
    for tag in blockquotes:
        tag.decompose()
    # Keep each link's target, so a hidden link stays visible: "Click here (http://...)".
    for link in soup.find_all("a", href=True, limit=MAX_LINKS):
        href = link["href"].strip()
        if href.lower().startswith(("http://", "https://", "www.", "mailto:")) and href not in link.get_text():
            link.append(f" ({href})")
    return soup.get_text(" "), bool(blockquotes)


def strip_list_footer(text):
    """Remove a mailing-list footer at the end. Returns (text, removed)."""
    words = None
    for words in FOOTER_WORDS.finditer(text):
        pass  # keep the last occurrence
    if words is None:
        return text, False
    window_start = max(0, words.start() - FOOTER_WINDOW)
    separator = SEPARATOR.search(text, window_start, words.start())  # first separator in the window
    if separator and len(text) - separator.start() <= MAX_FOOTER_CHARS:
        return text[:separator.start()], True
    return text, False


def split_quoted(text):
    """Split text into (new message, quoted history)."""
    cut = len(text)
    for marker in QUOTE_MARKERS:
        match = marker.search(text)
        if match:
            cut = min(cut, match.start())
    head, quoted = text[:cut], text[cut:]
    kept, dropped = [], []
    for line in head.split("\n"):
        (dropped if QUOTED_LINE.match(line) else kept).append(line)
    main = "\n".join(kept)
    quoted = "\n".join(dropped) + quoted
    if not any(ch.isalnum() for ch in main):
        return text, ""  # nothing left, for example a bare forward: keep the whole text
    return main, quoted


def find_signature(text):
    """Return the signature block of the new message, or '' if none is found."""
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]  # ignore blank lines
    for i, line in enumerate(lines):
        if SIGNATURE_DASHES.match(line):
            return "\n".join(lines[i + 1 : i + 1 + SIGNATURE_MAX_LINES])
    start = max(0, len(lines) - SIGNATURE_SEARCH_LINES)
    for i in range(len(lines) - 1, start - 1, -1):  # from the bottom up
        if CLOSING_LINE.match(lines[i]):
            return "\n".join(lines[i : i + 1 + SIGNATURE_MAX_LINES])
    return ""


def normalise_whitespace(text):
    """Collapse every run of spaces, tabs and line breaks into one space."""
    return " ".join(text.split())


def clean_body(raw):
    """Clean one raw body. Returns a dict with body_clean, signature and what was done."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    truncated = len(raw) > MAX_BODY_CHARS
    raw = raw[:MAX_BODY_CHARS]

    is_html = looks_like_html(raw)
    had_blockquote = False
    if is_html:
        text, had_blockquote = html_to_text(raw)
    else:
        text = html.unescape(raw)  # "&amp;" -> "&", "&nbsp;" -> no-break space

    text, footer_removed = strip_list_footer(text)
    main, quoted = split_quoted(text)
    signature = find_signature(main)

    return {
        "body_clean": normalise_whitespace(main),
        "signature": normalise_whitespace(signature),
        "was_html": is_html,
        "quote_removed": had_blockquote or bool(quoted.strip()),
        "footer_removed": footer_removed,
        "truncated": truncated,
    }
