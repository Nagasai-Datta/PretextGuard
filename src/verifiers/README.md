# src/verifiers/

Phase 8: the **header verifier** (N3, the core novelty) and the **request verifier**. They take the claims that `src/claims` found in an email and the evidence that `src/headers` read from its headers, and return **ledger rows**: one verdict per claim, with the evidence and the reason. The thread verifier (N2, Phase 9, `thread_verifier.py`, described in `src/thread/README.md`) adds a third kind of row; Phase 10 turns the rows into the risk score.

```bash
python -m src.verifiers.selftest                          # hand-made emails and crafted input, no data needed (67 PASS lines)
python -m src.verifiers.build --train-only --limit 6000   # a quick development run on a random 6,000 train emails
python -m src.verifiers.build --train-only --limit 6000 --diagnose affiliation_external,authority
                                                          # also prints up to 25 contradictions found in ham, and what passes in attacks (never saved)
python -m src.verifiers.build --train-only --limit 6000 --show-rules hv_ext_unknown_freemail,hv_sig_other_domain
                                                          # also prints up to 25 examples of each named rule, from any category (never saved)
python -m src.verifiers.build --train-only --workers 4    # every train email; validation is never loaded. --workers runs the claim extraction (the slow part,
                                                          # first time only) in 4 processes; the claims are the same
python -m src.verifiers.build --train-only                # the same with one process
python -m src.verifiers.build                             # the final run of a frozen rule version: also reads the validation emails, once
```

```python
from src.claims.extractor import extract_claims
from src.headers.parser import parse_header_fields
from src.headers.evidence import header_evidence
from src.verifiers.verify import verify_claims

claims = extract_claims(body_redacted, signature)
fields, _ = parse_header_fields(header_block)
evidence = header_evidence(fields, org_domain)            # org_domain: the recipient's organisation domain, or None
rows = verify_claims(claims, {**fields, **evidence}, contact_text=raw_signature, body_text=model_text(body_redacted))
# for the David email sent from gmail.com the first row is
rows[0]   # {"claim_id": "c1", "claim_type": "affiliation_internal", "verifier": "header", "rule": "hv_int_freemail",
          #  "evidence": {"from_domain": "gmail.com", "org_domain": "acmecorp.com", "freemail": True, "spf": "pass", ...},
          #  "contradiction": True, "severity": "high",
          #  "reason": "Claims to be internal (Finance at acmecorp.com), but the message comes from gmail.com, a free mailbox provider anyone can use. Authentication passed for gmail.com."}
```

## Files

