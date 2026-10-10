"""Phase 13: freeze everything before the first test number exists, and refuse to read the test split if anything changed.

    python -m src.eval.freeze --write     # record what is frozen in results/eval_freeze.csv (then commit it; do this BEFORE the first test run)
    python -m src.eval.freeze --check     # compare the files on this machine with the record and list every difference
    python -m src.eval.freeze             # the same as --check, plus the log of test runs so far

WHY. The test split gives the one honest number for each component. It stays honest only if no choice (a threshold, a rule, a weight, a score number)
was made after looking at it. The record below lists, with a SHA-256 for every file and the value of every setting, what the test runs will use.
Every script that reads the test split calls `begin()` below, which recomputes the record and stops if one line differs. The record is committed
before the first test run, so Git's history shows which came first. The scripts write each start and finish of a test run to results/eval_test_log.csv.

WHAT IS FROZEN: the code that decides a score or a label (patterns, lexicon, verifiers, thread signals, score and its reliability file, the
preprocessing, the tactic model and its thresholds, the metric functions), the data that defines the benchmark and the labels, the claim operating
points chosen on validation, the keyword thresholds tuned on validation, and the settings of the experiments. NOT frozen: the evaluation scripts
themselves (src/eval/*.py), because a bug in one of them is fixed and the script rerun with --rerun "reason"; that rerun is logged. A frozen
component that looks wrong after the test numbers are seen is reported as a finding in the report; it is not fixed.

A DRESS REHEARSAL on the validation split (`--split validation`, the default of every script) needs no freeze and writes to data/processed/rehearsal/.
"""

import argparse
import csv
import datetime
import hashlib
import sys
import time
from pathlib import Path

from src.data import paths

FROZEN_FILES = [
    "src/preprocess/clean.py", "src/preprocess/redact.py",
    "src/headers/parser.py", "src/headers/domains.py", "src/headers/evidence.py",
    "src/baseline/lexicon.py", "src/baseline/keywords.py",
    "src/claims/patterns.py", "src/claims/extractor.py", "src/claims/schema.py",
    "src/verifiers/rows.py", "src/verifiers/facts.py", "src/verifiers/brands.py", "src/verifiers/bank.py", "src/verifiers/header_verifier.py",
    "src/verifiers/request_verifier.py", "src/verifiers/verify.py", "src/verifiers/thread_verifier.py",
    "src/thread/signals.py", "src/thread/builder.py", "src/data/hijack_benchmark.py",
    "src/router/score.py", "src/router/router.py", "src/router/ledger.py", "src/router/reliability.json",
    "src/models/predict.py", "src/models/dataset.py", "src/eval/metrics.py",
    "artifacts/tactic_model/model.safetensors", "artifacts/tactic_model/config.json", "artifacts/tactic_model/thresholds.json",
    "artifacts/n1_model_a/model.safetensors", "artifacts/n1_model_a/config.json", "artifacts/n1_model_b/model.safetensors", "artifacts/n1_model_b/config.json",
    "results/tactic_run_info.json", "results/tactic_validation_scores.csv", "results/claim_scores.csv", "results/claim_operating_points.csv", "results/score_config.csv",
    "results/n1_run_info.json", "results/n1_training_log.csv", "results/n1_data_counts.csv",
    "data/labelled/labels.csv", "data/synthetic/synthetic.csv", "data/threads/cases.csv", "data/threads/injections.csv",
]
MANIFEST_COLUMNS = ["item", "kind", "value"]
LOG_COLUMNS = ["time_utc", "script", "split", "event", "freeze_digest", "reason"]


def root():
    return Path(paths.PROJECT_ROOT)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def current_versions():
    """The version strings the frozen components carry (read from the code, not typed here)."""
    from src.baseline.lexicon import LEXICON_VERSION
    from src.claims.patterns import PATTERN_VERSION
    from src.router.score import SCORE_VERSION
    from src.verifiers.thread_verifier import THREAD_RULES_VERSION
    from src.verifiers.verify import RULES_VERSION

    return {"lexicon_version": LEXICON_VERSION, "claim_pattern_version": PATTERN_VERSION, "verifier_rules_version": RULES_VERSION,
            "thread_rules_version": THREAD_RULES_VERSION, "score_version": SCORE_VERSION}


def current_settings():
    """The settings of the experiments, read from the modules that use them."""
    from src.eval import common, stats

    return {"bootstrap_resamples": stats.BOOTSTRAPS, "bootstrap_seed": stats.SEED, "min_positives": stats.MIN_POSITIVES,
            "matched_false_alarm_floor": common.MATCHED_FPR_FLOOR, "n1_threshold": common.N1_THRESHOLD, "flag_band": common.FLAG_BAND,
            "paraphrase_per_source": common.PARAPHRASE_PER_SOURCE, "paraphrase_ham_per_source": common.PARAPHRASE_HAM_PER_SOURCE,
            "paraphrase_batch": common.PARAPHRASE_BATCH, "paraphrase_temperature": common.PARAPHRASE_TEMPERATURE, "paraphrase_seed": common.PARAPHRASE_SEED}


def current_items():
    """[(item, kind, value)]: the SHA-256 of every frozen file (or 'absent'), then the versions and the settings."""
    items = []
    for relative in FROZEN_FILES:
        path = root() / relative
        items.append((relative, "file", sha256_of(path) if path.is_file() else "absent"))
    items += [(name, "version", str(value)) for name, value in current_versions().items()]
    items += [(name, "setting", str(value)) for name, value in current_settings().items()]
    return items


