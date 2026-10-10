"""Phase 13: run every experiment script on a tiny made-up project, so the long runs on the real data are not the first time the code runs.

Run from the project root:   python -m src.eval.selftest        (a few minutes; needs spaCy, scikit-learn, matplotlib and torch, not the real model or the data)

It builds in a temporary folder what Phases 1 to 10 build for the real data (staged, cleaned and header tables, claims, threads, a small hijack benchmark, labels,
synthetic pairs and the Phase 6 to 10 result files) from hand-made emails, with the stand-in tactic classifier of src/router/selftest.py, and runs the freeze guard and
each experiment script on it for the validation split (a rehearsal) and the test split (a logged run). The numbers mean nothing: the emails are made up. What it checks
is that each script runs end to end, writes the files and columns the dashboard and the docs script expect, refuses to run when it must (a changed frozen file, a second
test run without a reason), and gets the arithmetic right where a hand-made answer is known. Nothing here touches the real data, the real results or the real model.
"""

import contextlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import paths
from src.data.label_schema import TACTICS
from src.eval import freeze
from src.router import build_selftest as bs
from src.router.selftest import DAVID_BODY, PARAGRAPHS, StubClassifier

SPLITS = ("train", "validation", "test")
CLAIMS_ATTACK = [{"type": "affiliation_internal", "span": "This is David from Finance", "organisation": None},
                 {"type": "payment_request", "span": "process a wire transfer of $48,000", "organisation": None}]
CLAIMS_FRAUD = [{"type": "reply_direction", "span": "Please reply to me with your details", "organisation": None},
                {"type": "authority", "span": "I am the director of foreign operations", "organisation": None}]
THRESHOLDS = StubClassifier.thresholds


