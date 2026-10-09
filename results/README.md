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
| `tactic_data_counts.csv` | `python -m src.models.dataset` | Items and positive labels per origin (real, synthetic), split (train, validation) and tactic in the table sent to Colab |
| `tactic_training_log.csv` | `train.py` on Colab | Per condition (`mix`, `real_only`), seed and epoch: training loss, validation loss, validation macro-F1, and whether it was the chosen epoch |
| `tactic_seed_summary.csv` | `train.py` on Colab | Per condition and seed: best epoch, epochs run, validation macro-F1, and which seed was chosen |
| `tactic_val_probs.csv` | `train.py` on Colab | The chosen model's probability for each tactic on every validation email (ids and numbers only); the Mac compares its own predictions with these |
| `tactic_run_info.json` | `train.py` on Colab | Settings, `pos_weight`, thresholds, library versions, GPU name, data checksum, code commit and base-model revision of the Colab run |
| `tactic_validation_scores.csv` | `python -m src.models.validate` | Precision, recall and F1 per tactic for DistilBERT (with and without synthetic training emails) and the keyword baseline (default and tuned thresholds), on real and synthetic validation emails, apart; counts only below 10 positives |
| `tactic_checks.csv` | `python -m src.models.validate` | PASS/FAIL checks on the data and the model, including that the Mac's CPU reproduces Colab's predictions to within 0.001 |
| `claim_hit_rates.csv` | `python -m src.claims.build` | Train split: % of emails where each of the eleven claim types is found, for all emails and per category, for every claim and for strong claims only |
| `claim_pattern_hits.csv` | `python -m src.claims.build` | Train split: how many emails each claim pattern and rule fires on, per category (also patterns that never fired) |
| `claim_scores.csv` | `python -m src.claims.build` | Precision, recall and F1 per claim type on the labelled real emails and on the synthetic emails (train, and validation in the final run), apart, at two confidence levels; counts only below 10 positives |
| `claim_checks.csv` | `python -m src.claims.build` | PASS/FAIL checks on the claim extractor, plus pattern version, spaCy version and run details |
| `verifier_rates.csv` | `python -m src.verifiers.build` | Per split, group (all, category, source, source and category) and claim type: claims contradicted, consistent and not checkable, by severity, and the contradiction rate among the checkable ones (counts only; there are no contradiction labels, so these are rates, not precision or recall) |
| `verifier_rule_hits.csv` | `python -m src.verifiers.build` | How many ledger rows each verifier rule produced, by status and category (also rules that never fired) |
| `verifier_checks.csv` | `python -m src.verifiers.build` | PASS/FAIL checks on the header and request verifiers, plus rule version, claim pattern version and run details |
| `thread_counts.csv` | `python -m src.thread.build` | Threads and messages found per source and split, thread sizes, and how many candidate groups were dropped and why |
| `thread_signal_rates.csv` | `python -m src.thread.build` | Per split, source and thread rule: how many rows were contradictions, consistent or not checkable on REAL unmodified threads (every medium or high contradiction there is a false alarm); the `(all rules)` rows count messages and threads |
| `thread_checks.csv` | `python -m src.thread.build` | PASS/FAIL checks on the thread builder and verifier (self-test, structure, splits, false alarms), plus rule version and run details |
| `hijack_generation.csv` | `python -m src.data.hijack_benchmark collect` | Base threads planned, valid, dropped after a re-ask, and the problems the replies had |
| `hijack_cases.csv` | `python -m src.data.hijack_benchmark collect` | Benchmark cases and threads per split, source and variant |
| `thread_scores.csv` | `python -m src.thread.evaluate` | Per split, source and variant: detection by the thread verifier, by the Phase 8 verifiers and by either, which signal caught each case, whether the scan flips at the injected message, and false alarms on the negatives; rates with 95% intervals over threads, counts only below 10 cases |
| `hijack_checks.csv` | `python -m src.thread.evaluate` | PASS/FAIL checks on the benchmark (labels, structure, no thread in two splits, the construction invariants), plus rule versions and run details |
| `score_rule_weights.csv` | `python -m src.router.build` | Per rule and source of legitimate mail (ham) or real thread messages: denominator, hits, rate, whether it was judged, the proposed and the current reliability factor |
| `score_grid.csv` | `python -m src.router.build` | The 27 grid points of the score calibration on validation: meaning, budget, worst source, distance from the initial numbers, the chosen one |
| `score_config.csv` | `python -m src.router.build` | The frozen score numbers, the false-alarm budget and the reliability settings |
| `score_distribution.csv` | `python -m src.router.build` | Validation emails per band for all, per category, per source and per source and category, among all emails and among emails with a checked claim |
| `score_budget.csv` | `python -m src.router.build` | The false-alarm budget per source of legitimate mail and of real thread messages (spam listed, not budgeted), with Wilson intervals, an OVER note and the rules behind each verdict |
| `score_benchmark_check.csv` | `python -m src.router.build` | The hijack benchmark's validation cases scored with the frozen numbers, with and without the thread verifier (counts only below 10 cases) |
| `score_checks.csv` | `python -m src.router.build` | PASS/FAIL checks on the router, ledger, score and calibration, plus versions and run details (OVER and other findings are info, not failures) |
| `lime_checks.csv` | `python -m src.explain.check` | The LIME faithfulness check on real validation emails: deletion test against frequency-matched random words at three sizes, seconds per explanation, stability under another seed, overlap with the lime package |
| `api_checks.csv` | `python -m src.api.selftest` | PASS/FAIL checks on the API's security controls (key, rate limits, size caps, validation, headers, errors, audit log, XSS), run with a stand-in classifier, plus library versions |
| `api_mutations.csv` | `python -m src.api.mutation_check` | For each of 37 controls broken on purpose in a scratch copy of the code: whether the self-test noticed (CAUGHT) and the first check that failed |
| `api_smoke.csv` | `python -m src.api.smoke` | PASS/FAIL checks and timings from a real session with the running server and the trained model (oversize bodies, the canary in the server log, real corpus emails with script payloads) |
| `frontend_checks.csv` | `npm run check` (in `frontend/`) | PASS/FAIL checks on the interface: its source (no HTML injection, links, storage or outside addresses), its package pins and `npm audit`, its built bundle (no API key, no outside host, no inline script) and the offset and size logic on hand-made cases; the node version and bundle size as info |
| `frontend_mutations.csv` | `npm run mutation-check` (in `frontend/`) | For each of 26 things broken on purpose in a scratch copy of the interface: whether the static checks noticed (CAUGHT) and the first check that failed |
| `frontend_browser_checks.csv` | `npm run browser-check` (in `frontend/`) | PASS/FAIL checks from the built app driven in a real browser against the running API: what is drawn against what the API answered, error states, size limits, the dashboard against the API's tables, phone width, dark mode, and no Content-Security-Policy violation, script error or alert box |

## Still to come

| Phase | Results |
|---|---|
| 4 (F1) | Keyword baseline precision, recall and F1 against the labels: Phase 13, after the Phase 5 labels |
| 6 (test) | Tactic classifier and baseline on the test split: Phase 13, once, with the thresholds fixed on validation |
| 7 (test) | Claim extractor on the test split: Phase 13, once, with the patterns frozen |
| 8 (test) | Verifier contradiction rates on the test split and the N3 ablation: Phase 13, once, with the rules frozen |
| 9 (test) | Thread verifier on the test threads and the N2 ablation with the risk score: Phase 13, once, with the rules frozen |
| 10 (test) | The risk score, the router and `analyze()` on the test split and the architecture ablation: Phase 13, once, with score version 0.2 frozen |
| 13 | N1, N2, N3 and architecture ablations; claim-extraction accuracy; paraphrase and style-confound tests; charts |
