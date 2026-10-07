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


def relative(path):
    """Return path relative to the project root, for short printouts.

    Example: /Users/.../pretextguard/data/raw/enron -> data/raw/enron
    """
    return Path(path).resolve().relative_to(PROJECT_ROOT)
