"""Phase 13: build the caches the experiments read, for the test split (or, as a rehearsal, for the validation split, where they already exist).

Run from the project root, after src.eval.freeze --write has been committed:
    python -m src.eval.prepare_test --split test --workers 4      # the first time: about 35 minutes on the Mac (see below)
    python -m src.eval.prepare_test --split validation            # a rehearsal: everything is in the caches already, so this only checks them

Reads  data/processed/cleaned.parquet, headers.parquet     the emails of the split and their header evidence
       data/processed/threads.parquet                      the rebuilt threads of the split
       data/threads/cases.csv, injections.csv              the hijack benchmark cases of the split
       artifacts/tactic_model/                             the tactic classifier (only for emails that are not cached yet)
Writes data/processed/claims_cache/claims_<split>.parquet           the claims of every email (spaCy; the slow part, about 20 minutes for 14,903 emails with --workers 4)
       data/processed/tactic_probs/probs_<split>.parquet            the tactic probabilities of every email (about 11 minutes on the CPU)
       data/processed/thread_features/<split>.parquet and hijack.parquet     the same two things for the messages of real threads and for the injected benchmark messages
       results/eval_cache_counts.csv, eval_cache_checks.csv         what was built (counts only) and PASS/FAIL checks

No score, label or metric is computed here. The caches are inputs: the claims and the probabilities are what the frozen extractor and the frozen classifier say about
each email, and they do not depend on any label. Building them is allowed to repeat (a run that is stopped continues where it stopped), so this script is the one
test-split script that needs no --rerun. It still checks the freeze record first, because the caches must be built by the frozen components.
"""

import argparse
import sys

import pandas as pd

from src.data import paths
from src.data.hijack_benchmark import candidate_message
from src.eval import common, freeze
from src.router.build import get_probs, load_real_threads, run_stamp
from src.thread.features import attach_features
from src.verifiers.build import get_claims, load_split


def prime_hijack_features(split, threads, featurize=attach_features):
    """Features (tactic probabilities and claims) of the injected benchmark messages of a split; returns how many messages were examined."""
    cases = pd.read_csv(paths.HIJACK_CASES_CSV)
    cases = cases[(cases["split"] == split) & cases["thread"].isin(set(threads))]
    injections = pd.read_csv(paths.HIJACK_INJECTIONS_CSV).set_index("thread").to_dict("index")
    candidates = [candidate_message(c["variant"], threads[c["thread"]], int(c["index"]), injections[c["thread"]])[0] for c in cases.to_dict("records") if c["variant"] != "neg_real"]
    featurize(candidates, "hijack")
    return len(cases), len(candidates)


def run(split, rerun=None, workers=1, classifier=None, featurize=attach_features):
    """Build every cache of a split. classifier and featurize can be replaced (the self-test does). Returns (counts table, checks)."""
    guard = freeze.begin("prepare_test", split, rerun, once=False)
    checks = common.Checks()
    stamp = run_stamp()

    def classifier_factory():
        nonlocal classifier
        if classifier is None:
            from src.models.predict import TacticClassifier
            classifier = TacticClassifier()
        return classifier

    print("1. emails of the %s split" % split)
    table = load_split(split)
    claim_lists, extracted = get_claims(table, split, workers)
    probabilities = get_probs(table, split, classifier_factory, stamp)
    print("2. real threads of the %s split" % split)
    threads = load_real_threads(split, featurize)
    print("3. injected messages of the hijack benchmark")
    cases, injected = prime_hijack_features(split, threads, featurize) if paths.HIJACK_CASES_CSV.exists() else (0, 0)
    messages = sum(len(t) for t in threads.values())

    counts = pd.DataFrame([
        {"split": split, "cache": "emails", "items": len(table), "detail": "%d claims extracted in this run" % extracted},
        {"split": split, "cache": "claims", "items": sum(len(c) for c in claim_lists), "detail": "claims found in those emails"},
        {"split": split, "cache": "tactic probabilities", "items": len(probabilities), "detail": "emails, 7 probabilities each"},
        {"split": split, "cache": "real thread messages", "items": messages, "detail": "%d threads" % len(threads)},
        {"split": split, "cache": "hijack candidates", "items": injected, "detail": "%d cases of the split (neg_real needs no injected text)" % cases},
    ])
    expected = pd.read_csv(paths.SPLIT_COUNTS_CSV)
    expected = int(expected[split].sum()) if split in expected.columns else None
    checks.add("emails", "emails of the split equal results/split_counts.csv", len(table), expected, expected is None or len(table) == expected)
    checks.add("probabilities", "one row of 7 probabilities per email, all between 0 and 1", "%d x %d" % probabilities.shape,
               "%d x 7" % len(table), probabilities.shape == (len(table), 7) and bool(probabilities.min() >= 0) and bool(probabilities.max() <= 1))
    checks.add("claims", "one claim list per email", len(claim_lists), len(table), len(claim_lists) == len(table))
    seen = {m["split"] for t in threads.values() for m in t}
    checks.add("threads", "every thread message belongs to the split", ",".join(sorted(seen)) or "none", split, seen <= {split})
    checks.add("run", "tactic model run (the caches depend on it)", stamp.get("tactic_run"), "", None)
    common.write_table(guard, "eval_cache_counts", counts)
    common.write_table(guard, "eval_cache_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return counts, checks


def main(argv):
    parser = argparse.ArgumentParser(description="Build the claim, probability and thread-feature caches of a split (Phase 13).")
    freeze.add_run_arguments(parser)
    parser.add_argument("--workers", type=int, default=1, help="processes for the claim extraction")
    args = parser.parse_args(argv)
    _, checks = run(args.split, args.rerun, max(1, args.workers))
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