def quiet(call, *args, **kwargs):
    """Run a script function and swallow what it prints (the self-test prints its own lines)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


class World:
    """A made-up project in a temporary folder, with train, validation and test splits, and every module that reads a path pointed at it."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name).resolve()       # resolved: on macOS /var is a link to /private/var, and paths.relative() resolves
        self.undo = []
        self.emails = []

    # ---- patching
    def patch(self, obj, name, value):
        self.undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def __enter__(self):
        import src.models.dataset as dataset
        import src.router.build as router_build
        import src.thread.features as thread_features
        import src.verifiers.build as verifier_build

        folder = self.folder
        original_emails = bs.made_up_emails

        def with_test():
            rows = original_emails()
            return rows + [(s, c, "test", h, b) for s, c, sp, h, b in rows if sp == "validation"]

        bs.made_up_emails = with_test
        saved = (verifier_build.CLEANED_PARQUET, verifier_build.HEADERS_PARQUET, verifier_build.CLAIMS_CACHE_DIR, router_build.THREADS_PARQUET, router_build.STAGED_PARQUET,
                 router_build.TACTIC_PROBS_DIR, router_build.HIJACK_CASES_CSV, router_build.HIJACK_INJECTIONS_CSV, router_build.RESULTS_DIR, router_build.SCORE_FILES)
        self.undo.append((bs, "made_up_emails", original_emails))
        for name, value in zip(("CLEANED_PARQUET", "HEADERS_PARQUET", "CLAIMS_CACHE_DIR"), saved[:3]):
            self.undo.append((verifier_build, name, value))
        for name, value in zip(("THREADS_PARQUET", "STAGED_PARQUET", "TACTIC_PROBS_DIR", "HIJACK_CASES_CSV", "HIJACK_INJECTIONS_CSV", "RESULTS_DIR", "SCORE_FILES"), saved[3:]):
            self.undo.append((router_build, name, value))
        self.emails = bs.build_world(folder)
        results = folder / "results"
        results.mkdir(exist_ok=True)

        # threads and cases: three splits instead of two
        def split_of(tid):
            return SPLITS[int(tid.split("_t")[1]) % 3]

        threads = pd.read_parquet(folder / "threads.parquet")
        threads["split"] = [split_of(t) for t in threads["thread_id"]]
        threads.to_parquet(folder / "threads.parquet", index=False)
        cases = pd.read_csv(folder / "cases.csv")
        cases["split"] = [split_of(t) for t in cases["thread"]]
        cases.to_csv(folder / "cases.csv", index=False)

        # cleaned table: the columns N1 reads (is_attack, has_url); the made-up phishing emails carry a link in the raw view and [URL] in the redacted view
        cleaned = pd.read_parquet(folder / "cleaned.parquet")
        phishing = cleaned["source"] == "nazario"
        cleaned["is_attack"] = cleaned["category"].isin(["phishing", "fraud"])
        cleaned["has_url"] = phishing
        cleaned.loc[phishing, "body_clean"] = cleaned.loc[phishing, "body_clean"] + " Visit http://secure-login.example.net/verify today."
        cleaned.loc[phishing, "body_redacted"] = cleaned.loc[phishing, "body_redacted"] + " Visit [URL] today."
        cleaned.to_parquet(folder / "cleaned.parquet", index=False)
        (folder / "results").mkdir(exist_ok=True)
        link_rows = [{"check": "link_free", "item": "is_attack=%s link_free=%s split=%s" % (attack, free, split), "value": int(((cleaned["is_attack"] == attack) & (~cleaned["has_url"] == free) & (cleaned["split"] == split)).sum())}
                     for split in SPLITS for attack in (True, False) for free in (True, False)]
        pd.DataFrame(link_rows).to_csv(folder / "results" / "preprocess_checks.csv", index=False)

        # staged table: the columns the subject groups need
        ids = ["id%04d" % i for i in range(len(self.emails))]
        staged = pd.read_parquet(folder / "staged.parquet")
        staged["source"], staged["category"], staged["split"] = [e[0] for e in self.emails], [e[1] for e in self.emails], [e[2] for e in self.emails]
        staged.to_parquet(folder / "staged.parquet", index=False)

        # labels: the first 20 nazario and 20 fraud emails of every split, 20 ham and 10 spam
        rows = []
        for split in SPLITS:
            taken = {"nazario": 0, "kaggle_nigerian_fraud": 0, "ham": 0, "spam": 0}
            for uid, (source, category, sp, _, _) in zip(ids, self.emails):
                key = source if source in taken else category
                limit = {"nazario": 20, "kaggle_nigerian_fraud": 20, "ham": 20, "spam": 10}.get(key, 0)
                if sp != split or key not in taken or taken[key] >= limit:
                    continue
                taken[key] += 1
                labels = {"nazario": (1, 1, 0, 1), "kaggle_nigerian_fraud": (1, 0, 0, 1)}.get(source, (0, 0, 0, 0))
                claims = CLAIMS_ATTACK if source == "nazario" else CLAIMS_FRAUD if source == "kaggle_nigerian_fraud" else []
                rows.append({"id": uid, "source": source, "category": category, "split": split, "tactic_authority": labels[0], "tactic_urgency": labels[1],
                             "tactic_scarcity": labels[2], "tactic_reciprocity": 0, "tactic_social_proof": 0, "tactic_liking": 0, "tactic_secrecy": labels[3],
                             "claims": json.dumps(claims), "annotators": "annotator_1+annotator_2", "label_source": "llm_annotated"})
        labels = pd.DataFrame(rows)
        labels.to_csv(folder / "labels.csv", index=False)
        counts = []
        for split in SPLITS:
            part = labels[labels["split"] == split]
            for tactic in TACTICS:
                counts.append({"group_type": "split", "group": split, "kind": "tactic", "label": tactic, "positives": int(part["tactic_" + tactic].sum()), "items": len(part)})
        pd.DataFrame(counts).to_csv(results / "label_counts.csv", index=False)

        # synthetic pairs
        synthetic = []
        for split in SPLITS:
            for k in range(12):
                pair = "%s%02d" % (split[:2], k)
                attack = DAVID_BODY.replace("Maria", "Marcus") + " Variant %d of the request." % k
                benign = PARAGRAPHS[k % len(PARAGRAPHS)]
                for role, body, tactics, claims in (("attack", attack, (1, 1, 0, 1), CLAIMS_ATTACK), ("benign", benign, (0, 0, 0, 0), [])):
                    synthetic.append({"id": "%s_%s" % (pair, role), "pair": pair, "role": role, "scenario": "colleague", "split": split, "subject": "s", "body": body,
                                      "body_redacted": body, "tactic_authority": tactics[0], "tactic_urgency": tactics[1], "tactic_scarcity": tactics[2], "tactic_reciprocity": 0,
                                      "tactic_social_proof": 0, "tactic_liking": 0, "tactic_secrecy": tactics[3], "claims": json.dumps(claims), "label_source": "synthetic"})
        pd.DataFrame(synthetic).to_csv(folder / "synthetic.csv", index=False)

        # result files of earlier phases that the experiments read
        sizes = pd.DataFrame([{"source": s, "category": c, "split": sp} for s, c, sp, _, _ in self.emails]).groupby(["source", "category", "split"]).size().unstack(fill_value=0).reset_index()
        sizes["total"] = sizes[list(SPLITS)].sum(axis=1)
        totals = {"source": "total", "category": ""}
        totals.update({column: int(sizes[column].sum()) for column in list(SPLITS) + ["total"]})
        sizes = pd.concat([sizes, pd.DataFrame([totals])], ignore_index=True)           # the real file ends with a total row
        sizes.to_csv(results / "split_counts.csv", index=False)
        validation_rows = []
        for system in ("distilbert", "keyword_tuned", "keyword_default"):
            for tactic in TACTICS:
                validation_rows.append({"data": "real_validation", "system": system, "tactic": tactic, "threshold": THRESHOLDS[tactic] if system == "distilbert" else 0.5 if system == "keyword_tuned" else 1.0,
                                        "f1": 0.5 if tactic in ("authority", "urgency", "secrecy", "scarcity") else None})
            validation_rows.append({"data": "real_validation", "system": system, "tactic": "macro_main4", "threshold": None, "f1": 0.5})
        pd.DataFrame(validation_rows).to_csv(results / "tactic_validation_scores.csv", index=False)
        claim_rows = []
        for conf, f1s in ((0.0, (0.60, 0.70, 0.50, 0.40, 0.80)), (0.9, (0.65, 0.60, 0.50, 0.45, 0.70))):
            for claim_type, f1 in zip(("affiliation_external", "affiliation_internal", "authority", "credential_request", "signature_contact"), f1s):
                claim_rows.append({"data": "real_validation", "min_confidence": conf, "claim_type": claim_type, "items": 137, "positives": 20, "f1": f1})
        pd.DataFrame(claim_rows).to_csv(results / "claim_scores.csv", index=False)
        (results / "tactic_run_info.json").write_text(json.dumps({"finished_utc": "2026-01-01 00:00:00"}), encoding="utf-8")

        # the module variables that were imported by name
        self.patch(dataset, "LABELS_CSV", folder / "labels.csv")
        self.patch(dataset, "CLEANED_PARQUET", folder / "cleaned.parquet")
        self.patch(dataset, "SYNTHETIC_CSV", folder / "synthetic.csv")
        self.patch(router_build, "TACTIC_RUN_INFO_JSON", results / "tactic_run_info.json")
        self.patch(thread_features, "TACTIC_RUN_INFO_JSON", results / "tactic_run_info.json")
        self.patch(thread_features, "THREAD_FEATURES_DIR", folder / "thread_features")
        # the paths the Phase 13 modules read at call time
        for name, value in (("PROJECT_ROOT", folder), ("TACTIC_PROBS_DIR", folder / "tactic_probs"), ("PREPROCESS_CHECKS_CSV", folder / "results" / "preprocess_checks.csv"), ("STAGED_PARQUET", folder / "staged.parquet"), ("THREADS_PARQUET", folder / "threads.parquet"), ("HIJACK_CASES_CSV", folder / "cases.csv"),
                            ("HIJACK_INJECTIONS_CSV", folder / "injections.csv"), ("RESULTS_DIR", results), ("REHEARSAL_DIR", folder / "rehearsal"),
                            ("EVAL_FREEZE_CSV", results / "eval_freeze.csv"), ("EVAL_TEST_LOG_CSV", results / "eval_test_log.csv"), ("EVAL_FEATURES_DIR", folder / "eval_features"),
                            ("SPLIT_COUNTS_CSV", results / "split_counts.csv"), ("TACTIC_VALIDATION_SCORES_CSV", results / "tactic_validation_scores.csv"),
                            ("LABEL_COUNTS_CSV", results / "label_counts.csv"), ("LABELS_CSV", folder / "labels.csv"), ("SYNTHETIC_CSV", folder / "synthetic.csv"),
                            ("CLAIM_SCORES_CSV", results / "claim_scores.csv"), ("CLAIM_OPERATING_POINTS_CSV", results / "claim_operating_points.csv"),
                            ("CLEANED_PARQUET", folder / "cleaned.parquet"), ("HEADERS_PARQUET", folder / "headers.parquet"), ("LABEL_AGREEMENT_CSV", results / "label_agreement.csv"),
                            ("N1_DATA_PARQUET", folder / "n1_data.parquet"), ("N1_PROBS_DIR", folder / "n1_probs"), ("N1_MODEL_A_DIR", folder / "artifacts" / "n1_model_a"),
                            ("N1_MODEL_B_DIR", folder / "artifacts" / "n1_model_b"), ("PARAPHRASE_DIR", folder / "paraphrase"), ("FIGURES_DIR", folder / "figures")):
            self.patch(paths, name, value)
        self.thresholds = dict(THRESHOLDS)
        self.stub = StubClassifier()
        return self

    def __exit__(self, *exc):
        for obj, name, value in reversed(self.undo):
            setattr(obj, name, value)
        self.tmp.cleanup()
        return False

    def refreeze(self):
        """Forget earlier test runs and write a fresh freeze record (for tests that need a test run); the real script refuses to do this."""
        for name in ("EVAL_TEST_LOG_CSV", "EVAL_FREEZE_CSV"):
            Path(getattr(paths, name)).unlink(missing_ok=True)
        quiet(freeze.write_manifest)

    def ids(self, split, source=None, category=None):
        return ["id%04d" % i for i, e in enumerate(self.emails) if e[2] == split and (source is None or e[0] == source) and (category is None or e[1] == category)]


