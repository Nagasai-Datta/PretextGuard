# PretextGuard: context for a new chat

Version: 2 October 2026, written at the end of Phase 0, to go with master document v3.2.

**How to use this file.** Paste this whole file (or attach it) as the first message of any new chat:
claude.ai, Claude Code on the web, or another assistant. Also give the chat the master document,
`docs/master_document.md` (Markdown copy) or `docs/PretextGuard_Master_Document_v3.2.docx`.
The chat has no memory of earlier conversations; these two files are everything it knows.

---

## 1. Instructions to the assistant

You are continuing an existing project. Read this file fully, then the master document sections
you need. **If this file and the master document disagree, the master document wins**; point out
any conflict you notice.

### 1.1 Who you are working with

- **Nagasai** (Marupaka Naga Sai Dattu), final-year B.Tech CSE, VIT Vellore. This is his individual
  project for course BCSE410L Cyber Security, problem statement 37.
- He knows the MERN stack (plain JavaScript, not TypeScript) and basic ML/NLP. Assume nothing else:
  explain Python tooling, pandas, PyTorch, DistilBERT, Colab, FastAPI and similar from scratch, with
  Node/MERN comparisons where they help.
- He must explain every line at the viva: **minus 20 marks if he cannot explain his own code**,
  **minus 30 for code copied from GitHub repositories**, **minus 20 for fake results**.

### 1.2 Working agreement (follow exactly)

1. **Plan first.** Before each phase, give a short plan plus the background concepts he needs, then
   **stop and wait for his go-ahead**. Never jump straight into producing files.
2. **After "go":** every file in full, then a function-by-function plain-language explanation, then
   the exact commands to run with what the output should look like.
3. **You write all code.** Well-known libraries are fine; write the project logic fresh. Never copy
   code from GitHub repositories, and never open or adapt other students' PretextGuard-like projects.
4. **You never run Git.** No commit, push, branch or remote commands, even if you have tools that
   could. Nagasai commits and pushes. Suggest a short commit message after each working step.
5. **No unit tests per phase.** Each phase is verified by running its scripts and checking their
   printed output. `tests/test_environment.py` is the one setup check; keep it passing.
6. **End of every phase:** list exactly what changed in the master document (section number, old
   text, new text) and give a paste block that applies the edits to `docs/master_document.md`
   (see 1.4). Bump its version (3.3, 3.4, ...) and add a row to the decisions log (Section 14).
7. **When a design choice also improves security, say so explicitly** (security is 15 marks).
8. **Style:** direct and honest; recommendations rather than open questions; no em dashes; no filler
   words such as "showcase", "testament", "underscore", "passionate about". Keep answers no longer than
   they need to be. Documents for him are .docx or PDF, never HTML (repo READMEs are Markdown).
9. **If you are unsure or a fact may have changed** (URLs, library versions, dataset layouts), verify
   with your tools if you have them; otherwise give him a quick check command first (for example
   `curl -sI <url> | head -5`) and wait for the output. Never guess a URL into code.

### 1.3 How files reach his Mac

The project lives at `~/Desktop/pretextguard`. Pick the mode your interface supports:

**Mode A (you can attach downloadable files, for example claude.ai chat).** Files download to
`~/Downloads`. End every delivery with **one block of `mv` commands** that moves each file to its exact
place, for example:

```bash
mv ~/Downloads/download.py ~/Desktop/pretextguard/src/data/download.py
```

Never deliver two downloadable files with the same name in one batch (for example two `README.md`
or `__init__.py`); give same-named or tiny files as paste blocks instead. Dotfiles and small config
files are always paste blocks.

**Mode B (you cannot attach files, for example Claude Code on the web).** Deliver every file as a
**paste block** that creates it in place:

```bash
cd ~/Desktop/pretextguard
setopt NO_BANG_HIST
mkdir -p src/data
cat > src/data/paths.py << 'PG_EOF'
...full file contents...
PG_EOF
```

`setopt NO_BANG_HIST` stops zsh from treating `!` in pasted code as a history command; the quoted
`'PG_EOF'` marker stops the shell expanding `$` or backticks inside the file. One file per block,
so a long paste that breaks only affects one file.

