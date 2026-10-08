# src/claims/

Phase 7: the claim extractor. It reads one email and returns the **claims** the email makes about itself: who is writing, what rank they hold, where to reply, what they want. A verifier (Phases 8 and 9) can then check each claim against evidence the sender cannot easily fake. The tactic classifier (Phase 6) says *how* the writer pushes; the extractor says *what the writer asserts*.

```bash
python -m src.claims.extractor           # self-test: ten hand-made emails (one with no claims, one that must not match), non-text input, eight crafted 200,000-character inputs
python -m src.claims.build --train-only --limit 6000       # a quick development run (about 3 minutes): a random 6,000 train emails for the hit rates
python -m src.claims.build --train-only --limit 6000 --diagnose signature_contact,payment_request
                                         # also prints, for labelled TRAIN emails, the claims it misses and the ones nobody labelled (never saved)
python -m src.claims.build --train-only  # all 69,542 train emails: about 20 minutes; validation is never loaded
python -m src.claims.build               # the final run of a frozen version: also scores the validation emails, once
```

```python
from src.claims.extractor import extract_claims

claims = extract_claims(body_redacted, signature)       # signature may be None
# for "Hello, this is David from Finance. Please process the wire transfer before 3 PM today." the first claim is
claims[0]   # {"claim_id": "c1", "type": "affiliation_internal", "text": "this is David from Finance", "span": [7, 33],
            #  "attributes": {"person": "David", "organisation": None, "department": "Finance", "pattern": "ai_this_is_from", "zone": "body"},
            #  "confidence": 0.9}   (the second is a payment_request: "process the wire transfer")
```

## Files

| File | Job |
|---|---|
| `schema.py` | The claim dictionary of master document Section 6.3 (`make_claim`), the limits (12 claims per email, 3 per type), and `check_claim`, which verifies that a claim's text really is its span |
| `patterns.py` | The phrase patterns (data only, in a small pattern language), the role and organisation word lists, `PATTERN_VERSION` |
| `extractor.py` | `extract_claims(body, signature)`, `extract_many(...)` for batches, the pattern compiler, the organisation and signature rules, and the self-test |
| `build.py` | Hit rates on the train split, scores against the Phase 5 labels, and the checks; writes `results/claim_*.csv` |

## The eleven claim types

The same eleven as the annotation (`CLAIM_TYPES` in `src/data/label_schema.py`) and the routing table of master document Section 6.4:

| Type | What it says | Routed to (Phases 8 and 9) |
|---|---|---|
| `affiliation_internal` | "this is David from Finance", "IT help desk": the sender belongs to the reader's own organisation | Header verifier (needs the organisation domain) |
| `affiliation_external` | "PayPal Security Team", "Bank of Africa": the sender represents an outside organisation | Header verifier |
| `authority` | "I am the Internal Auditor", "As the CEO": a rank or role that gives power | Header verifier |
| `reply_direction` | "reply to my private email", "text me on WhatsApp": reply somewhere other than here | Header verifier (Reply-To against From) |
| `signature_contact` | a signature or footer with a phone number or address | Header verifier (signature address against From) |
| `prior_relationship` | "as we discussed", "great seeing you last week" | Thread verifier |
| `payment_request`, `payment_change`, `credential_request`, `gift_card`, `data_request` | what the sender wants | Request verifier, plus thread verifier for request drift |

## How an email becomes claims

