"""Phase 7: the claim object that extractor.py returns and the verifiers (Phases 8 and 9) will read.

A claim is a plain dictionary in the form of master document Section 6.3:

    {"claim_id": "c1",
     "type": "affiliation_internal",              one of the eleven types of src/data/label_schema.py
     "text": "this is David from Finance",         exactly the words of the email that make the claim
     "span": [10, 36],                             where they start and end (character offsets, see below)
     "attributes": {"person": "David", "organisation": null, "department": "Finance",
                    "pattern": "ai_this_is_from", "zone": "body"},
     "confidence": 0.9}

Spans are offsets into the text that was searched. zone says which text: "body" is the email as the classifier
reads it (body_redacted cut at 2,000 characters, see model_text in src/models/dataset.py), "signature" is the
signature block when it lies outside that cut. text always equals the zone's text[start:end], which is what
check_claim verifies, so a highlight in the report can never point at the wrong words.

confidence is not a probability. It is the strength of the rule that fired: 0.9 for a strong phrase, 0.6 for a
weak one (patterns.py explains the two). The verifiers use it to weigh a finding; nothing calibrates it.
"""

from src.data.label_schema import CLAIM_TYPES

MAX_CLAIMS = 12          # claims per email, the same cap Phase 5 put on the annotators
MAX_PER_TYPE = 3         # claims of one type per email: three examples are as good as ten for a verifier
SIGNATURE_CHARS = 1000   # the signature block is cut here before it is read
ZONES = ("body", "signature")
CONFIDENCES = (0.6, 0.9)


def make_claim(number, claim_type, text, start, end, confidence, attributes):
    """Build one claim dictionary. number is 1, 2, 3 ... in order of appearance."""
    return {"claim_id": "c%d" % number, "type": claim_type, "text": text, "span": [start, end],
            "attributes": attributes, "confidence": confidence}


def check_claim(claim, body, signature=""):
    """Return a list of problems with one claim (empty when it is valid). body and signature are the texts searched."""
    problems = []
    if claim.get("type") not in CLAIM_TYPES:
        problems.append("unknown type %r" % claim.get("type"))
    zone = claim.get("attributes", {}).get("zone")
    if zone not in ZONES:
        problems.append("unknown zone %r" % zone)
        return problems
    source = body if zone == "body" else signature
    start, end = claim["span"]
    if not (0 <= start < end <= len(source)):
        problems.append("span %r outside the %s (length %d)" % (claim["span"], zone, len(source)))
    elif source[start:end] != claim["text"]:
        problems.append("text does not equal the span")
    if claim.get("confidence") not in CONFIDENCES:
        problems.append("confidence %r" % claim.get("confidence"))
    return problems
