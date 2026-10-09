# PretextGuard

Payload-free pretexting detection through claim verification.

BCSE410L Cyber Security, VIT Vellore. Problem statement 37: Pretexting Pattern Classifier from Email Metadata. Individual project by Marupaka Naga Sai Dattu.

PretextGuard reads what an email claims about itself (who is writing, which organisation they represent, what they want) and checks each claim against evidence the email cannot easily fake: its own headers and its own conversation history. A claim that the evidence contradicts is the detection, and the contradiction is the explanation.

The full design, every decision and its reason live in the master document, [`docs/master_document.md`](docs/master_document.md). This README is the end-to-end overview.

## 1. The problem

Pretexting is social engineering built on a made-up identity or story. Business Email Compromise (BEC) is pretexting aimed at company money: "this is David from Finance, wire this before 3 PM, don't tell anyone". The victim does the damage personally.

Most email security looks for a **payload**: a malicious link or attachment. A pretexting email usually has neither, so link scanners, sandboxes and attachment checks find nothing. The whole attack is the story.

Running example used throughout the project:

```
From: "David Chen - Finance Director" <d.chen.finance@gmail.com>
Reply-To: finance.dept.acme@protonmail.com
Date: Tue, 14 Jul 2026 02:47 AM
Authentication-Results: spf=pass dkim=pass dmarc=pass (all for gmail.com)

Hi Priya, this is David from Finance. I need you to process a wire
transfer before 3 PM today. I'm in meetings all day and can't take
calls. Please don't loop in anyone else - just get it done.
```

Priya works at acmecorp.com. No link, no attachment, no typo, and every authentication check passes.

## 2. Email and authentication basics

An email is a plain text file: **headers** (who sent it, to whom, how it travelled), a blank line, then the **body**. The From line has a display name, which anyone can type freely, and an address.

| Header | What it is |
|---|---|
| From | Display name and address shown to the reader |
| Reply-To | Where replies actually go, if different from From |
| Return-Path | Where bounces go; the envelope sender |
| Received | One line added by every mail server on the way |
| Authentication-Results | The receiving server's SPF, DKIM and DMARC verdicts |
| Message-ID | Unique ID of this email |
| In-Reply-To, References | IDs of the earlier emails in the same conversation |

- **SPF:** the domain lists the servers allowed to send for it.
- **DKIM:** the sending server signs the message; a valid signature proves the domain signed it and nobody changed it.
- **DMARC:** passes when SPF or DKIM passed for the domain shown in From.

**The key fact:** these checks prove which *domain* sent a message, not who the *person* is. A real Gmail account passes all three while claiming to be Acme's Finance Director. Authentication passed, for the wrong domain.

## 3. The idea

Never trust what an email says about itself. Extract its claims and route each one to the evidence that can confirm or contradict it:

| Claim in the body | Evidence checked | Contradiction when |
|---|---|---|
| "This is David from Finance" (internal affiliation) | Authenticated From domain vs the organisation's domain | Claims to be internal, authenticates as gmail.com |
| "PayPal Security Team" (external affiliation) | Claimed organisation vs sending domain | The domain does not belong to that organisation |
| "As CFO I need this today" (authority) | Display name vs address, lookalike domains | Rank claimed from a freemail or lookalike sender |
| "Reply to me directly" | Reply-To vs From | Replies go to a different domain |
| "As we discussed on the call" (prior relationship) | The email's own thread | No such conversation exists |
| "Use this new account" (payment change) | Earlier messages in the thread | The bank details changed mid-thread |

Urgency, secrecy and similar tactics cannot be proven true or false by headers, so they act as modifiers: they raise the weight of any contradiction found next to them.

## 4. The four contributions

| ID | Name | In one line | Proof |
|---|---|---|---|
| N1 | Payload-free evaluation protocol | URLs, domains and file names are redacted before any model sees the body, so the model must read manipulation, not links | Models trained on raw vs redacted bodies, tested on raw, redacted and naturally link-free emails |
| N2 | Thread consistency verification | A message is checked against its own thread (tactic onset, request drift, sending-path drift, thread integrity) and the flip point is found | Detection with vs without the thread verifier on a thread-hijack benchmark |
| N3 (core) | Claim-evidence contradiction engine | Affiliation, identity and authority claims are checked against header evidence; the header check depends on the claim | Full system vs text-only vs headers-only vs parallel score fusion |
| Architecture | Claim-routed verification pipeline | Typed claims go to the verifier that can check them; the output is a ledger of claim, evidence, contradiction and reason | Same signals as a flat classifier vs claim-routed |

N3 catches the outside impersonator. N2 catches the attacker who does not need to impersonate, because they are already inside a real account.

## 5. Architecture and the run-time pipeline

![Claim-routed verification architecture](docs/figures/figure2_architecture.png)

One analysis request, step by step:

