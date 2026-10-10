# src/eval/

Phase 13: **every experiment of the project**, one script each, plus the shared tools they stand on. Metrics came first (Phase 6); the ablations, the test-split scores, the supporting experiments and the report charts are Phase 13. Every number in the report and the slides comes from a script in this folder and is saved in `results/`.

```bash
python -m src.eval.selftest
python -m src.eval.stats
python -m src.eval.metrics
```

The first runs every script on a tiny made-up project (no data, no model; about 30 seconds, 104 checks); the second checks the statistics helpers against scikit-learn and textbook values; the third is the Phase 6 metrics self-test (unchanged).

## The rules that make the test numbers honest

1. **The test split is read once per script, after a freeze.** `python -m src.eval.freeze --write` records a SHA-256 for every frozen file (patterns, lexicon, verifiers, thread signals, score and its reliability file, preprocessing, the tactic model and thresholds, the N1 weights, the claim operating points, the benchmark and label files), the version strings and the settings of the experiments, in `results/eval_freeze.csv`. Commit that file **before the first test run**. Every script run with `--split test` recomputes the record and stops if one line differs, then appends its start and finish to `results/eval_test_log.csv`. A second test run of the same script needs `--rerun "reason"` (a bug in the script, never a better number) and the reason is logged.
2. **Every script has a dress rehearsal.** `--split validation` (the default) runs the whole script on the validation split and writes to `data/processed/rehearsal/`, not to `results/`. Bugs in the evaluation code show up there, on real data, where they cost nothing. It also prints the validation figure beside the test figure later; the gap shows how optimistic validation was.
3. **Frozen components are never fixed after the test numbers are seen.** The evaluation scripts themselves are not frozen (a bug in one is fixed and the script rerun with `--rerun`); the tactic model and thresholds, the claim patterns, the verifier and thread rules, the score numbers and the N1 weights are. A frozen component that looks wrong after the test is a finding in the report.
4. **Same false-alarm rate before detection is compared.** The learned comparators of the N3 and architecture ablations are held to the false-alarm rate the frozen score shows on validation ham (`stats.matched_cut`), so no system wins by flagging more mail.
5. **Intervals draw whole groups.** Every rate or F1 has a 95% bootstrap interval (1,000 resamples, seed 42) that resamples the Phase 1 subject groups (campaigns), threads or synthetic pairs, never single emails. Differences between two systems are paired (the same resample for both).
6. **Counts, not rates, below 10 positives** (20 emails for the paraphrase groups), the Phase 5 rule. Real and synthetic results are always apart. Every F1 on tactics or claims says the labels are LLM labels from one model family.

