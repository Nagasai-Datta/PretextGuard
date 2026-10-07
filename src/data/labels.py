"""Phase 5: merge the annotators' answers into the final labels.

Run from the project root after validate_labels, agreement and the tie-break round:
    python -m src.data.labels

Reads  data/labelled/sample.csv and the valid answers of the two annotators and the tie-breaker
Writes data/labelled/labels.csv       one row per labelled email: ids, split, seven tactic labels, claims (committed)
       results/label_counts.csv       how many positives each tactic and claim type has, per split and category (committed)

The rules, in the order they apply:
- An email is labelled only when both annotators (annotator_1 and annotator_2) gave a valid answer.
- A tactic or claim type both agree on stands.
- Where they disagree, the tie-breaker's answer decides (the majority of three). An email on which they disagree
  and the tie-breaker has not answered (yet, or its answer was dropped) is left out and counted as pending.
- A claim type is kept when at least two annotators listed it. The span and organisation come from the
  first annotator in the order annotator_1, annotator_2, tiebreaker who listed that type.

The counts decide how Phase 13 reports each tactic. A tactic with fewer than 10 positives in the
validation or test items is reported as a count, not as an F1 score: with so few positives, one email
moves F1 by several points and the number would only look precise.
"""

import json

import pandas as pd

from src.data.label_schema import ALL_ANNOTATORS, ANNOTATORS, CLAIM_TYPES, TACTICS
from src.data.paths import LABEL_COUNTS_CSV, LABELS_CSV, RESULTS_DIR, SAMPLE_CSV, relative
from src.data.validate_labels import load_answers

MIN_POSITIVES = 10
PRIORITY = ALL_ANNOTATORS


def merge_item(votes):
    """votes: {annotator: clean item}. Returns (tactics, claims) or None when the item cannot be decided yet."""
    if not all(a in votes for a in ANNOTATORS):
        return None
    tactics = {}
    for name in TACTICS:
        answers = [votes[a]["tactics"][name] for a in PRIORITY if a in votes]
        if len(set(answers[:2])) == 1:
            tactics[name] = answers[0]
        elif len(answers) == 3:
            tactics[name] = int(sum(answers) >= 2)
        else:
            return None
    claims = []
    for kind in CLAIM_TYPES:
        listing = [a for a in PRIORITY if a in votes and any(c["type"] == kind for c in votes[a]["claims"])]
        agreed = len(listing) >= 2
        if len(votes) == 2 and len(listing) == 1:
            return None  # the two annotators disagree about this claim type and the tie-breaker has not decided yet
        if agreed:
            claims += [c for c in votes[listing[0]]["claims"] if c["type"] == kind]
    return tactics, claims


def main():
    pd.set_option("display.width", 220)
    sample = pd.read_csv(SAMPLE_CSV)
    answers = {a: load_answers(a).valid for a in ALL_ANNOTATORS}

    rows, undecided, unanswered = [], 0, 0
    for r in sample.itertuples():
        votes = {a: answers[a][r.local_id] for a in ALL_ANNOTATORS if r.local_id in answers[a]}
        if not all(a in votes for a in ANNOTATORS):
            unanswered += 1
            continue
        merged = merge_item(votes)
        if merged is None:
            undecided += 1
            continue
        tactics, claims = merged
        rows.append({"id": r.id, "source": r.source, "category": r.category, "split": r.split,
                     **{f"tactic_{t}": tactics[t] for t in TACTICS},
                     "claims": json.dumps(claims, ensure_ascii=False),
                     "annotators": "+".join(a for a in PRIORITY if a in votes), "label_source": "llm_annotated"})
    labels = pd.DataFrame(rows)
    print(f"Sample {len(sample)}: labelled {len(labels)}, waiting for a tie-break {undecided}, "
          f"missing a valid answer from an annotator {unanswered}")
    if labels.empty:
        raise SystemExit("No email is labelled yet.")

    labels.to_csv(LABELS_CSV, index=False)
    parsed = labels["claims"].map(json.loads)
    flags = pd.DataFrame({f"claim_{k}": parsed.map(lambda cs, k=k: any(c["type"] == k for c in cs)) for k in CLAIM_TYPES})
    tactic_cols = [f"tactic_{t}" for t in TACTICS]
    combined = pd.concat([labels[["split", "category"]], labels[tactic_cols].astype(int), flags.astype(int)], axis=1)

    count_rows = []
    for group_type, column in (("split", "split"), ("category", "category")):
        for group, part in combined.groupby(column):
            for label in tactic_cols + list(flags.columns):
                kind = "tactic" if label.startswith("tactic_") else "claim"
                count_rows.append({"group_type": group_type, "group": group, "kind": kind,
                                   "label": label.split("_", 1)[1] if kind == "tactic" else label[6:],
                                   "positives": int(part[label].sum()), "items": len(part)})
    for label in tactic_cols + list(flags.columns):
        kind = "tactic" if label.startswith("tactic_") else "claim"
        count_rows.append({"group_type": "all", "group": "all", "kind": kind,
                           "label": label.split("_", 1)[1] if kind == "tactic" else label[6:],
                           "positives": int(combined[label].sum()), "items": len(combined)})
    counts = pd.DataFrame(count_rows)

    print("\nPositive tactic labels, per split (items per split in the last row)")
    wide = counts[(counts.group_type == "split") & (counts.kind == "tactic")].pivot(index="label", columns="group", values="positives")
    wide = wide.reindex(list(TACTICS))[[c for c in ("train", "validation", "test") if c in wide.columns]]
    wide.loc["items"] = combined.groupby("split").size().reindex(wide.columns)
    print(wide.to_string())

    print("\nPositive tactic labels, per category")
    by_category = counts[(counts.group_type == "category") & (counts.kind == "tactic")].pivot(index="label", columns="group", values="positives")
    print(by_category.reindex(list(TACTICS)).to_string())

    print("\nPositive claim labels, per split")
    claim_wide = counts[(counts.group_type == "split") & (counts.kind == "claim")].pivot(index="label", columns="group", values="positives")
    print(claim_wide.reindex(list(CLAIM_TYPES))[[c for c in ("train", "validation", "test") if c in claim_wide.columns]].to_string())

    print("\nChecks")
    rare = [t for t in TACTICS for split in ("validation", "test")
            if split in wide.columns and wide.at[t, split] < MIN_POSITIVES]
    print(f"  {'PASS' if not rare else 'info'}  tactics with at least {MIN_POSITIVES} positives in validation and test: "
          + ("all seven" if not rare else f"not {sorted(set(rare))}: report these as counts, not F1"))
    print(f"  {'PASS' if labels['id'].is_unique else 'FAIL'}  every labelled email appears once")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(LABEL_COUNTS_CSV, index=False)
    print(f"\nSaved {relative(LABELS_CSV)}")
    print(f"Saved {relative(LABEL_COUNTS_CSV)}")


if __name__ == "__main__":
    main()
