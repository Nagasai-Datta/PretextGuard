"""Check a logged rerun of evaluation scripts against the results they replaced (13 October 2026).

Run from the project root, after copying results/*.csv to a folder BEFORE the reruns:
    python -m src.eval.rerun_check /tmp/pg_before

WHY. Two evaluation scripts had a bug that touched only some rows (master document Section 8.21, version 3.15.4):
  - style_confound.py read every email of a source in a same-kind pair, so the ham pairs of the four sources that hold ham and spam also read their spam,
    and the spam pairs repeated ham pairs; the same-kind rows of style_auc.csv change, the real-against-synthetic rows must not;
  - ablation_n3.py (and through it ablation_arch.py) and ablation_n1.py labelled each per-source row with the category of the source's first email, so a
    source holding ham and spam got one row over both; now there is one row per source and category, and every other row must stay exactly as it was.
The bootstrap draws depend only on the clusters, the number of resamples and the seed (src/eval/stats.py Resampler), so adding per-group columns cannot move any
pooled number or interval. This script proves that on the real files: every row the bug did not touch is compared as text, cell by cell.

It changes nothing. It prints PASS or FAIL per check and exits 1 on any FAIL.
"""

import sys
from pathlib import Path

import pandas as pd

from src.data import paths

UNCHANGED_FILES = ["n3_differences.csv", "n3_cuts.csv", "n3_synthetic_bec.csv", "arch_differences.csv", "arch_agreement.csv", "arch_reasons.csv",
                   "n1_differences.csv", "n1_view_counts.csv"]
RERUN_SCRIPTS = {"style_confound", "ablation_n3", "ablation_arch", "ablation_n1"}


def read(folder, name):
    path = Path(folder) / name
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else None


def same(a, b):
    return a is not None and b is not None and list(a.columns) == list(b.columns) and a.reset_index(drop=True).equals(b.reset_index(drop=True))


def main(argv):
    if len(argv) != 1:
        raise SystemExit("usage: python -m src.eval.rerun_check <folder with the results/*.csv copied before the reruns>")
    before, after = Path(argv[0]), paths.RESULTS_DIR
    results = []

    def check(label, ok, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, ("   [" + detail + "]") if detail else ""))

    # files the fix does not touch: identical
    for name in UNCHANGED_FILES:
        check("%s is unchanged" % name, same(read(before, name), read(after, name)))

    # N3 and architecture: every row except the per-source rows is unchanged; the per-source rows are per source and category
    for name in ("n3_systems.csv", "arch_systems.csv"):
        old, new = read(before, name), read(after, name)
        if old is None or new is None:
            check("%s exists before and after" % name, False)
            continue
        keep = lambda t: t[~t["scope"].str.startswith("source")]
        check("%s: every pooled and validation row is unchanged" % name, same(keep(old), keep(new)), "%d rows" % len(keep(new)))
        rows = new[(new["split"] == "test") & new["scope"].str.startswith("source: ") & (new["system"] == "full")]
        mixed = [s for s in ("spamassassin", "kaggle_ceas08", "kaggle_enron", "kaggle_ling") if {"source: %s (ham)" % s, "source: %s (spam)" % s} <= set(rows["scope"])]
        check("%s: the four mixed sources have a ham row and a spam row" % name, len(mixed) == 4, ", ".join(mixed))
        check("%s: the per-source rows of the full system count every test email once" % name, sum(int(n) for n in rows["n"]) == 14903, str(sum(int(n) for n in rows["n"])))

    # N1: every overall row is unchanged; per-source rows are per source and category
    old, new = read(before, "n1_scores.csv"), read(after, "n1_scores.csv")
    if old is None or new is None:
        check("n1_scores.csv exists before and after", False)
    else:
        keep = lambda t: t[t["scope"] == "overall"]
        check("n1_scores.csv: every overall row is unchanged", same(keep(old), keep(new)), "%d rows" % len(keep(new)))
        rows = new[(new["model"] == "distilbert_A") & (new["view"] == "raw") & new["scope"].str.startswith("source: ")]
        check("n1_scores.csv: the per-source rows of the raw view count every test email once", sum(int(n) for n in rows["n"]) == 14903, str(sum(int(n) for n in rows["n"])))

    # style: the real-against-synthetic rows are unchanged; the same-kind rows repeat no pair
    old, new = read(before, "style_auc.csv"), read(after, "style_auc.csv")
    if old is None or new is None:
        check("style_auc.csv exists before and after", False)
    else:
        keep = lambda t: t[t["task"].str.startswith("real against synthetic")]
        check("style_auc.csv: the real-against-synthetic rows are unchanged", same(keep(old), keep(new)))
        same_kind = new[new["task"].str.startswith("same-kind")]
        repeated = int(same_kind.duplicated(["features", "group_a", "group_b", "n_test_a", "n_test_b"]).sum())
        check("style_auc.csv: no same-kind row repeats another kind's pair", repeated == 0, "%d repeated" % repeated)
        ham = same_kind[(same_kind["task"] == "same-kind sources (ham)") & (same_kind["group_a"] == "kaggle_ceas08") & (same_kind["features"] == "words")]
        check("style_auc.csv: a CEAS-08 ham pair reads its 2,588 ham test emails only", len(ham) > 0 and set(ham["n_test_a"]) == {"2588"}, ",".join(sorted(set(ham["n_test_a"]))))

    # every check file of the reruns passes
    for name in ("style_checks.csv", "n3_checks.csv", "arch_checks.csv", "n1_checks.csv"):
        table = read(after, name)
        failed = 0 if table is None else int((table["status"] == "FAIL").sum())
        check("%s has no FAIL" % name, table is not None and failed == 0, "%d FAIL" % failed)

    # the log: each of the four scripts reran once, with a reason, and finished
    log = read(after, "eval_test_log.csv")
    old_log = read(before, "eval_test_log.csv")
    if log is None or old_log is None:
        check("eval_test_log.csv exists before and after", False)
    else:
        added = log.iloc[len(old_log):]
        check("eval_test_log.csv: the earlier lines are unchanged", same(old_log, log.iloc[:len(old_log)]))
        started = added[added["event"] == "started"]
        finished = added[added["event"] == "finished"]
        check("eval_test_log.csv: the four scripts each started once with a reason and finished",
              set(started["script"]) == RERUN_SCRIPTS and len(started) == 4 and (started["reason"] != "").all() and set(finished["script"]) == RERUN_SCRIPTS and len(finished) == 4,
              "; ".join("%s %s" % (r.script, r.event) for r in added.itertuples()))

    failed = results.count(False)
    print("\n%d checks, %d FAIL" % (len(results), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