| Step | What happens | Code |
|---|---|---|
| 1. Receive | An email or a thread is pasted or uploaded, with an optional organisation domain | `frontend/`, `src/api/` |
| 2. Validate | API key, rate limit, size cap, type and structure checks | `src/api/` |
| 3. Parse | Headers, body and thread links; headers become an evidence dictionary | `src/headers/`, `src/thread/` |
| 4. Redact (N1) | Links, domains and file names become placeholders | `src/preprocess/` |
| 5. Extract claims | Tactic probabilities (DistilBERT) plus typed claims (patterns and name detection) | `src/models/`, `src/claims/` |
| 6. Route and verify | Each claim goes to the header verifier (N3), the thread verifier (N2) or the request verifier | `src/router/`, `src/verifiers/` |
| 7. Ledger and score | Contradictions add points; urgency and secrecy multiply them; 0-100 risk score | `src/router/` |
| 8. Report | Score, highlighted phrases (LIME), findings table and plain-English reasons; the email is then discarded | `src/api/`, `src/explain/`, `frontend/` |

For the David email the ledger says: claims to be internal Acme Finance, but authenticates only as gmail.com (high); Reply-To points to protonmail.com (medium); a payment request from an external freemail sender (high). Result: high risk, with the advice to call David on a number from the company directory.

## 6. Build time and run time

![Build time versus run time](docs/figures/figure5_build_vs_run.png)

- **Build time** happens once, on the Mac and on Google Colab: collect and clean the data, label tactics and claims, train the tactic classifier, run the experiments.
- **Run time** is the web app. It analyses one email at a time and stores nothing.
- The only thing that crosses from build time to run time is the trained model in `artifacts/`. The experiment numbers go into `results/` and the report.

## 7. The data and where it lives

Phase 1 gathered nine sources into one table of **99,324 unique emails** (20,313 attacks). Details, licences and rebuild steps: [`data/README.md`](data/README.md).

| Source | Emails kept | Role |
|---|---|---|
| Kaggle "Phish No More" (CEAS-08, Enron, Ling, Nigerian Fraud files) | 73,273 | Body-level ham, spam and fraud; no original headers |
| Nazario phishing corpus (raw mbox) | 9,595 | Real phishing with full headers |
| phishing_pot (honeypot .eml files) | 7,491 | Modern phishing with real authentication headers |
| SpamAssassin public corpus (raw) | 5,775 | Ham and spam with full headers (2002 to 2005) |
| Apache user lists: tomcat and kafka (24 months) | 3,190 | Modern legitimate mail and real threads with full headers |
| Raw Enron (CMU maildir, 517,401 messages) | not in the table | Header check now; real threads in Phase 9 |

- `data/raw/`: downloads, never modified (not committed).
- `data/processed/staged.parquet`: the one table, with a fixed 70/15/15 train/validation/test split (not committed).
- `data/processed/cleaned.parquet` (Phase 2): the same rows plus clean and payload-free redacted bodies (not committed).
- `data/processed/headers.parquet` (Phase 3): header fields and evidence, one row per email, joined on `id` (not committed).
- `data/processed/tactic_data.parquet` (Phase 6): train and validation emails with their tactic labels, uploaded to Colab (not committed).
- `data/processed/claims_cache/` (Phase 8): the claims the Phase 7 extractor found per email, so later runs do not repeat its 20 minutes (not committed).
- `results/`: every count and score, written by scripts (committed).

## 8. Proof: one ablation per claim

An ablation removes one part and measures again; the drop is what that part contributed. Phase 13 runs one per contribution (N1, N2, N3 and the architecture), plus the tactic classifier against a keyword baseline, claim-extraction accuracy, a paraphrase robustness test and a style-confound test. Every number comes from a script in `src/eval/` and is saved in `results/`.

## 9. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 in a venv |
| Data | pandas, pyarrow (Parquet), requests, tqdm |
| Cleaning | BeautifulSoup (HTML to text) |
| Email parsing | Python `email` and `mailbox` (standard library); tldextract (public suffix list, offline) and rapidfuzz (lookalike domains) |
| Model | DistilBERT (Hugging Face Transformers, PyTorch), trained on Colab, run on CPU; weights stored as safetensors |
| NLP extras | spaCy for names and organisations |
| Explanations | LIME |
| Backend | FastAPI, Pydantic, slowapi |
| Frontend | React, Vite, Tailwind |
| Database | None, deliberately: email content is never stored |
| Checks | pytest (one environment check), pip-audit |

No paid APIs and no LLM at run time.

## 10. Security design

| Control | How |
|---|---|
| No persistence | Email content lives in memory for one request; never logged or written to disk |
| Input validation | Size caps, type and structure checks, Pydantic schemas |
| Safe parsing | Attachments are never opened or run; limits on MIME depth and thread length |
| Output encoding | Email text is rendered as text, never as HTML (XSS) |
| PII redaction | Addresses, phone and account numbers removed before any logging |
| Rate limiting and API key | slowapi limits; key on the analysis endpoint |
| Audit logging | Time, request ID and score only, never content |
| Dependency hygiene | Pinned requirements; pip-audit clean |
| Secrets | `.env` is never committed; `.env.example` lists the variable names only |
| Safe data handling (build time) | Archives unpacked with path-traversal and size checks; file types checked by their first bytes; raw data read-only; rebuilt headers squashed onto one line (header injection) |
| ReDoS-safe processing | Cleaning, redaction and header parsing run on attacker-written text, so every pattern has bounded repeats and every input is capped |
| Trusted authentication results | Only Authentication-Results headers added by the receiving organisation are read; fake ones written by the sender are ignored |

