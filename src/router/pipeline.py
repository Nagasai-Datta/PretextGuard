"""Phase 10: analyze(): the whole pipeline of Figure 3 for one request, and the report of master document Section 6.3.

    from src.router.pipeline import analyze, Analyzer

    report = analyze(raw_email, org_domain="acmecorp.com")             # one email: text or bytes, with or without headers
    report = analyze([raw_1, raw_2, raw_3], org_domain=None)           # a thread: the newest message is judged against the ones before it
    python -m src.router.pipeline email.eml --org acmecorp.com         # try it on a file
    python -m src.router.pipeline --thread a.eml b.eml c.eml           # a thread of files

The API (Phase 11) calls analyze and nothing else. The steps (the numbers are those of Figure 3):
    3 parse     headers become fields and evidence (src/headers); the body is decoded (a header-less paste is a body)
    4 redact    links, addresses, file names and domains become placeholders (N1, src/preprocess)
    5 extract   seven tactic probabilities (src/models) and typed claims (src/claims)
    6 route     each claim goes to the verifier that can check it (src/router/router.py); a thread adds the thread verifier
    6 verify    header (N3), request and thread (N2) verifiers write ledger rows (src/verifiers)
    7 score     the ledger and the tactics become 0 to 100, a band and an action (src/router/score.py)
    8 report    LIME highlights for the tactics that fired (src/explain), the coverage, and everything below. Nothing is stored.

THE REPORT (dictionary, JSON-ready):
    request_id    given, or made here (letters, digits, - and _ only)       mode  'email' or 'thread'
    score         0 to 100                                                 verdict  'Low risk' | 'Suspicious' | 'High risk'      action  fixed text
    org_domain    the organisation domain as used, or None                 versions  score, rules, thread rules, claim patterns
    text_read     the redacted text the classifier and the extractor read; every claim span and highlight offset points into it
    signature_read the redacted signature block (claims with zone 'signature' point into it)
    tactics       seven entries: name, probability, threshold, fired, scored (counts in the score), highlights [{start, end, text, weight, word}]
    explained     True when LIME ran (explain=True and a tactic fired)
    claims        the typed claims; routing: which verifiers each was sent to
    ledger        the rows, exactly as the verifiers return them, 'not checkable' rows included
    score_detail the strongest row of each claim and what it counted, the multiplier, the tactic points
    coverage      claims found / checked / contradicted / consistent / not checkable, why some checks could not run, one plain sentence
    header_findings the cleaned header evidence the header verifier read (evidence, not rows)
    thread        None for one email; for a thread: judged_index, flip_index, signals of the judged message, a timeline of every message

Security. The report is built for a browser that must never run anything from an email, so:
    - the text shown (text_read, signature_read, claim and highlight text) is DISPLAY-SAFE: '<' and '>' are shown as the look-alike
      characters U+2039 and U+203A, backticks as apostrophes and control or invisible characters as spaces, one character for one, so every offset still fits;
    - strings that came from the email in other places (display name, subject, claimed organisation) go through clean_text or clean_domain
      (letters, digits, spaces and . , - _ ' & ( ) only); reasons are built from validated values (src/verifiers/rows.py);
    - check_report verifies all of this on every report before it is returned, and no string of the report holds '<', '>' or a backtick;
    - sizes are capped: 300,000 bytes per message, 50 messages per thread, 2,000 characters read per body, 1,000 per signature, 20 levels of nested MIME parts;
    - nothing is written to disk and nothing is logged here (the API logs the request id, score and band, never content).
"""

import email
import sys
import time
import uuid

