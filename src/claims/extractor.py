"""Phase 7: the claim extractor. Reads one email and returns the claims it makes.

    from src.claims.extractor import extract_claims
    extract_claims(body_redacted, signature)      # a list of claim dictionaries (see schema.py)

Three kinds of rule find claims, all reading the same text:

1. Phrase patterns (patterns.py): spaCy token patterns for ten of the eleven types, for example
   "verify your account" (credential_request) or "this is David from Finance" (affiliation_internal).
2. Organisation names (affiliation_external): spaCy's named-entity recogniser finds ORG entities and a short
   list of often-imitated organisations catches the ones it misses. An organisation next to a word like
   Team, Support, Bank or Security is a strong claim; a bare mention is a weak one.
3. Signature blocks (signature_contact): in the signature block, or in the last 350 characters of an email
   that has none, a phone number or an [EMAIL] placeholder is a claim; a name or organisation next to it
   makes the claim strong.

spaCy also fills each claim's attributes (person, organisation, department) from the entities around it.
No claim is invented: every claim's text is a slice of the email, and check_claim in schema.py verifies it.

What is read: model_text(body), which is body_redacted cut at 2,000 characters, exactly what the annotators
labelled; and the signature column of cleaned.parquet, redacted here (that column is cut from body_clean, so it
still holds raw addresses and links) and cut at 1,000 characters. Only the tokenizer and the named-entity
recogniser of spaCy run (6 ms per email); the tactic classifier is separate (src/models/predict.py).

Security: the text is cut before anything runs, so input size cannot slow the extractor down; phrase matching
is token-based, with no regular expression over email text except two short bounded shapes (a phone number and
the [EMAIL] placeholder); the model is loaded from disk, never downloaded. The self-test below feeds eight
crafted 200,000-character inputs and checks each finishes in under two seconds.

Run the self-test from the project root (needs the spaCy model of requirements.txt):   python -m src.claims.extractor
"""

import re
import sys
import time

import spacy
from spacy.matcher import Matcher
from spacy.util import filter_spans

from src.claims.patterns import (
    CONTACT_LABELS, DEPARTMENT_WORDS, GENERIC_WORDS, KNOWN_ORGS, NOT_ORGS, ORG_CUES, PATTERN_VERSION, PHRASES, SIGNOFF_WORDS, STRONG, TITLE_WORDS,
    WEAK,
)
from src.claims.schema import CLAIM_TYPES, MAX_CLAIMS, MAX_PER_TYPE, SIGNATURE_CHARS, check_claim, make_claim
from src.models.dataset import model_text
from src.preprocess.redact import redact

MODEL_NAME = "en_core_web_sm"
TAIL_CHARS = 350                       # without a signature block, the last 350 characters are read as one
MAX_SPAN_CHARS = 300                   # the same cap Phase 5 put on annotated spans
PLACEHOLDERS = frozenset(("email", "url", "file", "domain"))
CONTRACTIONS = frozenset(("'m", "'s", "'re", "'ve", "'ll", "'d", "n't"))   # tokens spaCy only produces inside "I'm", "don't" ...
# A phone number: digits with spaces, brackets, dots, slashes or dashes inside; 7 to 15 digits are required below.
PHONE = re.compile(r"(?:\+|00)?\d[\d ()./-]{6,22}\d")
EMAIL_TAG = re.compile(r"\[EMAIL\]")
DATE = re.compile(r"\d{1,4}[./-]\d{1,2}[./-]\d{1,4}")
LABEL_BEFORE = re.compile(r"([A-Za-z-]{2,10})[\s:.›-]{0,4}$")   # "Tel:" or "E-mail -" just before a contact


# ----------------------------------------------------------------------------------------------------------
# Patterns: from the phrase language of patterns.py to spaCy token patterns
# ----------------------------------------------------------------------------------------------------------

