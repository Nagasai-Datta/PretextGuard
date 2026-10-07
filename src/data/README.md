# src/data/

Phase 1: turn six differently shaped downloads into one table of unique emails with a fixed train/validation/test split. Phase 5 adds annotation, labels and synthetic emails (last section); Phase 9 will add the thread-hijack benchmark.

## Scripts, in the order you run them

| Script | Reads | Writes | Job |
|---|---|---|---|
| `paths.py` | | | Every folder and file path, defined once |
| `fetch_apache.py` | lists.apache.org | `data/raw/apache/<list>/<YYYY-MM>.mbox` | 24 months of users@tomcat and users@kafka, one request per month |
| `unpack.py` | `data/raw/*` | unpacked folders next to each archive | Checks every download by its first bytes, then unpacks safely |
| `loaders.py` | unpacked sources | (used by `stage.py`) | One reader per source format, all returning the same record |
| `stage.py` | all sources | `data/processed/staged.parquet`, `results/staged_counts.csv`, `results/dedup_pairs.csv` | One table, empty bodies dropped, duplicates removed |
| `coverage.py` | staged table, raw Enron | `results/header_coverage.csv` | Share of messages carrying each header, per source |
| `split.py` | staged table | `split` column in the table, `results/split_counts.csv` | Fixed 70/15/15 split |

```bash
python -m src.data.fetch_apache
python -m src.data.unpack
python -m src.data.stage
python -m src.data.coverage
python -m src.data.split     # rerun after every stage.py run
```

## The staged table

`data/processed/staged.parquet`, one row per unique email:

| Column | Meaning |
|---|---|
| `id` | First 16 hex characters of SHA-256(raw_ref); stable across rebuilds |
| `source` | For example `nazario`, `phishing_pot`, `kaggle_ceas08`, `apache_tomcat_users` |
| `category` | `ham`, `spam`, `phishing` or `fraud` |
| `is_attack` | True only for phishing and fraud (spam is not an attack) |
| `has_full_headers` | False for Kaggle rows, whose header block was rebuilt from CSV columns |
| `raw_ref` | Where the original is inside `data/raw/`: a path, plus `#n` for the n-th mbox message or `#row=n` for a CSV row |
| `raw_headers` | The header block as text, exactly as in the original |
| `body_raw` | The body text: plain-text parts, or the HTML if there is no plain text; decoded but not cleaned |
| `split` | `train`, `validation` or `test` |

Later phases add columns (cleaned and redacted bodies, header evidence, labels, thread positions); see master document Section 8.7.

## Decisions built into the code

- **Kaggle files:** CEAS-08, Enron, Ling and Nigerian Fraud are read. `phishing_email.csv` is a pre-merged copy of the others and is skipped. `Nazario.csv` and `SpamAssasin.csv` are left out because they are reprocessed copies of the raw corpora we have in full (98% and 96% of the rows the body fingerprint missed matched a raw email by sender, date and subject).
- **Kaggle labels:** label 1 is spam for CEAS-08, Enron and Ling, fraud for Nigerian Fraud; label 0 is ham. CEAS-08 spam includes some phishing its labels do not separate, so it stays spam.
- **Bodies:** text/plain parts are used; HTML only when there is no plain text. Attachments are skipped and never decoded to disk. Emails with no readable text are dropped (208).
- **Duplicates:** fingerprint = SHA-256 of the body's lowercase letters and digits, so copies that differ only in spacing or punctuation match. One copy per fingerprint is kept, preferring full headers. 5,484 copies removed (`results/dedup_pairs.csv`).
- **Split:** stratified by (source, category). Emails with the same subject after removing "Re:"/"Fwd:" go to the same split, so threads and spam campaigns never sit on both sides. A subject shared by more than 2% of its stratum (and more than 25 emails) is split email by email. Group order comes from SHA-256 of seed 42 and the group key, so the split is identical everywhere. Result: 69,542 train, 14,879 validation, 14,903 test.

## Security

- `unpack.py`: tar members go through Python's `filter="data"`, zip members are checked by hand, so nothing can be written outside its folder (path traversal); archives over 5 GB unpacked are refused (decompression bombs); file types are checked by their first bytes; unpacked files are made read-only.
- `fetch_apache.py`: HTTPS only, timeouts, a 50 MB cap per reply, and a reply must look like an mbox before it is saved.
- `loaders.py`: emails are data only; nothing is opened or run. Kaggle values are squashed onto one line before they become header lines (header injection).

## Phase 5: labels (annotation, synthetic emails, SemEval mapping)

Phase 5 turns the sampled emails into labels the models can learn from and be scored against. The loop is described step by step in `data/labelled/README.md` and `data/synthetic/README.md`.

| Script | Job |
|---|---|
| `label_schema.py` | The seven tactics, the eleven claim types, their definitions, batch size, and how an email is shown to an annotator |
| `prompts.py` | The annotation prompt: security note, definitions, output format, then the emails as data |
| `clipboard.py` | Copy to and paste from the macOS clipboard (pbcopy, pbpaste) |
| `llm_api.py` | One chat request for the annotators and the tie-breaker through a free-tier API: key from `.env`, retries on rate limits, temperature 0 |
| `batches.py` | Draws the 700-email sample (`sample.csv`) and writes the 35 batch prompts |
| `annotate.py` | `check` and `auto <annotator>` send the batches to the provider's API and save the replies; `next` and `save` do the same by hand through the clipboard; `status` |
| `validate_labels.py` | Checks every reply against the schema, writes `reask_*` batches for invalid or missing items |
| `agreement.py` | Cohen's kappa per tactic and claim type, and `tiebreak_*` batches for the tie-breaker round |
| `labels.py` | Merges the answers into `data/labelled/labels.csv` and counts the positives |
| `synthetic.py` | `build`, `next`, `save`, `collect`: 240 attack-and-twin pairs written by a web chat, checked and loaded |
| `semeval_map.py` | The 23-to-7 SemEval mapping and a check against the registered data |

Run order: `batches`, then `annotate` for annotator_1 and annotator_2, `validate_labels`, `agreement`, `annotate` for tiebreaker, `labels`; `synthetic` runs on its own.

Decisions built into the code: the sample is a fixed allocation per source and category, not proportional, and no keyword hit picks any email; annotators see `body_redacted` only, cut at 2,000 characters; replies are kept raw and every save is logged with the model name; an invalid item is re-asked once, then dropped and counted; kappa is written by hand and cross-checked against scikit-learn.

Security: email text is wrapped as data and its angle brackets are replaced; replies must be an exact JSON shape and quoted spans must appear in the email; a reply that is the same for every email is rejected as a likely hijack; `data/labelled/batches/` is never committed because it holds full email text.