def exits(call):
    """True when the call stops with SystemExit (a refusal)."""
    try:
        quiet(call)
    except SystemExit:
        return True
    return False


# ---------------------------------------------------------------------------------------------------------------------
# The tests, one function per module. Each takes (world, check); more are added next to the module they test.
# ---------------------------------------------------------------------------------------------------------------------

TESTS = []


def test(function):
    TESTS.append(function)
    return function


@test
def test_stats(world, check):
    from src.eval import stats

    ok, total = quiet(stats.self_test, verbose=False)
    check("stats.py: its own self-test (bootstrap, Wilson, AUC and matched cut against scikit-learn and textbook values)", ok, "%d checks" % total)


@test
def test_split_total(world, check):
    from src.eval import common

    table = pd.read_csv(paths.SPLIT_COUNTS_CSV)
    check("common.split_total: the total row of results/split_counts.csv is left out, so each split is counted once (the real file has one)",
          (table["source"] == "total").sum() == 1 and all(common.split_total(s) == len(world.ids(s)) for s in SPLITS) and common.split_total("nonsense") is None,
          str({s: (common.split_total(s), len(world.ids(s))) for s in SPLITS}))
    from src.eval import world as world_module

    check("world.lookalike_score: numpy integers, floats, missing values and text all give a number between 0 and 1", world_module.lookalike_score(np.int64(80)) == 0.8 and world_module.lookalike_score(80.0) == 0.8
          and world_module.lookalike_score(None) == 0.0 and world_module.lookalike_score(float("nan")) == 0.0 and world_module.lookalike_score("x") == 0.0)


@test
def test_freeze(world, check):
    # the guard: no record -> no test run
    check("a test run is refused when results/eval_freeze.csv does not exist", exits(lambda: freeze.begin("x", "test")))
    run = freeze.begin("x", "validation")
    check("a validation rehearsal needs no record and writes to the rehearsal folder", run.path("a.csv").parent == Path(paths.REHEARSAL_DIR))
    items = quiet(freeze.write_manifest)
    check("--write records every frozen file (or 'absent'), the versions and the settings", len(items) == len(freeze.FROZEN_FILES) + len(freeze.current_versions()) + len(freeze.current_settings()) and {k for _, k, _ in items} == {"file", "version", "setting"},
          "%d items" % len(items))
    check("the record matches the machine straight after it was written", freeze.differences(freeze.read_manifest(), freeze.current_items()) == [])
    first = freeze.begin("script_a", "test")
    first.finish(True)
    log = freeze.read_log()
    check("a test run writes 'started' and 'finished' to the log with the freeze digest", [r["event"] for r in log] == ["started", "finished"] and log[0]["freeze_digest"] == freeze.digest_of(items)[:16])
    check("a second test run of the same script is refused without a reason", exits(lambda: freeze.begin("script_a", "test")))
    again = freeze.begin("script_a", "test", rerun="a bug in this script")
    again.finish(True)
    check("with a reason it runs and the reason is logged", freeze.read_log()[-2]["reason"] == "a bug in this script")
    freeze.begin("cache", "test", once=False).finish(True)
    freeze.begin("cache", "test", once=False).finish(True)
    check("a script that only builds caches (once=False) may repeat", sum(1 for r in freeze.read_log() if r["script"] == "cache" and r["event"] == "finished") == 2)
    check("the record is not rewritten once a test run is logged", exits(freeze.write_manifest))
    # a change in a frozen thing is caught
    target = Path(paths.RESULTS_DIR) / "tactic_run_info.json"
    original = target.read_text(encoding="utf-8")
    items_now = freeze.current_items()
    changed = [("src/eval/metrics.py", "file", "0" * 64) if i == "src/eval/metrics.py" else (i, k, v) for i, k, v in items_now]
    lines = freeze.differences(freeze.read_manifest(), changed)
    check("a changed frozen file is listed by name", len(lines) == 1 and lines[0].startswith("src/eval/metrics.py"), str(lines))
    check("an item that is new or gone is listed too", len(freeze.differences(freeze.read_manifest(), items_now[:-1])) == 1 and len(freeze.differences(freeze.read_manifest()[:-1], items_now)) == 1)
    target.write_text(original, encoding="utf-8")


@test
def test_prepare_test(world, check):
    from src.eval import prepare_test

    counts, checks = quiet(prepare_test.run, "validation", None, 1, world.stub, bs.stub_featurize)
    n = len(world.ids("validation"))
    row = counts[counts["cache"] == "emails"].iloc[0]
    check("prepare_test (validation rehearsal): builds the caches for every email of the split", int(row["items"]) == n, "%d emails" % n)
    check("prepare_test: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    check("prepare_test: the rehearsal writes into the rehearsal folder and not into results/", (Path(paths.REHEARSAL_DIR) / "eval_cache_counts.csv").exists()
          and not (Path(paths.RESULTS_DIR) / "eval_cache_counts.csv").exists())