def compile_phrase(phrase):
    """Turn a phrase of the pattern language into a spaCy token pattern (a list of dictionaries)."""
    items = phrase.split()
    if not items or items[0].startswith(("..", "?", "!")) or items[-1].startswith(("..", "?", "!")):
        raise ValueError("a phrase must start and end with a real word: %r" % phrase)
    pattern = []
    for item in items:
        if item.startswith(".."):
            count = int(item[2:])
            if not 1 <= count <= 6:
                raise ValueError("..N needs N between 1 and 6: %r" % phrase)
            pattern.extend({"OP": "?"} for _ in range(count))
        elif item.startswith("@"):
            pattern.append({"ENT_TYPE": item[1:], "OP": "+"})
        elif item == "#":
            pattern.append({"IS_DIGIT": True})
        else:
            optional = item.startswith("?")
            item = item.lstrip("?")
            negated, same_case = item.startswith("!"), item.startswith("=")
            words = item.lstrip("!=").split("|") if same_case else item.lstrip("!").lower().split("|")
            exact = [w for w in words if not w.endswith("*")]
            stems = [w[:-1] for w in words if w.endswith("*")]
            if (negated or same_case) and stems:
                raise ValueError("a stem cannot follow ! or =: %r" % phrase)
            if same_case:
                token = {"TEXT": exact[0]} if len(exact) == 1 else {"TEXT": {"IN": exact}}
            elif negated:
                token = {"LOWER": {"NOT_IN": exact}}
            elif stems:
                alternatives = [re.escape(s) for s in stems] + [re.escape(w) + "$" for w in exact]
                token = {"LOWER": {"REGEX": "^(?:" + "|".join(alternatives) + ")"}}
            elif len(exact) == 1:
                token = {"LOWER": exact[0]}
            else:
                token = {"LOWER": {"IN": exact}}
            if optional:
                token["OP"] = "?"
            pattern.append(token)
    return pattern


def check_patterns(nlp):
    """Compile every phrase and check ids and words. Raises ValueError on the first problem, else returns the count."""
    seen, count = set(), 0
    if set(PHRASES) - set(CLAIM_TYPES):
        raise ValueError("unknown claim types in PHRASES: %s" % sorted(set(PHRASES) - set(CLAIM_TYPES)))
    for claim_type, entries in PHRASES.items():
        for pattern_id, phrase, strength in entries:
            if pattern_id in seen:
                raise ValueError("duplicate pattern id %s" % pattern_id)
            seen.add(pattern_id)
            if strength not in (STRONG, WEAK):
                raise ValueError("%s: strength must be STRONG or WEAK" % pattern_id)
            compile_phrase(phrase)
            for item in phrase.split():
                if item.startswith(("..", "@")) or item == "#":
                    continue
                for word in item.lstrip("?!=").split("|"):
                    if not word.endswith("*") and word not in CONTRACTIONS and len(nlp.make_doc(word)) != 1:
                        raise ValueError("%s: %r is not one token" % (pattern_id, word))
            count += 1
    return count


KNOWN_LOWER = frozenset(name.lower() for name in KNOWN_ORGS)
_STATE = {}


def load_nlp():
    """The spaCy pipeline (tokenizer and named-entity recogniser only) with the matchers built on it; loaded once."""
    if "nlp" not in _STATE:
        nlp = spacy.load(MODEL_NAME, exclude=["tagger", "parser", "attribute_ruler", "lemmatizer"])
        check_patterns(nlp)
        phrases, meta = Matcher(nlp.vocab), {}
        for claim_type, entries in PHRASES.items():
            for pattern_id, phrase, strength in entries:
                key = claim_type + ":" + pattern_id
                phrases.add(key, [compile_phrase(phrase)])
                meta[nlp.vocab.strings[key]] = (claim_type, pattern_id, strength)
        orgs = Matcher(nlp.vocab)       # the known organisations, written as they are or in capitals
        for name in KNOWN_ORGS:
            tokens = [t.text for t in nlp.make_doc(name)]
            orgs.add(name, [[{"TEXT": t} for t in tokens], [{"TEXT": t.upper()} for t in tokens]])
        _STATE.update(nlp=nlp, phrases=phrases, meta=meta, orgs=orgs)
    return _STATE["nlp"]


# ----------------------------------------------------------------------------------------------------------
# Candidates: every rule produces (type, start, end, confidence, pattern id) in the characters of one text
# ----------------------------------------------------------------------------------------------------------

def is_not_an_org(span):
    """True for a span spaCy tagged ORG that is a number, a greeting, a placeholder, a job title or only a department word."""
    words = [t.lower_ for t in span]
    return (any(c.isdigit() for c in span.text) or span.text.lower() in NOT_ORGS
            or all(w in PLACEHOLDERS or w in NOT_ORGS or w in TITLE_WORDS or w in DEPARTMENT_WORDS for w in words))