def digest_of(items):
    return hashlib.sha256("\n".join("%s|%s|%s" % item for item in items).encode("utf-8")).hexdigest()


def read_manifest():
    path = Path(paths.EVAL_FREEZE_CSV)
    if not path.is_file():
        return None
    with open(path, newline="", encoding="utf-8") as handle:
        return [(r["item"], r["kind"], r["value"]) for r in csv.DictReader(handle)]


def differences(recorded, now):
    """Human-readable lines for every item that is new, gone or different."""
    before, after = {i: (k, v) for i, k, v in recorded}, {i: (k, v) for i, k, v in now}
    lines = []
    for item in sorted(set(before) | set(after)):
        if item not in before:
            lines.append("%s: not in the record (new)" % item)
        elif item not in after:
            lines.append("%s: in the record but no longer checked" % item)
        elif before[item] != after[item]:
            lines.append("%s: recorded %s, now %s" % (item, before[item][1][:16], after[item][1][:16]))
    return lines


def read_log():
    path = Path(paths.EVAL_TEST_LOG_CSV)
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def append_log(script, split, event, digest, reason=""):
    path = Path(paths.EVAL_TEST_LOG_CSV)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow({"time_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "script": script, "split": split,
                         "event": event, "freeze_digest": digest[:16], "reason": reason})


def write_manifest():
    """Record the current state. Refused once a test run has been logged: a record changed after that proves nothing."""
    started = [r for r in read_log() if r["split"] == "test"]
    if started:
        raise SystemExit("the log already holds a test run (%s at %s): the record is not rewritten after that. If this is a mistake, say so in the report." % (
            started[0]["script"], started[0]["time_utc"]))
    items = current_items()
    path = Path(paths.EVAL_FREEZE_CSV)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(MANIFEST_COLUMNS)
        writer.writerows(items)
    return items


class Run:
    """One run of an experiment script: where its outputs go and, for the test split, the guard and the log."""

    def __init__(self, script, split, out_dir, digest="", reason=""):
        self.script, self.split, self.out_dir, self.digest, self.reason = script, split, Path(out_dir), digest, reason
        self.started = time.time()

    def path(self, name):
        """results/<name>.csv for the test split, data/processed/rehearsal/<name>.csv for a rehearsal."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self.out_dir / name

    def finish(self, ok=True):
        if self.split == "test":
            append_log(self.script, "test", "finished" if ok else "failed", self.digest, self.reason)


def begin(script, split, rerun=None, once=True):
    """Start a script. split 'validation': a rehearsal, no guard. split 'test': the freeze record must match, and a script that already finished a test run
    needs rerun='reason' (once=False for scripts that only build caches and may be repeated)."""
    if split not in ("validation", "test"):
        raise SystemExit("--split must be validation (a rehearsal) or test")
    if split == "validation":
        return Run(script, split, paths.REHEARSAL_DIR)
    recorded = read_manifest()
    if recorded is None:
        raise SystemExit("results/eval_freeze.csv does not exist: run  python -m src.eval.freeze --write  and commit it before the first test run")
    now = current_items()
    changed = differences(recorded, now)
    if changed:
        raise SystemExit("the frozen components differ from results/eval_freeze.csv, so the test split is not read:\n  " + "\n  ".join(changed[:12])
                         + "\nIf this is a bug in an evaluation script, those are not frozen. If a frozen file changed, undo the change.")
    digest = digest_of(now)
    finished = [r for r in read_log() if r["script"] == script and r["split"] == "test" and r["event"] == "finished"]
    if once and finished and not rerun:
        raise SystemExit("%s already finished a test run at %s. A second run needs a reason (a bug in this script, never a better number):  --rerun \"reason\"" % (
            script, finished[-1]["time_utc"]))
    append_log(script, "test", "started", digest, rerun or "")
    return Run(script, "test", paths.RESULTS_DIR, digest, rerun or "")


def add_run_arguments(parser):
    parser.add_argument("--split", default="validation", choices=("validation", "test"),
                        help="validation is a dress rehearsal (the default); test reads the test split, once, after the freeze")
    parser.add_argument("--rerun", default=None, metavar="REASON", help="with --split test: why this script runs a second time (logged)")


# ---------------------------------------------------------------------------------------------------------------------

def main(argv):
    parser = argparse.ArgumentParser(description="Freeze what the test runs will use, and check that nothing changed.")
    parser.add_argument("--write", action="store_true", help="record the current state in results/eval_freeze.csv")
    parser.add_argument("--check", action="store_true", help="compare with the record")
    args = parser.parse_args(argv)
    if args.write:
        items = write_manifest()
        absent = [i for i, k, v in items if v == "absent"]
        print("Wrote %s: %d files, versions and settings. Digest %s." % (paths.relative(paths.EVAL_FREEZE_CSV), len(items), digest_of(items)[:16]))
        if absent:
            print("These frozen files do not exist on this machine (recorded as 'absent'): %s" % ", ".join(absent))
        print("Commit and push the file BEFORE the first test run.")
        return 0
    recorded = read_manifest()
    if recorded is None:
        print("No record yet: run  python -m src.eval.freeze --write")
        return 1
    changed = differences(recorded, current_items())
    print("The record holds %d items; %s." % (len(recorded), "nothing differs" if not changed else "%d differ:" % len(changed)))
    for line in changed:
        print("  " + line)
    if not args.check:
        log = read_log()
        print("\nTest log: %d lines" % len(log))
        for r in log:
            print("  %s  %-24s %-9s %s %s" % (r["time_utc"], r["script"], r["event"], r["freeze_digest"], r["reason"]))
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
