"""Phase 5: how much do the two annotators agree, and which emails go to the tie-breaker?

Run from the project root once the two annotators have answered (re-asks included):
    python -m src.data.agreement

Reads  the replies of the two annotators (through validate_labels.load_answers)
Writes results/label_agreement.csv    Cohen's kappa for each tactic and each claim type (committed)
       data/labelled/batches/tiebreak_NNN.txt  the emails the two annotators disagree on, for z.ai (not committed)

What Cohen's kappa is. Two annotators who both answer "0" for a rare tactic agree almost always, and
that proves little: most of that agreement is chance. Kappa subtracts the agreement two annotators
with these same answer rates would reach by chance:

    kappa = (po - pe) / (1 - pe)

po is the share of emails where they gave the same answer. pe is the chance agreement: the chance both say 1
(p1 * p2) plus the chance both say 0 ((1 - p1) * (1 - p2)), with p1 and p2 each annotator's share of 1s.
Kappa is 1 for perfect agreement, 0 for no better than chance. The common reading scale (Landis and Koch,
1977) is a convention, not a rule: under 0.2 slight, 0.2 to 0.4 fair, 0.4 to 0.6 moderate, 0.6 to 0.8
substantial, above 0.8 almost perfect. Kappa is computed here by hand and cross-checked against
scikit-learn's cohen_kappa_score, so the number is both explainable and independently confirmed.

Claim types are scored as present or absent per email. For claims both annotators listed, the span
overlap (one span contains the other, or at least half of their words are shared) says whether they
meant the same words.
"""

import math
import warnings

import pandas as pd

from src.data.batches import read_batch_file, write_batch_file
from src.data.label_schema import ANNOTATORS, BATCH_SIZE, CLAIM_TYPES, TACTICS, TIEBREAKER
from src.data.paths import BATCHES_DIR, LABEL_AGREEMENT_CSV, RESULTS_DIR, SAMPLE_CSV, relative
from src.data.validate_labels import all_texts, batch_stems, load_answers, squash


def kappa(first, second):
    """Cohen's kappa for two lists of 0/1 answers. NaN when it is undefined (both always give the same single answer)."""
    n = len(first)
    if n == 0:
        return math.nan
    observed = sum(a == b for a, b in zip(first, second)) / n
    p1, p2 = sum(first) / n, sum(second) / n
    chance = p1 * p2 + (1 - p1) * (1 - p2)
    return math.nan if chance >= 1 else (observed - chance) / (1 - chance)


def sklearn_kappa(first, second):
    """scikit-learn's value, for the cross-check; None if scikit-learn is not installed."""
    try:
        from sklearn.metrics import cohen_kappa_score
    except ImportError:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(cohen_kappa_score(first, second))


def reading(value):
    """Landis and Koch's verbal scale for a kappa value."""
    if math.isnan(value):
        return "undefined"
    if value < 0:
        return "poor"
    for limit, word in ((0.2, "slight"), (0.4, "fair"), (0.6, "moderate"), (0.8, "substantial")):
        if value < limit:
            return word
    return "almost perfect"


def spans_overlap(first, second):
    """True if one span contains the other, or at least half of their words are shared."""
    a, b = squash(first), squash(second)
    if a in b or b in a:
        return True
    words_a, words_b = set(a.split()), set(b.split())
    return bool(words_a and words_b) and len(words_a & words_b) / len(words_a | words_b) >= 0.5


def claim_types(item):
    return {claim["type"] for claim in item["claims"]}


def agreement_rows(first, second, ids):
    """One row per tactic and per claim type, plus the means."""
    rows = []
    for kind, name in [("tactic", t) for t in TACTICS] + [("claim", c) for c in CLAIM_TYPES]:
        is_tactic = kind == "tactic"
        a = [int(first[i]["tactics"][name]) if is_tactic else int(name in claim_types(first[i])) for i in ids]
        b = [int(second[i]["tactics"][name]) if is_tactic else int(name in claim_types(second[i])) for i in ids]
        value = kappa(a, b)
        row = {
            "kind": kind, "label": name, "items": len(ids),
            "positives_first": sum(a), "positives_second": sum(b), "both_positive": sum(x and y for x, y in zip(a, b)),
            "agree_pct": round(100 * sum(x == y for x, y in zip(a, b)) / len(ids), 1) if ids else math.nan,
            "kappa": round(value, 3) if not math.isnan(value) else math.nan, "reading": reading(value), "span_overlap_pct": math.nan,
        }
        cross = sklearn_kappa(a, b)
        row["_sklearn"], row["_exact"] = cross, value
        if not is_tactic:
            pairs = [(c1["span"], c2["span"]) for i in ids for c1 in first[i]["claims"] if c1["type"] == name
                     for c2 in second[i]["claims"] if c2["type"] == name]
            if pairs:
                row["span_overlap_pct"] = round(100 * sum(spans_overlap(x, y) for x, y in pairs) / len(pairs), 1)
        rows.append(row)
    for kind in ("tactic", "claim"):
        values = [r["kappa"] for r in rows if r["kind"] == kind and not math.isnan(r["kappa"])]
        rows.append({"kind": f"mean_{kind}", "label": f"mean of {len(values)} defined", "items": len(ids),
                     "kappa": round(sum(values) / len(values), 3) if values else math.nan,
                     "reading": reading(sum(values) / len(values)) if values else "undefined"})
    return rows