def attributes_for(doc, first, last, pattern_id, zone):
    """person, organisation and department from the entities and words around tokens first..last."""
    low, high = max(0, first - 6), min(len(doc), last + 6)
    person = organisation = department = None
    for ent in doc.ents:
        if ent.end <= low or ent.start >= high:
            continue
        if ent.label_ == "PERSON" and person is None:
            person = ent.text
        elif ent.label_ == "ORG" and organisation is None and not is_not_an_org(ent):
            organisation = ent.text
    for token in doc[low:high]:
        if token.lower_ in DEPARTMENT_WORDS:
            department = token.text
            break
    return {"person": person, "organisation": organisation, "department": department, "pattern": pattern_id, "zone": zone}


def is_placeholder(doc, i):
    """True if token i is the word inside a redaction placeholder: the EMAIL of [EMAIL], the URL of [URL] ..."""
    return (0 < i < len(doc) - 1 and doc[i].text in ("EMAIL", "URL", "FILE", "DOMAIN") and doc[i - 1].text == "[" and doc[i + 1].text == "]")


def phrase_candidates(doc, zone):
    """Claims from the phrase patterns."""
    found = []
    for match_id, first, last in _STATE["phrases"](doc):
        if is_placeholder(doc, first) or is_placeholder(doc, last - 1):
            continue      # the word "email" in the pattern must not match the EMAIL of the placeholder [EMAIL]
        claim_type, pattern_id, strength = _STATE["meta"][match_id]
        span = doc[first:last]
        found.append((claim_type, span.start_char, span.end_char, strength, pattern_id, first, last, zone))
    return found


def org_candidates(doc, zone):
    """affiliation_external claims from organisation names: spaCy's ORG entities plus the known organisations."""
    spans = [ent for ent in doc.ents if ent.label_ == "ORG"]
    spans += [doc[first:last] for _, first, last in _STATE["orgs"](doc)]
    found = []
    for span in filter_spans(spans):
        if is_not_an_org(span):
            continue                                         # "CFO", "Finance" and "Dear Customer" are not outside organisations
        words = [t.lower_ for t in span]
        if all(w in GENERIC_WORDS for w in words):
            continue                                         # "Bank", "Bank account" and "Security Company" name nobody
        end = span.end
        while end < len(doc) and end < span.end + 2 and doc[end].lower_ in ORG_CUES:   # "PayPal Security Team"
            end += 1
        cued = end > span.end or any(w in ORG_CUES for w in words)
        if not cued and span.text.lower() not in KNOWN_LOWER:
            continue            # a bare organisation name that spaCy found is too common in ordinary mail to be a claim
        found.append(("affiliation_external", span.start_char, doc[end - 1].idx + len(doc[end - 1]), STRONG if cued else WEAK,
                      "ae_org_cue" if cued else "ae_org_mention", span.start, end, zone))
    return found


def is_phone(shape):
    """True if text matched by PHONE looks like a phone number: 7 to 15 digits, not a date, not a bare number."""
    digits = sum(c.isdigit() for c in shape)
    if not 7 <= digits <= 15 or DATE.fullmatch(shape.strip()):
        return False
    return shape[0] in "+0" or any(c in shape for c in " ()./-")     # a bare run of digits must start like a phone number


def signature_candidates(doc, zone_text, base, zone):
    """signature_contact claims from a phone number or an [EMAIL] placeholder in the signature zone.

    zone_text is the zone's text and base is where it starts in the characters of doc.
    """
    contacts = [m.span() for m in PHONE.finditer(zone_text) if is_phone(m.group())]
    contacts += [m.span() for m in EMAIL_TAG.finditer(zone_text)]
    if not contacts:
        return signoff_candidates(doc, zone_text, base, zone)
    first, last = min(s for s, _ in contacts), max(e for _, e in contacts)
    window = max(0, first - 12)
    label = LABEL_BEFORE.search(zone_text[window:first])
    if label and label.group(1).lower() in CONTACT_LABELS:
        first = window + label.start(1)
    names = [(e.start_char - base, e.end_char - base) for e in doc.ents
             if e.label_ in ("PERSON", "ORG") and e.start_char >= base and e.end_char - base <= last
             and e.text.lower() not in NOT_ORGS and e.text.lower() not in PLACEHOLDERS and first - (e.start_char - base) <= 160]
    start = min([first] + [s for s, _ in names])
    end = min(last, start + MAX_SPAN_CHARS)
    return [("signature_contact", base + start, base + end, STRONG if start < first else WEAK, "sc_name_contact" if start < first else "sc_contact",
             None, None, zone)]


