"""Every folder and file path the data scripts use, defined once.

Other modules import their paths from here instead of typing them out, so a
folder can be renamed in one place. Paths are built from this file's own
location, so they are correct whichever folder a script is started from
(we still always run scripts from the project root).
"""

from pathlib import Path

# src/data/paths.py -> parents[0] is src/data, [1] is src, [2] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # downloads, never modified
PROCESSED_DIR = DATA_DIR / "processed"  # tables our scripts write
RESULTS_DIR = PROJECT_ROOT / "results"  # numbers that go into the report

# One folder per source inside data/raw/
KAGGLE_DIR = RAW_DIR / "kaggle"
SPAMASSASSIN_DIR = RAW_DIR / "spamassassin"
NAZARIO_DIR = RAW_DIR / "nazario"
ENRON_DIR = RAW_DIR / "enron"
PHISHING_POT_DIR = RAW_DIR / "phishing_pot"
APACHE_DIR = RAW_DIR / "apache"

# Files written by Phase 1 (src/data)
STAGED_PARQUET = PROCESSED_DIR / "staged.parquet"
STAGED_COUNTS_CSV = RESULTS_DIR / "staged_counts.csv"
DEDUP_PAIRS_CSV = RESULTS_DIR / "dedup_pairs.csv"
HEADER_COVERAGE_CSV = RESULTS_DIR / "header_coverage.csv"
SPLIT_COUNTS_CSV = RESULTS_DIR / "split_counts.csv"

# Files written by Phase 2 (src/preprocess)
CLEANED_PARQUET = PROCESSED_DIR / "cleaned.parquet"
PREPROCESS_SUMMARY_CSV = RESULTS_DIR / "preprocess_summary.csv"
PREPROCESS_CHECKS_CSV = RESULTS_DIR / "preprocess_checks.csv"

# Files written by Phase 3 (src/headers)
HEADERS_PARQUET = PROCESSED_DIR / "headers.parquet"
HEADER_EVIDENCE_SUMMARY_CSV = RESULTS_DIR / "header_evidence_summary.csv"
HEADER_TOP_DOMAINS_CSV = RESULTS_DIR / "header_top_domains.csv"
HEADER_AUTH_FORMATS_CSV = RESULTS_DIR / "header_auth_formats.csv"

# Files written by Phase 4 (src/baseline)
KEYWORD_HIT_RATES_CSV = RESULTS_DIR / "keyword_hit_rates.csv"
KEYWORD_PHRASE_HITS_CSV = RESULTS_DIR / "keyword_phrase_hits.csv"
KEYWORD_CHECKS_CSV = RESULTS_DIR / "keyword_checks.csv"

# Files written by Phase 5 (src/data): annotation, labels, synthetic emails, SemEval mapping
LABELLED_DIR = DATA_DIR / "labelled"
BATCHES_DIR = LABELLED_DIR / "batches"          # full email text, never committed
SAMPLE_CSV = LABELLED_DIR / "sample.csv"        # which emails were drawn (ids only, no text)
ANNOTATORS_CSV = LABELLED_DIR / "annotators.csv"
REPLIES_LOG_CSV = LABELLED_DIR / "replies_log.csv"
LABELS_CSV = LABELLED_DIR / "labels.csv"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
SYNTHETIC_CSV = SYNTHETIC_DIR / "synthetic.csv"
SEMEVAL_DIR = RAW_DIR / "semeval"
SAMPLE_COUNTS_CSV = RESULTS_DIR / "sample_counts.csv"
LABEL_VALIDATION_CSV = RESULTS_DIR / "label_validation.csv"
LABEL_AGREEMENT_CSV = RESULTS_DIR / "label_agreement.csv"
LABEL_COUNTS_CSV = RESULTS_DIR / "label_counts.csv"
SYNTHETIC_COUNTS_CSV = RESULTS_DIR / "synthetic_counts.csv"
SEMEVAL_MAPPING_CSV = RESULTS_DIR / "semeval_mapping.csv"

