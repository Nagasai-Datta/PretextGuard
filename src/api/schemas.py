"""Phase 11: the shapes of what goes into and comes out of the API (Pydantic).

A Pydantic model is a class that describes a JSON object: the fields, their types and their limits. `Model.model_validate_json(bytes)` parses the
text, checks every field and either returns an object or raises ValidationError. In JavaScript terms it is a Joi or Zod schema. The checks run
before any of our code touches the data, so nothing that has the wrong shape, type or size gets further.

REQUESTS (what a client may send; every model refuses unknown fields and does not convert types, so {"email": 123} is an error, not "123"):
    AnalyzeRequest   {"email": "...", "org_domain": "acmecorp.com"}               org_domain is optional
    ThreadRequest    {"messages": ["...", "..."], "org_domain": "acmecorp.com"}   1 to 50 messages
    ExplainRequest   exactly one of "email" or "messages", plus the optional org_domain

RESPONSES (what the API promises): Report is the report of master document Section 6.3 as analyze() builds it. The top level, the tactics, the
highlights and the ledger rows are typed; claims, routing, score_detail, coverage, header_findings and thread stay free-form dictionaries because
their shape belongs to the pipeline (src/router/pipeline.py checks it on every report with check_report). The models forbid unknown fields, so if
the pipeline ever adds a field the API refuses to send an unchecked report: the self-test passes real analyze() output of every mode through them.

ERRORS never repeat what the client sent. safe_errors keeps only where the problem is (the field name, or '?' for a name nobody declared, because
an attacker can choose the name of an extra field) and the kind of problem (Pydantic's fixed vocabulary, such as string_too_long).
"""

import json
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.api.settings import MAX_DOMAIN_CHARS, MAX_EMAIL_BYTES, MAX_THREAD_BYTES, MAX_THREAD_MESSAGES

LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
KNOWN_LOC = frozenset(("body", "query", "email", "messages", "org_domain", "name"))
MAX_TOP_LEVEL_KEYS = 10        # a request object has at most three fields; more is junk, refused before Pydantic builds one error per extra key


# ----------------------------------------------------------------------------------------------------------------- field checks

def check_email_bytes(value):
    """An email may hold at most MAX_EMAIL_BYTES bytes of UTF-8. (The field's own max_length counts characters, which is the cheap first test.)
    errors='replace' because JSON can carry a lone surrogate that has no UTF-8 form; the pipeline encodes the same way."""
    if len(value.encode("utf-8", errors="replace")) > MAX_EMAIL_BYTES:
        raise ValueError("email too large")
    return value


def check_domain(value):
    """None, or a domain name in lower case: letters, digits, hyphens and dots, labels of 1 to 63 characters that neither start nor end with a hyphen,
    at most 253 characters, one trailing dot allowed. Plain character tests, no regular expression. An empty text means 'not given'.
    Whether the domain is usable (not a free mailbox provider, has a dot) is the pipeline's job and ends in a note in the coverage."""
    if value is None:
        return None
    text = value.strip()
    if text.endswith("."):
        text = text[:-1]
    if not text:
        return None
    text = text.lower()
    if len(text) > MAX_DOMAIN_CHARS:
        raise ValueError("domain too long")
    for label in text.split("."):
        if not 1 <= len(label) <= 63 or label[0] == "-" or label[-1] == "-" or not set(label) <= LABEL_CHARS:
            raise ValueError("not a domain name")
    return text


EmailText = Annotated[str, Field(min_length=1, max_length=MAX_EMAIL_BYTES), AfterValidator(check_email_bytes)]
OrgDomain = Annotated[str | None, Field(max_length=MAX_DOMAIN_CHARS + 50), AfterValidator(check_domain)]


def thread_bytes(messages):
    return sum(len(m.encode("utf-8", errors="replace")) for m in messages)


# ------------------------------------------------------------------------------------------------------------------- requests

class Strict(BaseModel):
    """Requests: unknown fields and wrong types are errors."""
    model_config = ConfigDict(extra="forbid", strict=True)


class Typed(BaseModel):
    """Responses: unknown fields are errors (so a change in the pipeline cannot slip through unchecked), but a number that arrives as an int where a
    float is declared is fine. check_report in the pipeline has already checked the values."""
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(Strict):
    email: EmailText
    org_domain: OrgDomain = None


