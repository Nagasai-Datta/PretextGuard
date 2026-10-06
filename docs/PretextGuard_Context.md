# PretextGuard: context for a new chat

Version: 6 October 2026, written at the end of Phase 1, to go with master document v3.3.

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
   the exact commands to run with what the output should look like. **Deliver every file as a
   downloadable file plus one `mv` block** (Mode A in 1.3), never as a paste block, whenever the
   interface can attach files; that includes Python files and the document-update script (Nagasai's
   preference, 6 Oct 2026). Short commands stay in the chat as normal command blocks.
   **Fold each phase into two or three steps:** each step delivers several files at once, then one
   run, one check and one commit. Phase 1's five steps were too long.
3. **You write all code.** Well-known libraries are fine; write the project logic fresh. Never copy
   code from GitHub repositories, and never open or adapt other students' PretextGuard-like projects.
4. **You never run Git.** No commit, push, branch or remote commands, even if you have tools that
   could. Nagasai commits and pushes. Suggest a short commit message after each working step.
5. **No unit tests per phase.** Each phase is verified by running its scripts and checking their
   printed output. `tests/test_environment.py` is the one setup check; keep it passing.
6. **End of every phase:** list exactly what changed in the master document (section number, old
   text, new text) and deliver a script file that applies the edits to `docs/master_document.md`
   (see 1.4). Bump its version (3.3, 3.4, ...) and add a row to the decisions log (Section 14).
7. **When a design choice also improves security, say so explicitly** (security is 15 marks).
8. **Style:** direct and honest; recommendations rather than open questions; no em dashes; no filler
   words such as "showcase", "testament", "underscore", "passionate about". Keep answers no longer than
   they need to be. Documents for him are .docx or PDF, never HTML (repo READMEs are Markdown).
9. **If you are unsure or a fact may have changed** (URLs, library versions, dataset layouts), verify
   with your tools if you have them; otherwise give him a quick check command first (for example
   `curl -sI <url> | head -5`) and wait for the output. Never guess a URL into code.

### 1.3 How files reach his Mac

