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

# Files written by later Phase 1 scripts
STAGED_PARQUET = PROCESSED_DIR / "staged.parquet"
HEADER_COVERAGE_CSV = RESULTS_DIR / "header_coverage.csv"


def relative(path):
    """Return path relative to the project root, for short printouts.

    Example: /Users/.../pretextguard/data/raw/enron -> data/raw/enron
    """
    return Path(path).resolve().relative_to(PROJECT_ROOT)
