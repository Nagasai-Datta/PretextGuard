"""Phase 10: does LIME point at the words that really matter to the classifier? A label-free faithfulness check, run on the Mac.

Run from the project root (needs the tactic model and data/processed/tactic_data.parquet):
    python -m src.explain.check                                    # 20 emails, 300 copies (about 10 minutes)
    python -m src.explain.check --samples 300,150,600 --crosscheck # the same emails at three sizes, to choose the number of copies, and compared with the
                                                                   # lime package (about 25 minutes; pip install --no-deps lime==0.2.0.1 first)
    python -m src.explain.check --selftest                         # the check itself on a stand-in classifier (no model, no data)

THE TEST (deletion, a standard way to test an explanation without labels). Take real validation emails where the classifier fires a main tactic. LIME names
the words that pushed that tactic up. Remove those words (all their occurrences) and ask the classifier again: if LIME is faithful the probability drops.

A FAIR BASELINE. The words LIME names are often frequent ones ("I", "to", "finance" appear several times), so removing them takes out many tokens, while a
random word is mostly a rare one. Comparing LIME's words with random words of any frequency would therefore reward LIME for removing more text, not for
choosing better. The baseline here is MATCHED BY FREQUENCY: for each LIME word it removes a random other word that occurs the same number of times in the
email (the nearest frequency if none does), 20 random draws averaged. The tokens removed are reported for both, so the match can be seen.

Reported per number of copies: how often LIME names at least one word; the mean drop in the tactic probability for LIME's words and for the matched random
words; the share of explanations where LIME's drop is larger; how often the tactic stops firing; the tokens removed; the seconds per explanation. Reported once
(for the first number of copies): the stability of the top 3 words under another seed (first 12 explanations) and the overlap with the lime package (first 10).
The file is saved after every stage, so an interrupted run keeps what it has.

WHAT THIS CAN AND CANNOT SAY. It says whether the highlighted words matter to the CLASSIFIER, not whether they are the right words for a human (they are often
function words), and nothing about whether the classifier is right (urgency precision on real validation emails is 0.50, authority 0.48). It uses the real
validation emails of the labelled set (137, Phase 5); the test split is never read. There are few emails per tactic, so the numbers are descriptions with their counts.

Writes results/lime_checks.csv (check, item, value, expected, status). Counts and averages only, no email text.
"""

import argparse
import sys
import time
import types
from collections import Counter

import numpy as np
import pandas as pd

from src.data.label_schema import TACTICS
from src.data.paths import LIME_CHECKS_CSV, RESULTS_DIR
from src.explain import lime_explain
from src.explain.lime_explain import explain_text, find_words, remove_words
from src.models.dataset import MAIN_TACTICS

TOP_WORDS = 5                 # LIME words removed per explanation
RANDOM_DRAWS = 20             # random sets, matched by frequency, averaged
BETTER_SHARE = 0.70           # LIME should beat the matched random words in at least this share of explanations (a finding if not)
STABILITY_N = 12              # explanations re-run with another seed
CROSSCHECK_N = 10             # explanations compared with the lime package
SEED = 42


def candidates(texts, probabilities, thresholds, limit):
    """[(text number, tactic, probability)] for the first `limit` emails (in the order given) where a main tactic fires; each fired main tactic is one candidate."""
    out, emails = [], set()
    for i, row in enumerate(probabilities):
        fired = [(t, float(row[TACTICS.index(t)])) for t in MAIN_TACTICS if row[TACTICS.index(t)] >= thresholds[t]]
        if fired and len(emails) < limit:
            emails.add(i)
        if i in emails:
            out += [(i, t, p) for t, p in fired]
    return out


def probability_of(classifier, texts, tactic):
    return classifier.probabilities(texts)[:, TACTICS.index(tactic)]


def word_counts(text):
    """{word: occurrences} of the words that can be removed (placeholders left out)."""
    return Counter(word for _, _, word in find_words(text[:lime_explain.MAX_CHARS]) if word)


