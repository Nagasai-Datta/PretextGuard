# src/explain/

Phase 10: **LIME for text**, written by hand. For each tactic the classifier fires, it highlights the words that pushed that tactic's probability up. It explains the **classifier only**. A verifier's explanation is the `reason` in its ledger row (master document Section 4.5: the output is the explanation by construction; LIME has one small job).

```bash
python -m src.explain.lime_explain                          # the self-test: a stand-in classifier with planted words (33 PASS lines, no model, no data)
python -m src.explain.check --selftest                      # the faithfulness check run on the stand-in classifier (no model, no data)
python -m src.explain.check                                 # the faithfulness check on 20 real validation emails (about 40 explanations), 300 copies (about 10 minutes; needs the model)
python -m src.explain.check --samples 300,150,600 --crosscheck
                                                            # the same at three sizes, and compared with the lime package (about 25 minutes)
```

```python
from src.explain.lime_explain import explain_text

# text: the string the classifier reads; predict_fn: texts -> probabilities (n, 7) in TACTICS order, e.g. TacticClassifier.probabilities
result = explain_text(text, classifier.probabilities, {"urgency": 1, "secrecy": 6})
result["urgency"]["highlights"]   # [{"start": 41, "end": 47, "text": "urgent", "weight": 0.31, "word": "urgent"}, ...]
result["urgency"]["words"]        # the top 8 words by absolute weight, positive and negative, as the lime package reports them
result["urgency"]["fit_r2"]       # how well the small local model matches the classifier around this email (0 to 1)
```

`analyze()` (`src/router/pipeline.py`) calls it for the tactics that fired and puts the highlights in the report.

## What LIME does, in plain words

The classifier is a black box, but near one email its behaviour is simple enough for a straight line.

1. Cut the text into words. Each distinct word is one feature (the same word everywhere counts as one).
2. Make 300 copies of the email with a random set of words hidden. The first copy is the email itself.
3. Ask the classifier for the tactic probabilities of every copy (one batch, about 20 emails a second on the Mac's CPU).
4. Give copies close to the original more weight (a kernel on the cosine distance between "which words are present" vectors).
5. Fit a weighted linear model: tactic probability ~ which words are present. A word whose presence raises the probability gets a positive weight.

The highlights are the words with a clearly positive weight (at least 0.02 and at least a quarter of the strongest word's weight; small positive weights are noise of the random sampling), every occurrence of each. It is **not** removing one word at a time (that is occlusion): LIME hides many words together and fits all weights at once, so two words that matter only together are both found. Like the `lime` package for text it uses bag-of-words features, the kernel `sqrt(exp(-d^2 / 25^2))`, a ridge fit to choose the top features by absolute weight and a final ridge fit (alpha 1) on those features. The method is Ribeiro, Singh and Guestrin (2016).

**Why written by hand.** `pip install lime` also installs matplotlib and scikit-image, which only its image explainer uses; a service graded on security does not need them; and every line here can be explained at the viva. The self-test plants a classifier with known behaviour and checks that the words found are exactly the planted ones; `check.py --crosscheck` compares the words with the package's on real emails (install it with `pip install --no-deps lime==0.2.0.1`, not added to `requirements.txt`).

## Settings

| Setting | Value | Why |
|---|---|---|
| Text | the 2,000 characters the classifier reads (`text_read` of the report) | Offsets in the report point into the same text |
| Copies | 300 (clamped to 50 to 2,000) | One batch of 300 short texts is about 8 to 15 seconds on the Mac's CPU; `check.py --samples` compares 150, 300 and 600 on real emails |
| Features | at most 400 distinct words; at most 1,000 word positions; placeholders `[URL]` `[EMAIL]` `[FILE]` `[DOMAIN]` are never hidden | Bounded cost whatever the email |
| Top words | 8 per tactic | The `lime` package defaults to 10; 8 is enough for a reader |
| Seed | 42 | The same email gives the same highlights |
| Tactics | only those that fired; one sampling run serves all of them | The model cost is the copies, not the number of tactics |

## Files

| File | Job |
|---|---|
| `lime_explain.py` | `explain_text`, the maths (`weighted_ridge`, `kernel_weights`, `sample_masks`), the word finder (one pass over the characters, no regular expression), `remove_words` and `distinct_words`, and the self-test |
| `check.py` | The faithfulness check (below) |

## The faithfulness check (`check.py`)

A deletion test, a standard way to test an explanation without labels. Take real validation emails where the classifier fires a main tactic; LIME names the words that pushed it up; remove those words (all occurrences) and ask the classifier again. If LIME is faithful the probability drops.

**The baseline is matched by frequency.** The words LIME names are often frequent ones ("I", "to", "finance" occur several times), so removing them takes out many tokens, while a random word is mostly a rare one. Comparing with random words of any frequency would reward LIME for removing more text, not for choosing better. So for each LIME word the baseline removes a random other word that occurs the same number of times in the email (20 draws, averaged), and the tokens removed are reported for both. The first version of this check (random words of any frequency) was unfair in exactly this way; its numbers are not used.

Reported (`results/lime_checks.csv`, saved after every stage): how often LIME names a word, the mean drop for LIME words and for the matched random words, the share of explanations where LIME's drop is larger (a finding if under 70%), how often the tactic stops firing, the tokens removed, seconds per explanation, the stability of the top 3 words under another seed (12 explanations) and the overlap with the `lime` package (10 explanations).

It says whether the highlighted words matter to the **classifier**, not whether they are the right words for a human, and nothing about whether the classifier is right (precision of urgency on real validation emails is 0.50, authority 0.48). It reads the real validation emails of the labelled set (137, Phase 5) and never the test split.

## Security

- The result holds numbers and character offsets into the text, never markup. The report shows each highlight as a piece of the display-safe `text_read`; a word found by the finder holds only letters, digits and apostrophes, so a highlight cannot carry markup. The interface must still render it as text (Phase 12).
- Cost is bounded: 2,000 characters, 1,000 word positions, 400 features, 50 to 2,000 copies. Crafted inputs (one 5,000-character word, 2,000 one-letter words, 3,000 distinct words, control characters, markup) finish in a fraction of a second with the stand-in classifier; the time on the real model is the classifier's.
- LIME asks the classifier about 300 copies of the email instead of one, so a request with `explain=True` costs the classifier work of about 300 emails (shorter ones). The API (Phase 11) can run it after the score is sent, and rate-limit it.