In both modes, every command assumes:

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
```

### 1.4 Updating the master document

`docs/master_document.md` is the living master from v3.2 on (the styled
`PretextGuard_Master_Document_v3.2.docx` is a snapshot). Give edits as exact replacements applied by a
paste block that runs a small Python script, and make the script fail loudly if any old text is not
found exactly once. A fresh .docx can be exported when Nagasai wants one:
`pandoc docs/master_document.md -o docs/PretextGuard_Master_Document.docx` (needs `brew install pandoc`).

### 1.5 Your first reply in a new chat

1. Five lines confirming what the project is and where it stands.
2. Any conflict or gap you notice between this file and the master document.
3. The plan and background concepts for the next task (Section 5), then stop and wait for "go".

---

## 2. The project in ten lines

1. **Problem:** pretexting emails (Business Email Compromise and similar) carry no link or attachment,
   so payload-based scanners miss them; the attack is the story ("this is David from Finance, wire
   this before 3 PM, don't tell anyone").
2. **Idea:** never trust what an email says about itself. Extract its claims and check each one
   against evidence it cannot easily fake: its own headers and its own conversation history. A
   contradicted claim is the detection, and the contradiction is the explanation.
3. **Key fact:** SPF, DKIM and DMARC prove which domain sent an email, not who the person is. A real
   Gmail account passes all three while claiming to be Acme's Finance Director.
4. **N3 (core):** claim-evidence contradiction engine; affiliation, identity and authority claims
   checked against header evidence, with the header check conditioned on the claim.
5. **N2:** thread consistency verification; a message checked against its own thread (tactic onset,
   request drift, sending-path drift, thread integrity) to catch hijacked accounts; finds the flip point.
6. **N1:** payload-free evaluation protocol; URLs, domains and file names redacted before any model
   sees the body; an ablation measures how much prior accuracy was link-reading.
7. **Architecture contribution:** claim-routed verification; typed claims routed to the verifier that
   can check them; a verdict ledger of claim, evidence, contradiction and reason.
8. **Plain components:** DistilBERT 7-tactic classifier, keyword baseline, 0-100 risk score, LIME
   highlights, optional SemEval pretraining.
9. **Product:** web app (FastAPI + React + Vite + Tailwind, no database): paste an email, upload a
   .eml or a thread, optionally give the organisation domain; get a score, highlighted phrases, a
   findings table and plain-English reasons. Email content is never stored.
10. **Proof:** one ablation per novelty claim in Phase 13; every number comes from a script and is
    saved in `results/`.

Novelty was locked on 21 Sep 2026. Section 4.7 of the master document lists dead ideas; never
propose them again as novelty. Stack choices are never novelty (faculty rule).

---

## 3. Environment (facts, do not re-derive)

| Item | Value |
|---|---|
| Machine | MacBook Air, Apple Silicon, macOS, zsh, VS Code |
| Project folder | `~/Desktop/pretextguard` (iCloud Desktop sync is off) |
| Python | 3.12.14 from Homebrew (`python@3.12`), venv at `./venv` |
| Other Pythons on the Mac | Homebrew 3.14 (the default `python3`), python.org 3.11 at `/usr/local/bin`, Apple 3.9. Never use them for the project |
| Shell quirk | `python` is aliased to `python3`; harmless inside the venv. Check with `python -c "import sys; print(sys.executable)"` (must end in `/pretextguard/venv/bin/python3`) |
| Install packages with | `python -m pip install ...`, then pin with `==` in `requirements.txt` |
| Tools installed | Homebrew, Git, GitHub CLI (`gh`), VS Code with the Python extension |
| Repository | github.com/Nagasai-Datta/PretextGuard, public by Nagasai's choice, branch `main` |
| Colab | Python 3.12; pin torch and transformers to the same versions locally and on Colab |
| Rule | Always work from the project root, never from `src/` |

---

## 4. Current state of the repository (end of Phase 0)

```
pretextguard/
  .vscode/settings.json      VS Code uses venv/bin/python; pytest enabled
  .gitignore  .env (local)  .env.example  pytest.ini  requirements.txt  README.md (Phase 0 version)
  venv/                      Python 3.12.14 (ignored)
  data/raw/  data/processed/ (ignored)  data/labelled/.gitkeep  data/threads/.gitkeep
  artifacts/ (ignored)  results/.gitkeep  notebooks/.gitkeep  frontend/.gitkeep
  docs/                      master document v3.2 (.docx and .md), figures/, this file
  src/__init__.py and src/{data,preprocess,headers,thread,models,claims,verifiers,router,
       explain,baseline,eval,api}/__init__.py   (all empty)
  tests/test_environment.py  16 checks: Python 3.12, inside ./venv, every src package imports,
                             ".env" is a line in .gitignore, .env.example exists