def signoff_candidates(doc, zone_text, base, zone):
    """A weak signature_contact claim: a name or organisation right after a closing word ("Thanks, John Smith")."""
    for token in doc:
        if token.idx < base or token.idx - base >= len(zone_text) or token.lower_ not in SIGNOFF_WORDS:
            continue
        for ent in doc.ents:
            close = 0 <= ent.start_char - token.idx <= 40
            if close and ent.label_ in ("PERSON", "ORG") and ent.text.lower() not in NOT_ORGS and ent.text.lower() not in PLACEHOLDERS:
                return [("signature_contact", ent.start_char, ent.end_char, WEAK, "sc_signoff_name", None, None, zone)]
    return []


COPYRIGHT_SKIP = frozenset(("-", "\u2013", "\u2014", ",", "\u00a9", "(c)", "copyright"))
NOT_A_NAME = frozenset(("all", "alle", "tous", "todos", "tutti", "tutti", "rights", "reserved"))


def copyright_candidates(doc, zone):
    """affiliation_external claims: the name after a copyright sign and year, as in "(c) 2024 Omaha Steaks. All rights reserved"."""
    found = []
    for token in doc:
        if token.text not in ("\u00a9", "(c)") and token.lower_ != "copyright":
            continue
        i = token.i + 1
        while i < len(doc) and (doc[i].like_num or doc[i].lower_ in COPYRIGHT_SKIP):
            i += 1
        j = i
        while j < len(doc) and j < i + 3 and doc[j].text[:1].isalpha() and (doc[j].is_title or doc[j].is_upper) and doc[j].lower_ not in NOT_A_NAME:
            j += 1
        if j > i:
            found.append(("affiliation_external", doc[i].idx, doc[j - 1].idx + len(doc[j - 1]), STRONG, "ae_copyright", i, j, zone))
    return found


def labelled_contact_candidates(text, zone):
    """signature_contact claims: a phone number or [EMAIL] placeholder with a label (Tel, Fax, E-mail) just before it, anywhere in the text."""
    found = []
    shapes = [m.span() for m in PHONE.finditer(text) if is_phone(m.group())] + [m.span() for m in EMAIL_TAG.finditer(text)]
    for start, end in shapes:
        window = max(0, start - 14)
        label = LABEL_BEFORE.search(text[window:start])
        if label and label.group(1).lower() in CONTACT_LABELS:
            found.append(("signature_contact", window + label.start(1), end, STRONG, "sc_labelled_contact", None, None, zone))
    return found


def zone_candidates(doc, zone):
    """Every rule that works on one searched text."""
    return phrase_candidates(doc, zone) + org_candidates(doc, zone) + copyright_candidates(doc, zone) + labelled_contact_candidates(doc.text, zone)


# ----------------------------------------------------------------------------------------------------------
# From candidates to claims
# ----------------------------------------------------------------------------------------------------------

def select(candidates, min_confidence):
    """Drop weak ones below min_confidence and overlaps within a type (the longest wins), cap per type and in total."""
    chosen, per_type = [], {}
    for cand in sorted((c for c in candidates if c[3] >= min_confidence), key=lambda c: (-(c[2] - c[1]), -c[3], c[1])):
        claim_type, start, end, zone = cand[0], cand[1], cand[2], cand[7]
        if end - start > MAX_SPAN_CHARS or per_type.get(claim_type, 0) >= MAX_PER_TYPE:
            continue
        if any(k[0] == claim_type and k[7] == zone and start < k[2] and k[1] < end for k in chosen):
            continue
        chosen.append(cand)
        per_type[claim_type] = per_type.get(claim_type, 0) + 1
    chosen.sort(key=lambda c: (c[7] != "body", c[1]))
    return chosen[:MAX_CLAIMS]


