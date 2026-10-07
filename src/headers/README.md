# src/headers/

Phase 3: read each email's headers and turn them into the evidence the N3 header verifier checks claims against.

```bash
python -m src.headers.build     # run from the project root, after the Phase 2 script
```

## Files

| File | Job |
|---|---|
| `parser.py` | `split_headers(raw)` and `body_text(message)`: raw email to header block and body text (used by the Phase 1 loaders, later by the API). `parse_header_fields(block)`: header block to plain fields |
| `domains.py` | `registered_domain`, `is_freemail` (free mailbox providers and open platforms), `lookalike_score` |
| `evidence.py` | `header_evidence(fields, org_domain)`: one flat evidence dict, including which Authentication-Results headers to trust |
| `build.py` | Runs them over every email in `cleaned.parquet`, writes `headers.parquet` and three result files, prints the checks |

`parse_header_fields` and `header_evidence` work on one email at a time and know nothing about datasets, so the API (Phase 11) will reuse them unchanged on submitted emails.

## Output

`data/processed/headers.parquet` has one row per email and joins to `cleaned.parquet` on `id` (earlier files are never modified).

| Group | Columns | Meaning |
|---|---|---|
| Sender | `from_name`, `from_addr`, `from_domain`, `from_registered_domain` | Display name, address, its domain, and the part of the domain someone registered (`mail.paypal.co.uk` gives `paypal.co.uk`) |
| Other addresses | `reply_to`, `return_path`, `to_domain` | Where replies go, where bounces go (envelope sender), the first recipient's domain |
| Message | `subject`, `date`, `message_id`, `in_reply_to`, `references`, `list_id`, `mailer` | `date` is ISO text in the sender's own time zone; the IDs feed thread building in Phase 9 |
| Authentication | `spf`, `dkim`, `dmarc`, `auth_source`, `authenticated_domain`, `auth_aligned` | The receiving server's verdicts (or `unknown`), where they came from, the domain authentication vouched for, and whether that is the From domain |
| Route | `received_hops`, `origin_ip`, `send_hour` | Number of Received lines, the first public IPv4 address from the sender's end, hour on the sender's clock |
| Sender signals | `freemail`, `name_has_address`, `list_mail`, `reply_to_divergence`, `envelope_mismatch` | Section "How the evidence is read" below |
| Organisation | `org_domain`, `org_checkable`, `from_matches_org`, `org_lookalike_score` | The recipient organisation's domain, whether internal-affiliation checks are possible, and how the sender compares |
| Bookkeeping | `parse_problems` | Fields that could not be parsed (they are empty, the rest of the row is kept) |

True/False columns can also be unknown (`<NA>`). Missing evidence is recorded as unknown, never guessed and never pass.

Result files (committed): `results/header_evidence_summary.csv` (per-source percentages), `results/header_top_domains.csv` (most common sender and recipient domains, used to find missing freemail providers and collector addresses) and `results/header_auth_formats.csv` (which Authentication-Results formats each source uses).

## How the evidence is read