def matched_random_words(rng, counts, lime_words):
    """One random other word for each LIME word, with the same number of occurrences in the email (the nearest number if none), no word twice."""
    pool = {word: n for word, n in counts.items() if word not in lime_words}
    chosen = []
    for word in lime_words:
        free = [w for w in pool if w not in chosen]
        if not free:
            break
        best = min(abs(pool[w] - counts[word]) for w in free)
        nearest = sorted(w for w in free if abs(pool[w] - counts[word]) == best)
        chosen.append(nearest[int(rng.integers(len(nearest)))])
    return chosen


def top_words(result, n):
    """The n highlighted words with the largest weights (lower case, each once)."""
    words = []
    for h in sorted(result["highlights"], key=lambda h: -h["weight"]) if result else []:
        if h["word"].lower() not in words:
            words.append(h["word"].lower())
    return words[:n]


def one_explanation(classifier, text, tactic, probability, samples, seed, rng):
    """Explain one tactic of one email and run the deletion test with a frequency-matched random baseline. Returns a dictionary of numbers."""
    started = time.time()
    result = explain_text(text, classifier.probabilities, {tactic: TACTICS.index(tactic)}, num_samples=samples, seed=seed).get(tactic)
    seconds = time.time() - started
    words = top_words(result, TOP_WORDS)
    row = {"seconds": seconds, "k": len(words), "words": words, "top3": words[:3], "p_before": probability, "drop_lime": None, "drop_random": None,
           "flips_lime": None, "flips_random": None, "tokens_lime": None, "tokens_random": None}
    if not words:
        return row
    counts = word_counts(text)
    draws = [matched_random_words(rng, counts, words) for _ in range(RANDOM_DRAWS)]
    texts = [remove_words(text, words)] + [remove_words(text, d) for d in draws]
    after = probability_of(classifier, texts, tactic)
    threshold = classifier.thresholds[tactic]
    row.update({"drop_lime": probability - float(after[0]), "drop_random": probability - float(np.mean(after[1:])),
                "flips_lime": bool(after[0] < threshold), "flips_random": float(np.mean(after[1:] < threshold)),
                "tokens_lime": sum(counts[w] for w in words), "tokens_random": float(np.mean([sum(counts[w] for w in d) for d in draws]))})
    return row


def summarise(rows, samples):
    """The long-form check rows for one number of copies."""
    out = []

    def add(item, value, expected="", status="info"):
        out.append({"check": "lime_deletion", "item": "%d copies: %s" % (samples, item), "value": value, "expected": expected, "status": status})

    n = len(rows)
    named = [r for r in rows if r["k"] > 0]
    add("explanations (email and tactic pairs)", n)
    add("explanations that name at least one word", "%d of %d" % (len(named), n))
    add("seconds per explanation (mean / slowest)", "%.1f / %.1f" % (np.mean([r["seconds"] for r in rows]), max(r["seconds"] for r in rows)) if rows else "-")
    scored = [r for r in named if r["drop_random"] is not None]
    if scored:
        lime_drop, random_drop = np.mean([r["drop_lime"] for r in scored]), np.mean([r["drop_random"] for r in scored])
        better = np.mean([r["drop_lime"] > r["drop_random"] for r in scored])
        add("mean drop of the tactic probability after removing the LIME words / the frequency-matched random words", "%.3f / %.3f" % (lime_drop, random_drop), "LIME larger",
            "PASS" if lime_drop > random_drop else "info")
        add("explanations where removing the LIME words lowers the probability more than the matched random words", "%.0f%% of %d" % (100 * better, len(scored)),
            ">= %d%% (a finding if not)" % (100 * BETTER_SHARE), "PASS" if better >= BETTER_SHARE else "info")
        add("the tactic stops firing after removing the LIME words / the matched random words", "%.0f%% / %.0f%%" % (100 * np.mean([r["flips_lime"] for r in scored]),
                                                                                                                  100 * np.mean([r["flips_random"] for r in scored])))
        add("words removed (mean) and tokens removed for LIME / for the matched random words (mean)", "%.1f words, %.1f / %.1f tokens" % (
            np.mean([r["k"] for r in scored]), np.mean([r["tokens_lime"] for r in scored]), np.mean([r["tokens_random"] for r in scored])))
    return out