```

Exact contents of the small config files:

`.gitignore`
```
# Python
venv/
__pycache__/
*.pyc
.pytest_cache/

# Secrets
.env

# Data and model weights (large or separately licensed)
data/raw/
data/processed/
artifacts/
*.pt
*.bin
*.safetensors

# Notebooks
.ipynb_checkpoints/

# Frontend (Phase 12)
node_modules/
frontend/dist/

# macOS
.DS_Store
```

`.env.example`
```
# Copy this file to .env and put real values there. Never commit .env.
# Key the analysis endpoint will require from Phase 11 onwards.
PRETEXTGUARD_API_KEY=change-me
```

`pytest.ini`
```
[pytest]
testpaths = tests
pythonpath = .
addopts = -q
```

`requirements.txt`
```
# PretextGuard dependencies. Exact versions (==) so every machine installs the same thing.
# Grows phase by phase; each library is added in the phase that first uses it.

# Phase 0: setup check and dependency security audit
pip_audit==2.10.1
pytest==9.1.1
```

Phase 0 checks passed: `pytest` gives 16 passed; `pip-audit` reports no known vulnerabilities.

---

## 5. Next task: Phase 1, data acquisition (plan already approved)

Full detail: master document Sections 8.1, 8.6 to 8.9 and 12.2. Summary:

**Goal.** Download every source, load them all into one staging table with the same columns,
produce the header coverage table and the train/validation/test split, and write the READMEs.
No cleaning or modelling yet.

**Sources**

| Source | How it is obtained | What it gives |
|---|---|---|
| Kaggle "Phish No More" (7 CSVs, about 82,500 emails) | Nagasai downloads the zip in the browser (free Kaggle account) | Body-level ham, spam, phishing and fraud |
| SpamAssassin public corpus | Script downloads the archives | Full raw headers, ham and spam (2002 to 2005) |
| Nazario phishing corpus | Script downloads the yearly mbox files | Real phishing with full headers |
| phishing_pot (GitHub, data only) | Shallow `git clone` of the data into `data/raw/phishing_pot/` | Modern phishing with real authentication headers; recipients anonymised |
| Enron raw (CMU) | Script downloads about 0.4 GB, about 1.5 GB unpacked | Header check now; threads in Phase 9 |
| Apache mailing lists | Script downloads 12 months of 2 user-support lists as mbox | Modern benign mail and real threads with full headers |

**Scripts** (all in `src/data/`, run as `python -m src.data.<name>` from the project root)

| File | Job |
|---|---|
| `paths.py` | Every folder path in one place |
| `download.py` | Fetch each source; skip files already present; resume broken downloads; print sizes |
| `loaders.py` | One function per source format (CSV, mbox, .eml, Enron maildir) returning the same record: source, category, raw header text, body text, pointer back to the original file |
| `stage.py` | Run all loaders, remove duplicates, write `data/processed/staged.parquet`, print counts per source and category |
| `coverage.py` | Count which headers each source carries; write `results/header_coverage.csv` (answers the Enron thread-header question) |
| `split.py` | 70/15/15 train/validation/test split, stratified by source and category, fixed seed |

**Decisions already made**
- `category` is ham, spam, phishing or fraud; `is_attack` is true only for phishing and fraud.
- Deduplicate across sources by hashing normalised body text before splitting; keep the copy with
  full headers when duplicates exist.
- Kaggle rows get a minimal header block built from sender, receiver, date and subject;
  `has_full_headers` is false for them.
- Raw Enron is not added to the single-email table (the Kaggle merge already has Enron bodies).
- Apache: pick two user-support lists, after checking they are mostly human threads (developer lists
  are flooded with bot notifications).
- Phase 1 columns: `id, source, category, is_attack, has_full_headers, raw_ref, raw_headers, body_raw, split`.
- Storage is Parquet; `data/raw/` is read-only forever; nothing in `data/raw` or `data/processed` is committed.
- New libraries: pandas, pyarrow, requests, tqdm (install, then pin exact versions).
- About 1 GB downloaded, about 3 GB used after unpacking.

**Verify before writing download code:** current URLs and file names for Nazario, SpamAssassin, Enron
(CMU), the Apache archive (lists.apache.org mbox export) and the chosen lists; the phishing_pot licence
and folder layout; the exact Kaggle file names.

**READMEs (part of Phase 1)**
- **Root `README.md`** (replaces the Phase 0 one): the complete end-to-end idea for a beginner:
  - the problem
  - email and authentication basics
  - the idea and the four contributions
  - architecture and the run-time pipeline
  - build time vs run time
  - the data and where it lives
  - ablations
  - tech stack, security design and project structure
  - phases and status
  - setup and how to run
- **One README each for** `src/`, `data/`, `results/`, `notebooks/`, `docs/` and `artifacts/`:
  - `src/`: the package map, the `python -m` rule, and which phase builds what.
  - `data/`: every source with its origin and licence note, every storage stage, what is committed, and how to rebuild.
  - `results/`: what goes there, and the rule that every number comes from a script.
  - `notebooks/`: the Colab workflow and version pinning.
  - `docs/`: what each document is, and how to export the .docx.
  - `artifacts/`: what is stored, why it is not committed, and how to rebuild it.
- **`.gitignore` change:** `artifacts/` becomes `artifacts/*` plus `!artifacts/README.md`, so that README
  is committed. Keep the exact `.env` line (the environment check reads it).
- **Package READMEs:** each `src/` package gets its own README in the phase that builds it. The
  `frontend/` README comes in Phase 12.

**Order of work:** background concepts and plan → (go) → `paths.py` and `download.py` → Nagasai runs
downloads → `loaders.py` and `stage.py` → `coverage.py` and `split.py` → READMEs → change list for the
master document. Commit after each working step.

**Background to teach in Phase 1:**
- .eml, mbox and maildir formats.
- Python's `email` package and MIME multipart.
- pandas DataFrames and Parquet.
- Hashing for deduplication, and why train-test leakage fakes good results.
- Stratified splits and fixed seeds.
- What the header coverage table tells us.

---

## 6. The rest of the build (details in the master document, Section 12)

| Phase | Deliverable |
|---|---|
| 2 | Cleaning and N1 redaction (`src/preprocess`) |
| 3 | Email parser and header evidence extractor; organisation domain (`src/headers`) |
| 4 | Keyword baseline (`src/baseline`) |
| 5 | Tactic and claim labels via free web chats (Gemini and DeepSeek, z.ai breaks ties; Cohen's kappa); SemEval mapping; synthetic emails into `data/synthetic/` |
| 6 | DistilBERT tactic classifier on Colab; weights to `artifacts/` (`src/models`, `notebooks/`) |
| 7 | Claim extractor (`src/claims`) |
| 8 | Header verifier N3 and request verifier (`src/verifiers`) |
| 9 | Thread builder, hijack benchmark, thread verifier N2 (`src/thread`, `src/verifiers`, `src/data`) |
| 10 | Router, ledger, risk score, LIME (`src/router`, `src/explain`) |
| 11 | FastAPI backend with all security controls (`src/api`) |
| 12 | React frontend: analyzer and dashboard (`frontend/`) |
| 13 | All experiments and charts (`src/eval`, `results/`) |
| 14 | Report, viva preparation, Review deck update (`docs/`) |

No paid APIs anywhere (annotation and synthetic data use free web chats); no LLM at run time.
