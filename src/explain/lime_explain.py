"""Phase 10: LIME for text, written by hand. It highlights the words that pushed a tactic probability up.

    from src.explain.lime_explain import explain_text

    results = explain_text(text, predict_fn, {"urgency": 1, "secrecy": 6})
    results["urgency"]["highlights"]     # [{"start": 41, "end": 47, "text": "urgent", "weight": 0.31, "word": "urgent"}, ...]

text        the string the classifier reads (model_text of the redacted body, at most 2,000 characters)
predict_fn  a function from a list of texts to an array of shape (len(texts), 7): the classifier's probabilities in TACTICS order
            (TacticClassifier.probabilities does this, about 20 emails a second on the Mac's CPU)
columns     {tactic name: its column in that array}; only these tactics are explained (the ones that fired)

THE METHOD (Ribeiro, Singh and Guestrin, 2016, "Why Should I Trust You?"), in plain words. The classifier is a black box, but near ONE
email its behaviour is simple enough for a straight line. So:
    1. cut the text into words (each distinct word is one feature; the same word everywhere counts as one);
    2. make many copies of the email with a random set of words hidden (the first copy is the email itself);
    3. ask the classifier for the tactic probabilities of every copy;
    4. give copies close to the original more weight (a kernel on the cosine distance between "which words are present" vectors);
    5. fit a weighted linear model: tactic probability ~ which words are present. A word whose presence raises the probability gets a
       positive weight. The top positive words are the highlights.
It is not the same as removing one word at a time (that is occlusion): LIME removes many words together and fits all weights at once, so
two words that only matter together are both found. Like the lime package for text it uses bag-of-words features, the kernel
sqrt(exp(-d^2 / 25^2)), a ridge selection of the top features by absolute weight and a final ridge fit (alpha 1) on those features.

WHAT IT EXPLAINS. Only the tactic classifier. A verifier's explanation is the reason in its ledger row; LIME says nothing about those. And it says which words
pushed the classifier, not whether the email is dangerous or whether the classifier is right (precision of urgency on real validation emails is 0.50).

Reproducible. The random choices use a fixed seed (default 42), so the same email gives the same highlights.

Security and size. The text is cut at 2,000 characters, at most 1,000 words and 400 distinct words are looked at, and the number of copies is
clamped to 50 to 2,000 (default 300), so the cost is one classifier pass over that many short texts and nothing else. The result holds numbers
and character offsets into `text`, never markup: the interface cuts the text at those offsets and shows each piece as text. No regular
expression runs over the email (words are found in one pass over the characters). The placeholders [URL] [EMAIL] [FILE] [DOMAIN] are never hidden.

Self-test (needs no model):   python -m src.explain.lime_explain
"""

import sys
import time

import numpy as np

MAX_CHARS = 2000            # the classifier reads this much of an email
MAX_WORDS = 1000            # word positions looked at
MAX_FEATURES = 400          # distinct words that can be hidden; later new words stay in every copy
MIN_FEATURES = 3            # a text with fewer distinct words cannot be explained
DEFAULT_SAMPLES = 300
MIN_SAMPLES, MAX_SAMPLES = 50, 2000
KERNEL_WIDTH = 25.0         # the lime package's default for text
SELECT_ALPHA = 0.01         # ridge strength used to choose the top features (the lime package: 'highest_weights')
FIT_ALPHA = 1.0             # ridge strength of the final fit on the chosen features
DEFAULT_WORDS = 8           # features chosen per tactic
MIN_WEIGHT = 0.02           # a word is highlighted only if removing it lowers the tactic probability by at least this much ...
RELATIVE_MIN = 0.25         # ... and at least this share of the strongest word's effect (small positive weights are noise of the sampling)
SEED = 42
PLACEHOLDERS = frozenset(("url", "email", "file", "domain"))


# ------------------------------------------------------------------------------------------------------------ words

def find_words(text):
    """[(start, end, lower-case word)] in order: runs of letters and digits, with an apostrophe allowed inside a word, found in one pass.

    A word that is a placeholder ([URL], [EMAIL], [FILE], [DOMAIN]) is marked by a third element 'None' so it is never hidden."""
    spans, i, n = [], 0, len(text)
    while i < n and len(spans) < MAX_WORDS:
        if text[i].isalnum():
            j = i + 1
            while j < n and (text[j].isalnum() or (text[j] in "'’" and j + 1 < n and text[j + 1].isalnum())):
                j += 1
            word = text[i:j].lower()
            if word in PLACEHOLDERS and i > 0 and text[i - 1] == "[" and text[j:j + 1] == "]":
                word = None
            spans.append((i, j, word))
            i = j
        else:
            i += 1
    return spans