@test
def test_tactic_test(world, check):
    from src.eval import tactic_test

    scores, checks = quiet(tactic_test.run, "validation", None, world.stub)
    real = scores[(scores["data"] == "real_validation") & (scores["system"] == "distilbert")].set_index("tactic")
    check("tactic_test: the stand-in classifier finds urgency and secrecy in every labelled attack (F1 1.0) and misses authority (0.0), as worked out by hand",
          real.loc["urgency", "f1"] == 1.0 and real.loc["secrecy", "f1"] == 1.0 and real.loc["authority", "f1"] == 0.0, str(real[["positives", "tp", "fp", "fn", "f1"]].to_dict("index")))
    check("tactic_test: every F1 has a 95% interval that contains it", all(r.f1_ci_low <= r.f1 <= r.f1_ci_high for r in real.itertuples() if r.f1 == r.f1 and r.f1_ci_low == r.f1_ci_low),
          str(real[["f1", "f1_ci_low", "f1_ci_high"]].to_dict("index")))
    check("tactic_test: a tactic with no positive (scarcity) is counts only, never an F1", pd.isna(real.loc["scarcity", "f1"]) and real.loc["scarcity", "reported"].startswith("count only"))
    synthetic = scores[(scores["data"] == "synthetic_validation") & (scores["system"] == "keyword_tuned") & (scores["tactic"] == "urgency")].iloc[0]
    check("tactic_test: the keyword baseline gets recall only on synthetic emails", pd.isna(synthetic["f1"]) and pd.isna(synthetic["precision"]) and str(synthetic["reported"]).startswith("recall only"))
    check("tactic_test: a pooled synthetic set is added", (scores["data"] == "synthetic_pooled_train_validation").any())
    check("tactic_test: a paired difference DistilBERT minus the tuned keyword baseline is reported with an interval",
          ((scores["system"] == "distilbert minus keyword_tuned") & scores["f1_ci_low"].notna()).any())
    check("tactic_test: the validation F1 of Phase 6 is printed beside the real rows", real["validation_f1"].notna().any())
    cooc = pd.read_csv(Path(paths.REHEARSAL_DIR) / "analysis_cooccurrence.csv")
    both = cooc[(cooc["scope"] == "labels") & (cooc["tactic_a"] == "urgency") & (cooc["tactic_b"] == "secrecy")].iloc[0]
    check("analysis: urgency and secrecy occur together in the 20 labelled phishing emails", int(both["emails_both"]) == 20, str(both.to_dict()))
    confusion = pd.read_csv(Path(paths.REHEARSAL_DIR) / "analysis_confusion_pairs.csv")
    check("analysis: confusion pairs list every ordered pair of different tactics", len(confusion) == 42)
    check("tactic_test: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    world.refreeze()
    claim_scores = Path(paths.RESULTS_DIR) / "claim_scores.csv"
    text = claim_scores.read_text(encoding="utf-8")
    claim_scores.write_text(text + " ", encoding="utf-8")
    check("tactic_test: a test run is refused when a frozen file changed after the freeze", exits(lambda: tactic_test.run("test", None, world.stub)))
    claim_scores.write_text(text, encoding="utf-8")
    world.refreeze()
    scores_test, checks_test = quiet(tactic_test.run, "test", None, world.stub)
    check("tactic_test: the test run (after the freeze) writes into results/ and logs its start and finish",
          (Path(paths.RESULTS_DIR) / "tactic_test_scores.csv").exists() and [r["event"] for r in freeze.read_log() if r["script"] == "tactic_test"] == ["started", "finished"])
    check("tactic_test: a second test run is refused", exits(lambda: tactic_test.run("test", None, world.stub)))


@test
def test_claim_extraction(world, check):
    from src.eval import claim_extraction as ce
    from src.claims.schema import CLAIM_TYPES

    world.refreeze()                                  # forget earlier test runs: the choice is made before any test number exists
    table = quiet(ce.write_operating_points)
    chosen = dict(zip(table["claim_type"], table["min_confidence"]))
    check("claim_extraction --choose: the higher validation F1 wins per type (external strong 0.65 over 0.60; internal all 0.70 over 0.60; a tie goes to every claim), counts-only types get every claim",
          chosen["affiliation_external"] == 0.9 and chosen["affiliation_internal"] == 0.0 and chosen["authority"] == 0.0 and chosen["credential_request"] == 0.9
          and chosen["signature_contact"] == 0.0 and chosen["gift_card"] == 0.0, str(chosen))
    scores, checks = quiet(ce.run, "validation", None)
    real = scores[(scores["data"] == "real_validation") & scores["chosen"] & ~scores["claim_type"].str.startswith("macro")]
    check("claim_extraction: exactly one chosen row per claim type", sorted(real["claim_type"]) == sorted(CLAIM_TYPES), str(sorted(real["claim_type"])))
    check("claim_extraction: the five scoreable types with 10 or more positives have an F1 with an interval that contains it",
          all(r.f1_ci_low <= r.f1 <= r.f1_ci_high for r in real.itertuples() if r.claim_type in ce.SCOREABLE and r.f1 == r.f1), str(real[real["claim_type"].isin(ce.SCOREABLE)][["claim_type", "positives", "f1", "f1_ci_low", "f1_ci_high"]].to_dict("records")))
    check("claim_extraction: a type with fewer than 10 positives is counts only", all(pd.isna(r.f1) for r in real.itertuples() if r.positives < 10))
    check("claim_extraction: a macro row over the five scoreable types is added with an interval", ((scores["claim_type"] == "macro_chosen5") & scores["f1_ci_low"].notna()).any())
    check("claim_extraction: synthetic emails are scored apart", (scores["data"] == "synthetic_validation").any())
    check("claim_extraction: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    check("claim_extraction: the operating points are refused once a test run is logged",
          (world.refreeze(), freeze.begin("claim_extraction", "test").finish(True), exits(ce.write_operating_points))[2])
    world.refreeze()
    quiet(ce.run, "test", None)
    check("claim_extraction: the test run writes results/claim_test_scores.csv and a second run is refused", (Path(paths.RESULTS_DIR) / "claim_test_scores.csv").exists() and exits(lambda: ce.run("test", None)))


@test
def test_score_test(world, check):
    from src.eval import score_test

    distribution, budget, checks = quiet(score_test.run, "validation", None, 1, world.stub, bs.stub_featurize, world.thresholds)
    by_category = distribution[distribution["group_by"] == "category"].set_index("group")
    n_phish = len(world.ids("validation", category="phishing"))
    check("score_test: the made-up David emails are High risk and the ham is not", by_category.loc["phishing", "high"] == n_phish and by_category.loc["ham", "high"] == 0, str(by_category[["emails", "low", "suspicious", "high"]].to_dict("index")))
    check("score_test: both denominators are in the distribution (all emails and emails with a checked claim)", {"emails", "checked_emails", "checked_suspicious_or_high_pct"} <= set(distribution.columns)
          and int(by_category.loc["spam", "checked_emails"]) == 0)
    check("score_test: the budget table has email and real-thread groups (the made-up spam has no checked claim, so no spam group) and the validation figures of Phase 10 beside them",
          {"email", "thread"} <= set(budget["kind"]) and "email_spam" not in set(budget["kind"]) and {"validation_suspicious_or_high_pct", "validation_checked_n"} <= set(budget.columns))
    sa = budget[(budget["kind"] == "email") & (budget["group"] == "spamassassin")]
    check("score_test: made-up SpamAssassin ham (checked, calm) passes the budget", len(sa) == 1 and sa["budget"].iloc[0] == "PASS", str(sa.to_dict("records")))
    check("score_test: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    cached = Path(paths.EVAL_FEATURES_DIR) / "world_validation.parquet"
    check("score_test: the per-email table is cached for the other experiments", cached.exists())
    world.refreeze()
    quiet(score_test.run, "test", None, 1, world.stub, bs.stub_featurize, world.thresholds)
    check("score_test: the test run writes results/score_test_budget.csv", (Path(paths.RESULTS_DIR) / "score_test_budget.csv").exists())


@test
def test_ablation_n2(world, check):
    from src.eval import ablation_n2

    scores, benchmark, summary, checks = quiet(ablation_n2.run, "validation", None, world.stub, bs.stub_featurize, world.thresholds)
    apache = scores[scores["source"] == "apache"]

    def cell(variant, metric):
        return apache[(apache["variant"] == variant) & (apache["metric"] == metric)].iloc[0]

    a, a8 = cell("A", "detect_n2"), cell("A", "detect_phase8")
    check("ablation_n2: the takeover (A) is found by the thread verifier in every case and by the Phase 8 verifiers in none; four cases are a count only", a["hits"] == a["n"] == 4 and a8["hits"] == 0
          and pd.isna(a["rate"]), str(a.to_dict()))
    allattacks = cell("attacks (A+B+C)", "detect_n2")
    check("ablation_n2: all 12 hijacks together have a rate with an interval over threads", allattacks["n"] == 12 and allattacks["rate"] == 1.0 and allattacks["ci_low"] <= 1.0 <= allattacks["ci_high"], str(allattacks.to_dict()))
    check("ablation_n2: the calm real next reply (neg_real) is not a false alarm", cell("neg_real", "false_alarm_n2")["hits"] == 0)
    check("ablation_n2: the scan flips at exactly the injected message for the takeover", cell("A", "flip_exact")["hits"] == 4)
    sa = benchmark[(benchmark["source"] == "apache") & (benchmark["variant"] == "A")].set_index("metric")
    check("ablation_n2: in the frozen score the takeover reaches Suspicious with the thread verifier and never without it",
          sa.loc["suspicious_or_high_full", "hits"] == 4 and sa.loc["suspicious_or_high_phase8", "hits"] == 0, str(sa[["hits", "n"]].to_dict("index")))
    check("ablation_n2: false alarms are counted per source on messages with a past, with intervals over threads", len(summary) == 1 and summary["messages_with_a_past"].iloc[0] == 16
          and summary["ci_low"].iloc[0] is not None)
    check("ablation_n2: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    world.refreeze()
    quiet(ablation_n2.run, "test", None, world.stub, bs.stub_featurize, world.thresholds)
    check("ablation_n2: the test run writes results/n2_scores.csv and n2_score_benchmark.csv", (Path(paths.RESULTS_DIR) / "n2_scores.csv").exists() and (Path(paths.RESULTS_DIR) / "n2_score_benchmark.csv").exists())


@test
def test_ablation_n3(world, check):
    from src.eval import ablation_n3, systems

    rows, differences, cuts, bec, checks = quiet(ablation_n3.run, "validation", None, 1, world.stub, world.thresholds)
    table = pd.DataFrame(rows)

    def value(system, scope, metric):
        return table[(table["system"] == system) & (table["scope"] == scope) & (table["metric"] == metric)]["value"].iloc[0]

    check("ablation_n3: the frozen score detects every made-up David email (Nazario) and flags no ordinary mail",
          value("full", "source: nazario (phishing)", "detection_rate") == 1.0 and value("full", "source: spamassassin (ham)", "false_alarm_rate") == 0.0)
    check("ablation_n3: every system has pooled precision, recall, F1, false-alarm rate and AUC, each with an interval that contains it",
          all(((table["system"] == n) & (table["metric"] == m) & (table["scope"] == "pooled attacks against ham")).any() for n in systems.ORDER for m in ("precision", "recall", "f1", "false_alarm_rate", "auc"))
          and all(r.value_ci_low <= r.value <= r.value_ci_high for r in table.itertuples() if r.value == r.value and r.value_ci_low == r.value_ci_low))
    check("ablation_n3: a source with checked-claim scope is reported separately", table["scope"].str.startswith("source, emails with a checked claim").any())
    check("ablation_n3: differences are paired, full minus text, headers, fusion (the architecture ablation adds flat)", set(differences["system_b"]) >= {"text", "headers", "fusion", "flat"}
          and differences["difference_ci_low"].notna().any())
    check("ablation_n3: learned systems flag at most the target share of the validation ham", all(r.validation_ham_flag_rate <= r.target_false_alarm_rate + 1e-9 for r in cuts.itertuples() if r.system != "full"),
          str(cuts[["system", "cut", "target_false_alarm_rate", "validation_ham_flag_rate"]].to_dict("records")))
    check("ablation_n3: the synthetic arm reports attack, benign twin and the difference for every system, and the twins from the organisation's own domain are never flagged by the frozen score",
          set(bec["role"]) == {"attack", "benign twin", "attack minus twin"} and set(bec["system"]) == set(systems.ORDER)
          and int(bec[(bec["system"] == "full") & (bec["role"] == "benign twin")]["hits"].iloc[0]) == 0, str(bec[bec["system"] == "full"][["role", "n", "hits"]].to_dict("records")))
    check("ablation_n3: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    world.refreeze()
    quiet(ablation_n3.run, "test", None, 1, world.stub, world.thresholds)
    check("ablation_n3: the test run writes results/n3_systems.csv and n3_synthetic_bec.csv, with validation pooled rows beside the test rows",
          (Path(paths.RESULTS_DIR) / "n3_systems.csv").exists() and (Path(paths.RESULTS_DIR) / "n3_synthetic_bec.csv").exists()
          and set(pd.read_csv(Path(paths.RESULTS_DIR) / "n3_systems.csv")["split"]) == {"test", "validation"})


@test
def test_ablation_arch(world, check):
    from src.eval import ablation_arch

    rows, differences, agreement, reasons, checks = quiet(ablation_arch.run, "validation", None, 1, world.stub, world.thresholds)
    table = pd.DataFrame(rows)
    check("ablation_arch: routed (full) and flat are both evaluated, pooled and per source", set(table["system"]) == {"full", "flat"} and table["scope"].str.startswith("source:").any())
    by_category = agreement[agreement["group_by"] == "category"]
    check("ablation_arch: the agreement table accounts for every email (both, only routed, only flat, neither)", int(by_category["emails"].sum()) == len(world.ids("validation"))
          and (by_category[["both_flag", "only_routed", "only_flat", "neither"]].sum(axis=1) == by_category["emails"]).all())
    everyone = reasons[reasons["emails"] == "all"].set_index("system")
    check("ablation_arch: every email the routed score flags has a claim and a rule behind it, and the flat vector names no claim",
          everyone.loc["routed (full)", "share_with_a_traceable_reason"] == 1.0 and everyone.loc["flat", "names_the_claim_it_was_about"] == 0, str(everyone.to_dict("index")))
    check("ablation_arch: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    world.refreeze()
    quiet(ablation_arch.run, "test", None, 1, world.stub, world.thresholds)
    check("ablation_arch: the test run writes results/arch_systems.csv and arch_reasons.csv", (Path(paths.RESULTS_DIR) / "arch_systems.csv").exists() and (Path(paths.RESULTS_DIR) / "arch_reasons.csv").exists())


def make_tiny_base(folder, texts):
    """A tiny random DistilBERT (masked-language-model checkpoint, as a real base model has) and a word tokenizer over the words of `texts`, saved in folder. Not a model: a source of numbers for the tests."""
    import re

    from tokenizers import Tokenizer, models as tk_models, normalizers, pre_tokenizers
    from tokenizers.processors import TemplateProcessing
    from transformers import DistilBertConfig, DistilBertForMaskedLM, PreTrainedTokenizerFast

    words = sorted({w for t in texts for w in re.findall(r"[a-z0-9]+|\[|\]", t.lower())})
    vocab = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, "[MASK]": 4}
    vocab.update({w: i + 5 for i, w in enumerate(words)})
    tokenizer = Tokenizer(tk_models.WordPiece(vocab, unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.BertNormalizer(lowercase=True)
    tokenizer.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    tokenizer.post_processor = TemplateProcessing(single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 2), ("[SEP]", 3)])
    fast = PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]", pad_token="[PAD]", cls_token="[CLS]", sep_token="[SEP]", mask_token="[MASK]")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fast.save_pretrained(folder)
    import torch

    torch.manual_seed(0)
    config = DistilBertConfig(vocab_size=len(vocab), dim=32, n_layers=1, n_heads=2, hidden_dim=64, max_position_embeddings=512, pad_token_id=0)
    DistilBertForMaskedLM(config).save_pretrained(folder, safe_serialization=True)
    return folder


@test
def test_ablation_n1(world, check):
    import shutil

    from src.eval import ablation_n1, n1_data, n1_model, n1_train

    results = Path(paths.RESULTS_DIR)
    quiet(n1_data.main)
    sample = pd.read_parquet(paths.N1_DATA_PARQUET)
    check("n1_data: train and validation rows only, one sample row per email, both views, never a test email",
          set(sample["split"]) == {"train", "validation"} and sample["id"].is_unique and not sample["id"].isin(world.ids("test")).any() and {"text_raw", "text_redacted"} <= set(sample.columns))
    check("n1_data: the raw view keeps the link and the redacted view replaces it", sample[sample["has_url"]]["text_raw"].str.contains("http://").all() and sample[sample["has_url"]]["text_redacted"].str.contains(r"\[URL\]").all())
    counts = pd.read_csv(results / "n1_data_counts.csv")
    check("n1_data: the counts file lists emails, attacks and link share per split, source and category", {"emails", "attacks", "link_share_pct"} <= set(counts.columns) and counts["emails"].sum() == len(sample))

    base = make_tiny_base(world.folder / "tiny_base", list(sample["text_raw"]) + list(sample["text_redacted"]) + ["[url] [email] [domain] [file]"])
    out = world.folder / "colab_out"
    with contextlib.redirect_stdout(io.StringIO()):
        code = n1_train.main(["--data", str(paths.N1_DATA_PARQUET), "--out", str(out), "--model", str(base), "--seeds", "1", "2", "--epochs", "4", "--lr", "2e-3", "--batch-size", "16", "--no-fp16"])
    info = json.loads((out / "n1_run_info.json").read_text(encoding="utf-8"))
    log = pd.read_csv(out / "n1_training_log.csv")
    check("n1_train: runs, writes both models, the training log, the validation probabilities and the run record", code == 0 and (out / "n1_model_a" / "model.safetensors").exists() and (out / "n1_model_b" / "model.safetensors").exists()
          and (out / "n1_val_probs.csv").exists() and set(info["chosen"]) == {"A", "B"})
    check("n1_train: 2 seeds x 4 epochs x 2 models are logged and the training loss falls", len(log) == 16 and all(g.sort_values("epoch")["train_loss"].iloc[-1] < g.sort_values("epoch")["train_loss"].iloc[0] for _, g in log.groupby(["model", "seed"])))
    check("n1_train: model A reads the raw view and model B the redacted view", info["chosen"]["A"]["view"] == "text_raw" and info["chosen"]["B"]["view"] == "text_redacted")
    check("n1_train: a table with a test row is refused", exits(lambda: (pd.concat([sample, sample.head(1).assign(split="test", id="zz")]).to_parquet(world.folder / "bad.parquet", index=False),
                                                                          n1_train.main(["--data", str(world.folder / "bad.parquet"), "--out", str(world.folder / "bad_out"), "--model", str(base)]))))
    for source, target in ((out / "n1_model_a", paths.N1_MODEL_A_DIR), (out / "n1_model_b", paths.N1_MODEL_B_DIR)):
        shutil.copytree(source, target)
    for name in ("n1_run_info.json", "n1_training_log.csv", "n1_val_probs.csv"):
        shutil.copy(out / name, results / name)
    model, tokenizer = n1_model.load(paths.N1_MODEL_A_DIR)
    p = n1_model.predict(model, tokenizer, sample["text_raw"].head(20).tolist())
    check("n1_model: probabilities lie strictly between 0 and 1 and keep the order of the texts", ((p > 0) & (p < 1)).all() and len(p) == 20
          and np.allclose(p[::-1], n1_model.predict(model, tokenizer, sample["text_raw"].head(20).tolist()[::-1])[::-1], atol=1e-5) is True)

    scores, differences, checks = quiet(ablation_n1.run, "validation", None, 0)
    overall = scores[scores["scope"] == "overall"]
    check("ablation_n1: every model is scored on every view it reads, with F1, recall, precision and three false-positive rates; the link rule only on the raw and link-free raw views",
          set(overall["model"]) == set(ablation_n1.MODELS) and set(overall[overall["model"] == "link_rule"]["view"]) == {"raw", "linkfree_raw"}
          and set(overall["metric"]) == {"precision", "recall", "f1", "false_positive_rate", "false_positive_rate_ham", "false_positive_rate_spam"})
    link_rule = overall[(overall["model"] == "link_rule") & (overall["metric"] == "recall")].set_index("view")["value"]
    check("ablation_n1: the link rule finds the made-up phishing emails (the only ones with a link) in the raw view and flags nothing in the link-free view", link_rule["raw"] == 0.5 and link_rule["linkfree_raw"] == 0.0, str(link_rule.to_dict()))
    check("ablation_n1: paired differences are reported for the three model families", set(differences["family"]) == {"distilbert", "tfidf_sample", "tfidf_full"} and (differences["contrast"] == "A's drop minus B's drop").any()
          and differences["difference_ci_low"].notna().any())
    counts_view = pd.read_csv(Path(paths.REHEARSAL_DIR) / "n1_view_counts.csv")
    check("ablation_n1: the view counts show the redaction changing the phishing text only", counts_view[(counts_view["view"] == "all") & (counts_view["source"] == "nazario")]["text_changed_by_redaction_pct"].iloc[0] == 100.0
          and counts_view[(counts_view["view"] == "all") & (counts_view["source"] == "kaggle_enron")]["text_changed_by_redaction_pct"].iloc[0] == 0.0)
    parity = checks.frame()
    parity = parity[parity["check"] == "mac_reproduces_colab"]
    check("ablation_n1: the Mac reproduces the probabilities Colab recorded (here: the same machine, full precision)", len(parity) == 2 and (parity["status"] == "PASS").all(), str(parity.to_dict("records")))
    mine = np.array([0.10, 0.50, 0.90, 0.30])
    half = mine + np.array([0.0012, 0.0011, -0.0012, 0.001])
    worst, tolerance, missing, unexplained, flips = ablation_n1.parity_verdict(mine, half, True)
    check("ablation_n1: parity in half precision lets rounding through (0.0012, which fails at 0.001) but not a wrong model (0.05), a flip far from the cut or a missing email",
          worst <= tolerance and unexplained == 0 and ablation_n1.parity_verdict(mine, half, False)[0] > ablation_n1.PARITY_TOLERANCE
          and ablation_n1.parity_verdict(mine, mine + 0.05, True)[0] > tolerance and ablation_n1.parity_verdict(mine, np.array([0.10, 0.50, 0.30, 0.30]), True)[3] == 1
          and ablation_n1.parity_verdict(mine, np.array([0.10, 0.4995, 0.90, np.nan]), True)[2] == 1 and ablation_n1.parity_verdict(mine, np.array([0.10, 0.4995, 0.90, 0.30]), True)[3:] == (0, 1),
          str((worst, tolerance, missing, unexplained, flips)))
    check("ablation_n1: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    world.refreeze()
    quiet(ablation_n1.run, "test", None, 0)
    check("ablation_n1: the test run writes results/n1_scores.csv; a second run is refused", (results / "n1_scores.csv").exists() and exits(lambda: ablation_n1.run("test", None, 0)))


@test
def test_style_confound(world, check):
    from src.eval import style_confound, world as world_module

    for split in ("train", "validation"):
        quiet(world_module.load_world, split, 0, 1, lambda: world.stub, world.thresholds)
    table, checks = quiet(style_confound.run, "validation", None, world.stub)
    words = table[(table["features"] == "words") & table["task"].str.startswith("same-kind")]
    check("style_confound: sources of one kind are paired (one ham pair, one attack pair in the made-up data), with both feature sets", len(words) == 2 and set(table["features"]) == {"words", "tactic probabilities"},
          str(table[["task", "features", "group_a", "group_b", "auc"]].to_dict("records")))
    attack_pair = words[words["task"].str.contains("attack")].iloc[0]
    check("style_confound: the made-up Nazario and Nigerian-Fraud texts are told apart by their words (AUC above 0.9) with an interval", attack_pair["auc"] > 0.9 and attack_pair["auc_ci_low"] <= attack_pair["auc"] <= attack_pair["auc_ci_high"],
          str(attack_pair.to_dict()))
    check("style_confound: real against synthetic is tested for attacks and for benign emails", table["task"].str.startswith("real against synthetic").sum() == 4)
    check("style_confound: every AUC lies in [0, 1] and its own checks pass", checks.failed() == 0 and bool(((table["auc"] >= 0) & (table["auc"] <= 1)).all()), str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))


class FakeModel:
    """A stand-in for the language model of the paraphrase test: it swaps some words (so the stand-in tactic classifier loses urgency and secrecy) and fails the first call of every run once."""

    SWAPS = (("urgent", "pressing"), ("today", "by this afternoon"), ("confidential", "private"), ("secret", "hush-hush"), ("discreet", "careful"), ("Please", "Kindly"), ("process", "handle"))

    def __init__(self, fail_first=True):
        self.calls, self.fail_first = 0, fail_first

    def chat(self, provider, prompt, temperature=0.0, **kwargs):
        import re
        from types import SimpleNamespace

        self.calls += 1
        if self.fail_first and self.calls == 1:
            return SimpleNamespace(text="Sure! Here are the rewrites: not json", model="fake-model")
        texts = re.findall(r'<email number="\d+">\n(.*?)\n</email>', prompt, flags=re.S)
        out = []
        for text in texts:
            for old, new in self.SWAPS:
                text = text.replace(old, new)
            out.append("Hello there. " + text + " Thanks for your help with this.")
        return SimpleNamespace(text="```json\n" + json.dumps(out) + "\n```", model="fake-model")


@test
def test_paraphrase(world, check):
    from src.eval import paraphrase
    from src.router.pipeline import Analyzer

    model = FakeModel()
    analyzer = Analyzer(classifier=world.stub)
    results, bands, checks = quiet(paraphrase.run, "validation", None, 10, 4, analyzer, model.chat, 5)
    groups = set(results["group"])
    check("paraphrase: groups are the attack sources and a ham control", groups == {"nazario", "kaggle_nigerian_fraud", "ham (control)"}, str(groups))
    first_call_retried = model.calls > 4
    check("paraphrase: a batch whose reply is not a JSON array is asked again, and the rewrites are still obtained", first_call_retried and (results["measure"] == "emails").all() or first_call_retried, "%d requests" % model.calls)
    row = results[(results["group"] == "nazario") & (results["item"].str.startswith("urgency kept"))].iloc[0]
    check("paraphrase: the stand-in model's word swaps take urgency away from every made-up phishing email (0 of 10 kept)", row["hits"] == 0 and row["denominator"] == 10, str(row.to_dict()))
    kept = results[(results["group"] == "nazario") & (results["item"].str.startswith("kept: flagged"))].iloc[0]
    check("paraphrase: the contradiction survives the rewording because the headers and the claim are unchanged (10 of 10 stay flagged)", kept["hits"] == kept["denominator"] == 10, str(kept.to_dict()))
    control = results[(results["group"] == "ham (control)") & (results["item"].str.startswith("new: flagged"))].iloc[0]
    check("paraphrase: the ham control gets no new flags from the rewording", control["hits"] == 0)
    check("paraphrase: groups under 20 emails are counts only (no rate, no interval)", results[(results["group"] == "nazario") & (results["measure"] == "flag")]["rate"].isna().all())
    check("paraphrase: the band table lists band before against band after", {"band_before", "band_after", "emails"} <= set(bands.columns) and bands["emails"].sum() >= 20)
    stored = Path(paths.PARAPHRASE_DIR) / "replies_validation.jsonl"
    check("paraphrase: the replies are stored for a rerun", stored.exists() and len(stored.read_text().splitlines()) == 28)
    again = FakeModel(fail_first=False)
    quiet(paraphrase.run, "validation", None, 10, 4, analyzer, again.chat, 5)
    check("paraphrase: a rerun makes no request when every rewrite is stored", again.calls == 0)
    check("paraphrase: its own checks pass", checks.failed() == 0, str(checks.frame()[checks.frame()["status"] == "FAIL"].to_dict("records")))
    check("paraphrase: a valid rewrite is a changed text of similar length; a copy, an empty string and a very short one are refused",
          paraphrase.validity("a " * 100, "completely different words here " * 10) is None and paraphrase.validity("some text here", "some text here") is not None
          and paraphrase.validity("some text here", "") is not None and paraphrase.validity("x " * 200, "y") is not None)
    check("paraphrase: parse_array accepts a fenced JSON array of the right length only", paraphrase.parse_array('```json\n["a","b"]\n```', 2) == ["a", "b"] and paraphrase.parse_array('["a"]', 2) is None
          and paraphrase.parse_array("no", 1) is None and paraphrase.parse_array('["a", ""]', 2) is None)


@test
def test_charts(world, check):
    from src.eval import charts

    results = Path(paths.RESULTS_DIR)
    pd.DataFrame({"source": ["apache_kafka_users", "kaggle_enron"], "full_headers": [True, False], "messages": [1055, 15420], "Message-ID": [100.0, 0.0], "Date": [100.0, 100.0], "Reply-To": [100.0, 0.0]}).to_csv(results / "header_coverage.csv", index=False)
    pd.DataFrame({"kind": ["tactic", "tactic", "claim", "mean_tactic", "mean_claim"], "label": ["authority", "urgency", "payment_request", "mean of 7 defined", "mean of 11 defined"], "items": [692] * 5,
                  "positives_first": [218, 245, 20, None, None], "positives_second": [76, 178, 30, None, None], "both_positive": [73, 166, 10, None, None], "agree_pct": [78.6, 86.8, 90.0, None, None],
                  "kappa": [0.399, 0.694, 0.287, 0.501, 0.458], "reading": ["fair", "substantial", "fair", "moderate", "moderate"], "span_overlap_pct": [None, None, 50.0, None, None]}).to_csv(results / "label_agreement.csv", index=False)
    drawn, skipped = quiet(charts.draw_all, "validation")
    expected = {"n1", "links", "n2", "n3", "arch", "tactics", "claims", "style", "cooccurrence", "budget", "paraphrase", "coverage", "agreement"}
    check("charts: all thirteen charts are drawn from the rehearsal tables of the earlier tests", set(drawn) == expected, "drawn %s, skipped %s" % (sorted(drawn), skipped))
    check("charts: each PNG exists, is not empty and is a PNG", all(p.exists() and p.stat().st_size > 5000 and p.read_bytes()[:4] == b"\x89PNG" for p in drawn.values()), str({n: p.stat().st_size for n, p in drawn.items()}))
    empty_dir = world.folder / "empty"
    empty_dir.mkdir(exist_ok=True)
    drawn2, skipped2 = quiet(charts.draw_all, "test", None, empty_dir, world.folder / "figs_empty")
    check("charts: a missing table skips its chart instead of failing", True and isinstance(skipped2, list))


@test
def test_run_all(world, check):
    from src.eval import run_all

    names = [n for n, _, _ in run_all.plan("test")]
    check("run_all: the test plan runs the scripts in dependency order, with charts last and the paraphrase test left out unless asked for",
          names == ["prepare_test", "tactic_test", "claim_extraction", "score_test", "ablation_n2", "ablation_n3", "ablation_arch", "ablation_n1", "style_confound", "charts"], str(names))
    with_p = run_all.plan("validation", with_paraphrase=True, limit=100, train_limit=500, workers=3)
    commands = {n: " ".join(c[3:]) for n, c, _ in with_p}
    check("run_all: a rehearsal passes the sample sizes only to the scripts that take them, and small samples to the paraphrase test",
          "--limit 100" in commands["ablation_n1"] and "--train-limit 500" in commands["ablation_n3"] and "--limit" not in commands["tactic_test"] and "--workers 3" in commands["prepare_test"]
          and "--per-source 10" in commands["paraphrase"] and commands["charts"] == "--split validation", str(commands))
    check("run_all: the test run refuses a sample", exits(lambda: run_all.plan("test", limit=100)))
    check("run_all: --only and --skip pick scripts by name", [n for n, _, _ in run_all.plan("test", only=["n1", "n3"])] == ["ablation_n3", "ablation_n1"]
          and "charts" not in [n for n, _, _ in run_all.plan("test", skip=["charts"])])
    check("run_all: every script module named in the plan can be imported", all(__import__(c[2], fromlist=["main"]).main for _, c, _ in run_all.plan("test", with_paraphrase=True)))


def run_tests(only=None):
    started = time.time()
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    with World() as world:
        for function in TESTS:
            if only and only not in function.__name__:
                continue
            try:
                function(world, check)
            except (Exception, SystemExit) as error:     # a crashing test (or a refusal that was not expected) is a failed test, with the reason
                import traceback
                check("%s crashed" % function.__name__, False, "".join(traceback.format_exception_only(type(error), error)).strip() + " | " + traceback.format_exc().splitlines()[-3].strip())
    return results, time.time() - started


def self_test(verbose=True, only=None):
    results, seconds = run_tests(only)
    if verbose:
        for name, ok, detail in results:
            print("  %s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok or not detail else "  -> " + detail))
        print("%d of %d checks passed (%.0f seconds)" % (sum(ok for _, ok, _ in results), len(results), seconds))
    return all(ok for _, ok, _ in results), len(results)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if self_test(only=only)[0] else 1)