def claims_from(doc, text, sig_doc, sig, min_confidence):
    """Claims of one email from its parsed body (doc), its text and, when the signature lies outside the body, its parsed signature."""
    candidates = zone_candidates(doc, "body")
    if sig_doc is not None:
        candidates += zone_candidates(sig_doc, "signature")
        candidates += signature_candidates(sig_doc, sig, 0, "signature")
    elif sig:
        candidates += signature_candidates(doc, sig, text.rfind(sig), "body")
    else:
        tail = max(0, len(text) - TAIL_CHARS)
        candidates += signature_candidates(doc, text[tail:], tail, "body")
    claims = []
    for number, cand in enumerate(select(candidates, min_confidence), start=1):
        claim_type, start, end, confidence, pattern_id, first, last, zone = cand
        source, parsed = (text, doc) if zone == "body" else (sig, sig_doc)
        if first is None:                                    # a signature claim has characters, not tokens
            span = parsed.char_span(start, end, alignment_mode="expand")
            first, last = (span.start, span.end) if span is not None else (0, 0)
        claims.append(make_claim(number, claim_type, source[start:end], start, end, confidence,
                                 attributes_for(parsed, first, last, pattern_id, zone)))
    return claims


def prepare(body, signature):
    """The two texts that are read: (body text, redacted signature or '')."""
    text = model_text(body) if isinstance(body, str) else ""
    sig = redact(signature[:SIGNATURE_CHARS])[0].strip() if isinstance(signature, str) else ""
    return text, sig


def extract_claims(body, signature=None, min_confidence=0.0):
    """The claims of one email. body is body_redacted, signature the signature block (or None).

    min_confidence 0.9 keeps strong claims only; the default keeps weak ones too.
    """
    nlp = load_nlp()
    text, sig = prepare(body, signature)
    doc = nlp(text)
    sig_doc = nlp(sig) if sig and sig not in text else None
    return claims_from(doc, text, sig_doc, sig, min_confidence)


def extract_many(bodies, signatures=None, min_confidence=0.0, batch_size=64):
    """Claims for many emails at once (the build uses this; spaCy processes them in batches). Returns (claims, texts) lists."""
    nlp = load_nlp()
    signatures = signatures if signatures is not None else [None] * len(bodies)
    prepared = [prepare(b, s) for b, s in zip(bodies, signatures)]
    docs = list(nlp.pipe([t for t, _ in prepared], batch_size=batch_size))
    outside = [i for i, (t, s) in enumerate(prepared) if s and s not in t]
    sig_docs = dict(zip(outside, nlp.pipe([prepared[i][1] for i in outside], batch_size=batch_size)))
    results = []
    for i, ((text, sig), doc) in enumerate(zip(prepared, docs)):
        results.append(claims_from(doc, text, sig_docs.get(i), sig, min_confidence))
    return results, prepared


# ----------------------------------------------------------------------------------------------------------
# Self-test: python -m src.claims.extractor
# ----------------------------------------------------------------------------------------------------------