## The order of a run

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
python -m pip install -r requirements.txt                     # adds matplotlib
python -m src.eval.selftest
python -m src.eval.n1_data
```

`n1_data` builds the N1 training and validation samples (train and validation emails only). Then Colab (`notebooks/phase13_n1_models.ipynb`, see `notebooks/README.md`), then:

```bash
python -m src.eval.claim_extraction --choose
python -m src.eval.run_all --split validation --limit 1500 --workers 4
python -m src.eval.freeze --write
python -m src.eval.run_all --split test --workers 4 --with-paraphrase
python -m src.eval.freeze --check
```

In order: `--choose` fixes the claim operating points on the validation scores of Phase 7; the first `run_all` is the rehearsal of every script (about an hour the first time, because the per-email tables of the train and validation splits are built and cached, and a quarter of that afterwards: estimates); `freeze --write` records what is frozen, and `results/eval_freeze.csv` and `results/claim_operating_points.csv` are committed and pushed before the test run; the second `run_all` is the test run, once; the last command shows that nothing differs and the log holds each script once.

## Files

| File | Job |
|---|---|
| `metrics.py` | Precision, recall, F1, macro-F1 and threshold tuning, written by hand (Phase 6) |
| `stats.py` | Bootstrap over groups (`Resampler`, `Tally`), Wilson intervals, AUC with an interval, the matched false-alarm cut; self-test against scikit-learn |
| `freeze.py` | The freeze record, the test-run guard and the log (`begin`, `Run`, `--write`, `--check`) |
| `common.py` | The settings that are part of the freeze, the PASS/FAIL list every script saves, the subject-group ids, table writing |
| `world.py` | One per-email table per split (the full system's score and band, the contradictions behind them, and what text-only, headers-only and the flat vector see), built once and cached |
| `systems.py` | The five systems of the N3 and architecture ablations, how they are fitted and how they are held to one false-alarm rate |
| `prepare_test.py` | Builds the claim, probability and thread-feature caches of a split; no number is computed |
| `tactic_test.py` | DistilBERT and the keyword baseline on the labelled real and synthetic test emails; the co-occurrence and confusion analysis |
| `claim_extraction.py` | The frozen claim extractor on the test labels at the operating point chosen on validation (`--choose` makes the choice) |
| `score_test.py` | The frozen risk score on the test split: bands per category and source with both denominators, the false-alarm budget |
| `ablation_n1.py`, `n1_data.py`, `n1_train.py`, `n1_model.py` | N1: the training sample, the Colab training of model A (raw) and B (redacted), the model loader, and the test of both on four views next to a TF-IDF pair and a link-presence rule |
| `ablation_n2.py` | N2: the test hijack cases with and without the thread verifier, flip-point accuracy, false alarms on real test threads |
| `ablation_n3.py` | N3: the full system against text only, headers only and parallel fusion, per source, plus the synthetic BEC arm with synthetic header blocks |
| `ablation_arch.py` | Architecture: the routed score against a flat classifier on the same signals; agreement and traceable reasons |
| `style_confound.py` | The source-classifier AUC: can the collections be told apart by their writing? Real against synthetic |
| `paraphrase.py` | The adversarial paraphrase test: a language model rewords test emails, `analyze()` runs before and after |
| `charts.py` | The report PNGs, drawn from the results tables only (matplotlib) |
| `run_all.py` | Runs the scripts in order for a split and prints one summary |
| `selftest.py` | Every script on a tiny made-up project |

## What each script writes (prefix groups the dashboard)

| Script | Files in `results/` |
|---|---|
| `freeze.py` | `eval_freeze.csv`, `eval_test_log.csv` |
| `prepare_test.py` | `eval_cache_counts.csv`, `eval_cache_checks.csv` |
| `tactic_test.py` | `tactic_test_scores.csv`, `tactic_test_checks.csv`, `analysis_cooccurrence.csv`, `analysis_confusion_pairs.csv` |
| `claim_extraction.py` | `claim_operating_points.csv`, `claim_test_scores.csv`, `claim_test_checks.csv` |
| `score_test.py` | `score_test_distribution.csv`, `score_test_budget.csv`, `score_test_checks.csv` |
| `n1_data.py`, Colab, `ablation_n1.py` | `n1_data_counts.csv`, `n1_training_log.csv`, `n1_run_info.json` and `n1_val_probs.csv` (both from Colab), `n1_scores.csv`, `n1_differences.csv`, `n1_view_counts.csv`, `n1_checks.csv` |
| `ablation_n2.py` | `n2_scores.csv`, `n2_score_benchmark.csv`, `n2_false_alarms.csv`, `n2_checks.csv` |
| `ablation_n3.py` | `n3_systems.csv`, `n3_differences.csv`, `n3_cuts.csv`, `n3_synthetic_bec.csv`, `n3_checks.csv` |
| `ablation_arch.py` | `arch_systems.csv`, `arch_differences.csv`, `arch_agreement.csv`, `arch_reasons.csv`, `arch_checks.csv` |
| `style_confound.py` | `style_auc.csv`, `style_checks.csv` |
| `paraphrase.py` | `paraphrase_results.csv`, `paraphrase_bands.csv`, `paraphrase_checks.csv` |
| `charts.py` | `docs/figures/results/*.png` (13 charts) |

A new result file also needs its name in `RESULT_FILES` (`src/api/results.py`) before the dashboard can show it; this phase added all the CSV files above except the 6,000-row `n1_val_probs.csv` (a per-email list of probabilities, not a table to read).

## What the experiments can and cannot say

- **Labels.** Tactic and claim scores are agreement with LLM labels from one model family. The N1 labels are corpus labels (attack corpora against the rest).
- **Corpora.** No source holds both attacks and ordinary mail, so a pooled F1 mixes corpus and detection. Per-source rates, the matched false-alarm rate and the style-confound test are how this is handled; none of them removes it.
- **What favours which system.** The learned comparators are fitted on attack labels; the frozen score uses none. A headers-only model can partly learn which corpus an email came from. Both favour the learned systems.
- **Synthetic parts.** The hijack cases, the synthetic BEC header blocks and the paraphrases are synthetic or machine-written; they test that the rules do what they are defined to do, not how often real attackers behave that way.
- **One of each.** One N1 training sample (about 9,000 emails) and two seeds per model; intervals cover the test sample, not the training randomness.
- **The paraphrase test** reads six pairs by hand for meaning; the script cannot judge it.

## Security and privacy

No script in this folder sends anything over the network except `paraphrase.py`, which sends redacted bodies of public-corpus emails to the free language-model API of Phase 5 (the key is read from `.env`, never printed). Its rewrites are stored in `data/processed/paraphrase/`, which Git ignores. Nothing printed or saved in `results/` holds email text. The freeze guard reads files and hashes them; it writes only the two CSV files above.
