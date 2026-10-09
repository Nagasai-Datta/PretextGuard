# src/router/

Phase 10: the **claim router**, the **verdict ledger**, the **0 to 100 risk score** and **`analyze()`**, the one function that runs the whole pipeline of Figure 3 for one request and returns the report of master document Section 6.3. The API (Phase 11) calls `analyze` and nothing else.

```bash
python -m src.router.selftest                          # score, router, ledger and the whole pipeline on hand-made emails and threads (103 PASS lines; needs spaCy, not the model)
python -m src.router.build_selftest                    # build.py on a tiny made-up dataset: all the modes, every results file (38 PASS lines)
python -m src.router.pipeline email.eml --org acmecorp.com    # try analyze() on a file (needs the model); add --no-explain to skip LIME, --json for the raw report
python -m src.router.pipeline --thread a.eml b.eml c.eml     # a thread of files: the newest message (by its Date header) is judged against the ones before it
python -m src.router.build --train-only --limit 6000   # development: score a random 6,000 train emails, the rule weights, the grid (about 7 minutes the first time)
python -m src.router.build --weights-only --write-reliability   # the reliability of every rule from EVERY train email, no classifier (about 3 minutes); writes reliability.json
python -m src.router.build --calibrate                 # calibration: the grid on the validation split, the choice, nothing else saved but score_grid.csv
python -m src.router.build                             # the final run of a frozen score version: rule weights (train), validation emails and threads, benchmark check, checks
python -m src.router.build --parity 300                # also run the real analyze() on 300 validation emails and compare with the batch scores
```

```python
from src.router.pipeline import analyze

report = analyze(raw_email, org_domain="acmecorp.com")        # one email (text or bytes); org_domain is optional
report = analyze([raw_1, raw_2, raw_3])                       # a thread (a list): the newest message is judged against the earlier ones
report["score"], report["verdict"]                            # 100, "High risk"
report["action"]                                              # fixed text, never text from the email
[r["reason"] for r in report["ledger"] if r["contradiction"]] # the reasons: the ledger IS the explanation
```

## Files

| File | Job |
|---|---|
| `router.py` | The claim router: `assign` gives every claim the verifier(s) that can check it (the table of Section 6.4, `ROUTES` in `src/verifiers/rows.py`), `check_routing` finds a claim that got no row or a row that names no claim |
| `ledger.py` | The verdict ledger: `build_ledger` collects the claim rows and the thread signal rows and checks them (every row valid, filed under its verifier, no claim lost); `coverage` says how much could be checked and why some checks could not run; `flat_features` gives the same signals as one fixed-length vector for the Phase 13 architecture ablation |
| `score.py` | The score: points per severity, the strongest row of each claim, the half-weight sum, the pressure multiplier, tactic points, the cap, the three bands and the fixed action texts. Holds `SCORE_VERSION`, `SCORE_LOG` and loads the reliability factors from `reliability.json` |
| `reliability.json` | Data: the reliability factor (0 or 0.5) of each rule that cries wolf on legitimate real mail (ham), and the score version it was written for. Written by `build.py --weights-only --write-reliability` and committed, like `thresholds.json` next to the model weights; a file for another score version is refused |
| `pipeline.py` | `analyze`, the `Analyzer` class (loads the model once), `check_report` (runs on every report), and the command-line try-out |
| `selftest.py` | 99 checks: the worked values of Section 6.6, the router and ledger checks, the David email and its variants, five hijack threads, crafted input, tampered reports |
| `build.py` | The calibration and the results: rule reliability from train, the grid on validation, the false-alarm budget, the distribution of bands, the hijack benchmark check, parity with `analyze` |
| `build_selftest.py` | Runs `build.py` on a made-up dataset in a temporary folder, so the long runs are not the first time it runs |

## The report

`analyze` returns a dictionary (JSON-ready). The fields, in the order of Section 6.3:

| Field | Meaning |
|---|---|
| `request_id`, `mode` | Given or made here (letters, digits, `-` and `_`, at most 64); `email` or `thread` |
| `score`, `verdict`, `action` | 0 to 100; `Low risk`, `Suspicious` or `High risk`; one fixed text per band plus one sentence keyed on the strongest finding |
| `org_domain`, `versions` | The organisation domain as used (or `null`); the versions of the score, the rules, the thread rules and the claim patterns that made the report |
| `text_read`, `signature_read` | The redacted text the classifier and the claim extractor read. Every claim span and every highlight offset points into it. Display-safe: see Security |
| `tactics` | The seven tactics: `name`, `probability`, `threshold`, `fired`, `scored` (counts in the score) and `highlights` (`start`, `end`, `text`, `weight`, `word`) for a tactic that fired |
| `explained` | `true` when LIME ran (`explain=True` and at least one tactic fired) |
| `claims`, `routing` | The typed claims with their spans, and for each claim the verifier(s) it was sent to |
| `ledger` | The rows, exactly as the verifiers return them, including the ones marked not checkable |
| `score_detail` | The strongest row of each claim and what it counted, the multiplier, the tactic points, whether the cap applied |
| `coverage` | Claims found, checked, contradicted, consistent, not checkable; the checks that could not run and why; one plain sentence |
| `header_findings` | The cleaned header evidence the header verifier read (domains, SPF, DKIM and DMARC verdicts, authentication state, freemail, look-alike score). Evidence, not rows; no addresses |
| `thread` | `null` for one email. For a thread: `judged_index`, `flip_index` (the first message with a medium or high contradiction), the signals that fired for the judged message and a timeline of every message |

### Input

- One email as text or bytes, **with or without headers**. A pasted body (no header block) is analysed as a body: the tactics and claims are found, but every check that compares a claim with the sender is **not checkable**, and the coverage says so (`headers_missing`). The first line decides: a header line (`From:`, `Received:`, `X-Mailer:` and so on) or an mbox `From user@host date` line means headers.
- A thread is a list of messages in any order; they are sorted by their `Date` header when every message has one, otherwise taken as given. At most 50 messages (the last 50). The newest is judged. A thread of one message is analysed as a single email.
- `org_domain` is optional. When it is missing the To header's domain is used, with the Phase 3 exceptions (collector mailboxes, placeholder domains, free-mailbox recipients). A value that is not a usable domain, or is a free mailbox provider, is ignored and the coverage says so.

## The score (version 0.2; Phase 10 freezes the numbers)

1. Only contradictions add points. A consistent row adds nothing and takes nothing away; a row that is not checkable adds nothing.
2. Points come from the **severity** of the row: high 60, medium 35, low 5, times the rule's reliability factor (1, 0.5 or 0; `reliability.json`).
3. Rows are grouped by claim (claim id and type; each thread signal is its own group) and only the strongest row of a group counts.
4. The groups are sorted by points and the k-th counts half as much as the one before: 60 + 30 + 15 and so on.
5. If urgency or secrecy fired, that sum is multiplied by 1 plus 0.25 for each.
6. Authority, urgency, scarcity and secrecy that fired add 4 points each (at most 12). Reciprocity, social proof and liking are shown but not scored.
7. Rounded and capped at 100. Bands: 0 to 34 Low risk, 35 to 69 Suspicious, 70 to 100 High risk.

Worked values (the self-test checks them): a lone medium 35, a lone high 60, a lone high with urgency 75 (79 with its 4 tactic points), two highs 90, twelve lows 10. "Low risk" means that no contradiction was found among the claims that could be checked. It never means the email is safe; read `coverage`.

In JavaScript terms the router is an Express route table (claim type to handler), the ledger is the log of what every handler said, and the score is a pure function of that log.

## Calibration (`build.py`)

There are no contradiction labels, so the score has no precision or recall here. What is calibrated is the **false-alarm side**, with a budget declared in `build.py` before the validation emails were read: per source of legitimate mail (**ham**) and per source of real unmodified thread messages, with at least 20 emails that had a checked claim, **High risk at most 1%** and **Suspicious or above at most 5%**. The budget is a policy choice, not something the data decide.

**Spam is not budgeted.** Spam is not legitimate mail, so flagging it is not a false alarm; it is listed in `score_budget.csv` (kind `email_spam`) and in `score_distribution.csv` for information, and it does not count towards the reliability of a rule. The first version of this file counted ham and spam together as "ordinary" mail; the first validation run showed the cost (spam asking for payments from free mailboxes pushed `rv_freemail`, the core business-email-compromise rule, down to half weight, and one spam email decided a budget verdict), so the definition was corrected. That correction was made after the validation emails had been read, so the validation figures are a check, not an independent test; the test split (Phase 13) is the clean measurement. `ORDINARY` in `build.py` is the one line that holds the definition.

**A miss is a finding, not a failure.** A group over the budget is marked `OVER` with a note saying whether its 95% interval still includes the budget. If no grid point meets the budget the initial numbers are kept and the run says so (`settle` in `build.py`).