def feature_index(spans):
    """({word: feature number} in order of first appearance, the feature number of every span or -1 when the span is never hidden)."""
    features, per_span = {}, []
    for _, _, word in spans:
        if word is None:
            per_span.append(-1)
        elif word in features:
            per_span.append(features[word])
        elif len(features) < MAX_FEATURES:
            features[word] = len(features)
            per_span.append(features[word])
        else:
            per_span.append(-1)
    return features, np.array(per_span, dtype=int)


def render(text, spans, per_span, present):
    """The text with every word whose feature is absent (present[feature] False) removed; everything between the words is kept."""
    parts, previous = [], 0
    for (start, end, _), feature in zip(spans, per_span):
        parts.append(text[previous:start])
        if feature < 0 or present[feature]:
            parts.append(text[start:end])
        previous = end
    parts.append(text[previous:])
    return "".join(parts)


# ------------------------------------------------------------------------------------------------------- the maths

def weighted_ridge(x, y, weights, alpha):
    """Weighted ridge regression with an intercept: (coefficients, weighted R squared).

    Minimises sum_i w_i (y_i - b - x_i . c)^2 + alpha * |c|^2. The data are centred with the weighted means, which takes the intercept out of
    the problem; the rest is the normal equation (X'WX + alpha I) c = X'Wy."""
    total = weights.sum()
    x_mean = (weights[:, None] * x).sum(axis=0) / total
    y_mean = (weights * y).sum() / total
    xc, yc = x - x_mean, y - y_mean
    gram = xc.T @ (weights[:, None] * xc) + alpha * np.eye(x.shape[1])
    coefficients = np.linalg.solve(gram, xc.T @ (weights * yc))
    residual = (weights * (yc - xc @ coefficients) ** 2).sum()
    spread = (weights * yc ** 2).sum()
    r2 = 1.0 - residual / spread if spread > 1e-12 else 0.0
    return coefficients, float(r2)


def kernel_weights(masks):
    """Weight of every copy: close to the original (few words hidden) counts more. Distance is the cosine distance to the all-ones row."""
    ones = np.ones(masks.shape[1])
    norms = np.sqrt(masks.sum(axis=1)) * np.sqrt(ones.sum())
    cosine = np.divide(masks.sum(axis=1), norms, out=np.zeros(len(masks)), where=norms > 0)
    distance = 1.0 - cosine
    return np.sqrt(np.exp(-(distance ** 2) / KERNEL_WIDTH ** 2))


def sample_masks(features, samples, rng):
    """A (samples + 1) x features 0/1 matrix. Row 0 is the original (nothing hidden). Every other row hides a random number of words
    (1 to features - 1, equally likely), chosen at random, as the lime package does for text."""
    masks = np.ones((samples + 1, features))
    for i in range(1, samples + 1):
        hidden = rng.choice(features, size=int(rng.integers(1, features)), replace=False)
        masks[i, hidden] = 0.0
    return masks


# --------------------------------------------------------------------------------------------------------- helpers

def distinct_words(text):
    """The distinct lower-case words of a text in order of first appearance, placeholders left out (the words that can be hidden)."""
    seen, out = set(), []
    for _, _, word in find_words(text[:MAX_CHARS]):
        if word is not None and word not in seen:
            seen.add(word)
            out.append(word)
    return out


def remove_words(text, words):
    """The text with every occurrence of the given words (lower case) removed. Everything between the words is kept; placeholders are never removed."""
    text = text[:MAX_CHARS]
    drop, parts, previous = set(words), [], 0
    for start, end, word in find_words(text):
        parts.append(text[previous:start])
        if word is None or word not in drop:
            parts.append(text[start:end])
        previous = end
    parts.append(text[previous:])
    return "".join(parts)


# --------------------------------------------------------------------------------------------------------- the API