from src.claims.patterns import PATTERN_VERSION
from src.claims.schema import SIGNATURE_CHARS, check_claim
from src.data.label_schema import TACTICS
from src.explain.lime_explain import DEFAULT_SAMPLES, explain_text
from src.headers.build import organisation_domain
from src.headers.domains import is_freemail, registered_domain
from src.headers.evidence import header_evidence
from src.headers.parser import body_text, parse_header_fields, split_headers
from src.models.dataset import model_text
from src.preprocess.clean import clean_body
from src.preprocess.redact import redact
from src.router import ledger as ledger_module
from src.router.router import assign, check_routing
from src.router.score import DEFAULT_CONFIG, SCORE_VERSION, SCORED_TACTICS, action_for, band_of, fired_tactics, score_ledger
from src.thread import builder
from src.thread.signals import MAX_MESSAGES
from src.verifiers.facts import CONTACT_CHARS, prepare_facts
from src.verifiers.rows import check_row, clean_domain, clean_text, simple
from src.verifiers.thread_verifier import THREAD_RULES_VERSION, scan_thread, signal_rows
from src.verifiers.verify import RULES_VERSION, verify_claims

MAX_RAW_BYTES = 300_000          # bytes read from one message (the thread code reads no more)
MAX_REQUEST_ID = 64
MAX_MIME_DEPTH = 20              # nested multipart levels read (a real email has fewer than ten); a deeper one is read as plain text
HEADER_SCAN_BYTES = 8192
HEADER_NAMES = frozenset((b"from", b"to", b"subject", b"date", b"received", b"message-id", b"return-path", b"mime-version", b"delivered-to", b"reply-to",
                          b"content-type", b"authentication-results", b"dkim-signature", b"list-id", b"in-reply-to", b"references", b"sender", b"cc", b"bcc"))
THREAD_CLAIMS = frozenset(("prior_relationship", "payment_request", "payment_change", "credential_request", "gift_card", "data_request"))
SAFE_MAP = {ord("<"): "‹", ord(">"): "›", ord("`"): "'"}
FINDING_KEYS = ("from_name", "from_domain", "reply_domain", "spf", "dkim", "dmarc", "auth_state", "authenticated_domain", "freemail", "list_mail",
                "name_address", "name_domain", "reply_to_divergence", "envelope_mismatch", "org_domain", "org_checkable", "from_matches_org", "org_lookalike_score")
REPORT_KEYS = {"request_id", "mode", "score", "verdict", "action", "org_domain", "versions", "text_read", "signature_read", "tactics", "explained", "claims", "routing",
               "ledger", "score_detail", "coverage", "header_findings", "thread"}


class ReportError(RuntimeError):
    """The report broke one of its own rules. This is a bug, never bad input: the caller should answer with a server error and log the request id."""


# ---------------------------------------------------------------------------------------------------------- text helpers

def display_safe(text):
    """The text with '<' '>' '`' replaced and every unprintable character turned into a space; the length is unchanged."""
    return "".join(ch if (ch.isprintable() or ch == " ") else " " for ch in text.translate(SAFE_MAP))


def to_bytes(raw):
    if isinstance(raw, str):
        return raw.encode("utf-8", errors="replace")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    raise TypeError("an email must be text or bytes, not %s" % type(raw).__name__)


def looks_like_headers(data):
    """True when the first non-empty line is a header line ('From: ...', 'Received: ...', 'X-Mailer: ...') or an mbox 'From user@host date' line.

    A pasted body starts with a greeting. Plain string tests on the first line only, no regular expression."""
    first = data[:HEADER_SCAN_BYTES].lstrip(b"\xef\xbb\xbf \t\r\n").split(b"\n", 1)[0]
    if first.lower().startswith(b"from "):
        parts = first.split()
        return len(parts) >= 3 and b"@" in parts[1]
    if b":" not in first:
        return False
    name = first.split(b":", 1)[0].strip().lower()
    return name in HEADER_NAMES or (name.startswith((b"x-", b"arc-")) and b" " not in name)


def usable_org(org_domain):
    """(registered domain or None, True when a value was given but not usable). A free mailbox provider is not an organisation (as in Phase 3)."""
    if org_domain is None or (isinstance(org_domain, str) and not org_domain.strip()):
        return None, False
    domain = clean_domain(org_domain) if isinstance(org_domain, str) else None
    domain = registered_domain(domain) if domain and "." in domain else None
    if not domain or is_freemail(domain):
        return None, True
    return domain, False