- **Reliability** per rule, from every train email: a rule that fires on more than 5% of the checked ordinary mail of a source (or of real thread messages), with 20 or more hits, counts half; above 10% it counts nothing. 5% is the Suspicious budget: such a rule would breach it on its own. `--weights-only --write-reliability` computes it (no classifier needed) and writes `reliability.json`; the final run checks that the file equals the factors computed from every train email, so a stale file fails the run. The end-to-end self-test also guards the shipped file: a payment request from a free mailbox must still reach Suspicious under it.
- **The grid** (`score_grid.csv`): high points 50, 60, 70; medium 25, 35, 45; pressure step 0.15, 0.25, 0.35. A point is allowed only if the meaning of Section 6.6 holds (a lone high is Suspicious but not High risk, a lone medium is Suspicious, a lone high with one pressure tactic is High risk). Among the allowed points that also meet the budget on validation the one **closest to the initial numbers** is chosen. If none qualifies the initial numbers are kept and the run reports the finding.
- **Not fitted:** the attack corpora, the hijack benchmark and the labelled tactics. They are reported against the chosen numbers (`score_distribution.csv`, `score_benchmark_check.csv`) and never used to choose one. The benchmark cases are built to trigger the rules, so fitting on them would be circular; attacks and legitimate mail come from different corpora with different header evidence, so their rates are per source and describe, they do not measure recall.
- **Discipline:** `--train-only` never loads a validation email; `--calibrate` and the final run read validation (the calibration is the use of validation for this score version); the test split is never read here (Phase 13). A change to any number is a new `SCORE_VERSION` with a line in `SCORE_LOG`.
- **Parity:** `--parity N` runs the real `analyze()` on N validation emails rebuilt from `staged.parquet` and compares band and score with the batch code, so the number calibrated is the number the product computes. One known difference: the batch code does not run the single-email thread rule (`tv_single_no_reply_ids`, low severity, 5 points) because Phase 2 threw away the quoted text it needs. The check separates the differences that rule explains (analyze() has it as its only extra contradiction) from any others, and fails only on others.

## Results files

| File | Content |
|---|---|
| `results/score_rule_weights.csv` | Per rule and source: denominator, hits, rate, whether it was judged, the proposed and the current reliability |
| `results/score_grid.csv` | Every grid point: meaning, budget, worst source, distance from the initial numbers, the chosen one |
| `results/score_config.csv` | The frozen numbers and the budgets |
| `results/score_distribution.csv` | Emails per band for all, per category, per source and per source and category, overall and among emails with a checked claim |
| `results/score_budget.csv` | The false-alarm budget per source of legitimate mail and per source of real thread messages (spam listed, not budgeted), with Wilson intervals, an `OVER` note and the rules behind each Suspicious or High risk verdict (`top_rules`) |
| `results/score_benchmark_check.csv` | The hijack benchmark scored with the frozen numbers, with and without the thread verifier (cells under 10 cases are counts only) |
| `results/score_checks.csv` | PASS/FAIL checks, versions and run details |

Tactic probabilities are cached in `data/processed/tactic_probs/` (never committed). The classifier reads 69,542 train and 14,879 validation emails at about 20 a second on the Mac's CPU the first time; the final run needs only the validation ones (the train rows give the rule weights from the verifier rows alone).

## Security

- **Sizes:** 300,000 bytes per message, 50 messages per thread, 2,000 characters of body and 1,000 of signature read. The API enforces its own limits first.
- **Nothing runs in a browser.** `text_read`, `signature_read`, claim texts and highlight texts are display-safe: `<` and `>` are shown as the look-alike characters U+2039 and U+203A, backticks as apostrophes and control or invisible characters as spaces, one for one, so every offset still fits. Other strings from an email (display name, subject, claimed organisation) go through `clean_text` or `clean_domain`; reasons are built from validated values; action texts are fixed. `check_report` verifies all of it, and that no string of the report holds `<`, `>` or a backtick, on every report before it is returned.
- **The report must equal its own ledger.** `check_report` recomputes the score from the ledger and the tactics and the coverage from the claims and rows; a mismatch raises `ReportError`, which the API answers with a server error.
- **Nothing is stored or logged here.** The API logs the request id, score and band, never content.
- **Header-less input is not an error** and not a free pass: the coverage says what could not be checked.

## Known limits

- A calm, well-copied hijack (a hijacker with mailbox access who copies IDs, sending details and wording) cannot be caught by any rule here; only the content signals can see the change.
- A pasted body with no headers can only be scored on tactics, which add at most 12 points: a classic BEC body without headers is "Low risk" with a coverage note saying that nothing could be checked. That is by design (missing evidence is never a contradiction) and it is the case the UI must explain.
- The tactics come from a classifier trained on LLM labels (urgency precision on real validation emails is 0.50), the claims from a rule-based extractor scored against the same labels, and the injected hijack cases are synthetic. See master document Sections 8.14, 8.15 and 8.17.
