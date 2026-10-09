"""Phase 8: find bank details in an email's text (IBANs, account numbers, routing and sort codes, SWIFT codes).

    find_bank_details("Our new IBAN is DE89 3704 0044 0532 0130 00, account number 12345678.")
      -> [{"kind": "iban", "value": "DE89370400440532013000", "masked": "DE**3000"},
          {"kind": "account", "value": "12345678", "masked": "****5678"}]

Why it exists. In business email compromise the most telling request is "we have changed our bank details" followed by
account numbers the reader has never seen. The request verifier (this phase) raises a payment-change contradiction's
severity when the message really carries bank details, and the thread verifier (Phase 9) compares the details of one
message with the earlier ones in the thread (request drift), using bank_detail_keys.

IBAN CHECK. An IBAN is 2 letters (country), 2 check digits and up to 30 letters or digits. Move the first four
characters to the end, turn every letter into a number (A = 10 ... Z = 35) and read the result as one huge number: it
must leave remainder 1 when divided by 97. The test catches typing errors and random digit strings (about 1 in 97 random
strings of the right shape would pass, so the country's known length is checked too).

Account numbers, routing numbers, sort codes and SWIFT codes have no checksum that works for all banks, so they count only
when a label word stands in front of them ("account number", "routing", "sort code", "swift"). That keeps order numbers
and phone numbers out.

Security: this reads attacker-written text. No regular expressions: the text is cut at 5,000 characters, split into
words, and every word is examined a bounded number of times (an IBAN can span at most 9 words), so the cost grows with the
length of the text and nothing else. Values are shown masked (country and last four characters only): the ledger and the
logs must not carry whole account numbers (master document Section 10, PII redaction).
"""

MAX_CHARS = 5000
MAX_DETAILS = 10
MAX_GROUPS = 9                      # an IBAN has at most 34 characters: 9 groups of up to 4

# Official IBAN lengths of the larger countries. A country that is not listed is accepted with any length from 15 to 34.
IBAN_LENGTHS = {
    "DE": 22, "GB": 22, "FR": 27, "ES": 24, "IT": 27, "NL": 18, "BE": 16, "CH": 21, "AT": 20, "IE": 22, "PT": 25,
    "SE": 24, "NO": 15, "DK": 18, "FI": 18, "PL": 28, "LU": 20, "GR": 27, "TR": 26, "AE": 23, "SA": 24, "CZ": 24,
    "HU": 28, "RO": 24,
}

LABELS = {"account": "account", "acct": "account", "a/c": "account", "routing": "routing", "aba": "routing",
          "sort": "routing", "swift": "swift", "bic": "swift"}
FILLER = frozenset(("number", "no", "no.", "num", "nr", "nr.", "code", "is", "are", "#", ":", "-", "=", "was", "iban"))
LENGTHS = {"account": range(6, 18), "routing": (6, 9)}
STRIP = "()[]{}<>\"'.,;:!?"


def word(token):
    """A word with the punctuation around it removed."""
    return token.strip(STRIP)


def iban_checksum_ok(value):
    """True if value (upper-case letters and digits only) passes the mod 97 test described in the module text."""
    remainder = 0
    for ch in value[4:] + value[:4]:
        if ch.isdigit():
            remainder = (remainder * 10 + int(ch)) % 97
        else:
            remainder = (remainder * 100 + ord(ch) - 55) % 97      # A is 10, Z is 35
    return remainder == 1


def valid_iban(value):
    """True if value looks like an IBAN (shape, known length, check digits) and passes the checksum."""
    if not (15 <= len(value) <= 34 and value.isascii() and value.isalnum() and value == value.upper()):
        return False
    if not (value[:2].isalpha() and value[2:4].isdigit()):
        return False
    if IBAN_LENGTHS.get(value[:2], len(value)) != len(value):
        return False
    return iban_checksum_ok(value)


def find_ibans(words):
    """Valid IBANs in a list of words, whether written as one word or in groups of four ('DE89 3704 0044 ...')."""
    found = []
    for i, token in enumerate(words):
        head = word(token)
        if not (head.isascii() and head.isalnum() and head[:2].isalpha() and head[2:4].isdigit()):
            continue
        candidate = head.upper()
        best = candidate if valid_iban(candidate) else None
        if len(head) == 4:                                    # printed in groups: join the groups that follow
            for next_word in words[i + 1:i + MAX_GROUPS]:
                part = word(next_word)
                if not (part.isascii() and part.isalnum() and 1 <= len(part) <= 4):
                    break
                candidate += part.upper()
                if valid_iban(candidate):
                    best = candidate                          # keep the longest valid one
        if best and best not in found:
            found.append(best)
    return found


def find_labelled(words):
    """(kind, value) for numbers that stand right after a label word: account, routing/sort and SWIFT/BIC codes."""
    found = []
    for i, token in enumerate(words):
        kind = LABELS.get(word(token).lower())
        if kind is None:
            continue
        for next_word in words[i + 1:i + 5]:
            part = word(next_word)
            if part.lower() in FILLER:
                continue
            if kind == "swift":
                if len(part) in (8, 11) and part.isascii() and part[:6].isalpha() and part.isalnum():
                    found.append((kind, part.upper()))
            else:
                digits = part.replace("-", "")
                if part.isascii() and digits.isdigit() and len(digits) in LENGTHS[kind]:
                    found.append((kind, digits))
            break
    return found


def mask(kind, value):
    """Show a detail without revealing it: IBAN country and last four, others last four only."""
    if kind == "iban":
        return value[:2] + "**" + value[-4:]
    if kind == "swift":
        return value[:4] + "****"
    return "****" + value[-4:]


def find_bank_details(text):
    """Bank details found in text, as a list of {'kind', 'value', 'masked'} (at most 10, no repeats)."""
    if not isinstance(text, str):
        return []
    words = text[:MAX_CHARS].split()
    pairs = [("iban", v) for v in find_ibans(words)] + find_labelled(words)
    details, seen = [], set()
    for kind, value in pairs:
        if (kind, value) not in seen and len(details) < MAX_DETAILS:
            seen.add((kind, value))
            details.append({"kind": kind, "value": value, "masked": mask(kind, value)})
    return details


def bank_detail_keys(text):
    """The set of (kind, value) in text: the thread verifier compares these sets between messages (request drift)."""
    return frozenset((d["kind"], d["value"]) for d in find_bank_details(text))