def mime_depth(message):
    """How deeply the parts of a parsed message are nested (1 for a single part). Counted with a list, not recursion, and it stops once the depth is over the limit."""
    deepest, stack = 1, [(message, 1)]
    while stack:
        part, depth = stack.pop()
        deepest = max(deepest, depth)
        if depth > MAX_MIME_DEPTH:
            break
        if part.is_multipart():
            stack.extend((child, depth + 1) for child in part.get_payload())
    return deepest


def text_after_headers(data):
    """Everything after the first blank line, decoded as text (the whole data when there is no blank line)."""
    data = data.replace(b"\r\n", b"\n")
    end = data.find(b"\n\n")
    return (data if end == -1 else data[end + 2:]).decode("utf-8", errors="replace")


def read_body(data):
    """(body text, True when the parts were nested too deeply to read). Python's own parser and walker recurse once per level, so 3,000 nested
    parts in 150 KB end in RecursionError. Too deep (over MAX_MIME_DEPTH, or the parser gave up) means the text after the header block is read as
    it is, and the coverage says so. Attachments are never opened either way (body_text skips them)."""
    try:
        message = email.message_from_bytes(data)
        if mime_depth(message) <= MAX_MIME_DEPTH:
            return body_text(message), False
    except RecursionError:
        pass
    return text_after_headers(data), True


def parse_message(raw, org, key):
    """One message parsed: record (the thread message dictionary), headers_found, truncated, mime_too_deep. Never raises on odd input; a broken header costs only its own field."""
    data = to_bytes(raw)
    truncated = len(data) > MAX_RAW_BYTES
    data = data[:MAX_RAW_BYTES]
    found = looks_like_headers(data)
    too_deep = False
    if found:
        fields, _ = parse_header_fields(split_headers(data))
        body, too_deep = read_body(data)
    else:
        fields, _ = parse_header_fields("")
        body = data.decode("utf-8", errors="replace")
    used = org or organisation_domain(fields.get("to_domain"))
    evidence = header_evidence(fields, used)
    record = builder.message_record(key, "analyze", fields, evidence, body)
    return {"record": record, "headers_found": found, "truncated": truncated, "mime_too_deep": too_deep, "body": body}


def read_texts(redacted, signature):
    """(text read from the body, redacted signature read), exactly as the claim extractor reads them (src/claims/extractor.py prepare)."""
    sig = redact(signature[:SIGNATURE_CHARS])[0].strip() if isinstance(signature, str) else ""
    return model_text(redacted), sig


# ------------------------------------------------------------------------------------------------------------ the analyzer