1. **What is read.** `model_text(body)`: `body_redacted` cut at 2,000 characters, exactly the text the annotators labelled. The signature block is read too: the `signature` column of `cleaned.parquet` is cut from `body_clean`, so it still holds raw addresses and links; `extract_claims` redacts it first (Phase 2's `redact`) and cuts it at 1,000 characters. If the redacted signature is already inside the body text, it is not read twice; if the body was cut before the signature, the signature is read as its own zone.
2. **spaCy** (`en_core_web_sm`, only the tokenizer and the named-entity recogniser, about 8 ms per email) splits the text into tokens and marks people (PERSON) and organisations (ORG).
3. **Phrase patterns** (`patterns.py`) match token sequences for ten of the eleven types. Examples: `verif*|confirm* ..2 your ..2 account*` finds "verify your account"; `this|here is|'s ..3 from|with ..2 finance|hr|it ...` finds "this is David from Finance".
4. **Organisation rules** (`affiliation_external`): an ORG entity from spaCy next to a word like Team, Support, Bank or Security is a strong claim ("PayPal Security Team"); the name after a copyright sign and year ("(c) 2024 Omaha Steaks") is a strong claim; a bare mention counts only for a short list of often-imitated organisations that spaCy can miss (`KNOWN_ORGS`, data only; Phase 8 attaches their real domains), and then weakly. Numbers, greetings, placeholders, bare job titles, department words and spans made only of generic words ("Bank account") are not organisations.
5. **Contact rules** (`signature_contact`): a phone number (7 to 15 digits, not a date) or an `[EMAIL]` placeholder with a label just before it (Tel, Fax, E-mail) is a strong claim anywhere in the text; without a label it counts in the signature block, or in the last 350 characters of an email that has none, and a name or organisation within 160 characters before it makes it strong. Postal addresses, disclaimers, copyright lines and a name right after a closing word ("Thanks, John") are weak claims, because the train labels show annotators marked them.
6. **Selection.** Weak claims below `min_confidence` are dropped; within a type, overlapping candidates keep the longest; at most 3 claims per type and 12 per email.
7. **Attributes.** The nearest PERSON, the nearest ORG and a department word (IT, HR, Finance ...) within 6 tokens of the claim fill `attributes`; `pattern` names the rule that fired and `zone` says which text the span points into.

## The pattern language (`patterns.py`)

A phrase is words separated by spaces, each word one spaCy token:

| Written | Means |
|---|---|
| `verify` | the token "verify", any case |
| `verif*` | any token that starts with "verif" |
| `sign\|log` | either word (each alternative may end in `*`) |
| `!writing\|to` | any token except these |
| `=IT\|HR` | the token with exactly this capitalisation ("IT" the department, never "it" the pronoun) |
| `#` | one token made of digits (a house number, a postcode) |
| `?the` | the token is optional |
| `..3` | up to 3 tokens of anything (1 to 6; never first or last) |
| `@PERSON`, `@ORG` | a run of tokens spaCy marks as that entity |

Why this and not regular expressions over the email: patterns match **tokens**, so the cost grows with the number of tokens, never with the ways a regular expression can backtrack (ReDoS-safe, as in Phases 2 to 4). A word is checked to be one token (`check_patterns`): spaCy splits "id" into "i" and "d", so a pattern containing "id" could never match, and the check says so.

Each phrase is **strong** (confidence 0.9: hard to say innocently, such as "verify your account") or **weak** (0.6: also common in ordinary mail, such as "thank you for your reply"). Confidence is **not a probability**: it is the strength of the rule that fired, and nothing calibrates it. `extract_claims(..., min_confidence=0.9)` keeps strong claims only.

## Where the patterns come from, and what is off limits

- Written from the claim definitions, general knowledge of how business email compromise, phishing and advance-fee fraud are worded, and the **train split only**: its labelled spans (`data/labelled/labels.csv`) and the synthetic train emails. No pattern was written from a validation or test email or label.
- The first round was checked on the synthetic train emails (which have full text and required claims) and on the real train spans fed to the extractor alone. Real emails could not be read in the sandbox where the code was written, so the first look at real text is the first run of `build.py` on the Mac.
- Every revision changes `PATTERN_VERSION` (saved in `results/claim_checks.csv`). `--train-only` never loads a validation email or label; the full run reads validation once per frozen version, and a revision made because of those scores is tuning on validation, logged as that. The test split is used once, in Phase 13.

| Version | Date | Change |
|---|---|---|
| 0.1 | Oct 2026 | First patterns: 71 phrases, the organisation rule, the signature rule. First run on the 69,542 train emails showed: `affiliation_external` found in 57% of all emails (a bare organisation name from spaCy fired it), "make money" and "send Mr Pratchett money" fired `payment_request`, "it) may support" fired `affiliation_internal` (the pronoun "it"), "as let's talk" and "as \"promiscuous\"" fired `prior_relationship` (the stem `promis*`), "return with your credit" fired `data_request`, "gift voucher" fired `gift_card`, "message for direct mail" and "my personal mail" fired `reply_direction`; `signature_contact` found 43% of the labelled signatures |
| 0.2 | Oct 2026 | Read off those train results: a bare organisation counts only for the known, often-imitated ones (or when a word like Team or Bank is next to it); "IT" is matched in capitals only; "make money" and "send money" are weak; `as discussed` uses whole words; gift vouchers are weak; `data_request` needs "your" before the sensitive word; `reply_direction` no longer fires on "my personal mail" as a strong claim. `signature_contact` now also reads postal addresses, disclaimers ("please notify the sender"), copyright lines and a name right after a closing word, because the train labels show annotators marked those. The regression cases above are in the self-test. Added `--diagnose` |
| 0.3 | Oct 2026 | Read off the second train run (`--diagnose`): the name after a copyright sign is an organisation (the labels show McDonald's, Lowe's, Omaha Steaks, MetaMask and OpenSea marked this way); a span of generic words only ("Bank", "Bank account", "Security Company") is not an organisation; a labelled phone number or e-mail (Tel, Fax, E-mail) counts anywhere, not only at the end; `affiliation_internal` no longer fires on "I am a social worker with", "I'm one of the authors of the OAuth support" or "system maintenance" (`worker`, `member`, `of`, `maintenance` removed); `data_request` no longer fires on "charged to your credit card" (the card pattern needs a request verb) or "Customer, Our records"; "payment pending" is weak. Six more regression cases in the self-test |
| 0.4 | Oct 2026 | Read off the third train run: redaction placeholders no longer match pattern words (the EMAIL of `[EMAIL]` matched the word "email", which made "You have added [EMAIL] as a new email address" a reply direction); "called me on" no longer matches the contact verb "call"; "your account through the office" no longer matches the internal-affiliation pattern; `official`, `advisor` and `spokesman` count as titles. Four more regression cases. **Frozen here for the validation read** if the full train run is acceptable |

## Scoring (`build.py`)

- **Hit rates** (part 1): all train emails (69,542), no labels. A claim type should fire far more on the attacks it belongs to than on ordinary mail; `results/claim_hit_rates.csv` has the percentages per category for all claims and for strong claims only, and `results/claim_pattern_hits.csv` the emails per pattern. The strong claims found in ham are printed (never saved): those are the false positives to read.
- **Real labelled emails** (part 2, train, and validation unless `--train-only`): does the email contain a claim of this type, as the annotators say (email-level), and for the five types with enough labels, do the found words overlap a labelled span (the Phase 5 rule: one contains the other, or at least half of the words are shared). Precision, recall and F1 come from `src/eval/metrics.py`; a type with fewer than 10 positives in a set is shown as counts only. Only five types have 10 or more real positives in both validation and test: `affiliation_external`, `affiliation_internal`, `authority`, `credential_request` and `signature_contact`.
- **Synthetic emails** (part 3), always apart from the real ones. Their labels list only the claims the generator was **required** to include, not every claim in the email, so precision on them is a lower bound; recall is the meaningful number. They are the only place the rarest request types (`payment_request`, `payment_change`, `gift_card`, `prior_relationship`) can be measured at all.
- **Two operating points** per set: every claim, and strong claims only (`min_confidence` 0 and 0.9).
- **Checks** (`results/claim_checks.csv`): the patterns compile and every word is one token; each expected attack-versus-ham contrast holds (credential requests on phishing, reply directions and authority and data requests on fraud, outside organisations on phishing: at least twice the ham rate); every claim's text is the slice of its span; caps hold (12 per email, 3 per type); eight crafted 200,000-character inputs each finish in under 2 seconds; no validation or test email was read for the hit rates. Coverage (a type that fires on fewer than 20 train emails) and a dominant pattern (more than half of a type's hits) are reported as findings (`info`), not failures.

