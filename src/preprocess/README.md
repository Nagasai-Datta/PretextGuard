# src/preprocess/

Phase 2: turn each raw email body into clean text and a payload-free (N1) redacted text.

```bash
python -m src.preprocess.build     # run from the project root, after the Phase 1 scripts
```

## Files

| File | Job |
|---|---|
| `clean.py` | `clean_body(raw)`: HTML to text, list footer and quoted history removed, signature found, whitespace collapsed |
| `redact.py` | `redact(text)`: links, addresses, file names and domains replaced by placeholders; `contains_url(text)` |
| `build.py` | Runs both over every staged email, writes `data/processed/cleaned.parquet` and the result files, prints the checks |

`clean_body` and `redact` work on one string at a time and know nothing about datasets, so the API (Phase 11) will reuse them unchanged on submitted emails.

## Output

`data/processed/cleaned.parquet` holds every column of `staged.parquet` (which is never modified) plus:

| Column | Meaning |
|---|---|
| `has_url` | The original email had a link: in its text, hidden in HTML, or spaced out; for CEAS-08 and Nigerian Fraud also when Kaggle's own `urls` column says so |
| `body_clean` | Readable text of the new message. Links stay in: this is the "raw" view for N1's model A |
| `body_redacted` | `body_clean` with `[URL]`, `[EMAIL]`, `[FILE]` and `[DOMAIN]`: what PretextGuard's own models read |
| `signature` | The signature block (also left inside `body_clean`), for signature-contact claims in Phase 7 |

Result files (committed): `results/preprocess_summary.csv` (per-source counts) and `results/preprocess_checks.csv` (leftover check, Kaggle `urls` comparison, link-free counts per split).

## What cleaning does, in order

1. **Cap** the body at 200,000 characters.
2. **HTML to text** with BeautifulSoup and Python's built-in parser. Scripts, styles and `<blockquote>` replies are dropped; each link's hidden target is written after its text, `Click here (http://...)`, so model A sees the links HTML hides.
3. **List footer** removed: a separator line up to 300 characters before "unsubscribe" or "mailing list" at the end of the text. Footers would tell a model "this came from a mailing list, so it is ham".
4. **Quoted history** removed: from the earliest reply marker (`-----Original Message-----`, `On ... wrote:`, `From: ... Sent:`, a forwarded header) and every line starting with `>`. If nothing readable is left, the whole text is kept.
5. **Signature** found (a `-- ` line, or a closing such as "Best regards," near the end) and returned separately; it stays in the text because claims like "Finance Director, Acme" live there.
6. **Whitespace** collapsed to single spaces for every source, so no source can be recognised by its spacing.

## What redaction does, in order

| Placeholder | Catches | Spaced form (pre-tokenised text) |
|---|---|---|
| `[URL]` | `http://`, `https://`, defanged `hxxp://`, `www.` | `http : / / site . com`, `www . site . com` |
| `[EMAIL]` | `name@example.com`, `mailto:` | `john @ enron . com` |
| `[FILE]` | attachment names: `.pdf`, `.docx`, `.zip`, `.exe`, `.js` and others | `report . xls` |
| `[DOMAIN]` | bare domains with a real ending from the public suffix list (`paypa1.co.uk`), but not `Mr.Smith` or `e.g` | `enron . com` (only .com .net .org .edu .gov .mil .info .biz) |

The order is fixed: URLs before domains, so a link's domain is not caught on its own; file names before domains, because some file endings are real top-level domains (`invoice.zip`). Words such as "see attached" stay: they are language, not payload.

**Why the spaced forms exist.** The Kaggle Enron and Ling files are stored pre-tokenised: lowercase, with every punctuation mark set apart (`davilal @ txu . com`). The first version of this phase missed those, and a check found spaced links or addresses left in 13,107 Enron and 2,192 Ling redacted bodies. The spaced patterns need strong evidence (a scheme, `www` plus two labels, `@`, or an unambiguous ending), because in such text an ordinary sentence end also looks like ` . `: "the end . it was" must not become a domain. Some real phishing spaces out links on purpose, so the same patterns help there.

## Security

- **ReDoS.** These functions will clean attacker-written email in the API, so every pattern is written to avoid catastrophic backtracking: bounded repeats, no look-ahead over long text. Testing found two real problems in the first draft: a list-footer pattern that ran for hours on 200,000 dashes, and line-break insertion that took 10 seconds on 20,000 nested `<div>` tags. Both were rewritten; across 31 crafted inputs of up to 200,000 characters the slowest now takes under two seconds.
- **HTML as data.** HTML is parsed, never rendered; no script runs and nothing is fetched.
- **Offline public suffix list.** `tldextract` is set up with `suffix_list_urls=()`, so it uses its built-in copy and never downloads anything.
- **No real addresses or live links leave the machine.** `[EMAIL]` and `[URL]` also protect privacy: the Phase 5 annotation batches go to outside web chats and contain only redacted text.

## Known limits

- Kaggle Enron and Ling stay lowercase and tokenised in `body_clean` (the original casing and spacing are gone). DistilBERT-uncased and TF-IDF both lowercase and split punctuation, so they see the same tokens either way.
- Signatures are found only when the text keeps its line breaks; collapsed Kaggle text rarely yields one.
- A spaced link's path can leave a fragment such as `. html` behind; the domain and scheme are always removed.