class Analyzer:
    """The loaded pipeline. Create it once (the model and spaCy load here) and call analyze many times.

    classifier   anything with .thresholds ({tactic: number}) and .probabilities(list of texts) -> array (n, 7) in TACTICS order;
                 the default is the trained TacticClassifier (torch is imported only then)
    extractor    a function (list of redacted bodies, list of signatures) -> list of claim lists; the default is the Phase 7 extractor
    config       the score configuration (src/router/score.py make_config); the frozen one by default
    explain_samples  LIME copies per explanation (50 to 2,000)
    """

    def __init__(self, classifier=None, extractor=None, config=None, explain_samples=DEFAULT_SAMPLES):
        if classifier is None:
            from src.models.predict import TacticClassifier
            classifier = TacticClassifier()
        if extractor is None:
            from src.claims.extractor import extract_many
            extractor = lambda bodies, signatures: extract_many(bodies, signatures)[0]
        self.classifier, self.extractor = classifier, extractor
        self.config = config or DEFAULT_CONFIG
        self.explain_samples = explain_samples

    # -- the two entry points -------------------------------------------------------------------------------------------

    def analyze(self, raw, org_domain=None, explain=True, request_id=None):
        """The report for one email (text or bytes) or one thread (a list of them, the newest judged). Raises ReportError only on a bug."""
        rid = self.request_id(request_id)
        org, ignored = usable_org(org_domain)
        limits = ["org_domain_ignored"] if ignored else []
        if isinstance(raw, (list, tuple)):
            if not raw:
                raise ValueError("a thread needs at least one message")
            report = self.run(list(raw), org, explain, rid, limits, thread=True)
        else:
            report = self.run([raw], org, explain, rid, limits, thread=False)
        problems = check_report(report, self.config)
        if problems:
            raise ReportError("request %s: the report failed its own checks: %s" % (rid, "; ".join(problems[:5])))
        return report

    @staticmethod
    def request_id(value):
        if value is None:
            return uuid.uuid4().hex
        text = str(value)
        if not text or len(text) > MAX_REQUEST_ID or not all(ch.isalnum() or ch in "-_" for ch in text):
            raise ValueError("request_id must be 1 to %d letters, digits, - or _" % MAX_REQUEST_ID)
        return text

    # -- the pipeline ---------------------------------------------------------------------------------------------------

    def run(self, raws, org, explain, rid, limits, thread):
        limits = list(limits)
        parsed = [parse_message(raw, org, "m%d" % i) for i, raw in enumerate(raws)]
        if any(p["truncated"] for p in parsed):
            limits.append("text_truncated")
        if len(parsed) > MAX_MESSAGES:
            parsed = parsed[-MAX_MESSAGES:]
            limits.append("thread_truncated")
        if any(p["mime_too_deep"] for p in parsed):
            limits.append("mime_too_deep")
        if thread and len(parsed) > 1:
            stamps = [builder.timestamp(p["record"]["date"]) for p in parsed]
            if all(s is not None for s in stamps):
                parsed = [p for _, _, p in sorted(zip(stamps, range(len(parsed)), parsed), key=lambda t: (t[0], t[1]))]
            else:
                limits.append("thread_unordered")
        records = [p["record"] for p in parsed]
        for i, record in enumerate(records):
            record["key"] = "m%d" % i
        judged = parsed[-1]
        me = judged["record"]
        cleaned = clean_body(judged["body"])
        signature = cleaned["signature"]
        contact = signature if signature.strip() else cleaned["body_clean"][-CONTACT_CHARS:]

        # tactic probabilities and claims for every message (the thread signals compare messages with each other)
        probabilities = self.classifier.probabilities([r["redacted"] for r in records])
        claim_lists = self.extractor([r["redacted"] for r in records], [None] * (len(records) - 1) + [signature])
        thresholds = dict(self.classifier.thresholds)
        for record, row, found in zip(records, probabilities, claim_lists):
            record["tactics"] = {t: round(float(p), 4) for t, p in zip(TACTICS, row)}
            record["claims"] = found
        claims = me["claims"]
        text_original, sig_original = read_texts(me["redacted"], signature)

        # route and verify
        assignments, _ = assign(claims, has_thread=thread and len(records) > 1)
        if thread and len(records) > 1:
            scan = scan_thread(records, thresholds)
            claim_rows = verify_claims(claims, me["facts"], contact, text_original, thread=(records, len(records) - 1))
            signals = [r for r in scan["messages"][-1]["rows"] if r["claim_id"] == "thread"]
        else:
            scan = None
            claim_rows = verify_claims(claims, me["facts"], contact, text_original)
            signals = signal_rows([], me, thresholds)
        rows, problems = ledger_module.build_ledger(claims, assignments, claim_rows, signals)
        if problems:
            raise ReportError("request %s: the ledger broke its rules: %s" % (rid, "; ".join(problems[:5])))

        # score
        fired = fired_tactics(me["tactics"], thresholds)
        tactics = [{"name": t, "probability": me["tactics"][t], "threshold": round(float(thresholds[t]), 4),
                    "fired": t in fired, "scored": t in SCORED_TACTICS, "highlights": []} for t in TACTICS]
        detail = score_ledger(rows, fired, self.config)

        # LIME for the tactics that fired
        explained = False
        if explain and fired:
            columns = {t: TACTICS.index(t) for t in fired}
            lime = explain_text(text_original, self.classifier.probabilities, columns, num_samples=self.explain_samples)
            for entry in tactics:
                if entry["name"] in lime:
                    entry["highlights"] = [{"start": h["start"], "end": h["end"], "text": display_safe(h["text"]), "weight": h["weight"], "word": display_safe(h["word"])}
                                           for h in lime[entry["name"]]["highlights"]]
            explained = bool(lime)

        # coverage
        facts = prepare_facts(me["facts"])
        if not judged["headers_found"]:
            limits.append("headers_missing")
        else:
            if not facts["from_domain"]:
                limits.append("no_from")
            if facts["auth_state"] == "unknown":
                limits.append("no_authentication")
        if not facts["org_domain"] and any(c["type"] == "affiliation_internal" for c in claims) and "org_domain_ignored" not in limits:
            limits.append("no_org_domain")
        if not (thread and len(records) > 1) and any(c["type"] in THREAD_CLAIMS for c in claims):
            limits.append("single_email")
        coverage = ledger_module.coverage(claims, rows, limits)

        safe_text, safe_sig = display_safe(text_original), display_safe(sig_original)
        return {
            "request_id": rid, "mode": "thread" if thread and len(records) > 1 else "email", "score": detail["score"], "verdict": detail["band"],
            "action": action_for(detail["band"], detail), "org_domain": clean_domain(facts["org_domain"]),
            "versions": {"score": SCORE_VERSION, "rules": RULES_VERSION, "thread_rules": THREAD_RULES_VERSION, "claim_patterns": PATTERN_VERSION},
            "text_read": safe_text, "signature_read": safe_sig, "tactics": tactics, "explained": explained,
            "claims": [safe_claim(c, safe_text, safe_sig) for c in claims], "routing": assignments, "ledger": rows, "score_detail": detail,
            "coverage": coverage, "header_findings": header_findings(facts, judged["headers_found"]), "thread": thread_section(scan, records, rows),
        }


