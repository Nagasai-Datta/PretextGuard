"""Phase 13: run every experiment script in order, for the validation split (a dress rehearsal) or the test split, and print one summary.

Run from the project root:
    python -m src.eval.run_all --split validation --limit 3000 --train-limit 20000     # the rehearsal: every script on the validation split, the big ones on a sample (about 20 minutes)
    python -m src.eval.run_all --split test                                            # the test run, once: every script reads the test split once (needs results/eval_freeze.csv)
    python -m src.eval.run_all --split test --only n1,n3                                # only the scripts whose name contains one of these words
    python -m src.eval.run_all --split test --with-paraphrase                           # also the paraphrase test (needs GEMINI_API_KEY in .env)

The order is the dependency order: caches first (prepare_test), then the scripts that score one component (tactic_test, claim_extraction, score_test), then the ablations (ablation_n2, ablation_n3,
ablation_arch, ablation_n1), the style-confound test, optionally the paraphrase test, and last the charts, which only read the tables the others wrote. Each script is a separate process, so one that
fails does not take the others with it; the run stops at the first failure unless --keep-going is given (a test script that failed halfway through needs `--rerun "reason"` to run again, see
src/eval/freeze.py). The summary reads each script's checks file and counts PASS, FAIL and info.

This file only starts the scripts. Every number is computed by them, and each one writes its own table to results/ (test) or data/processed/rehearsal/ (validation).
"""

import argparse
import subprocess
import sys
import time

import pandas as pd

from src.data import paths

# (name, module, checks file, takes --workers, takes --limit, takes --train-limit)
SCRIPTS = [
    ("prepare_test", "src.eval.prepare_test", "eval_cache_checks", True, False, False),
    ("tactic_test", "src.eval.tactic_test", "tactic_test_checks", False, False, False),
    ("claim_extraction", "src.eval.claim_extraction", "claim_test_checks", False, False, False),
    ("score_test", "src.eval.score_test", "score_test_checks", True, True, False),
    ("ablation_n2", "src.eval.ablation_n2", "n2_checks", False, False, False),
    ("ablation_n3", "src.eval.ablation_n3", "n3_checks", True, True, True),
    ("ablation_arch", "src.eval.ablation_arch", "arch_checks", True, True, True),
    ("ablation_n1", "src.eval.ablation_n1", "n1_checks", False, True, False),
    ("style_confound", "src.eval.style_confound", "style_checks", False, False, False),
    ("paraphrase", "src.eval.paraphrase", "paraphrase_checks", False, False, False),
    ("charts", "src.eval.charts", None, False, False, False),
]


def plan(split, only=(), skip=(), with_paraphrase=False, limit=0, train_limit=0, workers=1, rerun=None):
    """[(name, command list, checks file)] for the scripts to run, in order."""
    if split == "test" and (limit or train_limit):
        raise SystemExit("--limit and --train-limit are for rehearsals: the test run uses every email")
    steps = []
    for name, module, checks, takes_workers, takes_limit, takes_train_limit in SCRIPTS:
        if name == "paraphrase" and not (with_paraphrase or any(w in name for w in only)):
            continue
        if only and not any(word in name for word in only):
            continue
        if any(word in name for word in skip):
            continue
        command = [sys.executable, "-m", module, "--split", split]
        if name != "charts":
            if rerun:
                command += ["--rerun", rerun]
            if takes_workers and workers > 1:
                command += ["--workers", str(workers)]
            if takes_limit and limit:
                command += ["--limit", str(limit)]
            if takes_train_limit and train_limit:
                command += ["--train-limit", str(train_limit)]
            if name == "paraphrase" and split == "validation":
                command += ["--per-source", "10", "--ham-per-source", "4"]
        steps.append((name, command, checks))
    return steps


def summarise(folder, steps, results):
    print("\n%-18s %-9s %8s  %s" % ("script", "exit", "seconds", "checks (PASS / FAIL / info)"))
    failed = 0
    for (name, command, checks), (code, seconds) in zip(steps, results):
        text = "-"
        if checks:
            path = folder / (checks + ".csv")
            if path.exists():
                table = pd.read_csv(path)
                counts = [int((table["status"] == s).sum()) for s in ("PASS", "FAIL", "info")]
                text = "%d / %d / %d" % tuple(counts)
                failed += counts[1]
        print("%-18s %-9s %8.0f  %s" % (name, "ok" if code == 0 else "FAILED (%d)" % code, seconds, text))
        failed += 1 if code != 0 else 0
    return failed


def main(argv):
    parser = argparse.ArgumentParser(description="Run every Phase 13 experiment script in order (a rehearsal on validation, or the test run).")
    parser.add_argument("--split", default="validation", choices=("validation", "test"))
    parser.add_argument("--only", default="", help="comma-separated words: run only the scripts whose name contains one of them")
    parser.add_argument("--skip", default="", help="comma-separated words: skip the scripts whose name contains one of them")
    parser.add_argument("--with-paraphrase", action="store_true", help="also run the paraphrase test (it calls the free language-model API)")
    parser.add_argument("--limit", type=int, default=0, help="rehearsal only: a random sample of N emails for score_test, ablation_n3, ablation_arch and ablation_n1")
    parser.add_argument("--train-limit", type=int, default=0, help="rehearsal only: a random sample of N train emails for the fits of ablation_n3 and ablation_arch")
    parser.add_argument("--workers", type=int, default=1, help="processes for the claim extraction")
    parser.add_argument("--rerun", default=None, metavar="REASON", help="test only: pass --rerun REASON to every script (a script that already finished needs it)")
    parser.add_argument("--keep-going", action="store_true", help="continue after a script fails")
    parser.add_argument("--list", action="store_true", help="print the commands and stop")
    args = parser.parse_args(argv)
    words = lambda text: [w for w in text.split(",") if w]
    steps = plan(args.split, words(args.only), words(args.skip), args.with_paraphrase, args.limit, args.train_limit, max(1, args.workers), args.rerun)
    if args.list:
        for name, command, _ in steps:
            print(" ".join(command[1:]))
        return 0
    folder = paths.RESULTS_DIR if args.split == "test" else paths.REHEARSAL_DIR
    print("Running %d scripts on the %s split (outputs in %s)" % (len(steps), args.split, folder))
    results = []
    for name, command, _ in steps:
        print("\n" + "=" * 100 + "\n%s   %s\n" % (name, " ".join(command[1:])) + "=" * 100, flush=True)
        started = time.time()
        code = subprocess.run(command, cwd=str(paths.PROJECT_ROOT)).returncode
        results.append((code, time.time() - started))
        if code != 0 and not args.keep_going:
            steps = steps[:len(results)]
            break
    failed = summarise(folder, steps, results)
    print("\n%s" % ("Everything passed." if not failed else "%d problem(s): read the lines above." % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
