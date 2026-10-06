"""N1 payload-free redaction: replace links, addresses, file names and domains with placeholders.

redact(text) returns the redacted text and how many of each placeholder it used.
The order matters and is fixed:
    [URL]     http://..., https://..., www...., and defanged hxxp://...
    [EMAIL]   name@example.com, mailto:name@example.com
    [FILE]    attachment-style file names such as invoice.pdf or update.zip
    [DOMAIN]  bare domains such as paypa1.co.uk, checked against the public suffix list
URLs go first so a URL's domain is not caught on its own; file names go before
domains because some file endings are real top-level domains (invoice.zip).
Words such as "see attached" stay: they are language, not payload.

contains_url(text) answers "did this email have a link?" on the raw body,
including link targets hidden inside HTML.

Security: every pattern is written so attacker-written text cannot make it
backtrack for minutes (ReDoS): repeats are bounded (for example at most 64
characters before "@"), and an open-ended repeat only ever ends a pattern.
tldextract uses its built-in copy of the public suffix list and never
downloads anything.
"""

import re
from functools import lru_cache

import tldextract

URL = re.compile(r"\b(?:https?|hxxps?|ftp)://[^\s<>\"'()\[\]{}]+|\bwww\.[^\s<>\"'()\[\]{}]+", re.IGNORECASE)
EMAIL = re.compile(r"\b(?:mailto:)?[a-z0-9._%+-]{1,64}@[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){1,8}\b", re.IGNORECASE)
FILE = re.compile(
    r"\b[\w-]{1,100}\.(?:pdf|docx?|docm|xlsx?|xlsm|pptx?|rtf|odt|csv|txt|zip|rar|7z|gz|tar|iso|img|"
    r"exe|scr|msi|bat|cmd|js|jar|vbs|ps1|lnk|one|html?|png|jpe?g|gif)\b",
    re.IGNORECASE,
)
# A domain candidate: 2 to 10 dot-separated labels, each 1 to 63 letters, digits or inner hyphens.
DOMAIN_CANDIDATE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,9}[a-z][a-z0-9-]{0,62}\b", re.IGNORECASE
)
TRAILING_PUNCTUATION = ".,;:!?"

# suffix_list_urls=() means: never download the list, use the copy shipped inside tldextract.
_extract = tldextract.TLDExtract(suffix_list_urls=())


@lru_cache(maxsize=200_000)
def is_real_domain(candidate):
    """True if the candidate ends in a real public suffix and has a name before it (paypa1.co.uk)."""
    parts = _extract(candidate)
    return bool(parts.domain and parts.suffix)


def _replace_url(match):
    """Replace a URL with [URL], but keep sentence punctuation that ended up stuck to it."""
    url = match.group(0)
    trimmed = url.rstrip(TRAILING_PUNCTUATION)
    return "[URL]" + url[len(trimmed):]


def redact(text):
    """Return (redacted text, counts) where counts says how many of each placeholder were used."""
    counts = {}
    text, counts["url"] = URL.subn(_replace_url, text)
    text, counts["email"] = EMAIL.subn("[EMAIL]", text)
    text, counts["file"] = FILE.subn("[FILE]", text)

    domain_count = 0

    def replace_domain(match):
        nonlocal domain_count
        if is_real_domain(match.group(0)):
            domain_count += 1
            return "[DOMAIN]"
        return match.group(0)  # "Mr.Smith", "e.g", "version1.2" stay as they are

    text = DOMAIN_CANDIDATE.sub(replace_domain, text)
    counts["domain"] = domain_count
    return text, counts


def contains_url(text):
    """True if the text contains a URL anywhere, including inside HTML attributes such as href."""
    return URL.search(text) is not None