def safe_claim(claim, safe_text, safe_sig):
    """The claim for the report: its text is the slice of the display-safe text it points into, and its attributes are cleaned."""
    attributes = claim.get("attributes") or {}
    start, end = claim["span"]
    source = safe_text if attributes.get("zone") == "body" else safe_sig
    return {"claim_id": claim["claim_id"], "type": claim["type"], "text": source[start:end], "span": [start, end], "confidence": claim["confidence"],
            "attributes": {"person": clean_text(attributes.get("person")) or None, "organisation": clean_text(attributes.get("organisation")) or None,
                           "department": clean_text(attributes.get("department")) or None, "pattern": clean_text(attributes.get("pattern")), "zone": attributes.get("zone")}}


def header_findings(facts, headers_found):
    """The cleaned header evidence the header verifier read. Addresses are not included, only domains; free text goes through clean_text."""
    out = {"headers_found": bool(headers_found)}
    for key in FINDING_KEYS:
        value = facts.get(key)
        out[key] = clean_text(value) or None if key == "from_name" else clean_domain(value) if key.endswith("domain") else simple(value)
    return out


def thread_section(scan, records, rows):
    """None for one email; for a thread the judged index, the flip index, the signals that fired for the judged message and a timeline."""
    if scan is None:
        return None
    last = len(records) - 1
    signals = [{"claim_type": r["claim_type"], "rule": r["rule"], "severity": r["severity"], "reason": r["reason"]}
               for r in rows if r["claim_id"] == "thread" and r["contradiction"] is True]
    timeline = [{"index": m["index"], "from_domain": clean_domain(records[m["index"]]["from_domain"]), "subject": clean_text(records[m["index"]]["subject"]),
                 "worst": m["worst"], "rules": m["rules"]} for m in scan["messages"]]
    return {"messages": len(records), "judged_index": last, "flip_index": scan["flip_index"], "signals": signals, "timeline": timeline}


# -------------------------------------------------------------------------------------------------------------- the checks