# (email text, signature, claim types that must be found, claim types that must NOT be found[, min_confidence])
# The last cases are false positives that the first train run (pattern version 0.1) printed for ordinary emails.
CASES = [
    ("Hello, this is David from Finance. Please process the wire transfer before 3 PM today.", None,
     {"affiliation_internal", "payment_request"}, {"credential_request", "gift_card"}),
    ("Please verify your account by clicking the link below to avoid suspension.", None, {"credential_request"}, {"payment_request"}),
    ("I am Mr. Brooks Donald, the Internal Auditor of the Foreign Payment Office. Reply to my private email address [EMAIL].", None,
     {"authority", "reply_direction"}, {"gift_card"}),
    ("Kindly send me your full name, address and a copy of your passport.", None, {"data_request"}, {"gift_card", "payment_change"}),
    ("We have changed our bank details. Please use the new bank details for all future payments.", None, {"payment_change"}, {"gift_card"}),
    ("Buy five gift cards and send me the codes. As we discussed on the call, keep it quiet.", None, {"gift_card", "prior_relationship"}, {"credential_request"}),
    ("Dear customer, this is the PayPal Security Team. Your account needs attention.", None, {"affiliation_external"}, {"gift_card"}),
    ("Thanks for the lunch. See you at the meeting on Friday.\nBest regards,\nJames Sterling\nProject Manager\nTel: 555-0199 [EMAIL]", None,
     {"signature_contact"}, {"credential_request", "payment_request", "gift_card", "data_request"}),
    ("The quarterly report is attached. Let me know if the numbers look right.", None, set(), set(CLAIM_TYPES)),
    ("I am writing to the manager of the hotel to book a room.", None, set(), {"authority"}),
    ("Thanks for the update on the site work.\nBest regards,\nJames Sterling", None, {"signature_contact"}, set()),
    ("Visit our office at 1000 Lowes Blvd, Mooresville, NC 28117 any weekday.", None, {"signature_contact"}, set()),
    ("If you have received this message in error, please notify the sender immediately.", None, {"signature_contact"}, set()),
    ("Kindly reply to me. My private TEL: 233-27-587908. E-MAIL: [EMAIL]. " + "The fund will be moved after the audit is done. " * 12, None,
     {"signature_contact"}, set(), 0.9),
    ("Thank you for shopping with us. \u00a9 2024 Omaha Steaks. All rights reserved.", None, {"affiliation_external"}, set(), 0.9),
    ("I work in a Bank here in Abidjan and need a Bank account to receive it.", None, set(), {"affiliation_external"}),
    ("Please send your credit card number to confirm the order.", None, {"data_request"}, set(), 0.9),
    ("PayPal has successfully charged $175 to your credit card.", None, set(), {"data_request"}, 0.9),
    ("My name is Anna and I am a social worker with a small charity.", None, set(), {"affiliation_internal"}),
    ("You have added [EMAIL] as a new email address for your account.", None, set(), {"reply_direction"}),
    ("He secretly called me on his bed side and told me about a secret fund.", None, set(), {"reply_direction"}),
    ("Transfer the funds into your account through the office of the director.", None, set(), {"affiliation_internal"}),
    ("I am Peter Kok, a top government official in the ministry.", None, {"authority"}, set()),
    ("Hi, this is Maria from IT. Your mailbox is full.", None, {"affiliation_internal"}, set()),
    ("I think it may support the new format, so ask them whether it will work.", None, set(), {"affiliation_internal"}),
    ("As let's talk about it later. The word \"promiscuous\" means something else here.", None, set(), {"prior_relationship"}),
    ("You can make money fast. I will send Mr Pratchett money tomorrow.", None, set(), {"payment_request"}, 0.9),
    ("Please return with your credit for the new card. We accept credit.", None, set(), {"data_request"}),
    ("The gift voucher is valid for one year.", None, set(), {"gift_card"}, 0.9),
    ("Please note that my personal mail is not checked often.", None, set(), {"reply_direction"}, 0.9),
]


def crafted_inputs():
    """Eight inputs of 200,000 characters that try to make an extractor slow."""
    size = 200_000
    return [
        ("one repeated word", "verify " * (size // 7)),
        ("one long token", "a" * size),
        ("digits and separators", "1 2 3 4 5 6 7 8 9 0 " * (size // 20)),
        ("nested brackets", "(" * (size // 2) + ")" * (size // 2)),
        ("placeholders", "[EMAIL] " * (size // 8)),
        ("zero-width characters", "ver​ify your acc​ount " * (size // 24)),
        ("repeated pattern start", "sign in to your " * (size // 16)),
        ("many lines", "Regards,\nJohn\n" * (size // 14)),
    ]


def self_test():
    """Run the hand-made cases and the crafted inputs. Returns True when everything passes."""
    ok = True

    def check(name, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        print("  %-4s %s %s" % ("PASS" if passed else "FAIL", name, detail))

    nlp = load_nlp()
    check("patterns compile", True, "(%d phrases, version %s, spaCy model %s)" % (check_patterns(nlp), PATTERN_VERSION, nlp.meta["version"]))
    for text, signature, must, must_not, *conf in CASES:
        claims = extract_claims(text, signature, conf[0] if conf else 0.0)
        found = {c["type"] for c in claims}
        valid = all(not check_claim(c, model_text(text), prepare(text, signature)[1]) for c in claims)
        check("%r" % (text[:48] + "..."), must <= found and not (found & must_not) and valid,
              "found %s" % sorted(found) if not (must <= found and not (found & must_not) and valid) else "")
    check("a body that is not text gives no claims", extract_claims(None) == [] and extract_claims(12345) == [])
    strong = extract_claims("Please verify your account and sign in to your PayPal account.", None, min_confidence=0.9)
    check("min_confidence 0.9 keeps strong claims only", bool(strong) and all(c["confidence"] == 0.9 for c in strong))
    for name, text in crafted_inputs():
        started = time.time()
        claims = extract_claims(text, text)
        seconds = time.time() - started
        check("crafted input: %s" % name, seconds < 2.0 and len(claims) <= MAX_CLAIMS, "(%.2f s, %d claims)" % (seconds, len(claims)))
    return ok


if __name__ == "__main__":
    print("Claim extractor self-test:")
    sys.exit(0 if self_test() else 1)