## 11. Project structure

```
pretextguard/
  README.md          this file
  src/               all code, one package per module (see src/README.md)
  data/              datasets; raw/ and processed/ are not committed (see data/README.md)
  results/           every number and chart, written by scripts (committed)
  artifacts/         trained model weights (not committed; README only)
  notebooks/         Colab training notebooks
  frontend/          React + Vite + Tailwind app (Phase 12)
  docs/              master document, context file, figures, report and slides
  tests/             test_environment.py: the setup check
  requirements.txt   exact library versions
  .env.example       names of the secrets the app needs
```

## 12. Phases and status

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Environment, repository, environment check, pip-audit | Done |
| 1 | Data acquisition: staged table, header coverage table, split, READMEs | Done |
| 2 | Cleaning and payload-free redaction (N1) | Done |
| 3 | Email parser and header evidence extractor | Done |
| 4 | Keyword baseline | Done |
| 5 | Tactic and claim labels (free web-chat annotators, Cohen's kappa), synthetic emails | Done |
| 6 | DistilBERT tactic classifier on Colab | Done |
| 7 | Claim extractor | Done |
| 8 | Header verifier (N3) and request verifier | In progress |
| 9 | Thread builder, thread-hijack benchmark, thread verifier (N2) | Not started |
| 10 | Claim router, verdict ledger, risk score, LIME | Not started |
| 11 | FastAPI backend with all security controls | Not started |
| 12 | React frontend | Not started |
| 13 | All experiments and charts | Not started |
| 14 | Report, viva preparation, slides | Not started |

## 13. Setup and how to run

Needs macOS (or Linux), Python 3.12 and Git.

```bash
git clone https://github.com/Nagasai-Datta/PretextGuard.git pretextguard
cd pretextguard
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env    # then put real values in .env
```

Checks:

```bash
pytest       # the environment check: 16 passed
pip-audit    # known vulnerabilities in installed packages
```

Every script runs from the project root as a module, for example `python -m src.data.stage`, never from inside `src/`.

Rebuild the Phase 1 data (downloads first, as listed in [`data/README.md`](data/README.md)):

```bash
python -m src.data.fetch_apache   # Apache list archives, 48 monthly files
python -m src.data.unpack         # check every download and unpack the archives safely
python -m src.data.stage          # one table, duplicates removed -> data/processed/staged.parquet
python -m src.data.coverage       # which sources carry which headers -> results/header_coverage.csv
python -m src.data.split          # fixed 70/15/15 split -> split column + results/split_counts.csv
```

Then the Phase 2 and 3 tables, and the Phase 4 baseline (self-test, then train-split hit rates):

```bash
python -m src.preprocess.build    # clean and redacted bodies -> data/processed/cleaned.parquet
python -m src.headers.build       # header fields and evidence -> data/processed/headers.parquet
python -m src.baseline.keywords   # keyword baseline self-test
python -m src.baseline.build      # hit rates and sanity checks -> results/keyword_*.csv
```

Phase 5 (labels) starts with `python -m src.data.batches` and continues as a copy-and-paste loop with two chat services; see `data/labelled/README.md` and `data/synthetic/README.md`.

Phase 6 (tactic classifier): build the file for Colab, train on Colab with `notebooks/phase6_tactic_classifier.ipynb`, then validate on the Mac. The exact steps are in `notebooks/README.md`.

```bash
python -m src.eval.metrics        # metrics self-test (hand-written functions against scikit-learn)
python -m src.models.dataset      # train and validation emails with their labels -> data/processed/tactic_data.parquet (upload to Drive)
python -m src.models.validate     # after Colab: scores and PASS/FAIL checks -> results/tactic_validation_scores.csv, tactic_checks.csv
```

Phase 7 (claim extractor): `requirements.txt` installs spaCy and its English model (pinned by URL and SHA-256). Details in [`src/claims/README.md`](src/claims/README.md).

```bash
python -m src.claims.extractor            # self-test: hand-made emails and crafted inputs
python -m src.claims.build --train-only   # train-split hit rates and train scores (validation never loaded) -> results/claim_*.csv
python -m src.claims.build                # final run of a frozen pattern version: also scores the validation emails, once
```

Phase 8 (header verifier N3 and request verifier): no new library. Details in [`src/verifiers/README.md`](src/verifiers/README.md).

```bash
python -m src.verifiers.selftest          # hand-made emails with real header blocks and crafted input (no data needed)
python -m src.verifiers.build --train-only   # contradiction rates on the train split (validation never loaded) -> results/verifier_*.csv
python -m src.verifiers.build             # final run of a frozen rule version: also reads the validation emails, once
```

## Privacy

Submitted email content is processed in memory only. There is no database, and email content is never logged or written to disk. The research datasets are used locally and never redistributed in this repository.
