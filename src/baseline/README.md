# src/baseline/

Phase 4: the keyword baseline. Fixed word and phrase lists for the seven manipulation tactics and a scorer that turns an email body into seven tactic scores. It is the simple-rules reference that the DistilBERT tactic classifier (Phase 6) has to beat.

```bash
python -m src.baseline.keywords    # self-test: normalisation, scoring rules, lexicon check, crafted inputs
python -m src.baseline.build       # train-split hit rates and sanity checks; needs cleaned.parquet (Phase 2)
```

## Files

| File | Job |
|---|---|
| `lexicon.py` | The word lists, data only: seven tactics, each with `strong` and `weak` phrases, and `LEXICON_VERSION` |
| `keywords.py` | `normalise(text)`, `build_index(lexicon)` (checks the lists), `score_tactics(text)`, `fired_tactics(scores, threshold)`, and the self-test |
| `build.py` | Scores the train split of `cleaned.parquet`, prints and saves hit rates, phrase hits and sanity checks |

`score_tactics` works on one string and knows nothing about datasets, so Phase 13 reuses it unchanged on the validation and test splits (only `build.py` is limited to train).

```python
from src.baseline.keywords import score_tactics, fired_tactics

scores = score_tactics("Please keep this between us. It is urgent.")
scores["secrecy"]          # {'score': 1.0, 'phrases': ['keep this between us']}
fired_tactics(scores)      # ['urgency', 'secrecy']
```

## How an email is scored

1. **Normalise.** Unicode NFKC, lowercase, zero-width characters removed, curly quotes turned into `'`. A placeholder such as `[URL]` becomes one word (`plhurl`), so removing punctuation cannot turn it into "url". Pre-tokenised contractions are glued back (`don ' t` to `don't`, only for the real endings t, s, re, ve, ll, d, m, so `' hello '` stays apart), apostrophes inside words are dropped (`dont`), and every other punctuation mark becomes a space. The phrases in `lexicon.py` go through the same function, so both sides always look the same. This is what makes the Kaggle Enron and Ling text (stored lowercase and pre-tokenised) match like every other source.
2. **Match whole words.** Each phrase is stored under its first word. For every word of the email, the phrases starting with it are checked against the next words. "now" never matches inside "know", and phrase matching uses no regular expressions.
3. **Longest phrase wins.** When two phrases of one tactic overlap in the text, only the longer counts ("this is urgent" beats "urgent"), so the same words are not counted twice.
4. **Each distinct phrase counts once**, however often it appears, so a long message cannot score high by repeating itself.
5. **Score and threshold.** Strong phrases weigh 1.0, weak ones 0.5; a tactic's score is the sum. A tactic fires at score 1.0 or more by default: one strong phrase, or two different weak ones. `fired_tactics` accepts one number or a `{tactic: number}` dict (tactics left out use 1.0).

Strong phrases almost only appear when the tactic is being used ("keep this between us"). Weak phrases hint at it but also appear in ordinary mail ("urgently", "valued customer"). The weights are the cheap way to say which words are precise and which are broad.

## Where the lists come from, and what is off limits

- Written fresh from the tactic definitions in master document Section 7 and general knowledge of how business email compromise, phishing and advance-fee fraud are worded. No list was copied.
- Authority holds assertion phrases only ("this is the CFO", "on behalf of the CEO"). Bare job titles are left out because every signature has one.
- `build.py` reads **only the train split**: the Parquet filter never loads validation or test rows. The lists may be revised after reading its output, never after looking at validation or test emails.
- Every revision changes `LEXICON_VERSION`; the version is saved in `results/keyword_checks.csv`. The lists are frozen before the Phase 5 labels come back.

| Version | Date | Change |
|---|---|---|
| 0.1 | 7 Oct 2026 | First lists. Before any data was read, weak words that would obviously fire on business and technical mail (regulation, government, limited, lose, restricted, pending and similar) were removed |

## Output (`results/`, committed; counts only, never email text)

| File | Columns | Meaning |
|---|---|---|
| `keyword_hit_rates.csv` | `group_type`, `group`, `emails`, `tactic`, `fired_pct`, `any_hit_pct`, `mean_score` | For all train emails (`all`), per category and per source / category: % of emails where the tactic fires, % with at least one matching phrase, and the mean score. `tactic = any_tactic` means at least one of the seven fires; its `mean_score` is the mean number of tactics firing per email |
| `keyword_phrase_hits.csv` | `tactic`, `phrase`, `strength`, `emails`, `ham`, `spam`, `phishing`, `fraud`, `share_of_tactic_hits_pct` | Every phrase of the lexicon (also the ones that never matched), how many train emails contain it, and its share of the emails with any hit for its tactic |
| `keyword_checks.csv` | `check`, `item`, `value`, `expected`, `status` | The sanity checks below (PASS, FAIL or info) plus the lexicon version, phrase count, train rows and scoring time |

## The sanity checks

Tactic labels do not exist before Phase 5, so Phase 4 cannot say how accurate the lists are. `build.py` checks that they behave sensibly:

1. **Attack vs ham.** Secrecy on fraud and on phishing, urgency, scarcity and authority on phishing, and liking on fraud must fire at least twice as often as the same tactic on ham, and more than 0%.
2. **Coverage.** Each tactic fires on at least 20 train emails. Rare tactics (reciprocity, social proof) may fail this on real data. That is a finding to report, not an error: such a tactic is later reported with counts instead of an F1 score.
3. **No dominant phrase.** No phrase accounts for more than half of the emails with a hit for its tactic. A phrase that does makes the list depend on one word.

The script also prints the most common phrases per tactic and, per tactic, a few ordinary (ham) emails where it fired: those are the false positives to read when deciding whether a phrase is too broad. A passed check shows the lists behave sensibly across categories; it does not show they are correct. F1 against the labels comes in Phase 13.

## How Phase 13 uses it

- **Fair comparison.** The baseline's thresholds are tuned on the validation labels, one number per tactic, with the same budget as DistilBERT's. The test split is used once.
- **Sampling bias.** None: no keyword hit was used to pick any labelled email (Phase 5 drew a stratified random sample), so the baseline has no selection advantage. The Phase 4 results explain why a top-up was dropped: the baseline fires on a tiny share of phishing for reciprocity and social proof, and most of those firings are on ham and spam, so selecting by its hits would have picked false positives.
- **N1.** The baseline reads `body_redacted`, so links and addresses never help it: it is already payload-free.

## Known limits

No negation ("there is no rush" still matches rush phrases), no misspellings, no paraphrase, and no sense of who is speaking: these are the gaps the learned model should close, and the report says so. Tactics that depend on a claim (authority) are only caught when the sentence asserts it in a listed form.

## Security

- Phrase matching uses no regular expressions, and the few short patterns in `normalise` have no nested or open-ended repeats beyond one character class, so nothing backtracks: cost grows in proportion to the text length (ReDoS-safe, as in Phases 2 and 3).
- Bodies are cut at 200,000 characters, as in cleaning. The self-test runs eight crafted inputs of that size (a repeated word, apostrophes, placeholders, zero-width characters and others); each finishes in under one second.
- Invisible characters are removed before matching, so a phrase cannot be hidden by splitting it with zero-width spaces.
- `build.py` never prints email text to a file: result files hold counts only. The ham examples are printed to the terminal only.