1. **Parsing.** Python's `email` package with its default (legacy) parser, the most forgiving with the malformed headers common in spam. Every field is parsed on its own, so one broken header costs only its own field. Encoded words (`=?utf-8?B?...?=`) are decoded and folded lines joined.
2. **From, Reply-To, Return-Path, To.** Python's address parser is strict and gives up on display names with an unquoted `@`, `,` or `;`, such as `service@paypal.com <x@evil.ru>` or `Temu, jehd <service@stayfriends.de>`. Those are common in attacks, so when it gives up, the last `<...>` address is the address and the text before it is the name. This raised the share of phishing_pot From headers parsed from 72% to 92%.
3. **SPF, DKIM, DMARC.** Read from the Authentication-Results header the receiving server wrote; PretextGuard never recomputes them. Two forms exist: the standard one starts with the checking server's name (`mx.google.com; spf=pass ...`), Microsoft's leaves the name out (`spf=pass (sender IP is ...) ...`). Every phishing_pot mailbox is on Microsoft, and the first version missed its SPF verdicts. Which headers are trusted is explained under Security. Without Authentication-Results, the topmost Received-SPF header gives SPF only.
4. **Authenticated domain.** DMARC's `header.from`, else DKIM's `header.d`, else SPF's `smtp.mailfrom`, and only from a check that passed. `auth_aligned` says whether it is the From domain. For the fake David it is gmail.com: authentication passed, for the wrong domain.
5. **Route.** Received lines are read from the bottom (the sender's end) up; `origin_ip` is the first public IPv4 address (10.x, 192.168.x and 127.x are skipped). `send_hour` comes from the Date header, on the sender's own clock.
6. **Domains.** `registered_domain` uses the public suffix list through tldextract. `freemail` covers free and consumer mailbox providers (a hand-written list of about 100) and open platforms where anyone can create a sub-domain (`onmicrosoft.com` for Microsoft 365 tenants, `firebaseapp.com` for Firebase projects). On those platforms the tenant name counts as the registered name, so `acme-payroll.onmicrosoft.com` is compared as `acme-payroll`.
7. **Lookalike score.** Punycode (`xn--...`) is decoded and look-alike characters are mapped (`0` to `o`, `1` to `l`, `rn` to `m`, Cyrillic `а` to `a`), then rapidfuzz compares the two names, 0 to 100. `paypa1.com` against `paypal.com` scores 100.
8. **Name shows an address.** True when the display name contains a domain that is not the sender's own: `"service@paypal.com" <x@evil.ru>`.
9. **Mailing lists.** `list_mail` is true when a List-Id header exists. A list sets Reply-To to the list address, so `reply_to_divergence` is never counted for list mail. A list also sends bounces to its own server, so `envelope_mismatch` (Return-Path domain differs from From domain) is normal for list mail; Phase 8 has to account for that.
10. **Organisation domain.** The registered domain of the To address, except where it says nothing about an organisation: corpus collector mailboxes (`monkey.org` for Nazario, `ceas-challenge.cc` for CEAS 2008, `taint.org` for SpamAssassin), placeholders written over real recipients (`example.com`, `domain.com`), and free mailboxes (a gmail.com recipient is a person, not an organisation). Then `org_checkable` is false and internal-affiliation checks are recorded as not checkable instead of guessed.

## Security

- **Headers are written by the attacker.** The header block is cut at 64 KB, each field at 2,000 characters; at most 50 Received lines, 10 Authentication-Results headers and 100 reference IDs are kept. Every pattern has bounded repeats (no ReDoS). Crafted inputs (60,000-character fields, thousands of Received lines, nested comments, 6,000 addresses in one To) each finish in under 0.2 seconds.
- **Only trusted authentication results.** An attacker can put a fake `Authentication-Results: ...; dmarc=pass` header into the email they send. Servers add headers at the top, so the topmost one is always the receiving server's own. Below it, `trusted_verdicts` reads only headers from the same organisation (same registered domain of the server name) and stops at the first header from anyone else. This is needed at Apache, where the topmost header only records an internal hand-over (`auth=pass`) and the DKIM check sits in the header below it, from another apache.org server; Proton splits SPF, DKIM and DMARC over several headers the same way. A higher header always wins, and Microsoft's form (no server name) is never read past the first header. The rule relies on the receiver deleting incoming headers that carry its own organisation's name, which RFC 8601 (Section 5) requires.
- **Display-name spoofing.** The strict-parser fallback recovers the real address from `service@paypal.com <x@evil.ru>`. An address hidden inside an encoded word is never taken as the sender: such a From stays unknown.
- **Homograph and lookalike domains.** Punycode decoding and look-alike character mapping, plus tenant names on open platforms.
- **Offline.** tldextract uses its built-in public suffix list and never downloads anything.

## Known limits

- Kaggle rows carry only a rebuilt header block (From, To, Date, Subject; Enron and Ling Subject only), so most of their evidence is unknown.
- No benign source carries SPF or DMARC verdicts, and Apache carries DKIM only. Authentication evidence is therefore never used as a learned feature; N3 uses it only through claim-conditioned rules, and Phase 13 reports authentication-based findings per source.
- `send_hour` comes from the Date header, which the sender writes.
- `origin_ip` reads IPv4 addresses only.
- The freemail list is hand-written; `results/header_top_domains.csv` shows any large provider it misses.
- 86 emails have a Date header that could not be parsed (their `date` and `send_hour` are empty).