The project lives at `~/Desktop/pretextguard`. Use Mode A whenever your interface can attach files
(Nagasai's preference); Mode B only when it cannot:

**Mode A (you can attach downloadable files, for example claude.ai chat or Claude Code on the web).** Files download to
`~/Downloads`. End every delivery with **one block of `mv` commands** that moves each file to its exact
place, for example:

```bash
mv ~/Downloads/download.py ~/Desktop/pretextguard/src/data/download.py
```

Never deliver two downloadable files with the same name in one batch: give them distinct download
names (for example `README_src.md`, `README_data.md`) and let the `mv` block rename them. Dotfiles get
a visible download name (for example `gitignore.txt`) and are renamed by `mv`, because macOS hides
files whose names start with a dot.

**Mode B (you cannot attach files).** Deliver every file as a
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

**Never put a file that contains ``` fences (most READMEs and other Markdown files) inside a ```
paste block:** the chat display ends the block at the first inner fence and the paste breaks (this
happened on 6 Oct 2026). Deliver such files as downloadable files with `mv` commands. Python files
without fences are fine as paste blocks.

In both modes, every command assumes:

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
```

**Claude Code on the web.** Its sandbox usually cannot reach the data hosts (Kaggle, monkey.org,
CMU, lists.apache.org), so test new scripts there on small hand-made samples before handing them
over; real numbers always come from Nagasai's runs. It can read the public GitHub repository, so
files Nagasai has pushed (for example `results/*.csv`) can be read there instead of asking him to
paste them. It can attach downloadable files (Mode A), which is the safe way to deliver long or
Markdown files. Large data downloads are done by Nagasai in the browser and moved into place with `mv`.

### 1.4 Updating the master document

`docs/master_document.md` is the living master from v3.2 on (the styled
`PretextGuard_Master_Document_v3.2.docx` is a snapshot). Give edits as exact replacements applied by a
small Python script delivered as a downloadable file (run it once from `~/Downloads`, then delete it), and make the script fail loudly if any old text is not
found exactly once. A fresh .docx can be exported when Nagasai wants one:
`pandoc docs/master_document.md --resource-path=docs -o docs/PretextGuard_Master_Document.docx` (needs `brew install pandoc`; `--resource-path=docs` lets pandoc find the figures).

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
| Phase 1 libraries | pandas 3.0.6, pyarrow 25.0.1, requests 2.34.2, tqdm 4.70.1 (pinned in `requirements.txt`) |
| Data on disk | `data/raw/` about 3 GB after unpacking, read-only (`chmod a-w`); `data/processed/staged.parquet` about 245 MB |
| Rule | Always work from the project root, never from `src/` |

---

## 4. Current state of the repository (end of Phase 1)

```
pretextguard/
  README.md                  end-to-end overview (Phase 1 version)
  CLAUDE.md                  points Claude Code at this file
  .vscode/settings.json      VS Code uses venv/bin/python; pytest enabled
  .gitignore  .env (local)  .env.example  pytest.ini  requirements.txt
  venv/                      Python 3.12.14 (ignored)
  data/README.md             every source, licence, stage and how to rebuild
  data/raw/                  downloads and unpacked archives, read-only (ignored)
  data/processed/            staged.parquet (ignored)
  data/labelled/.gitkeep  data/threads/.gitkeep
  artifacts/README.md        everything else in artifacts/ is ignored
  results/README.md  staged_counts.csv  dedup_pairs.csv  header_coverage.csv  split_counts.csv
  notebooks/README.md  frontend/.gitkeep
  docs/README.md  master_document.md (v3.3)  PretextGuard_Master_Document_v3.2.docx (snapshot)
  docs/PretextGuard_Context.md (this file)  docs/figures/ (5 PNGs)
  src/README.md
  src/data/                  README.md  paths.py  unpack.py  fetch_apache.py  loaders.py  stage.py
                             coverage.py  split.py
  src/{preprocess,headers,thread,models,claims,verifiers,router,explain,baseline,eval,api}/__init__.py
                             (all empty)
  tests/test_environment.py  16 checks (unchanged): Python 3.12, inside ./venv, every src package
                             imports, ".env" is a line in .gitignore, .env.example exists
```

`data/raw/` on Nagasai's Mac:

```
kaggle/phish_no_more.zip      + phish_no_more/ (7 CSVs; CEAS_08, Enron, Ling, Nigerian_Fraud are read)
spamassassin/<5 .tar.bz2>     + one unpacked folder per archive (easy_ham, easy_ham_2, hard_ham, spam, spam_2)
nazario/                      17 mbox files: phishing0-3.mbox, 20051114.mbox, private-phishing4.mbox,
                              phishing-2015.txt ... phishing-2025.txt
phishing_pot/phishing_pot-main.zip + phishing_pot-main/phishing_pot-main/email/*.eml (8,614 files)
enron/enron_mail_20150507.tar.gz   + enron_mail_20150507/maildir/ (517,401 files)
apache/tomcat_users/YYYY-MM.mbox, apache/kafka_users/YYYY-MM.mbox (Oct 2024 to Sep 2026)
```

The staged table, `data/processed/staged.parquet`: 99,324 unique emails, columns
`id, source, category, is_attack, has_full_headers, raw_ref, raw_headers, body_raw, split`.

| Source | Rows | Notes |
|---|---|---|
| kaggle_ceas08 | 38,077 | 17,253 ham, 20,824 spam; header block rebuilt from CSV columns |
| kaggle_enron | 29,119 | 15,420 ham, 13,699 spam; Subject only |
| kaggle_ling | 2,850 | 2,392 ham, 458 spam; Subject only |
| kaggle_nigerian_fraud | 3,227 | fraud |
| nazario | 9,595 | phishing, full headers |
| phishing_pot | 7,491 | phishing, full headers |
| spamassassin | 5,775 | 4,099 ham, 1,676 spam, full headers |
| apache_tomcat_users | 2,135 | ham, full headers |
| apache_kafka_users | 1,055 | ham, full headers |

Totals: 42,354 ham, 36,657 spam, 17,086 phishing, 3,227 fraud (20,313 attacks). Split: 69,542
train, 14,879 validation, 14,903 test. Header coverage highlights: Authentication-Results on 99.5% of
phishing_pot, about 100% of Apache, 20.4% of Nazario, 0% of SpamAssassin and raw Enron; raw Enron has
no In-Reply-To, References, Received or X-Mailer. Every Apache message has a list-set Reply-To and a
List-Id. Full detail: master document Sections 8.1, 8.6 and 8.8.

Current `.gitignore`:
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
artifacts/*
!artifacts/README.md
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

Current `requirements.txt`:
```
# PretextGuard dependencies. Exact versions (==) so every machine installs the same thing.
# Grows phase by phase; each library is added in the phase that first uses it.

# Phase 0: setup check and dependency security audit
pip_audit==2.10.1
pytest==9.1.1

# Phase 1: data acquisition (tables, Parquet files, HTTP downloads, progress bars)
pandas==3.0.6
pyarrow==25.0.1
requests==2.34.2
tqdm==4.70.1
```

`.env.example` and `pytest.ini` are unchanged from Phase 0.

---

## 5. Next task: Phase 2, cleaning and N1 redaction (plan not yet approved)

Full detail: master document Sections 4.2, 6.2 (body preprocessor), 8.7, 11 (N1 ablation), 12.6 and
15 (item 4). Start by proposing the plan and the background concepts, then wait for "go".

**Goal.** Add `body_clean`, `body_redacted` and `has_url` for every row of the staged table, in
`src/preprocess/` (planned files `clean.py` and `redact.py`), plus `src/preprocess/README.md`.

**What is fixed already**
- Redaction (N1): URLs become `[URL]`, bare domains `[DOMAIN]`, attachment file names `[FILE]`.
  Words such as "see attached" stay, because they are language, not payload.
- Cleaning: HTML stripping, quote splitting and signature splitting (the claim extractor in Phase 7
  needs the signature block for signature-contact claims).
- N1 evaluates three views of the same held-out set: raw, redacted, and naturally link-free (emails
  that had no URL before redaction), so `has_url` must be computed before redaction.

**Notes from Phase 1 the plan must handle**
- The Kaggle bodies still in use (CEAS-08, Enron, Ling, Nigerian Fraud) were reprocessed by the merge:
  line breaks collapsed and `<...>` stripped. Normalise whitespace for every source, so a model cannot
  tell a Kaggle email by its spacing.
- `<...>` stripping may have removed links from Kaggle text, so `has_url` from the text undercounts.
  Kaggle's own `urls` column can be read back through `raw_ref` (`kaggle/...csv#row=n`).
- Raw bodies from SpamAssassin, Nazario and phishing_pot are often raw HTML (no plain-text part).
- Apache and SpamAssassin ham contain quoted replies (`> ...`) and list footers.

**Decisions for the plan to recommend:** HTML-to-text library (for example BeautifulSoup or the standard
library), where the new columns are saved (same Parquet file or a new one), what exactly counts as a
domain, and which printed counts and examples prove the redaction worked (no unit tests).

**Background to teach in Phase 2:** regular expressions for URLs and domains; HTML vs text; shortcut
learning and why redaction matters; quoting and signature conventions in email.

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