class ThreadRequest(Strict):
    messages: Annotated[list[EmailText], Field(min_length=1, max_length=MAX_THREAD_MESSAGES)]
    org_domain: OrgDomain = None

    @model_validator(mode="after")
    def total_size(self):
        if thread_bytes(self.messages) > MAX_THREAD_BYTES:
            raise ValueError("thread too large")
        return self


class ExplainRequest(Strict):
    email: EmailText | None = None
    messages: Annotated[list[EmailText], Field(min_length=1, max_length=MAX_THREAD_MESSAGES)] | None = None
    org_domain: OrgDomain = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.email is None) == (self.messages is None):
            raise ValueError("give exactly one of email or messages")
        if self.messages is not None and thread_bytes(self.messages) > MAX_THREAD_BYTES:
            raise ValueError("thread too large")
        return self


# ------------------------------------------------------------------------------------------------------------------ responses

class Highlight(Typed):
    start: int
    end: int
    text: str
    weight: float
    word: str


class Tactic(Typed):
    name: str
    probability: float
    threshold: float
    fired: bool
    scored: bool
    highlights: list[Highlight]


class LedgerRow(Typed):
    claim_id: str
    claim_type: str
    verifier: Literal["header", "request", "thread"]
    rule: str
    evidence: dict[str, Any]
    contradiction: bool | None
    severity: Literal["none", "low", "medium", "high", "not_checkable"]
    reason: str


class Report(Typed):
    request_id: str
    mode: Literal["email", "thread"]
    score: int = Field(ge=0, le=100)
    verdict: Literal["Low risk", "Suspicious", "High risk"]
    action: str
    org_domain: str | None
    versions: dict[str, str]
    text_read: str
    signature_read: str
    tactics: list[Tactic]
    explained: bool
    claims: list[dict[str, Any]]
    routing: list[dict[str, Any]]
    ledger: list[LedgerRow]
    score_detail: dict[str, Any]
    coverage: dict[str, Any]
    header_findings: dict[str, Any]
    thread: dict[str, Any] | None


class ErrorItem(Typed):
    loc: list[str | int]
    type: str


class ErrorResponse(Typed):
    detail: str
    code: str
    request_id: str | None = None
    errors: list[ErrorItem] | None = None


class Health(Typed):
    status: Literal["ok", "unavailable"]
    model_loaded: bool
    explain_samples: int
    versions: dict[str, str]
    results_files: int


class ResultEntry(Typed):
    name: str
    description: str
    columns: list[str]
    rows: int


class ResultIndex(Typed):
    files: list[ResultEntry]
    missing: list[str]


class ResultTable(Typed):
    name: str
    description: str
    columns: list[str]
    rows: list[dict[str, Any]]


# ------------------------------------------------------------------------------------------------------------- safe error lists

def safe_errors(errors, limit=10):
    """[{'loc': [...], 'type': '...'}] from Pydantic's or FastAPI's error list: where and what kind, never what was sent.
    A location part that is not a declared field name (an attacker can choose it) becomes '?'; at most `limit` entries."""
    cleaned = []
    for item in list(errors)[:limit]:
        loc = [part if isinstance(part, int) or part in KNOWN_LOC else "?" for part in item.get("loc", ())][:6]
        kind = str(item.get("type", "error"))
        if len(kind) > 60 or not all(ch.isalnum() or ch in "_." for ch in kind):
            kind = "error"
        cleaned.append({"loc": loc, "type": kind})
    return cleaned


class InvalidRequest(Exception):
    """The request body did not match the model. `errors` is already safe: where and what kind, never what was sent."""

    def __init__(self, errors):
        super().__init__("invalid request")
        self.errors = errors


def parse_request(model, body):
    """The model built from the JSON bytes of a request body, or InvalidRequest.

    Four steps: strict UTF-8, the standard JSON parser (nesting that is too deep ends in RecursionError, which is just 'invalid'), a look at the top
    level (an object with at most MAX_TOP_LEVEL_KEYS keys: 3.5 MB of made-up keys otherwise cost Pydantic 2.3 seconds to describe as errors), then
    the Pydantic model (which refuses a lone surrogate such as "\\ud800" as string_unicode)."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise InvalidRequest([{"loc": [], "type": "json_invalid"}])
    if not isinstance(data, dict):
        raise InvalidRequest([{"loc": [], "type": "model_type"}])
    if len(data) > MAX_TOP_LEVEL_KEYS:
        raise InvalidRequest([{"loc": [], "type": "too_many_fields"}])
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise InvalidRequest(safe_errors(error.errors(include_url=False, include_context=False, include_input=False)))