def strings_of(value):
    """Every string inside nested dictionaries and lists."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_of(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings_of(item)


def check_report(report, config=None):
    """The ways a report breaks the contract of Section 6.3 and this file (an empty list when it is sound). analyze runs it on every report."""
    config = config or DEFAULT_CONFIG
    if not isinstance(report, dict) or set(report) != REPORT_KEYS:
        return ["keys are %s" % (sorted(set(report) ^ REPORT_KEYS) if isinstance(report, dict) else type(report).__name__)]
    problems = []
    rid = report["request_id"]
    if not (isinstance(rid, str) and 1 <= len(rid) <= MAX_REQUEST_ID and all(ch.isalnum() or ch in "-_" for ch in rid)):
        problems.append("request_id")
    if report["mode"] not in ("email", "thread"):
        problems.append("mode")
    score = report["score"]
    if not (isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100):
        problems.append("score %r" % (score,))
    elif report["verdict"] != band_of(score, config["cuts"]):
        problems.append("verdict %r does not fit score %d" % (report["verdict"], score))
    if not isinstance(report["action"], str) or not report["action"]:
        problems.append("action")
    text, sig = report["text_read"], report["signature_read"]
    if not isinstance(text, str) or len(text) > 2000 or not isinstance(sig, str) or len(sig) > SIGNATURE_CHARS:
        problems.append("text_read or signature_read")
        return problems
    # tactics
    tactics = report["tactics"]
    if [t.get("name") for t in tactics] != list(TACTICS):
        problems.append("tactics are not the seven in order")
        return problems
    for t in tactics:
        if not 0.0 <= t["probability"] <= 1.0:
            problems.append("probability of %s" % t["name"])
        if t["fired"] != (t["probability"] >= t["threshold"]):
            problems.append("fired flag of %s" % t["name"])
        if t["scored"] != (t["name"] in SCORED_TACTICS):
            problems.append("scored flag of %s" % t["name"])
        if t["highlights"] and not t["fired"]:
            problems.append("highlights on a tactic that did not fire (%s)" % t["name"])
        for h in t["highlights"]:
            if not (0 <= h["start"] < h["end"] <= len(text)) or text[h["start"]:h["end"]] != h["text"]:
                problems.append("highlight of %s does not match the text" % t["name"])
    fired = [t["name"] for t in tactics if t["fired"]]
    # claims and routing
    claims = report["claims"]
    for c in claims:
        problems += ["claim %s: %s" % (c["claim_id"], p) for p in check_claim(c, text, sig)]
    ledger_rows = report["ledger"]
    claim_ids = {c["claim_id"] for c in claims}
    for row in ledger_rows:
        problems += ["row %s: %s" % (row.get("rule"), p) for p in check_row(row, ledger_module.KNOWN_RULES)]
    if [a["claim_id"] for a in report["routing"]] != [c["claim_id"] for c in claims]:
        problems.append("routing does not list the claims in order")
    problems += check_routing(report["routing"], [r for r in ledger_rows if r["claim_id"] != "thread"])
    for row in ledger_rows:
        if row["claim_id"] != "thread" and row["claim_id"] not in claim_ids:
            problems.append("row %s names an unknown claim" % row["rule"])
    # the score must be what the ledger and the tactics give
    expected = score_ledger(ledger_rows, fired, config)
    if report["score_detail"] != expected:
        problems.append("score_detail is not what the ledger and the tactics give")
    elif score != expected["score"]:
        problems.append("score does not equal score_detail")
    if report["coverage"] != ledger_module.coverage(claims, ledger_rows, report["coverage"].get("limits", [])):
        problems.append("coverage is not what the ledger gives")
    if (report["thread"] is None) != (report["mode"] == "email"):
        problems.append("thread section does not fit the mode")
    elif report["thread"] is not None:
        th = report["thread"]
        if th["judged_index"] != th["messages"] - 1 or len(th["timeline"]) != th["messages"]:
            problems.append("thread timeline")
        if th["flip_index"] is not None and not 1 <= th["flip_index"] < th["messages"]:
            problems.append("flip index")
    # nothing that could run in a browser
    for value in strings_of(report):
        if "<" in value or ">" in value or "`" in value:
            problems.append("a string holds '<', '>' or a backtick")
            break
    return problems


# ------------------------------------------------------------------------------------------------- module function and CLI

_ANALYZER = None


def get_analyzer():
    """The shared Analyzer, created on first use (loads the model and spaCy)."""
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = Analyzer()
    return _ANALYZER


def analyze(raw, org_domain=None, explain=True, request_id=None):
    """The report for one email (text or bytes) or one thread (a list of them). See the module text."""
    return get_analyzer().analyze(raw, org_domain, explain, request_id)


def print_report(report):
    detail = report["score_detail"]
    print("Score %d  %s   (%s mode, request %s)" % (report["score"], report["verdict"].upper(), report["mode"], report["request_id"]))
    print("Action: %s" % report["action"])
    print("Coverage: %s" % report["coverage"]["note"])
    print("\nTactics (probability / threshold; * = fired; only authority, urgency, scarcity and secrecy are scored):")
    for t in report["tactics"]:
        best = {}
        for h in t["highlights"]:
            word = best.setdefault(h["word"].lower(), [h["weight"], 0])
            word[1] += 1
        ranked = sorted(best.items(), key=lambda item: -item[1][0])[:6]
        words = ", ".join("%s %.2f%s" % (w, weight, " x%d" % n if n > 1 else "") for w, (weight, n) in ranked)
        print("  %-13s %.2f / %.2f %s %s" % (t["name"], t["probability"], t["threshold"], "*" if t["fired"] else " ", ("top words: " + words) if words else ""))
    print("\nLedger (%d rows). Counted in the score, strongest first:" % len(report["ledger"]))
    for g in detail["groups"]:
        print("  %-8s %-22s %-24s %-6s x%.2f -> %5.1f  %s" % (g["verifier"], g["claim_type"], g["rule"], g["severity"], g["weight"], g["counted"], g["reason"][:110]))
    if not detail["groups"]:
        print("  (no contradiction)")
    print("  contradiction points %.1f x multiplier %.2f + tactic points %d = %.1f%s" % (
        detail["contradiction_points"], detail["multiplier"], detail["tactic_points"], detail["raw"], "  (capped at 100)" if detail["capped"] else ""))
    others = [r for r in report["ledger"] if r["contradiction"] is not True]
    print("\nOther rows (consistent or not checkable; they add nothing):")
    for r in others:
        print("  %-8s %-22s %-24s %-13s %s" % (r["verifier"], r["claim_type"], r["rule"], r["severity"], r["reason"][:100]))
    if report["thread"]:
        th = report["thread"]
        print("\nThread: %d messages, judged message %d, flip at %s" % (th["messages"], th["judged_index"], th["flip_index"]))
        for m in th["timeline"]:
            print("  %2d %-24s %-40s worst %-6s %s" % (m["index"], m["from_domain"] or "-", m["subject"][:40], m["worst"] or "-", ",".join(m["rules"])))


def main(argv):
    import json
    args = list(argv)
    flags = {"--no-explain": False, "--json": False, "--thread": False}
    org = None
    files = []
    while args:
        arg = args.pop(0)
        if arg == "--org":
            org = args.pop(0) if args else None
        elif arg in flags:
            flags[arg] = True
        else:
            files.append(arg)
    if not files:
        raise SystemExit("Usage: python -m src.router.pipeline FILE [--org DOMAIN] [--no-explain] [--json]\n"
                         "       python -m src.router.pipeline --thread FILE1 FILE2 ... [--org DOMAIN]   (any order: the newest message by Date is judged)")
    blobs = []
    for name in files:
        with open(name, "rb") as handle:
            blobs.append(handle.read(MAX_RAW_BYTES + 1))
    started = time.time()
    report = analyze(blobs if flags["--thread"] else blobs[0], org_domain=org, explain=not flags["--no-explain"])
    if flags["--json"]:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
        print("\n%.1f seconds" % (time.time() - started))


if __name__ == "__main__":
    main(sys.argv[1:])