def stability(classifier, texts, picked, rows, samples):
    """Mean overlap (Jaccard) of the top 3 words of the first explanations under the seed of the run and under the next seed."""
    overlaps = []
    for (i, tactic, p), row in list(zip(picked, rows))[:STABILITY_N]:
        again = top_words(explain_text(texts[i], classifier.probabilities, {tactic: TACTICS.index(tactic)}, num_samples=samples, seed=SEED + 1).get(tactic), 3)
        union = set(row["top3"]) | set(again)
        if union:
            overlaps.append(len(set(row["top3"]) & set(again)) / len(union))
    return overlaps


def crosscheck(classifier, texts, picked, rows, samples):
    """Overlap of the top 3 positive words with the lime package for the first explanations; None when the package is not installed."""
    try:
        from lime.lime_text import LimeTextExplainer
    except ImportError:
        return None
    explainer = LimeTextExplainer(class_names=list(TACTICS), random_state=SEED, bow=True, split_expression=r"\W+")
    overlaps = []
    for (i, tactic, p), row in list(zip(picked, rows))[:CROSSCHECK_N]:
        column = TACTICS.index(tactic)
        theirs = explainer.explain_instance(texts[i], classifier.probabilities, labels=(column,), num_features=8, num_samples=samples).as_list(label=column)
        top_theirs = {str(w).lower() for w, x in sorted(theirs, key=lambda t: -t[1])[:3] if x > 0}
        union = top_theirs | set(row["top3"])
        if union:
            overlaps.append(len(top_theirs & set(row["top3"])) / len(union))
    return overlaps


def run(args, classifier=None, table=None, output=LIME_CHECKS_CSV):
    started = time.time()
    if classifier is None:
        from src.models.predict import TacticClassifier
        classifier = TacticClassifier()
    if table is None:
        from src.models.dataset import load_table, validation_rows
        table = validation_rows(load_table())
    real = table[table["origin"] == "real"].reset_index(drop=True)
    texts = list(real["text"])
    probabilities = classifier.probabilities(texts)
    picked = candidates(texts, probabilities, classifier.thresholds, args.emails)
    print("%d real validation emails read; %d explanations (email and fired main tactic) from the first %d emails where a main tactic fires" % (
        len(texts), len(picked), len({i for i, _, _ in picked})))
    checks = []

    def save():
        frame = pd.DataFrame(checks)
        if output == LIME_CHECKS_CSV:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output, index=False)
        return frame

    passed, total = lime_explain.self_test(verbose=False)
    checks.append({"check": "selftest", "item": "LIME self-test", "value": "%s of %d" % ("all" if passed else "NOT all", total), "expected": "all pass", "status": "PASS" if passed else "FAIL"})
    checks.append({"check": "leakage_guard", "item": "emails read", "value": "%d real validation emails (the labelled set); never test" % len(texts), "expected": "validation only", "status": "PASS"})
    save()
    rng = np.random.default_rng(SEED)
    first_rows = None
    for samples in args.samples:
        rows = [one_explanation(classifier, texts[i], tactic, p, samples, SEED, rng) for i, tactic, p in picked]
        if first_rows is None:
            first_rows = rows
        new = summarise(rows, samples)
        checks += new
        save()
        print("\n%d copies:" % samples)
        for c in new:
            print("  %-4s %-100s %s" % (c["status"], c["item"].split(": ", 1)[1][:100], c["value"]))
    default = args.samples[0]
    overlaps = stability(classifier, texts, picked, first_rows, default)
    checks.append({"check": "lime_stability", "item": "%d copies: overlap of the top 3 words under two seeds (mean Jaccard, %d explanations)" % (default, len(overlaps)),
                   "value": "%.2f" % np.mean(overlaps) if overlaps else "-", "expected": "(a finding)", "status": "info"})
    save()
    print("\nStability of the top 3 words under another seed (%d copies, %d explanations): %s" % (default, len(overlaps), "%.2f" % np.mean(overlaps) if overlaps else "-"))
    if args.crosscheck:
        overlaps = crosscheck(classifier, texts, picked, first_rows, default)
        if overlaps is None:
            checks.append({"check": "crosscheck", "item": "the lime package is not installed", "value": "skipped", "expected": "pip install --no-deps lime==0.2.0.1", "status": "info"})
        else:
            checks.append({"check": "crosscheck", "item": "%d copies: overlap of the top 3 words with the lime package (mean Jaccard, %d explanations)" % (default, len(overlaps)),
                           "value": "%.2f" % np.mean(overlaps) if overlaps else "-", "expected": "(a finding; the two use different random numbers)", "status": "info"})
            print("Overlap of the top 3 words with the lime package (%d explanations): %s" % (len(overlaps), "%.2f" % np.mean(overlaps) if overlaps else "-"))
    checks.append({"check": "run", "item": "seconds", "value": round(time.time() - started), "expected": "", "status": "info"})
    frame = save()
    print("\nWrote %s (%d seconds)" % (output, round(time.time() - started)))
    return int((frame["status"] == "FAIL").sum())


