"""Phase 13: the small things every experiment script shares (settings, the PASS/FAIL list, the subject groups used by the bootstrap, table helpers).

The settings here are part of the freeze (src/eval/freeze.py records their values), so they are written down before the test split is read.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.data import paths
from src.eval.stats import MIN_POSITIVES

MATCHED_FPR_FLOOR = 0.005          # comparators are held to the frozen score's own false-alarm rate on validation ham, but never below this share
N1_THRESHOLD = 0.5                 # the cut of both N1 models and of the TF-IDF models: fixed, never tuned
FLAG_BAND = "Suspicious"           # an email is flagged when its band is this or higher (score 35 or more)
PARAPHRASE_PER_SOURCE = 50         # test attack emails rewritten per attack source
PARAPHRASE_HAM_PER_SOURCE = 10     # test ham emails rewritten per ham source (the control: does rewording create false alarms?)
PARAPHRASE_BATCH = 5               # emails per request to the language model
PARAPHRASE_TEMPERATURE = 0.7
PARAPHRASE_SEED = 42
ATTACK_CATEGORIES = ("phishing", "fraud")      # is_attack; spam is neither attack nor legitimate mail
LABEL_NOTE = "labels are LLM labels from one model family"


def split_total(split):
    """The number of emails of a split according to results/split_counts.csv, or None when the file or the column is missing.

    The file ends with a 'total' row (source 'total'); it is left out here, otherwise every email would be counted twice."""
    path = paths.SPLIT_COUNTS_CSV
    if not Path(path).exists():
        return None
    table = pd.read_csv(path)
    if split not in table.columns:
        return None
    return int(table[table["source"] != "total"][split].sum())


def is_flagged(band):
    """True for Suspicious and High risk."""
    return band != "Low risk"


def round_or_none(value, digits=4):
    return None if value is None or (isinstance(value, float) and value != value) else round(float(value), digits)


def interval_cells(prefix, interval, digits=4):
    """{prefix: point, prefix_ci_low: low, prefix_ci_high: high} from a (point, low, high) triple."""
    point, low, high = interval
    return {prefix: round_or_none(point, digits), prefix + "_ci_low": round_or_none(low, digits), prefix + "_ci_high": round_or_none(high, digits)}


class Checks:
    """The PASS/FAIL/info list every script saves as <prefix>_checks.csv."""

    COLUMNS = ["check", "item", "value", "expected", "status"]

    def __init__(self):
        self.rows = []

    def add(self, check, item, value, expected, passed):
        """passed True gives PASS, False FAIL, None info."""
        self.rows.append({"check": check, "item": item, "value": value, "expected": expected, "status": "info" if passed is None else "PASS" if passed else "FAIL"})

    def frame(self):
        return pd.DataFrame(self.rows, columns=self.COLUMNS)

    def failed(self):
        return sum(1 for r in self.rows if r["status"] == "FAIL")

    def print(self, only_problems=False):
        for r in self.rows:
            if only_problems and r["status"] != "FAIL":
                continue
            print("  %-4s %-22s %-70s %s%s" % (r["status"], r["check"], str(r["item"])[:70], r["value"], "  (expected %s)" % r["expected"] if r["expected"] != "" else ""))
        print("%d PASS, %d FAIL, %d info" % tuple(sum(1 for r in self.rows if r["status"] == s) for s in ("PASS", "FAIL", "info")))


def write_table(run, name, frame):
    """Write one results table (results/<name>.csv for a test run, the rehearsal folder otherwise) and say so."""
    path = run.path(name + ".csv")
    frame.to_csv(path, index=False)
    print("  wrote %s (%d rows)" % (path.relative_to(paths.PROJECT_ROOT) if str(path).startswith(str(paths.PROJECT_ROOT)) else path, len(frame)))
    return path


def cluster_ids(split):
    """A Series (index = email id) with the Phase 1 subject group of every email in a split: the unit the bootstrap draws.

    The group is the one src/data/split.py used (source, category and the subject without Re:/Fwd:), and groups bigger than the split's cap are broken up into
    single emails exactly as there (they were too common to be one thread). The cap uses the size of the whole stratum, read from the staged table."""
    from src.data.split import GROUP_CAP_SHARE, MIN_GROUP_CAP, group_keys

    staged = pd.read_parquet(paths.STAGED_PARQUET, columns=["id", "source", "category", "raw_headers"], filters=[("split", "==", split)]).reset_index(drop=True)
    strata = pd.read_parquet(paths.STAGED_PARQUET, columns=["source", "category"]).groupby(["source", "category"]).size()
    staged["group"] = group_keys(staged)
    size = staged.groupby("group")["id"].transform("size")
    cap = pd.Series([max(GROUP_CAP_SHARE * strata[(s, c)], MIN_GROUP_CAP) for s, c in zip(staged["source"], staged["category"])], index=staged.index)
    staged["group"] = staged["group"].where(size <= cap, staged["group"] + "|" + staged["id"])
    return pd.Series(staged["group"].to_numpy(), index=staged["id"].to_numpy())


def clusters_for(ids, split):
    """The cluster of each id in `ids` (an array in the order of the items). An id the staged table does not know is its own cluster."""
    table = cluster_ids(split)
    return np.array([table.get(i, "id:" + str(i)) for i in ids])


def source_summary(frame, by, flag_column, label):
    """Rows of (source, n, flagged, rate) for a boolean column, per value of `by`; used for the per-source tables."""
    rows = []
    for key, part in frame.groupby(by):
        rows.append({"group": key, "n": len(part), "flagged": int(part[flag_column].sum()), "rate": round(float(part[flag_column].mean()), 4) if len(part) else None, "what": label})
    return pd.DataFrame(rows)


def enough(positives):
    """True when a score may be reported as a rate (the Phase 5 rule: 10 positives)."""
    return positives >= MIN_POSITIVES