def explain_text(text, predict_fn, columns, num_samples=DEFAULT_SAMPLES, num_words=DEFAULT_WORDS, seed=SEED):
    """{tactic: {"fit_r2", "words": [{"word", "weight"}], "highlights": [{"start", "end", "text", "weight", "word"}]}} for the tactics in columns.

    words are the top `num_words` by absolute weight (as the lime package reports them, positive and negative); highlights are the words whose
    weight is clearly positive (at least MIN_WEIGHT and at least RELATIVE_MIN of the strongest weight), every occurrence, sorted by position:
    the words that pushed that tactic UP. Tiny positive weights are noise of the random sampling and are not highlighted. Returns {} when the
    text has too few distinct words."""
    text = text[:MAX_CHARS] if isinstance(text, str) else ""
    num_samples = int(min(MAX_SAMPLES, max(MIN_SAMPLES, num_samples)))
    spans = find_words(text)
    features, per_span = feature_index(spans)
    if len(features) < MIN_FEATURES or not columns:
        return {}
    rng = np.random.default_rng(seed)
    masks = sample_masks(len(features), num_samples, rng)
    texts = [render(text, spans, per_span, masks[i] > 0) for i in range(len(masks))]
    probabilities = np.asarray(predict_fn(texts), dtype=float)
    if probabilities.shape[0] != len(texts):
        raise ValueError("predict_fn returned %d rows for %d texts" % (probabilities.shape[0], len(texts)))
    weights = kernel_weights(masks)
    names = list(features)
    out = {}
    for tactic, column in columns.items():
        y = probabilities[:, column]
        coefficients, _ = weighted_ridge(masks, y, weights, SELECT_ALPHA)        # choose the features
        chosen = np.argsort(-np.abs(coefficients), kind="stable")[:num_words]
        final, r2 = weighted_ridge(masks[:, chosen], y, weights, FIT_ALPHA)      # explain with them
        order = np.argsort(-np.abs(final), kind="stable")
        words = [{"word": names[chosen[k]], "weight": round(float(final[k]), 4)} for k in order]
        strongest = max([float(v) for v in final] + [0.0])
        floor = max(MIN_WEIGHT, RELATIVE_MIN * strongest)
        positive = {names[chosen[k]]: float(final[k]) for k in range(len(chosen)) if final[k] >= floor}
        highlights = [{"start": s, "end": e, "text": text[s:e], "weight": round(positive[w], 4), "word": w}
                      for (s, e, w) in spans if w in positive]
        out[tactic] = {"fit_r2": round(r2, 3), "words": words, "highlights": highlights}
    return out


# ------------------------------------------------------------------------------------------------------ self-test

PLANTED = {"urgency": ("urgent", "immediately", "today"), "secrecy": ("confidential", "nobody"), "authority": ("director", "ceo")}
COLUMNS = {"authority": 0, "urgency": 1, "scarcity": 2, "reciprocity": 3, "social_proof": 4, "liking": 5, "secrecy": 6}
FILLER = ("please send the quarterly figures for the vendor list and the new office budget after the team meeting about shipping and the warehouse "
          "schedule thanks for your help with the invoice review and the contract draft ")


def stub_predict(texts):
    """A fake classifier with known behaviour: a tactic's probability is 0.05 plus 0.3 for each of its planted words that is still present."""
    out = np.full((len(texts), 7), 0.05)
    for i, text in enumerate(texts):
        words = {w for _, _, w in find_words(text) if w}
        for tactic, planted in PLANTED.items():
            out[i, COLUMNS[tactic]] = min(0.95, 0.05 + 0.3 * len(words & set(planted)))
    return out


def sample_text():
    return ("Hello Maria, this is the Director. " + FILLER + "Please do this today and immediately, it is urgent. Keep it confidential, tell nobody. "
            + FILLER + "Thanks.")