def disagreements(first, second, ids):
    """Ids where the annotators differ on any tactic or on any claim type."""
    return [i for i in ids if first[i]["tactics"] != second[i]["tactics"] or claim_types(first[i]) != claim_types(second[i])]


def write_tiebreaks(todo):
    """Write tiebreak_NNN.txt batches for the ids in todo. Returns the file names."""
    texts = all_texts()
    number = sum(1 for stem in batch_stems(TIEBREAKER) if stem.startswith("tiebreak_"))
    names = []
    for start in range(0, len(todo), BATCH_SIZE):
        number += 1
        name = f"tiebreak_{number:03d}"
        write_batch_file(name, [(i, texts[i]) for i in todo[start:start + BATCH_SIZE]])
        names.append(name)
    return names


def main():
    pd.set_option("display.width", 220)
    first_answers, second_answers = (load_answers(a) for a in ANNOTATORS)
    expected = len(pd.read_csv(SAMPLE_CSV)) if SAMPLE_CSV.exists() else None
    ids = sorted(set(first_answers.valid) & set(second_answers.valid))
    print(f"Valid answers: {ANNOTATORS[0]} {len(first_answers.valid)}, {ANNOTATORS[1]} {len(second_answers.valid)}; "
          f"answered validly by both: {len(ids)}" + (f" of {expected}" if expected else ""))
    if not ids:
        raise SystemExit("Nothing to compare yet. Finish the annotation and run validate_labels first.")
    if expected and len(ids) < expected:
        print(f"  {expected - len(ids)} emails lack a valid answer from one annotator (not yet answered, or dropped after a re-ask)")

    rows = agreement_rows(first_answers.valid, second_answers.valid, ids)
    table = pd.DataFrame(rows)
    shown = table.drop(columns=["_sklearn", "_exact"])
    print("\nAgreement between the two annotators (kappa per label)")
    print(shown.to_string(index=False))

    print("\nChecks")
    pairs = [(r["label"], r["_exact"], r["_sklearn"]) for r in rows if "_sklearn" in r and r["_sklearn"] is not None
             and not math.isnan(r["_exact"])]
    if pairs:
        worst = max(abs(k - s) for _, k, s in pairs)
        print(f"  {'PASS' if worst < 0.001 else 'FAIL'}  hand-written kappa matches scikit-learn's cohen_kappa_score "
              f"(largest difference {worst:.4f} over {len(pairs)} labels)")
    else:
        print("  skip  scikit-learn cross-check (not installed, or no defined kappa)")

    differing = disagreements(first_answers.valid, second_answers.valid, ids)
    done = load_answers(TIEBREAKER)
    asked = {i for stem in batch_stems(TIEBREAKER) if stem.startswith("tiebreak_") for i, _ in read_batch_file(BATCHES_DIR / f"{stem}.txt")}
    todo = [i for i in differing if i not in asked and i not in done.valid]
    written = write_tiebreaks(todo)
    print(f"  info  {len(differing)} of {len(ids)} emails ({100 * len(differing) / len(ids):.1f}%) differ on at least one label; "
          f"{len(todo)} newly sent to the tie-breaker in {len(written)} file(s)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    shown.to_csv(LABEL_AGREEMENT_CSV, index=False)
    print(f"\nSaved {relative(LABEL_AGREEMENT_CSV)}")
    if written:
        print("Tie-break files were written into data/labelled/batches/: run annotate.py auto tiebreaker (or next and save) to answer them.")


if __name__ == "__main__":
    main()
