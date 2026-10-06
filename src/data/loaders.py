"""Read every source for the staged table into the same record shape.

Each load_* function is a generator: it yields one dict per email, with keys
    source            where the email comes from, for example "nazario" or "kaggle_ceas08"
    category          "ham", "spam", "phishing" or "fraud"
    has_full_headers  True when the email's original headers are available
    raw_ref           where the original is: a path inside data/raw/, plus "#<n>"
                      for the n-th message of an mbox or "#row=<n>" for a CSV row
    raw_headers       the header block as text (everything before the first blank line)
    body_raw          the body text, decoded but otherwise unchanged

Nothing is cleaned here: HTML stays HTML and links stay links. Cleaning and
redaction are Phase 2. Raw Enron is not loaded here; the Kaggle merge already
has Enron bodies, and raw Enron is used for the header coverage table and,
in Phase 9, for threads.

Security: emails are treated as data only. Attachments are skipped, never
decoded to disk, and nothing in an email is opened or run.
"""

import email
import mailbox

import pandas as pd

from src.data.paths import (
    APACHE_DIR,
    KAGGLE_DIR,
    NAZARIO_DIR,
    PHISHING_POT_DIR,
    RAW_DIR,
    SPAMASSASSIN_DIR,
)

# The Kaggle files we read: (source name, category for label 1). Label 0
# always means ham. CEAS-08 spam contains some phishing that its labels do not
# separate, so it stays "spam" (not an attack).
#
# Left out on purpose:
# - phishing_email.csv: a pre-merged copy of the per-source files (text and
#   label only); reading it as well would count every email twice.
# - Nazario.csv and SpamAssasin.csv: copies of the raw Nazario and SpamAssassin
#   corpora we download in full with headers. Of the rows the body fingerprint
#   in stage.py missed, a check on 6 Oct 2026 matched 98% (Nazario) and 96%
#   (SpamAssassin) to a raw email by sender, date and subject. Their bodies were
#   reprocessed (line breaks collapsed, <...> stripped, some Nazario rows run
#   into the next message), so the fingerprint could not catch them, and they
#   would leak copies of training emails into the test set.
KAGGLE_FILES = {
    "CEAS_08.csv": ("kaggle_ceas08", "spam"),
    "Enron.csv": ("kaggle_enron", "spam"),
    "Ling.csv": ("kaggle_ling", "spam"),
    "Nigerian_Fraud.csv": ("kaggle_nigerian_fraud", "fraud"),
}

# Kaggle columns that become header lines: (header name, CSV column).
# Enron.csv and Ling.csv only have a subject, so they get a Subject line only.
KAGGLE_HEADER_COLUMNS = [("From", "sender"), ("To", "receiver"), ("Date", "date"), ("Subject", "subject")]


def raw_ref(path, suffix=""):
    """Describe where an email came from, relative to data/raw/: 'nazario/phishing-2015.txt#12'."""
    return path.relative_to(RAW_DIR).as_posix() + suffix


# ---------- Kaggle CSV files ----------

def one_line(value):
    """Squash a CSV value onto one line, so it cannot add fake header lines (header injection)."""
    return " ".join(str(value).split())


def kaggle_header_block(row):
    """Build a minimal header block from a Kaggle row's sender, receiver, date and subject."""
    lines = []
    for header, column in KAGGLE_HEADER_COLUMNS:
        value = one_line(row.get(column, ""))
        if value:
            lines.append(f"{header}: {value}")
    return "\n".join(lines)


def load_kaggle():
    """Kaggle "Phish No More": the CSV files in KAGGLE_FILES, one row per email, no original headers."""
    folder = KAGGLE_DIR / "phish_no_more"
    for file_name, (source, attack_category) in KAGGLE_FILES.items():
        path = folder / file_name
        # dtype=str and keep_default_na=False: read every cell as text, empty cells as ""
        table = pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")
        skipped = 0
        for row_number, row in enumerate(table.to_dict("records")):
            label = row["label"].strip()
            if label not in ("0", "1"):
                skipped += 1
                continue
            yield {
                "source": source,
                "category": attack_category if label == "1" else "ham",
                "has_full_headers": False,
                "raw_ref": raw_ref(path, f"#row={row_number}"),
                "raw_headers": kaggle_header_block(row),
                "body_raw": row["body"],
            }
        if skipped:
            print(f"    {file_name}: skipped {skipped} rows whose label is not 0 or 1")


# ---------- Raw emails (.eml files, mbox messages) ----------

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


def email_record(raw, source, category, ref):
    """Build one record from the raw bytes of an email file or an mbox message."""
    # The default (legacy) parser is used on purpose: it is the most forgiving
    # with the malformed messages common in old corpora and in spam.
    message = email.message_from_bytes(raw)
    return {
        "source": source,
        "category": category,
        "has_full_headers": True,
        "raw_ref": ref,
        "raw_headers": split_headers(raw),
        "body_raw": body_text(message),
    }


def load_mbox(path, source, category):
    """Yield one record per message in an mbox file."""
    box = mailbox.mbox(path, create=False)  # opens read-only files read-only; never writes
    try:
        for key in box.iterkeys():
            yield email_record(box.get_bytes(key), source, category, raw_ref(path, f"#{key}"))
    finally:
        box.close()


def visible_files(folder):
    """Files in a folder, sorted, skipping hidden ones such as macOS's .DS_Store."""
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))


def load_spamassassin():
    """Raw SpamAssassin corpus: one file per email; the folder name says ham or spam."""
    # Layout: spamassassin/<archive name>/<easy_ham|hard_ham|spam|...>/<email file>
    for folder in sorted(SPAMASSASSIN_DIR.glob("*/*")):
        if not folder.is_dir():
            continue
        category = "spam" if folder.name.startswith("spam") else "ham"
        for path in visible_files(folder):
            if path.name == "cmds":  # the corpus's own bookkeeping file, not an email
                continue
            yield email_record(path.read_bytes(), "spamassassin", category, raw_ref(path))


def load_nazario():
    """Raw Nazario corpus: mbox files of phishing, one file per period."""
    for path in visible_files(NAZARIO_DIR):
        yield from load_mbox(path, "nazario", "phishing")


def load_phishing_pot():
    """phishing_pot: one .eml file per honeypot-caught phishing email."""
    for path in sorted((PHISHING_POT_DIR / "phishing_pot-main").rglob("*.eml")):
        yield email_record(path.read_bytes(), "phishing_pot", "phishing", raw_ref(path))


def load_apache():
    """Apache mailing lists: one mbox per month per list; all legitimate (ham)."""
    for folder in sorted(p for p in APACHE_DIR.iterdir() if p.is_dir()):
        for path in sorted(folder.glob("*.mbox")):
            yield from load_mbox(path, f"apache_{folder.name}", "ham")


# The order matters only for ties: among copies of the same email that all have
# full headers, the one read first is kept.
LOADERS = [
    ("spamassassin", load_spamassassin),
    ("nazario", load_nazario),
    ("phishing_pot", load_phishing_pot),
    ("apache", load_apache),
    ("kaggle", load_kaggle),
]