| File in `results/` | Columns | Meaning |
|---|---|---|
| `claim_hit_rates.csv` | `group_type`, `group`, `emails`, `claim_type`, `fired_pct`, `strong_pct` | % of train emails with a claim of the type, for all emails and per category, for every claim and for strong claims only |
| `claim_pattern_hits.csv` | `claim_type`, `pattern`, `strength`, `emails`, `ham`, `spam`, `phishing`, `fraud`, `share_of_type_hits_pct` | Train emails each pattern fires on (also patterns that never fired) |
| `claim_scores.csv` | `data`, `min_confidence`, `claim_type`, `items`, `positives`, `predicted`, `tp`, `fp`, `fn`, `precision`, `recall`, `f1`, `reported`, `span_precision`, `span_recall`, `note` | Scores per labelled set (`real_train`, `real_validation`, `synthetic_train`, `synthetic_validation`); precision, recall and F1 empty where `reported` says counts only |
| `claim_checks.csv` | `check`, `item`, `value`, `expected`, `status` | PASS, FAIL or info |

## Security

- **Input is cut before anything runs:** 2,000 characters of body and 1,000 of signature. A crafted 200,000-character input costs the same as a short one (the self-test and `claim_checks.csv` time eight of them). spaCy's tokenizer is slower on a long run of brackets than on ordinary text, which is one more reason for the cut.
- **No regular expression over email text** except two short bounded shapes (a phone number and the `[EMAIL]` placeholder); phrase matching is token-based.
- **No raw address leaves the machine:** the signature column is redacted before it is read, and the results files hold counts only. The printed ham examples are claim phrases, not emails.
- **The model is loaded from disk, never downloaded at run time.** `spacy` and the English model are pinned in `requirements.txt`; the model is not on PyPI, so it is pinned by URL and SHA-256 (pip refuses a file with a different hash). `pip-audit` reports no known vulnerability in spaCy or its dependencies, and says it cannot audit the model itself because it is not on PyPI.
- **Spans are checked:** `check_claim` verifies for every claim that its text is exactly the slice of its span, so a highlight in the report can never point at the wrong words.

## Known limits

- English only: the real corpora contain Portuguese, German, Italian and other mail, which the patterns do not read.
- Patterns do not understand negation ("never send your password" can still match) or paraphrase.
- spaCy's organisation tagger finds some organisations and mislabels some words; the claim `attributes` inherit its mistakes. It finds nothing in phrases like "this is David from Finance", so the department patterns do that work.
- The labels are LLM labels from one model family and annotators agreed only moderately (mean kappa 0.458 over the claim types; `prior_relationship` 0.187, `payment_request` and `data_request` 0.287), so a score is agreement with those labels, and a rule-based extractor cannot do much better than the labels agree with each other.
- Six of the eleven types have fewer than 10 real positives in validation or test and can only be reported as counts on real emails.
