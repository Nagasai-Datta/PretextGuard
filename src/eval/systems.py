"""Phase 13: the systems the N3 and architecture ablations compare, and how they are held to the same false-alarm rate.

    full      the frozen claim-routed risk score of Phase 10 (flagged at Suspicious or above, score 35 or more). It uses no attack label anywhere.
    text      text only: the seven tactic probabilities and how many claims of each type the extractor found. A logistic regression fitted on the train split.
    headers   headers only: authentication verdicts, free mailbox, look-alike of the organisation domain, Reply-To and so on, with no claim in sight. Fitted on train.
    fusion    parallel score fusion in the style of BEC-Guard: the mean of the text score and the headers score. Two scores added; neither knows what the other is about.
    flat      the architecture ablation's classifier: every signal of the ledger as one flat vector (which rules fired anywhere, the worst severity per verifier, the tactic
              probabilities, two counts) without the link between a claim and the evidence against it. Fitted on train.

THE FIT. Attack (phishing and fraud) against legitimate mail (ham) on the train split; spam is left out of the fit and out of the F1 and false-alarm rate, because it is neither an
attack nor legitimate mail (it is listed apart). A logistic regression after standardising each feature, balanced class weights, nothing tuned.

THE MATCH. Systems are compared at the same false-alarm rate, otherwise a system that flags everything would win on detection. The false-alarm rate is the share of the VALIDATION ham that the
frozen score flags (floored at 0.5% so the cut is not degenerate); each learned system gets the cut that flags at most that share of the validation ham (src/eval/stats.py matched_cut). The cuts are
therefore fixed on validation, before the test split is read, and applied once to the test split.

WHAT THIS FAVOURS. The learned systems are fitted on attack labels; the frozen score never saw one. A headers-only model can also partly learn WHICH CORPUS an email came from (the corpora differ in
header evidence: the Kaggle Enron and Ling emails carry none), which helps it separate attacks from ham without understanding either. Both favour the learned systems, so a learned system
that matches the frozen score is not evidence against the frozen score. The per-source tables show where the corpus is doing the work.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.eval import common
from src.eval.stats import matched_cut
from src.eval.world import FLAT_NAMES, HEADER_NAMES, TEXT_NAMES, matrix
from src.router.score import DEFAULT_CONFIG

FEATURES = {"text": TEXT_NAMES, "headers": HEADER_NAMES, "flat": FLAT_NAMES}
LEARNED = ("text", "headers", "flat")
ORDER = ("full", "text", "headers", "fusion", "flat")
DESCRIPTION = {"full": "frozen claim-routed risk score (Suspicious or above)", "text": "text only (tactic probabilities and claim counts), logistic regression",
               "headers": "headers only (authentication, free mailbox, look-alike, Reply-To ...), logistic regression", "fusion": "parallel fusion: mean of the text and headers scores",
               "flat": "flat vector of every ledger signal without the claim-to-evidence link, logistic regression"}
FIT_SEED = 0


def roles(world):
    """Boolean arrays (attack, ham, spam) for the categories of a world table."""
    category = world["category"].to_numpy()
    return np.isin(category, common.ATTACK_CATEGORIES), category == "ham", category == "spam"


def fit(train_world, names=LEARNED):
    """{system: fitted pipeline}: attack against ham on the train split, spam left out."""
    attack, ham, _ = roles(train_world)
    keep = attack | ham
    models = {}
    for name in names:
        model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=3000, C=1.0, random_state=FIT_SEED))
        model.fit(matrix(train_world, FEATURES[name])[keep], attack[keep].astype(int))
        models[name] = model
    return models


def scores_of(models, world):
    """{system: score array} for a world table; every score is higher for 'more suspicious'. full is the 0 to 100 risk score."""
    out = {"full": world["score"].to_numpy(dtype=float)}
    for name, model in models.items():
        out[name] = model.predict_proba(matrix(world, FEATURES[name]))[:, 1]
    if "text" in out and "headers" in out:
        out["fusion"] = (out["text"] + out["headers"]) / 2.0
    return out


def full_cut():
    """'flag when score > cut' for the frozen score: Suspicious starts at the first cut of the configuration (35), so the cut is 34.5."""
    return DEFAULT_CONFIG["cuts"][0] - 0.5


def target_rate(validation_world, validation_scores):
    """The false-alarm rate every learned system is held to: what the frozen score flags of the validation ham, but at least the floor."""
    _, ham, _ = roles(validation_world)
    observed = float((validation_scores["full"][ham] > full_cut()).mean())
    return max(observed, common.MATCHED_FPR_FLOOR), observed


def choose_cuts(validation_world, validation_scores, target):
    """{system: cut} so that at most `target` of the validation ham is flagged; the frozen score keeps its own cut."""
    _, ham, _ = roles(validation_world)
    cuts = {"full": full_cut()}
    for name in validation_scores:
        if name != "full":
            cuts[name] = matched_cut(validation_scores[name][ham], target)
    return cuts


def flags(scores, cuts):
    """{system: boolean array}: score above the cut."""
    return {name: scores[name] > cuts[name] for name in scores}


def top_contributions(model, world, names):
    """For a fitted standardise+logistic-regression pipeline: (index of the feature with the largest positive contribution per email, contributions are coefficient x standardised value)."""
    scaler, logistic = model.steps[0][1], model.steps[1][1]
    x = (matrix(world, names) - scaler.mean_) / np.where(scaler.scale_ == 0, 1.0, scaler.scale_)
    contribution = x * logistic.coef_[0]
    return contribution.argmax(axis=1), contribution
