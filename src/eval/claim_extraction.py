"""Phase 13: the frozen claim extractor on the test split, once, at the operating point chosen on validation.

Run from the project root:
    python -m src.eval.claim_extraction --choose                 # BEFORE the freeze: choose all-claims or strong-only per claim type from the validation scores of Phase 7
    python -m src.eval.claim_extraction --split validation       # a dress rehearsal (writes to data/processed/rehearsal/)
    python -m src.eval.claim_extraction --split test             # the one test run (needs results/eval_freeze.csv)

Reads  results/claim_scores.csv                  the validation F1 of Phase 7 at the two operating points (min_confidence 0.0 = every claim, 0.9 = strong claims only)
       data/labelled/labels.csv, cleaned.parquet the labelled real emails of the split (140 in test) and their text and signatures
       data/synthetic/synthetic.csv              the synthetic emails of the split, scored apart
       results/label_agreement.csv               how often the two LLM annotators agree on each claim type (for context beside each F1)
Writes results/claim_operating_points.csv        the choice per claim type and the validation F1 it rests on (written by --choose, committed with the freeze)
       results/claim_test_scores.csv             precision, recall, F1 (with a 95% interval for the five scoreable types) at both operating points, real and synthetic apart
       results/claim_test_checks.csv             PASS/FAIL checks

The choice. For each of the five claim types that can get an F1 (affiliation_internal, affiliation_external, authority, credential_request, signature_contact) the operating point with the
higher validation F1 is chosen (a tie goes to 'every claim'). The other six types are reported as counts at both points; their point is 'every claim'. The choice is written to a file
BEFORE any test email is read and the file is part of the freeze (src/eval/freeze.py), so it cannot be changed after the test numbers are seen.

WHAT THIS CAN AND CANNOT SAY. The extractor is rule-based and was written from definitions and the train split (Phase 7); this run only scores it. A score is agreement with LLM labels from one
model family, not with people; for context the F1 that annotator 2 reaches against annotator 1 is printed beside each type. Six of the eleven types have fewer than 10 real positives in
test and are counts. affiliation_internal does not generalise (it cannot be decided from the body alone: the header verifier decides whether a claim is internal), signature_contact finds
nearly every labelled signature but with low precision, and reply_direction recall is low: the weak spots are reported, not hidden. Synthetic labels list only the claims the generator was required
to include, so synthetic precision is a lower bound.
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

from src.claims.build import OPERATING_POINTS, SCOREABLE, score_set, truth_matrix
from src.claims.patterns import PATTERN_VERSION, STRONG
from src.claims.schema import CLAIM_TYPES, MAX_CLAIMS, MAX_PER_TYPE
from src.data import paths
from src.eval import common, freeze
from src.eval.stats import MIN_POSITIVES, Resampler, cluster_matrix, f1_counts, outcome_columns


# ---------------------------------------------------------------------------------------------------------------------
# The operating point, chosen on validation
# ---------------------------------------------------------------------------------------------------------------------

def choose_operating_points(scores):
    """DataFrame with the chosen min_confidence per claim type, from the validation rows of claim_scores.csv (real emails)."""
    real = scores[scores["data"] == "real_validation"]
    rows = []
    for claim_type in CLAIM_TYPES:
        part = real[real["claim_type"] == claim_type]
        f_all = part[part["min_confidence"] == OPERATING_POINTS[0]]["f1"]
        f_strong = part[part["min_confidence"] == OPERATING_POINTS[1]]["f1"]
        f_all, f_strong = (None if s.empty or pd.isna(s.iloc[0]) else float(s.iloc[0]) for s in (f_all, f_strong))
        if claim_type in SCOREABLE and f_all is not None and f_strong is not None:
            chosen = OPERATING_POINTS[1] if f_strong > f_all else OPERATING_POINTS[0]
            basis = "higher validation F1 (a tie goes to every claim)"
        else:
            chosen, basis = OPERATING_POINTS[0], "counts only (fewer than %d real positives in validation or test): every claim" % MIN_POSITIVES
        rows.append({"claim_type": claim_type, "min_confidence": chosen, "validation_f1_all_claims": f_all, "validation_f1_strong_only": f_strong, "basis": basis})
    return pd.DataFrame(rows)


def write_operating_points():
    if any(r["split"] == "test" for r in freeze.read_log()):
        raise SystemExit("a test run is already logged: the operating points are not chosen again")
    scores = pd.read_csv(paths.CLAIM_SCORES_CSV)
    table = choose_operating_points(scores)
    table["pattern_version"] = PATTERN_VERSION
    table.to_csv(paths.CLAIM_OPERATING_POINTS_CSV, index=False)
    print("Operating points chosen on the validation scores of Phase 7 (pattern version %s):" % PATTERN_VERSION)
    print(table[["claim_type", "min_confidence", "validation_f1_all_claims", "validation_f1_strong_only"]].to_string(index=False))
    print("Wrote %s. Commit it with the freeze record." % paths.relative(paths.CLAIM_OPERATING_POINTS_CSV))
    return table


def read_operating_points():
    path = paths.CLAIM_OPERATING_POINTS_CSV
    if not path.exists():
        raise SystemExit("%s does not exist: run  python -m src.eval.claim_extraction --choose  first" % path.name)
    table = pd.read_csv(path)
    return {r.claim_type: float(r.min_confidence) for r in table.itertuples()}, table


# ---------------------------------------------------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------------------------------------------------

def load_text(ids):
    """body_redacted and signature of the labelled emails with these ids (the extractor reads both)."""
    table = pd.read_parquet(paths.CLEANED_PARQUET, columns=["id", "body_redacted", "signature"], filters=[("id", "in", list(ids))])
    return table.set_index("id")


def chosen_matrix(claims, points):
    """(emails x 11) yes/no matrix of the claims found, each type at its own operating point."""
    return np.array([[any(c["type"] == t and c["confidence"] >= points[t] for c in email_claims) for t in CLAIM_TYPES] for email_claims in claims], dtype=bool)


def f1_of(t, offset=0):
    return f1_counts(t[..., offset], t[..., offset + 1], t[..., offset + 2])


def macro5(t):
    return np.mean([f1_of(t, 3 * k) for k in range(len(SCOREABLE))], axis=0)


def agreement_f1(path):
    """{claim type: F1 of annotator 2 against annotator 1} from label_agreement.csv (2 x both / (positives of one + positives of the other))."""
    if not path.exists():
        return {}
    table = pd.read_csv(path)
    table = table[table["kind"] == "claim"]
    out = {}
    for r in table.itertuples():
        total = (0 if pd.isna(r.positives_first) else r.positives_first) + (0 if pd.isna(r.positives_second) else r.positives_second)
        out[r.label] = round(2 * r.both_positive / total, 4) if total else None
    return out


def validation_f1(path):
    """{(claim type, min_confidence): validation F1 of Phase 7} for the real validation rows."""
    if not path.exists():
        return {}
    table = pd.read_csv(path)
    table = table[table["data"] == "real_validation"]
    return {(r.claim_type, float(r.min_confidence)): (None if pd.isna(r.f1) else float(r.f1)) for r in table.itertuples()}


def run(split, rerun=None):
    guard = freeze.begin("claim_extraction", split, rerun)
    points, point_table = read_operating_points()
    checks = common.Checks()
    labels = pd.read_csv(paths.LABELS_CSV, dtype={"id": str})
    labels = labels[labels["split"] == split].sort_values("id").reset_index(drop=True)
    text = load_text(labels["id"])
    signatures = [s if isinstance(s, str) else "" for s in text.loc[labels["id"], "signature"]]
    label_lists = [json.loads(c) for c in labels["claims"]]
    rows, problems, claims, _ = score_set("real_" + split, text.loc[labels["id"], "body_redacted"].tolist(), signatures, label_lists)

    synthetic = pd.read_csv(paths.SYNTHETIC_CSV, dtype={"id": str})
    synthetic = synthetic[synthetic["split"] == split].sort_values("id").reset_index(drop=True)
    synthetic_rows, synthetic_problems, _, _ = score_set("synthetic_" + split, synthetic["body_redacted"].tolist(), None, [json.loads(c) for c in synthetic["claims"]],
                                                         note="labels list only the claims the generator was required to include: precision is a lower bound")
    scores = pd.DataFrame(rows + synthetic_rows)

    # ---- intervals for the five scoreable types at their chosen point (whole subject groups are drawn)
    truth = np.array(truth_matrix(label_lists), dtype=bool)
    predicted = chosen_matrix(claims, points)
    clusters = common.clusters_for(labels["id"], split)
    cols = []
    for claim_type in SCOREABLE:
        c = CLAIM_TYPES.index(claim_type)
        cols += outcome_columns(truth[:, c], predicted[:, c])[:3]
    _, matrix = cluster_matrix(clusters, cols)
    resampler = Resampler(len(matrix))
    scores["chosen"] = [bool(r.min_confidence == points.get(r.claim_type, 0.0)) if r.claim_type in points else False for r in scores.itertuples()]
    scores["f1_ci_low"], scores["f1_ci_high"] = None, None
    for k, claim_type in enumerate(SCOREABLE):
        sub = matrix[:, 3 * k:3 * k + 3]
        mask = (scores["data"] == "real_" + split) & (scores["claim_type"] == claim_type) & scores["chosen"]
        for index in scores.index[mask]:
            if pd.notna(scores.loc[index, "f1"]):
                point, low, high = resampler.interval(sub, f1_of)
                scores.loc[index, ["f1_ci_low", "f1_ci_high"]] = [common.round_or_none(low), common.round_or_none(high)]
    point, low, high = resampler.interval(matrix, macro5)
    macro = {"data": "real_" + split, "min_confidence": None, "claim_type": "macro_chosen5", "items": len(labels), "f1": round(point, 4), "f1_ci_low": common.round_or_none(low),
             "f1_ci_high": common.round_or_none(high), "reported": "mean F1 over %s, each at its chosen operating point" % ", ".join(SCOREABLE), "chosen": True,
             "note": common.LABEL_NOTE}
    scores = pd.concat([scores, pd.DataFrame([macro])], ignore_index=True)
    scores["chosen"] = scores["chosen"].astype(bool)
    validation, annotators = validation_f1(paths.CLAIM_SCORES_CSV), agreement_f1(paths.LABEL_AGREEMENT_CSV)
    scores["validation_f1"] = [validation.get((r.claim_type, float(r.min_confidence))) if r.data.startswith("real") and pd.notna(r.min_confidence) else None for r in scores.itertuples()]
    scores["annotator_agreement_f1"] = [annotators.get(r.claim_type) if r.data.startswith("real") else None for r in scores.itertuples()]
    scores["note"] = scores["note"].fillna("")
    scores.loc[scores["data"].str.startswith("real"), "note"] = scores["note"] + common.LABEL_NOTE
    columns = ["data", "min_confidence", "chosen", "claim_type", "items", "positives", "predicted", "tp", "fp", "fn", "precision", "recall", "f1", "f1_ci_low", "f1_ci_high",
               "validation_f1", "annotator_agreement_f1", "span_precision", "span_recall", "reported", "note"]
    scores = scores.reindex(columns=columns)
    common.write_table(guard, "claim_test_scores", scores)
    show(scores, "real_" + split)

    # ---- checks
    counts_path = paths.LABEL_COUNTS_CSV
    if counts_path.exists():
        counts = pd.read_csv(counts_path)
        counts = counts[(counts["group_type"] == "split") & (counts["group"] == split) & (counts["kind"] == "claim")].set_index("label")
        for claim_type in CLAIM_TYPES:
            if claim_type in counts.index:
                have = int(truth[:, CLAIM_TYPES.index(claim_type)].sum())
                checks.add("labels", "%s positives among the real %s emails equal results/label_counts.csv" % (claim_type, split), have, int(counts.loc[claim_type, "positives"]),
                           have == int(counts.loc[claim_type, "positives"]))
    checks.add("leakage_guard", "split of the labelled emails scored", ",".join(sorted(set(labels["split"]))), split, set(labels["split"]) == {split})
    checks.add("claims_valid", "claims whose text is not the slice of their span, or with a bad type, zone or confidence", len(problems) + len(synthetic_problems), "0",
               not problems and not synthetic_problems)
    most = max((len(c) for c in claims), default=0)
    checks.add("claims_capped", "most claims in one email", most, "<= %d" % MAX_CLAIMS, most <= MAX_CLAIMS)
    checks.add("claims_capped", "most claims of one type in one email", max((sum(1 for x in c if x["type"] == t) for c in claims for t in CLAIM_TYPES), default=0), "<= %d" % MAX_PER_TYPE,
               max((sum(1 for x in c if x["type"] == t) for c in claims for t in CLAIM_TYPES), default=0) <= MAX_PER_TYPE)
    recomputed = choose_operating_points(pd.read_csv(paths.CLAIM_SCORES_CSV))
    same = recomputed[["claim_type", "min_confidence"]].equals(point_table[["claim_type", "min_confidence"]])
    checks.add("operating_points", "the file still equals the choice recomputed from the validation scores", "equal" if same else "different", "equal", same)
    checks.add("operating_points", "pattern version of the choice equals the version scored", "%s / %s" % (point_table["pattern_version"].iloc[0], PATTERN_VERSION), "equal",
               str(point_table["pattern_version"].iloc[0]) == str(PATTERN_VERSION))
    try:
        from sklearn.metrics import f1_score
        worst = 0.0
        for claim_type in SCOREABLE:
            c = CLAIM_TYPES.index(claim_type)
            row = scores[(scores["data"] == "real_" + split) & (scores["claim_type"] == claim_type) & scores["chosen"]]
            if len(row) and pd.notna(row["f1"].iloc[0]):
                worst = max(worst, abs(float(row["f1"].iloc[0]) - f1_score(truth[:, c], predicted[:, c], zero_division=0)))
        checks.add("metrics", "hand-written F1 equals scikit-learn for every scoreable type at its chosen point", "%.1e" % worst, "< 1e-3 (the table rounds to 4 decimals)", worst < 1e-3)
    except ImportError:
        checks.add("metrics", "scikit-learn cross-check", "scikit-learn is not installed", "", None)
    checks.add("run", "claim pattern version", PATTERN_VERSION, "", None)
    checks.add("run", "strong-claim confidence", STRONG, "", None)
    common.write_table(guard, "claim_test_checks", checks.frame())
    print()
    checks.print()
    guard.finish(checks.failed() == 0)
    return scores, checks


def show(scores, data):
    part = scores[(scores["data"] == data) & scores["chosen"]]
    print("\n%s: the chosen operating point per type (%s)" % (data, common.LABEL_NOTE))
    print("%-22s %6s %9s %6s %6s %6s  %-26s %9s %9s" % ("claim type", "conf", "positives", "tp", "fp", "fn", "F1 [95% interval]", "validation", "annotator2"))
    for r in part.itertuples():
        if r.claim_type.startswith("macro"):
            print("%-22s %6s %9s %6s %6s %6s  %-26s" % ("macro (5 scoreable)", "", "", "", "", "", "%.3f [%.3f, %.3f]" % (r.f1, r.f1_ci_low, r.f1_ci_high)))
            continue
        f1 = ("%.3f [%.3f, %.3f]" % (r.f1, r.f1_ci_low, r.f1_ci_high) if pd.notna(r.f1_ci_low) else "%.3f" % r.f1) if pd.notna(r.f1) else "counts only"
        print("%-22s %6.1f %9d %6d %6d %6d  %-26s %9s %9s" % (r.claim_type, r.min_confidence, r.positives, r.tp, r.fp, r.fn, f1,
                                                             "-" if pd.isna(r.validation_f1) else "%.3f" % r.validation_f1, "-" if pd.isna(r.annotator_agreement_f1) else "%.3f" % r.annotator_agreement_f1))


def main(argv):
    parser = argparse.ArgumentParser(description="Score the frozen claim extractor on the test split (Phase 13).")
    freeze.add_run_arguments(parser)
    parser.add_argument("--choose", action="store_true", help="choose the operating point per claim type from the validation scores and write results/claim_operating_points.csv")
    args = parser.parse_args(argv)
    if args.choose:
        write_operating_points()
        return 0
    _, checks = run(args.split, args.rerun)
    return 1 if checks.failed() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