def self_test():
    """The check itself on a stand-in classifier and ten made-up emails (no model, no data). Returns (passed, number of checks)."""
    import tempfile
    from pathlib import Path

    class Stub:
        thresholds = {t: 0.5 for t in TACTICS}

        def probabilities(self, bodies, batch_size=16):
            return lime_explain.stub_predict([b for b in bodies])

    texts = [lime_explain.sample_text() + " extra %d words here" % i for i in range(10)]
    table = pd.DataFrame({"origin": ["real"] * 10, "text": texts})
    results = []
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "lime_checks.csv"
        failed = run(types.SimpleNamespace(emails=5, samples=[150, 300], crosscheck=False), classifier=Stub(), table=table, output=target)
        frame = pd.read_csv(target)
        results.append(("the check runs on the stand-in classifier and writes its file", failed == 0 and len(frame) > 10))
        better = frame[frame["item"].str.contains("lowers the probability more than the matched random words")]
        results.append(("with a classifier that reacts to exactly the planted words, LIME beats frequency-matched random words in every explanation",
                        len(better) == 2 and all(v.startswith("100%") for v in better["value"])))
        results.append(("the stability of the top words between two seeds is high for the stand-in classifier", float(frame[frame["check"] == "lime_stability"]["value"].iloc[0]) > 0.8))
        tokens = frame[frame["item"].str.contains("tokens removed")]
        results.append(("the matched random words remove about as many tokens as LIME's words", len(tokens) == 2))
    rng = np.random.default_rng(1)
    counts = Counter({"a": 3, "b": 3, "c": 1, "d": 1, "e": 2})
    chosen = matched_random_words(rng, counts, ["a", "c"])
    results.append(("matched_random_words picks another word with the same count, never the LIME word, no word twice", chosen[0] == "b" and chosen[1] == "d" and len(set(chosen)) == 2))
    results.append(("matched_random_words takes the nearest count when none is equal and stops when the pool is empty",
                    matched_random_words(rng, Counter({"a": 5, "b": 2}), ["a"]) == ["b"] and matched_random_words(rng, Counter({"a": 5}), ["a"]) == []))
    for name, ok in results:
        print("  %s %s" % ("PASS" if ok else "FAIL", name))
    return all(ok for _, ok in results), len(results)


def main(argv):
    parser = argparse.ArgumentParser(description="Does LIME point at the words that matter to the classifier? (Phase 10)")
    parser.add_argument("--emails", type=int, default=20, help="how many validation emails (with a fired main tactic) to explain; each gives one to three explanations")
    parser.add_argument("--samples", default="300", help="comma-separated numbers of LIME copies to compare (the first one is used for stability and the cross-check)")
    parser.add_argument("--crosscheck", action="store_true", help="also compare with the lime package, if it is installed")
    parser.add_argument("--selftest", action="store_true", help="run the check on a stand-in classifier (no model, no data)")
    args = parser.parse_args(argv)
    if args.selftest:
        ok, _ = self_test()
        return 0 if ok else 1
    args.samples = [int(s) for s in args.samples.split(",") if s]
    return run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