def self_test(verbose=True):
    """(all passed, number of checks)."""
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    text = sample_text()
    started = time.time()
    out = explain_text(text, stub_predict, {"urgency": 1, "secrecy": 6, "authority": 0})
    check("a text of about 70 words is explained with 300 copies in under 2 seconds", time.time() - started < 2.0, "%.2f s" % (time.time() - started))
    for tactic in ("urgency", "secrecy", "authority"):
        words = [w["word"] for w in out[tactic]["words"] if w["weight"] > 0.05]
        present = set(PLANTED[tactic]) & {w for _, _, w in find_words(text)}
        check("%s: the words with a clear positive weight are exactly the planted words that are in the text" % tactic, set(words) == present, str(words))
        highlighted = {h["word"] for h in out[tactic]["highlights"]}
        check("%s: the highlighted words are exactly the planted words that are in the text (no noise words)" % tactic, highlighted == present, str(highlighted))
        top = max(out[tactic]["words"], key=lambda w: w["weight"])
        check("%s: the top weight is near the planted effect (0.3 per word)" % tactic, 0.2 < top["weight"] < 0.4, str(top))
        check("%s: the local model fits the stub almost perfectly (R squared above 0.95)" % tactic, out[tactic]["fit_r2"] > 0.95, str(out[tactic]["fit_r2"]))
    allh = [h for t in out.values() for h in t["highlights"]]
    check("every highlight is the slice of the text its offsets name", all(text[h["start"]:h["end"]] == h["text"] for h in allh), "%d highlights" % len(allh))
    check("highlights are sorted by position and do not overlap", all(a["end"] <= b["start"] for t in out.values() for a, b in zip(t["highlights"], t["highlights"][1:])))
    check("same input and seed give identical output", out == explain_text(text, stub_predict, {"urgency": 1, "secrecy": 6, "authority": 0}))
    other = explain_text(text, stub_predict, {"urgency": 1}, seed=7)
    check("another seed still finds the planted words", {w["word"] for w in other["urgency"]["words"] if w["weight"] > 0.05} == set(PLANTED["urgency"]))
    check("a tactic with no planted word that is present gets no strong word", all(abs(w["weight"]) < 0.05 for w in explain_text(text, stub_predict, {"scarcity": 2})["scarcity"]["words"]))
    repeated = "urgent " * 3 + FILLER
    rep = explain_text(repeated, stub_predict, {"urgency": 1})["urgency"]
    check("a repeated word is highlighted at every place it occurs", sum(1 for h in rep["highlights"] if h["word"] == "urgent") == 3)
    marked = "Pay today [URL] and [EMAIL] now " + FILLER
    seen = []

    def spy(texts):
        seen.extend(texts)
        return stub_predict(texts)

    explain_text(marked, spy, {"urgency": 1})
    check("placeholders are never hidden", all("[URL]" in t and "[EMAIL]" in t for t in seen), "%d copies" % len(seen))
    check("the first copy is the email itself", seen[0] == marked)
    check("300 copies plus the original are asked for", len(seen) == 301, str(len(seen)))
    sizes = []
    explain_text(text, lambda ts: (sizes.append(len(ts)), stub_predict(ts))[1], {"urgency": 1}, num_samples=1)
    explain_text(text, lambda ts: (sizes.append(len(ts)), stub_predict(ts))[1], {"urgency": 1}, num_samples=10 ** 9)
    check("the number of copies is clamped to 50 and 2,000", sizes == [51, 2001], str(sizes))
    check("a text with fewer than 3 distinct words is not explained", explain_text("urgent urgent urgent", stub_predict, {"urgency": 1}) == {})
    check("an empty text, a non-string and no tactic give nothing", explain_text("", stub_predict, {"urgency": 1}) == {} and explain_text(None, stub_predict, {"urgency": 1}) == {}
          and explain_text(text, stub_predict, {}) == {})
    try:
        explain_text(text, lambda ts: np.zeros((3, 7)), {"urgency": 1})
        check("a predict function that returns the wrong number of rows is refused", False)
    except ValueError:
        check("a predict function that returns the wrong number of rows is refused", True)
    crafted = [
        ("one 5,000-character word", "a" * 5000),
        ("2,000 one-letter words", "a " * 1000),
        ("3,000 distinct words (only 400 can be hidden)", " ".join("w%d" % i for i in range(3000))),
        ("zero-width and control characters", ("​\x00\x07 urgent " * 400)),
        ("markup in the text", "<script>alert(1)</script> urgent <b>today</b> " + FILLER),
    ]
    for name, content in crafted:
        started = time.time()
        crafted_out = explain_text(content, stub_predict, {"urgency": 1})
        seconds = time.time() - started
        slices = all(content[:MAX_CHARS][h["start"]:h["end"]] == h["text"] for t in crafted_out.values() for h in t["highlights"])
        check("crafted input: %s (%.2f s)" % (name, seconds), seconds < 3.0 and slices)
    check("highlight text holds only letters, digits and apostrophes (no markup can come out of it)",
          all(all(ch.isalnum() or ch in "'’" for ch in h["text"]) for t in explain_text(crafted[4][1], stub_predict, {"urgency": 1}).values() for h in t["highlights"]))
    check("remove_words removes every occurrence of a word and keeps the rest and the placeholders", remove_words("Pay today [URL] and today again", {"today"}) == "Pay  [URL] and  again"
          and distinct_words("a b a [URL] c") == ["a", "b", "c"])
    passed = all(ok for _, ok, _ in results)
    if verbose:
        for name, ok, detail in results:
            print("  %s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok or not detail else "  -> " + detail))
        print("%d of %d checks passed" % (sum(ok for _, ok, _ in results), len(results)))
    return passed, len(results)


if __name__ == "__main__":
    ok, _ = self_test()
    sys.exit(0 if ok else 1)