| File | Job |
|---|---|
| `rows.py` | The ledger row (master document Section 6.3 plus `claim_type` and `rule`), `check_row`, the routing table `ROUTES`, and `clean_text` / `clean_domain`, which make anything that came from an email safe to print |
| `facts.py` | `prepare_facts` (one dictionary of cleaned evidence; derives `auth_state` and `external`), `similar_domain` (same, suffix, look-alike), `find_addresses` (e-mail addresses in a signature, bounded, no regular expressions) |
| `brands.py` | Data only: the real registered domains of the often-imitated organisations of `KNOWN_ORGS` (55 names: 51 organisations with domains, three spellings that are aliases of one of them, and Yahoo, which has none yet), and the entries to double-check |
| `bank.py` | `find_bank_details`: IBANs (with the mod 97 checksum and the country's length), labelled account numbers, routing and sort codes, SWIFT codes; values shown masked. The thread verifier (Phase 9) reuses `bank_detail_keys` for request drift |
| `header_verifier.py` | N3: `affiliation_internal`, `affiliation_external`, `authority`, `reply_direction`, `signature_contact` |
| `request_verifier.py` | Who is asking: `payment_request`, `payment_change`, `credential_request`, `gift_card`, `data_request` |
| `verify.py` | `verify_claims`: routes each claim to its verifier (Section 6.4), holds `RULES_VERSION`, `VERSION_LOG` and the list of all rules |
| `thread_verifier.py` | Phase 9: N2. `verify_thread_message`, `scan_thread` (the flip point), the `tv_` rules; `verify_claims` calls it for `prior_relationship` and request claims when it is given `thread=(messages, index)` |
| `selftest.py` | 41 hand-made emails with real header blocks and the rows they must give, 16 helper checks, 8 crafted inputs |
| `build.py` | Runs the verifiers over the train split (and validation in the final run), caches the extracted claims, writes `results/verifier_*.csv` |

## What a row says: three values, never two

| `contradiction` | `severity` | Meaning |
|---|---|---|
| `true` | `high`, `medium` or `low` | The evidence disagrees with the claim |
| `false` | `none` | The evidence was there and does not disagree |
| `null` | `not_checkable` | The evidence this claim needs is missing |

In JavaScript terms: true, false, null. Mixing the last two would turn missing evidence into "safe". A source with no authentication verdicts (CEAS-08, SpamAssassin, the Kaggle files) therefore gets "not checkable" for every rule that reads one, and `build.py` checks that no such rule ever fires without a verdict.

Severity is a label of **rule strength** (high: hard to explain innocently; medium: suspicious, has innocent explanations; low: weak). It is not a probability and not a score. A **weak claim** (confidence 0.6) lowers its row's severity by one step. Phase 10 turns severities into points and calibrates them on the validation split.

## Why the same header means different things (the point of N3)

Three domains: the **From domain** is what the reader sees; the **authenticated domain** is what SPF, DKIM or DMARC actually vouched for; the **claimed domain** comes from the body (the organisation domain, or a brand's real domains). A contradiction is a mismatch between them that the claim makes meaningful.

| Claim | Same headers | Meaning |
|---|---|---|
| none | `spf=fail` on a newsletter | No row at all: no claim, no finding |
| payment request | `spf=fail` | `rv_spf_fail`, medium |
| rank ("As CFO") | `spf=fail` | `hv_auth_spf_fail`, medium |
| "this is David from Finance" | `dmarc=pass` for gmail.com | `hv_int_freemail`, **high**: authentication passed for the wrong domain |
| "this is David from Finance" | From shows the organisation's domain, `dmarc=fail` | `hv_int_spoof`, **high**: exact-domain spoof |
| "this is David from Finance" | From shows the organisation's domain, `dmarc=pass` | `hv_int_ok_auth`, consistent |

Authentication enters **only** through rules like these, never as a learned feature (no benign source has SPF or DMARC verdicts, and Apache has DKIM only: a model would read "has verdicts" as "attack").

## The rules

Every row names its rule (`rule`), the way every claim names its pattern. `verify.py` lists all 63; `results/verifier_rule_hits.csv` counts them. The main ones:

| Claim | Contradiction when | Severity |
|---|---|---|
| `affiliation_internal` | sender is a free mailbox, or a look-alike of the organisation domain | high |
| | sender uses the organisation's name under another suffix | medium |
| | sender is an unrelated domain (weak: without a List-Id the recipient domain is often a mailing list, or a partner) | low |
| | From shows the organisation's own domain, but DMARC failed | high |
| | ... SPF failed, or authentication vouched for another domain | medium |
| | not checkable: no organisation domain, mailing-list mail (the recipient domain is the list's), no From, or From shows the organisation's domain but there is no verdict | |
| `affiliation_external` | checked only if the claim's own words name the organisation **and** say the sender is that organisation: a team, department, support, security, customer, billing ... (or a footer, or "on behalf of"). "your Microsoft account" or "SharePoint Services" is a reference, not a claim of identity, and is not checkable. The organisation is read from the claim text, not from the nearest organisation in the email | |
| | the named organisation is in `brands.py` and the sender is a free mailbox, a look-alike, or the display name shows another e-mail address | high |
| | ... the sender is an unrelated domain (brand mail sometimes goes through a third-party mailer) | medium |
| | consistent: the brand's own domain sent it and authentication passed, or the brand's domain authenticated the message | |
| | the organisation has no domain on file: low for a free mailbox (the name comes from a name recogniser), otherwise not checkable; a claim that names no organisation is not checkable | |
| `authority` | display name shows another address, look-alike of the organisation domain, DMARC failed | high |
| | free mailbox, SPF failed | medium |
| `reply_direction` | the Reply-To header points to another domain; to a free mailbox while the sender is not one, or to a look-alike | medium; high |
| | list-set Reply-To is excluded; no Reply-To header is not checkable (the body's own address is redacted) | |
| `signature_contact` | checked only for contact claims (a name with a phone or address, a labelled contact, a bare contact in the signature); a postal address, disclaimer, copyright line or sign-off name is not checkable | |
| | no e-mail address in the sender's **unredacted** signature block is on the From domain. The block ends at the first footer or quoted-header marker (unsubscribe, mailing list, on behalf of, Sent:, wrote:); an address on the recipient's domain is ignored when the recipient has no organisation; a match on the same free mailbox provider is not checkable | low |
| | the sender is a free mailbox and the signature shows a company address | medium |
| | an address that looks like the sender's own domain | high |
| Request claims | the asker is a look-alike (of the organisation, or of the brand the request names), DMARC failed | high |
| | free mailbox (**high** when the sender is outside the recipient's organisation), Reply-To to another domain, display name shows another e-mail address, SPF failed | medium |
| | the display name shows only a bare domain ("Amazon.com"); brands write their site name like this, so it is weak | low |
| | adjustments: `payment_change` and `gift_card` +1 step, `data_request` -1, valid bank details in a payment message +1 | |
| | consistent only if authentication passed for the sender's own domain; a bank-detail change is always "needs the thread" | |

Fixed numbers, set from definitions and never tuned: a **look-alike** is a registered name that differs only by look-alike characters (paypa1, a Cyrillic a, rn for m), or has rapidfuzz ratio 80 or more when both names have at least 6 letters (visa and vista are too short to count). The same name under another suffix (paypal.net) is "suffix", medium.

## Brands (`brands.py`)

`KNOWN_ORGS` (Phase 7) names the organisations the extractor recognises. `brands.py` attaches to each one the domains it really sends mail from. Rules of the file:

- Only domains that are certain. A missing domain makes the verifier slightly more suspicious of a genuine message (a medium contradiction, never high), so a gap costs a little precision and opens no hole.
- No brand domain may be a free mailbox domain (outlook.com, yahoo.com, icloud.com ...). Yahoo is therefore listed in `NO_DOMAINS_YET` with the reason. `build.py` checks all this.
- Third-party mailers (amazonses.com, sendgrid.net) are not brand domains. Mail a brand sends through one counts as genuine only if the brand's **own** domain authenticated it (DKIM `header.d` or SPF).
- `CONFIRM` lists 15 secondary domains to double-check by hand. They are believed correct, but a typing mistake there would matter most. `NOT_CONFIRMED` lists six domains that were left out because they are not certain.

To double-check the `CONFIRM` list (run from any folder; the registrant line may be hidden by privacy services, then the redirect shows where the domain leads):

```bash
for d in facebookmail.com fb.com meta.com docusign.net zoom.com dhl.de jpmorganchase.com lloydsbankinggroup.com truist.com verizonwireless.com xfinity.com steamcommunity.com microsoftonline.com office.com moneybookers.com; do echo "== $d"; whois $d | grep -i -E "registrant (organi[sz]ation|name)" | head -2; curl -sIL --max-time 10 "https://$d" | grep -i -E "^(HTTP|location)" | head -3; done
```

If a domain is wrong, remove it from `BRAND_DOMAINS` and `CONFIRM`, bump `RULES_VERSION` and log the change in `VERSION_LOG`.

## Bank details (`bank.py`)

An IBAN is two letters (country), two check digits and up to 30 letters or digits. Move the first four characters to the end, turn every letter into a number (A is 10, Z is 35), read the result as one number: it must leave remainder 1 when divided by 97. That separates real bank details from random digits (about 1 random string in 97 of the right shape would pass, so the country's known length is checked too). Account numbers, routing and sort codes and SWIFT codes have no checksum that works for all banks, so they count only after a label word ("account number", "routing", "sort code", "swift"). Details are shown masked (`DE**3000`, `****5678`): the ledger and the logs never carry a whole account number.

## How the build verifies it without labels

Nobody marked which emails contain a contradicted claim, so there is no precision or recall for contradictions. What `build.py` does instead:

1. **The self-test** (`selftest.py`): hand-made emails with real header blocks, including the David email (Section 6.7), the exact-domain spoof, an honest internal mail, a newsletter with `spf=fail`, mailing-list mail, a display name that shows `service@paypal.com`, paypa1.com, a brand through a third-party mailer, and crafted input.
2. **Contradiction rates** (`results/verifier_rates.csv`): per category, per source and per source and category, for every claim type and for all together, among the claims that could be checked. An attack should show more contradictions than ordinary mail. **Caution:** attacks and ham come from different corpora with different header evidence (master document Section 8.11): phishing_pot has verdicts for 99%, Nazario for 21%, Apache for DKIM only, SpamAssassin, CEAS-08 and Kaggle for none. A difference between categories is partly a difference between corpora; the per-source rows show it, and "not checkable" is never counted as "no contradiction".
3. **The false alarms are read:** the contradictions found in ham are printed (three per type, 25 with `--diagnose`), the way Phase 7 printed false positives. They are never saved.
4. **Freeze, then one read of validation.** Rules are written from definitions and revised only after reading **train** results (`--train-only` never loads a validation email). The final run reads the validation emails once. The test split is used in Phase 13.
5. **Checks** (`results/verifier_checks.csv`): the self-test; the brand file (no free-mailbox domain, every `KNOWN_ORGS` name covered); every row passes `check_row`; contradiction + consistent + not checkable add up to the claims in every group; no rule that reads authentication fires without a verdict; no internal-affiliation row is decided without an organisation domain or on mailing-list mail; no weak claim has severity high; six attack-versus-ham contrasts (the share of *emails* with a contradicted claim of the type must be at least twice the ham share to pass; above ham but below twice is an `info` finding, and not above ham is a FAIL; judged only with 20 or more checkable claims in the attack category. The rate among checkable claims is no fair measure: it was close to 100% in every category in the first run, because "checkable" mostly meant "contradicted"); crafted inputs under 2 seconds; coverage and dominant-rule findings (`info`, not failures).

How much contradictions add to detection is the N3 ablation of Phase 13, with real affiliation positives and synthetic BEC apart. The synthetic emails have no headers; Phase 13 will generate clearly synthetic header blocks for them for that ablation only (generating them now would mean tuning the rules on headers written by the same person, which is circular).

| File in `results/` | Meaning |
|---|---|
| `verifier_rates.csv` | Per split, group (`all`, `category`, `source`, `source_category`) and claim type (`any` = all types): claims, emails, contradiction / consistent / not checkable counts, severities, `checkable_pct`, `contradiction_pct_of_checkable`, `contradiction_email_pct` |
| `verifier_rule_hits.csv` | Per rule (also the ones that never fired): rows by status and by category |
| `verifier_checks.csv` | PASS, FAIL or info, with `rules_version`, the claim pattern version and run details |

The extracted claims are cached in `data/processed/claims_cache/` (ignored by Git; one file per split). The cache is rebuilt automatically when `PATTERN_VERSION` or the spaCy model changes. The first run over the whole train split takes about 20 minutes (the Phase 7 extractor); later runs take about a minute. Phases 10 and 13 reuse the cache.

## Security

- **Headers and signatures are attacker-written.** The verifiers read only values the Phase 3 code has already capped and parsed per field; signature text is cut at 1,000 characters and read by a bounded scanner (at most 40 `@` signs, 64 characters to the left, 255 to the right); bank details are found by word lookup on the first 5,000 characters. No backtracking regular expression runs over email text. The self-test feeds 60,000-character display names and Reply-To values, floods of `@`, IBAN-shaped words and markup; each finishes in about 0.02 seconds.
- **Reasons and evidence are built from validated values only.** Anything that came from an email (a claimed organisation, a department) goes through `clean_text`, and every domain through `clean_domain`; `check_row` rejects a reason with `<`, `>` or backticks. The interface must still escape them (Phase 12).
- **No whole account number in a row.** IBANs and account numbers are masked; the self-test checks that a full IBAN never appears in a row's JSON.
- **Authentication is read, never recomputed, and only from trusted headers** (Phase 3). Domain comparisons go through the offline `tldextract`.

## Known limits

- Rules are written from definitions and a short list of organisations; a brand that is not in `brands.py` can only be compared when it is a free mailbox (medium) and is otherwise not checkable.
- `affiliation_internal` needs the recipient's organisation domain, which exists for only 3.6% of phishing_pot and 9.8% of Nazario emails (Section 8.11); the claim extractor also finds only 13% of the labelled internal claims. Real internal-affiliation evidence is therefore thin, and a missing claim is never evidence of honesty.
- A sender that authenticates as its own domain is "consistent" only in the sense that nothing contradicts it: a compromised real account passes every check here. That is what the thread verifier (N2, Phase 9) is for: it compares the message with its own thread.
- `prior_relationship` is routed to the thread verifier (Phase 9). Without a thread (`verify_claims(..., thread=None)`, the Phase 8 behaviour) its row says "not checkable: needs a thread"; with one, the `tv_prior_*` rules answer.
- Severities are initial labels. The claim labels behind Phase 7's scores are LLM labels from one model family; the contradiction rates here use claims found by the Phase 7 extractor, not the labels.

## Versions of the rules

| Version | Change |
|---|---|
| 0.1 | First version: rules written from master document Sections 4.4 and 6.5, the Phase 3 and Phase 7 notes and the claim definitions; thresholds fixed (look-alike score 80, names of 6 or more letters); severities are initial labels. No real email had been read |
| 0.2 | Read off the first train run (6,000 emails): affiliation_external was contradicted in 98% to 100% of its checkable claims in every category, because claims that only MENTION a brand (your Microsoft account, SharePoint Services) were treated as claims of identity, and the claimed organisation was taken from the nearest organisation in the text (Lloyds next to the Financial Services Authority). Now an external claim is checked only if the claim's own words name the organisation and say the sender is that organisation (a team, department, support, security ... or a footer or 'on behalf of'); a mere reference is not checkable. An unrelated domain under an internal claim is low (in sources without a List-Id the recipient domain is often a mailing list, as in the opensuse.org and linux.ie ham examples); an unknown organisation from a free mailbox is low (the name comes from a name recogniser: 'Hi team'). A display name that holds only a bare domain name (brands write their site name, such as Brand.com, in the display name and send through mailers) is now low; only a shown e-mail address is medium. signature_contact compares addresses only for contact claims, not for postal addresses, disclaimers, copyright lines or sign-off names. The attack-versus-ham check now compares the share of EMAILS with a contradicted claim, because the rate among checkable claims is close to 100% in every category when 'checkable' mostly means 'contradicted' |
| 0.3 | Read off the second train run (6,000 emails): the fix of 0.2 removed the external-affiliation false alarms (share of emails with a contradicted external claim 7.1% in phishing against 0.1% in ham), but signature_contact still failed its contrast (7.9% against 4.9%), and its ham alarms were list footers ('List maintainer', 'To unsubscribe from this group', 'For additional commands'), quoted headers ('On Behalf Of', 'Sent:', X-Spam lines) and the reader's own address on a collector domain (ceas-challenge.cc, monkey.org). Now the signature text is cut at the first footer or quoted-header marker, an address on the recipient's domain is ignored when the recipient has no organisation (collector, free mailbox, mailing list), and a signature address on the same free mailbox provider as the sender is not checkable (everyone at hotmail.com matches). 'Office' is no longer a speaker cue ('Microsoft Office' is a product; the digitalriver.com reseller mail in ham). An attack-versus-ham contrast that is above ham but below 2x is now a finding (info), not a failure; only a rate that is not above ham fails |