# Files written by Phase 6 (src/models): the tactic classifier
TACTIC_DATA_PARQUET = PROCESSED_DIR / "tactic_data.parquet"   # train + validation text uploaded to Colab; never committed
TACTIC_MODEL_DIR = PROJECT_ROOT / "artifacts" / "tactic_model"  # weights, tokenizer, thresholds; never committed
TACTIC_DATA_COUNTS_CSV = RESULTS_DIR / "tactic_data_counts.csv"
TACTIC_TRAINING_LOG_CSV = RESULTS_DIR / "tactic_training_log.csv"
TACTIC_SEED_SUMMARY_CSV = RESULTS_DIR / "tactic_seed_summary.csv"
TACTIC_VAL_PROBS_CSV = RESULTS_DIR / "tactic_val_probs.csv"
TACTIC_RUN_INFO_JSON = RESULTS_DIR / "tactic_run_info.json"
TACTIC_VALIDATION_SCORES_CSV = RESULTS_DIR / "tactic_validation_scores.csv"
TACTIC_CHECKS_CSV = RESULTS_DIR / "tactic_checks.csv"

# Files written by Phase 7 (src/claims): the claim extractor
CLAIM_HIT_RATES_CSV = RESULTS_DIR / "claim_hit_rates.csv"
CLAIM_PATTERN_HITS_CSV = RESULTS_DIR / "claim_pattern_hits.csv"
CLAIM_SCORES_CSV = RESULTS_DIR / "claim_scores.csv"
CLAIM_CHECKS_CSV = RESULTS_DIR / "claim_checks.csv"

# Files written by Phase 8 (src/verifiers): the header and request verifiers
CLAIMS_CACHE_DIR = PROCESSED_DIR / "claims_cache"   # extracted claims per split, reused by Phases 8, 10 and 13; never committed
VERIFIER_RATES_CSV = RESULTS_DIR / "verifier_rates.csv"
VERIFIER_RULE_HITS_CSV = RESULTS_DIR / "verifier_rule_hits.csv"
VERIFIER_CHECKS_CSV = RESULTS_DIR / "verifier_checks.csv"

# Files written by Phase 9 (src/thread, src/data/hijack_benchmark.py): threads and the thread-hijack benchmark
ENRON_MAILDIR = ENRON_DIR / "enron_mail_20150507" / "maildir"          # the unpacked CMU archive: one file per message
ENRON_INDEX_PARQUET = PROCESSED_DIR / "enron_index.parquet"            # one row per distinct Enron message; never committed
THREADS_PARQUET = PROCESSED_DIR / "threads.parquet"                    # one row per message of every rebuilt thread; never committed
THREAD_FEATURES_DIR = PROCESSED_DIR / "thread_features"                # tactic probabilities and claims per message, cached; never committed
THREADS_DIR = DATA_DIR / "threads"                                     # the benchmark: manifest, injected texts, raw replies (committed)
HIJACK_PLAN_CSV = THREADS_DIR / "plan.csv"
HIJACK_PROMPTS_DIR = THREADS_DIR / "prompts"                           # prompts hold excerpts of real emails: never committed
HIJACK_REPLIES_DIR = THREADS_DIR / "replies"
HIJACK_GENERATOR_CSV = THREADS_DIR / "generator.csv"
HIJACK_LOG_CSV = THREADS_DIR / "replies_log.csv"
HIJACK_INJECTIONS_CSV = THREADS_DIR / "injections.csv"                 # the synthetic texts (attack, benign twin, fake quote) per thread
HIJACK_CASES_CSV = THREADS_DIR / "cases.csv"                           # the benchmark manifest: one row per case
THREAD_COUNTS_CSV = RESULTS_DIR / "thread_counts.csv"
THREAD_SIGNAL_RATES_CSV = RESULTS_DIR / "thread_signal_rates.csv"
THREAD_CHECKS_CSV = RESULTS_DIR / "thread_checks.csv"
HIJACK_GENERATION_CSV = RESULTS_DIR / "hijack_generation.csv"
HIJACK_CASE_COUNTS_CSV = RESULTS_DIR / "hijack_cases.csv"
THREAD_SCORES_CSV = RESULTS_DIR / "thread_scores.csv"
HIJACK_CHECKS_CSV = RESULTS_DIR / "hijack_checks.csv"


def relative(path):
    """Return path relative to the project root, for short printouts.

    Example: /Users/.../pretextguard/data/raw/enron -> data/raw/enron
    """
    return Path(path).resolve().relative_to(PROJECT_ROOT)
