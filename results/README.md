# results/

Every number and chart that goes into the report, the slides or the dashboard.

## The rule

Every number here is written by a script in `src/`, never typed by hand. If a number appears in the report, the script that produced it and the file it was saved to must be named next to it. Fake or manipulated results cost 20 marks, and this rule is how the project proves it has none. A result is never edited after the fact: if something changes, the script is fixed and rerun, and Git keeps the history.

The files here hold counts and scores only, never email text, so they are safe to commit.

## Files so far

| File | Written by | What it shows |
|---|---|---|
| `staged_counts.csv` | `python -m src.data.stage` | Emails per source and category in the staged table (99,324 in total) |
| `dedup_pairs.csv` | `python -m src.data.stage` | Duplicates removed, by the source of the removed copy and of the kept copy (5,484 in total) |
| `header_coverage.csv` | `python -m src.data.coverage` | % of messages in each source that carry each header; decides where header signals can be scored |
| `split_counts.csv` | `python -m src.data.split` | Emails per source, category and split (train, validation, test) |
| `preprocess_summary.csv` | `python -m src.preprocess.build` | Per source: % HTML, % with a link, % with quotes, footers or a signature removed, empty and cut bodies, placeholders added |
| `preprocess_checks.csv` | `python -m src.preprocess.build` | Link and address patterns left after redaction; Kaggle's `urls` column against the text; naturally link-free emails per split |
| `header_evidence_summary.csv` | `python -m src.headers.build` | Per source: % of emails with each kind of header evidence (From parsed, authentication verdicts, freemail, list mail, organisation checkable and so on) |
| `header_top_domains.csv` | `python -m src.headers.build` | The most common sender and recipient domains per source |
| `header_auth_formats.csv` | `python -m src.headers.build` | Which Authentication-Results formats each source uses (server domain and method names only) |
| `keyword_hit_rates.csv` | `python -m src.baseline.build` | Train split: % of emails where each tactic fires, for all emails, per category and per source and category |
| `keyword_phrase_hits.csv` | `python -m src.baseline.build` | Train split: how many emails contain each phrase of the keyword lexicon, per category |
| `keyword_checks.csv` | `python -m src.baseline.build` | The keyword baseline's sanity checks (PASS, FAIL, info), lexicon version and run details |
| `sample_counts.csv` | `python -m src.data.batches` | Emails drawn per source, category and split for annotation, and how many were eligible or too short |
| `label_validation.csv` | `python -m src.data.validate_labels` | Per annotator: batch files answered, items valid, re-asked, dropped, and the problems seen |
| `label_agreement.csv` | `python -m src.data.agreement` | Cohen's kappa per tactic and per claim type between the two annotators, with span overlap for claims |
| `label_counts.csv` | `python -m src.data.labels` | Positive labels per tactic and claim type, per split and category |
| `synthetic_counts.csv` | `python -m src.data.synthetic collect` | Valid and dropped synthetic pairs, attack tactics per split, claims per role |
| `semeval_mapping.csv` | `python -m src.data.semeval_map` | The 23 SemEval techniques, the tactic each maps to and how well |

## Still to come

| Phase | Results |
|---|---|
| 4 (F1) | Keyword baseline precision, recall and F1 against the labels: Phase 13, after the Phase 5 labels |
| 6 | Tactic classifier precision, recall and F1 per tactic |
| 13 | N1, N2, N3 and architecture ablations; claim-extraction accuracy; paraphrase and style-confound tests; charts |
