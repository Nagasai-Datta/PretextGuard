# PretextGuard: context for a new chat

Version: October 2026, written at the end of Phase 9 and corrected on 9 October 2026 before Phase 10 started (see the start of Section 5), to go with master document v3.11.1.

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
   **Fold each phase into as few steps as possible (two at most; Nagasai asked for more per step on
   7 Oct 2026):** each step delivers every file it needs, including READMEs, edits to existing files
   and the document updates, then one run, one check and one commit. Phase 1's five steps were too
   long; Phase 4's second step carried `build.py`, its README, the document-update script and this
   file together. On 8 Oct 2026 he asked again for "as much as you can in one step": Phase 8 delivered all code,
   the READMEs, the self-test and the document-update script (which also writes the next phase's context
   file) in one step; the runs, the script and the commits followed; Phase 9 was delivered the same way (all code, READMEs, the self-test and this script in one step).
3. **You write all code.** Well-known libraries are fine; write the project logic fresh. Never copy
   code from GitHub repositories, and never open or adapt other students' PretextGuard-like projects.
4. **You never run Git.** No commit, push, branch or remote commands, even if you have tools that
   could. Nagasai commits and pushes. Suggest a short commit message after each working step. In
   Claude Code on the web, a stop hook may ask you to commit and push untracked files; this rule
   still wins (Nagasai confirmed it again: he always commits, you never do). Say so in
   one line and carry on. **Always end a step with the exact commit commands for him to run** (`git add .`,
   `git commit -m "..."`, `git push origin main`), even though you never run them (Nagasai, 8 Oct 2026: "don't
   commit or push, but always give me the commit commands too"). To verify that a push arrived, **read** the
   repository (GitHub tools or plain downloads from raw.githubusercontent.com) and compare files with what you
   sent; never write to it.
5. **No unit tests per phase.** Each phase is verified by running its scripts and checking their
   printed output. `tests/test_environment.py` is the one setup check; keep it passing.
6. **End of every phase:** list exactly what changed in the master document (section number, old
   text, new text) and deliver a script file that applies the edits to `docs/master_document.md`
   (see 1.4). Bump its version (3.3, 3.4, ...) and add a row to the decisions log (Section 14). When a
   script needs results that do not exist yet, deliver it with the step that produces them (Phase 6: the script
   reads `results/` and stops if a check failed). Always give him the exact command to run it: inside the venv
   (it needs pandas), `cd ~/Downloads`, then `python update_docs_phaseN.py`, then delete the script; he did not
   know how to run it in Phase 6.
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

**Attach every file you name.** A `mv` line for a file that was never attached cost him a round (7 Oct 2026).

**Never put `#` comments inside terminal commands.** zsh does not treat `#` as a comment in an
interactive shell, so a pasted line with a trailing comment fails (Nagasai, 7 Oct 2026). Explain a
command in the text around the block, not inside it. This applies to every command block in chat.

In both modes, every command assumes:

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
```

**Claude Code on the web.** Its sandbox usually cannot reach the data hosts (Kaggle, monkey.org,
CMU, lists.apache.org) or huggingface.co (PyPI works), so test new scripts there on small hand-made samples before handing them
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
| Colab | Free T4 GPU. In Phase 6 it ran Python 3.13.15 (the venv is 3.12), pandas 2.2.3, numpy 2.1.3 and its own torch 2.11.0+cu130, which is not reinstalled; `transformers` is pinned to the same version as the Mac. The notebook clones the public repo, so push before running it |
| Phase 1 libraries | pandas 3.0.6, pyarrow 25.0.1, requests 2.34.2, tqdm 4.70.1 (pinned in `requirements.txt`) |
| Phase 2 libraries | beautifulsoup4 4.15.0, tldextract 5.4.0 (pinned) |
| Phase 3 to 5 libraries | RapidFuzz 3.14.6 (Phase 3); Phase 4 none; scikit-learn 1.9.1 (Phase 5, for Cohen's kappa cross-check); all pinned |
| Phase 6 libraries | torch 2.14.1 (the Mac; macOS arm64 wheel), transformers 5.19.0 (Mac and Colab); pinned, `pip-audit` found nothing in them or their dependencies |
| Phase 7 libraries | spaCy 3.8.16 and its English model `en_core_web_sm` 3.8.0, installed from `requirements.txt` (the model is not on PyPI, so it is pinned by URL and SHA-256 and `pip-audit` lists it as not auditable; it found nothing in spaCy or its dependencies). The extractor loads the model from disk and never downloads it at run time |
| Phase 8 libraries | none; the verifiers use the standard library, tldextract and RapidFuzz (Phase 3) and pandas in `build.py`. `requirements.txt` is unchanged |
| Phase 9 libraries | none; the thread code uses the standard library, pandas, numpy (for the bootstrap, already installed with pandas) and the Phase 3 to 8 code. `requirements.txt` is unchanged |
| Secrets in `.env` (names only here) | `PRETEXTGUARD_API_KEY`; `GEMINI_API_KEY`, `ANNOTATOR_1_MODEL`, `ANNOTATOR_2_MODEL`, `TIEBREAKER_MODEL` (Phase 5). `.env` is ignored; `.env.example` lists the names |
| Data on disk | `data/raw/` about 3 GB after unpacking, read-only (`chmod a-w`); `data/processed/staged.parquet` about 245 MB; `data/processed/cleaned.parquet` (Phase 2); `data/processed/tactic_data.parquet` (Phase 6, train and validation text for Colab); `data/processed/claims_cache/` (Phase 8, the extracted claims per split, ignored by Git, Mac only); `data/processed/enron_index.parquet`, `threads.parquet` and `thread_features/` (Phase 9, the rebuilt threads and their cached tactic probabilities and claims, ignored by Git, Mac only); `artifacts/tactic_model/` (Phase 6, about 270 MB, ignored by Git, exists only on the Mac) |
| Rule | Always work from the project root, never from `src/` |

---

## 4. Current state of the repository (end of Phase 9)

```
pretextguard/
  README.md                  end-to-end overview
  CLAUDE.md                  points Claude Code at this file
  .vscode/settings.json      VS Code uses venv/bin/python; pytest enabled
  .gitignore  .env (local)  .env.example  pytest.ini  requirements.txt
  venv/                      Python 3.12.14 (ignored)
  data/README.md             every source, licence, stage and how to rebuild
  data/raw/                  downloads and unpacked archives, read-only (ignored)
  data/processed/            staged.parquet (1), cleaned.parquet (2), headers.parquet (3), tactic_data.parquet (6), claims_cache/ (8) (ignored)
  data/labelled/             README.md  sample.csv  annotators.csv  replies_log.csv  labels.csv
                             annotator_1/ annotator_2/ tiebreaker/ (raw replies)  batches/ (ignored)
  data/synthetic/            README.md  plan.csv  generator.csv  synthetic.csv  prompts/  replies/
  data/threads/              README.md  plan.csv  injections.csv  cases.csv  generator.csv  replies_log.csv  replies/ (raw API replies)  prompts/ (ignored)
  artifacts/README.md        everything else in artifacts/ is ignored (tactic_model/ holds the Phase 6 weights, local only)
  results/README.md  staged_counts.csv  dedup_pairs.csv  header_coverage.csv  split_counts.csv
                     preprocess_summary.csv  preprocess_checks.csv
                     header_evidence_summary.csv  header_top_domains.csv  header_auth_formats.csv
                     keyword_hit_rates.csv  keyword_phrase_hits.csv  keyword_checks.csv
                     sample_counts.csv  label_validation.csv  label_agreement.csv  label_counts.csv
                     synthetic_counts.csv  semeval_mapping.csv
                     tactic_data_counts.csv  tactic_training_log.csv  tactic_seed_summary.csv
                     tactic_val_probs.csv  tactic_run_info.json  tactic_validation_scores.csv  tactic_checks.csv
                     claim_hit_rates.csv  claim_pattern_hits.csv  claim_scores.csv  claim_checks.csv
                     verifier_rates.csv  verifier_rule_hits.csv  verifier_checks.csv
                     thread_counts.csv  thread_signal_rates.csv  thread_checks.csv  hijack_generation.csv  hijack_cases.csv  thread_scores.csv  hijack_checks.csv
  notebooks/README.md  phase6_tactic_classifier.ipynb  frontend/.gitkeep
  docs/README.md  master_document.md (v3.11.1)  PretextGuard_Master_Document_v3.2.docx (snapshot)
  docs/PretextGuard_Context.md (this file)  docs/figures/ (5 PNGs)
  src/README.md
  src/data/                  README.md  paths.py  unpack.py  fetch_apache.py  loaders.py  stage.py
                             coverage.py  split.py  label_schema.py  prompts.py  clipboard.py  llm_api.py
                             batches.py  annotate.py  validate_labels.py  agreement.py  labels.py
                             synthetic.py  semeval_map.py  hijack_benchmark.py
  src/preprocess/            README.md  clean.py  redact.py  build.py
  src/headers/               README.md  parser.py  domains.py  evidence.py  build.py
  src/baseline/              README.md  lexicon.py  keywords.py  build.py
  src/models/                README.md  dataset.py  train.py  predict.py  validate.py
  src/eval/                  README.md  metrics.py
  src/claims/                README.md  schema.py  patterns.py  extractor.py  build.py
  src/verifiers/             README.md  rows.py  facts.py  brands.py  bank.py  header_verifier.py  request_verifier.py  verify.py  selftest.py  build.py
                             thread_verifier.py
  src/thread/                README.md  signals.py  builder.py  features.py  build.py  selftest.py  evaluate.py
  src/{router,explain,api}/__init__.py  (all empty)
  tests/test_environment.py  16 checks (unchanged)
```

`data/raw/` is unchanged since Phase 1 (layout: master document Section 8.8 and `data/README.md`).

**The tables.** `data/processed/staged.parquet` (Phase 1, never modified): 99,324 unique emails with
`id, source, category, is_attack, has_full_headers, raw_ref, raw_headers, body_raw, split`.
`data/processed/cleaned.parquet` (Phase 2): the same rows and columns plus `has_url, body_clean,
body_redacted, signature`. `data/processed/headers.parquet` (Phase 3): one row per email, joined on
`id`, with the header fields and evidence (column list: master document Section 8.7). Sources:
kaggle_ceas08 38,077, kaggle_enron 29,119, kaggle_ling 2,850, kaggle_nigerian_fraud 3,227, nazario
9,595, phishing_pot 7,491, spamassassin 5,775, apache_tomcat_users 2,135, apache_kafka_users 1,055.
Totals: 42,354 ham, 36,657 spam, 17,086 phishing, 3,227 fraud (20,313 attacks). Split: 69,542 train,
14,879 validation, 14,903 test.

**Phase 2 in brief** (master document Section 8.10):
- `clean_body(raw)` and `redact(text)` in `src/preprocess` work on one string at a time; the API
  (Phase 11) will reuse them unchanged.
- `body_clean` keeps links (N1 model A's raw view); `body_redacted` has `[URL] [EMAIL] [FILE] [DOMAIN]`.
- Kaggle Enron and Ling are stored pre-tokenised ("john @ enron . com"); spaced patterns handle them.
- 4,580 attacks are naturally link-free (696 in test).

**Phase 3 in brief** (master document Section 8.11 and `src/headers/README.md`):
- `parse_header_fields(block)` and `header_evidence(fields, org_domain)` in `src/headers` work on one
  email at a time; the API will reuse them. `split_headers` and `body_text` moved from
  `src/data/loaders.py` to `src/headers/parser.py`.
- SPF, DKIM and DMARC are read, never recomputed, only from trusted Authentication-Results headers:
  the topmost one plus the headers directly below it from the same organisation. Both formats
  (standard, and Microsoft's without a server name) are read. Missing means `unknown`, never pass.
- phishing_pot: 54.7% SPF pass, 38.3% DMARC pass, From parsed 92.1%. Apache:
  verdicts (DKIM only) for 85.1% of kafka and 71.1% of tomcat. No benign source has SPF or DMARC
  verdicts, so authentication evidence is never a learned feature (N3 uses it through rules).
- No organisation domain (internal affiliation not checkable) for collector mailboxes, placeholder
  domains and free-mailbox recipients. Envelope mismatch is normal for list mail.
- Headers are attacker-written: size caps, per-field parsing, bounded patterns (master document
  Section 10). New library: RapidFuzz 3.14.6.

**Phase 4 in brief** (master document Section 8.12 and `src/baseline/README.md`):
- `score_tactics(text)` in `src/baseline/keywords.py` returns `{tactic: {"score", "phrases"}}` for the
  seven tactics (names as in the `tactic_*` columns: authority, urgency, scarcity, reciprocity,
  social_proof, liking, secrecy); `fired_tactics(scores, threshold)` applies a threshold (one number
  or a per-tactic dict). It works on one string, so Phase 13 reuses it on validation and test.
- `lexicon.py` holds the lists (data only): strong phrases (1.0, one fires the tactic) and weak
  phrases (0.5, two different ones fire it). `LEXICON_VERSION` says which revision produced the
  results (0.1 at first delivery; read it from `results/keyword_checks.csv`).
- Matching is whole-word lookup on normalised text, no regular expressions over email text; the same
  `normalise` handles Kaggle's pre-tokenised text. Overlapping phrases: the longer wins; a distinct
  phrase counts once. Default threshold 1.0, tuned per tactic on validation in Phase 13.
- `build.py` reads the train split only and writes `results/keyword_hit_rates.csv`,
  `keyword_phrase_hits.csv` and `keyword_checks.csv` (hit rates per category and source, hits per
  phrase, PASS/FAIL sanity checks). It cannot measure F1: there are no tactic labels yet.
- Rare tactics (reciprocity, social proof) may fail the coverage check on real data; that is a
  finding to carry into Phase 5 and 13, not an error.
- The authority list holds assertion phrases only, not bare job titles (every signature has one).
- No new library; `requirements.txt` is unchanged.

**Phase 5 in brief** (master document Section 8.13, `data/labelled/README.md`, `data/synthetic/README.md`):
- **Sample:** 700 real emails, a fixed number per source and category (450 attacks, 150 ham, 100 spam), drawn
  from all three splits in 60/20/20 shares by SHA-256 order of seed 42 (`src/data/batches.py`,
  `data/labelled/sample.csv`, ids only). Emails under 8 words are not eligible. **No keyword hit picks any
  email** (the Phase 4 baseline fires on almost no real reciprocity or social-proof attacks, so a top-up
  would have picked false positives); the `sample_origin` column was dropped.
- **Annotators:** three roles, `annotator_1`, `annotator_2` and `tiebreaker`, all called through Google's
  Gemini API with the one free `GEMINI_API_KEY`, each with its own model id from `.env`, at temperature 0
  (`src/data/llm_api.py`; `annotate.py check|auto|status`). The model names actually used are in
  `data/labelled/annotators.csv`. DeepSeek, z.ai and Mistral have no free API and Groq's free token limits
  are too small for 20-email batches, so agreement is between models of ONE family and their errors are
  partly shared: a limitation the report states. `annotate.py auto` refuses to run two annotators on the same
  model. The copy-and-paste chat loop (`next`, `save`) still exists as a fallback. Nagasai refused about 120
  manual pastes: never design a task that needs that many.
- **Checks on every reply** (`validate_labels.py`): JSON array with exactly the batch's ids, seven tactics as
  0 or 1, claims of the eleven types whose span's words appear in a row in the email (punctuation and case
  ignored), identical answers for all emails rejected as a likely hijack. An invalid item is re-asked once,
  then dropped and counted. Raw replies are kept untouched.
- **Final labels** (`labels.py`): both annotators must have answered; a label they agree on stands; the
  tie-breaker decides the rest (majority of three); a claim type needs two votes. `labels.csv` has the seven
  `tactic_*` columns, `claims` as JSON, `label_source = llm_annotated`. The counts per tactic, split and
  category are in `results/label_counts.csv`: **a tactic with fewer than 10 positives in validation or test is
  reported as a count, not as an F1.** Final run: 690 of 700 emails labelled (413 train, 137 validation, 140
  test; 8 lack a valid annotator answer, 2 were dropped after the tie-break re-ask). Real positives (train /
  validation / test): authority 71/21/25, urgency 122/39/44, scarcity 91/27/26, secrecy 41/12/16 (F1 allowed);
  liking 11/3/4, reciprocity 5/2/0, social_proof 2/0/0 (counts only). Models used: annotator_1
  `gemini-3.1-flash-lite`, annotator_2 `gemini-3.5-flash-lite`, tiebreaker `gemini-flash-lite-latest`, which is
  a moving alias (the provider's reply does not say which version it served, so it may equal an annotator).
  Annotator 1 marks far more positives than annotator 2 (authority 218 against 76), so the tie-breaker decides
  most authority labels. Mean kappa: tactics 0.501, claims 0.458 (moderate).
- **Agreement** is in `results/label_agreement.csv` (Cohen's kappa per tactic and claim type, hand-written
  and cross-checked with scikit-learn). Low kappa on rare labels is expected; `affiliation_internal` cannot be
  decided from the body alone (it needs the organisation domain, Phase 8).
- **Synthetic emails** (`synthetic.py`): 240 attack-and-benign-twin pairs planned over 12 situations, written
  by the same API (annotator_1's model, temperature 0.8), every attack's tactics fixed by the plan and
  confirmed by a quoted cue, twins must not make the keyword baseline fire, pairs split together (70/15/15).
  222 pairs were valid (444 emails; 18 dropped after one re-ask). `data/synthetic/synthetic.csv`. Always
  reported separately from real-email results (style confound, master document Section 8.5). Attack emails per
  tactic (train / validation / test): authority 54/14/14, urgency 57/16/6, scarcity 43/18/13, reciprocity
  60/9/9, social_proof 52/12/16, liking 57/14/7, secrecy 53/16/8. By the same rule only authority, scarcity
  and social_proof reach 10 in both validation and test. Because twins that tripped the keyword baseline were
  dropped, the baseline's false-positive rate on synthetic twins is zero by construction: never report it
  as the baseline's precision.
- **SemEval** (`semeval_map.py`): the 23-to-7 table (3 direct, 5 partial, 15 none); tactics SemEval cannot
  label (reciprocity, and secrecy only weakly) are masked, never 0 (`tactic_labels`). The technique names are
  unchecked against real data (registration needed); `--check FILE` tests them. SemEval is optional.
- **Not committed:** `data/labelled/batches/` (full email text; phishing_pot's licence forbids
  redistribution). Rebuild with `python -m src.data.batches`.

**Phase 6 in brief** (master document Section 8.14, `src/models/README.md`, `notebooks/README.md`):
- **Code:** `src/models`: `dataset.py` builds `data/processed/tactic_data.parquet` (train and validation rows only,
  932 rows: real 413 + 137, synthetic 306 + 76; a test row stops the build and the training), `train.py` is the
  Colab loop, `predict.py` holds `TacticClassifier` (load once, `predict(body_redacted)`), `predict_probs` and
  `load_tactic_model`, `validate.py` scores on the Mac and runs the PASS/FAIL checks. `src/eval/metrics.py` has
  hand-written precision, recall, F1, macro-F1 and `tune_threshold`, cross-checked against scikit-learn (F1 is
  hidden below 10 positives; Phase 13 reuses it). The model reads `model_text(body_redacted)` (2,000 characters,
  the annotators' text without the truncation note).
- **Settings:** `distilbert/distilbert-base-uncased`, 7 sigmoid outputs, binary cross-entropy with `pos_weight`
  (negatives over positives, at most 10), 512 tokens, batch 16, AdamW 3e-5 with 10% warm-up and linear decay,
  at most 8 epochs, stop after 3 without improvement, seeds 42, 43, 44. Two conditions: `mix` (real + synthetic
  train emails; the model) and `real_only` (comparison). Epoch and seed chosen by macro-F1 over authority, urgency,
  scarcity and secrecy on real validation at threshold 0.5; thresholds for those four tuned on real validation;
  reciprocity, social proof and liking stay at 0.5 (counts only). Safetensors only, offline loading, output order
  checked.
- **The run:** Colab T4, 22.2 minutes, code commit 407861e, base model revision 12040acc. Chosen: mix, seed 43,
  epoch 8; thresholds authority 0.55, urgency 0.45, scarcity 0.65, secrecy 0.90, others 0.5. The Mac's CPU
  reproduced Colab's probabilities to within 0.000001 (limit 0.001; torch 2.11.0 on Colab, 2.14.1 on the Mac);
  213 validation emails in 9.6 s. All checks passed (results/tactic_checks.csv).
- **Results** (validation only, real and synthetic apart; `results/tactic_validation_scores.csv`). Real validation
  macro-F1 over the four main tactics: DistilBERT 0.613, trained without synthetic emails 0.617, keyword baseline
  tuned 0.495, keyword default 0.296. Per tactic, DistilBERT against the tuned baseline: authority 0.593 / 0.316,
  urgency 0.606 / 0.492, scarcity 0.552 / 0.654 (the baseline is ahead), secrecy 0.700 / 0.518. Synthetic
  validation macro-F1: 0.420 with and 0.269 without synthetic training emails. The model found 0 of the 5 real
  validation positives of reciprocity, social proof and liking (counts only). The final comparison is Phase 13,
  once, on the test split; validation scores are slightly optimistic (validation chose the epoch, seed and
  thresholds), and the labels are LLM labels from one model family.
- **Findings to carry forward:** the synthetic training emails made no measurable difference on real emails (a
  difference of -0.005 against a seed spread of 0.539 to 0.571) but are the only reason the rare tactics are
  learned at all, and only on synthetic emails. In 4 of 6 runs the best epoch was the last (8), but the validation
  loss had stopped falling (minimum around epochs 5 to 7 for the mix seeds), so more epochs were not tried. Secrecy
  at threshold 0.90 scores 0.222 F1 on synthetic emails (0.700 on real ones). The tuned keyword thresholds all
  landed at 0.5 (any single weak phrase fires). Phase 13 should add bootstrap confidence intervals: each tactic has
  only 12 to 39 real validation positives.
- **Where things live:** the weights (`artifacts/tactic_model/`, about 270 MB) and `tactic_data.parquet` exist only
  on Nagasai's Mac (ignored by Git), so Claude Code on the web cannot load the model: test code that uses it on
  hand-made samples and have him run it. Phase 6 was tested offline with a tiny random DistilBERT (a masked-LM base
  saved as safetensors, tokenizer built with `vocab=`) and fake text for the real ids. In transformers 5.x
  `from_pretrained` raises when a head's size differs from the checkpoint, and tokenizers take `vocab=`, not
  `vocab_file=`.
- **Docs:** `update_docs_phase6.py` (a download, run from `~/Downloads` inside the venv; it reads `results/`) made
  master document v3.8. SemEval pretraining was skipped.

**Phase 7 in brief** (master document Section 8.15, `src/claims/README.md`):
- **Code:** `src/claims`: `schema.py` (the claim dictionary, the limits of 12 claims per email and 3 per type,
  `check_claim`), `patterns.py` (data only: 85 phrases in a small token-pattern language, `KNOWN_ORGS` with about 55
  often-imitated organisations, word lists, `PATTERN_VERSION` "0.4"), `extractor.py` and `build.py`.
  `extract_claims(body_redacted, signature=None, min_confidence=0.0)` works on one email and returns claims in the
  master document 6.3 form: `claim_id, type, text, span, attributes {person, organisation, department, pattern, zone},
  confidence`, for the eleven types of `CLAIM_TYPES` (`src/data/label_schema.py`); `extract_many` does a batch. The
  API reuses it unchanged. Self-test: `python -m src.claims.extractor` (41 PASS lines, crafted 200,000-character
  inputs under 2 seconds).
- **What it reads:** `model_text(body_redacted)` (2,000 characters, what the annotators labelled) plus the `signature`
  column. That column is cut from `body_clean` in Phase 2, so it still holds raw addresses: `extract_claims` redacts it
  first and cuts it at 1,000 characters. Spans point into the text that was read, not into the raw email; `zone` says
  `body` or `signature`.
- **Method:** no model is trained. spaCy 3.8.16 (`en_core_web_sm`, tokenizer and named-entity recogniser only) plus
  token patterns compiled to spaCy's Matcher (words, `stem*`, alternatives `a|b`, `!not`, exact-case `=IT`, `?optional`,
  `..N` free tokens, `#` digits, `@PERSON`/`@ORG`), an organisation rule, a signature rule. No regular expression
  runs over email text except two short bounded ones (a phone number and the `[EMAIL]` placeholder). **Confidence is
  the strength of the rule that fired** (0.9 strong, 0.6 weak), not a probability; results are reported at two
  operating points (`min_confidence` 0.0 = all claims, 0.9 = strong claims only).
- **Discipline:** patterns written from the definitions and the train split only, in four versions (0.1 to 0.4), each
  revision read off train results (`--train-only`, `--limit`, `--diagnose` never load validation). Version 0.4 was
  committed (8633c4f) and then `python -m src.claims.build` (no flags, 1,197 seconds) scored the validation emails
  once; nothing changed afterwards. The test split is unused; Phase 13 adds `src/eval/claim_extraction.py` to score
  the frozen patterns on it once.
- **Results** (final run, `results/claim_*.csv`, all 31 checks PASS, 11 info). Train hit rates (69,542 emails): a
  credential request in 31.7% of phishing against 1.0% of ham, an outside organisation in 50.3% of phishing against
  12.5% of ham, authority in 52.3% of fraud against 1.6% of ham, a reply direction in 23.1% of fraud against 2.5%, a
  data request in 18.2% of fraud against 2.6%. Real validation emails (137), F1 for all claims / strong only:
  affiliation_external 0.703 / 0.651, authority 0.621 / 0.500, credential_request 0.783 / 0.683, signature_contact
  0.505 / 0.510 (precision 0.35 at recall 0.92 for all claims), affiliation_internal 0.167 / 0.087 (0.492 on the train
  development set); macro over these five 0.556 / 0.486 (train 0.617 / 0.605). Counts only on real validation (tp/fp/fn):
  reply_direction 5/3/4, data_request 2/13/3, prior_relationship 0/4/1, payment_request 0/11/0, payment_change
  1/3/0, gift_card 0/1/0. For context, annotator 2's labels against annotator 1's give F1 0.410 (internal), 0.721
  (external), 0.662 (authority), 0.613 (signature), 0.730 (credential) from `label_agreement.csv`. Synthetic
  validation macro 0.536 / 0.613 (0.570 / 0.599 without credential_request, which has one positive there; caveat in master document
  8.15); affiliation_external recall there is 0.28 because the generic-word filter rejects
  the generic-sounding company names the generator invented. All scores are agreement with LLM labels from one model
  family; the train scores are development scores.
- **Findings to carry forward:** (1) affiliation_internal does not generalise (15 validation positives, 2 found): it
  cannot be decided from the body, so the header verifier decides whether a claim is internal, and a missing claim
  is never evidence of honesty. (2) signature_contact finds nearly every labelled signature but precision is low;
  in redacted text every address is `[EMAIL]`, so the verifier must read signature addresses from the unredacted
  signature, not from the claim. (3) Strong-only claims lower F1 on 4 of 5 types, so weak claims stay in; Phase 13
  picks the operating point per type on validation. (4) Six of eleven types are counts only on real emails. The
  labelled positives for payment_request and data_request are sparse (annotator kappa 0.287), so their many "false
  positives" against the labels are not all extractor errors. (5) `ae_org_cue`, `ai_dept_role`, `pc_details_changed`
  and `gc_gift_card` dominate their types (info findings in `claim_checks.csv`).
- **Where things live:** nothing large. spaCy and the model install from `requirements.txt`; Claude Code on the web
  may not reach the model host, so test code that needs the extractor on hand-made samples and have him run it on
  real data. `data/processed/` tables exist only on his Mac.
- **Docs:** `update_docs_phase7.py` (a download, run from `~/Downloads` inside the venv; it reads `results/` and stops
  if a check failed or the validation emails were not scored) made master document v3.9.

**Phase 8 in brief** (master document Section 8.16, `src/verifiers/README.md`):
- **Code:** `src/verifiers`: `rows.py` (the ledger row, `check_row`, `ROUTES`, `clean_text`, `clean_domain`), `facts.py` (`prepare_facts`,
  `auth_state`, `similar_domain`, `find_addresses`), `brands.py` (data only), `bank.py` (`find_bank_details`, `bank_detail_keys`),
  `header_verifier.py` (N3), `request_verifier.py`, `verify.py` (`verify_claims(claims, {**fields, **evidence}, contact_text, body_text)`,
  `RULES_VERSION`, `VERSION_LOG`, `ALL_RULES`), `selftest.py` and `build.py`. No new library. The API reuses `verify_claims` unchanged.
- **Ledger row** (Section 6.3 plus `claim_type` and `rule`): `contradiction` is true (severity high, medium or low), false (severity none)
  or null (severity not_checkable). Missing evidence is never 'no contradiction'. Severity is rule strength, not a probability; a weak claim
  (confidence 0.6) lowers it one step; Phase 10 turns severities into points. 63 rules (50 header, 12 request, one
  thread placeholder `tv_needs_thread` for prior_relationship).
- **Header verifier:** internal affiliation (free mailbox or look-alike of the organisation domain: high; exact-domain spoof with DMARC fail:
  high; not checkable without an organisation domain, on mailing-list mail, or when From shows the organisation's domain and there is no
  verdict), external affiliation (brand domains from `brands.py`; free mailbox, look-alike or display name showing another address: high; an
  unrelated domain: medium; no organisation named or no domain on file: not checkable), authority, reply direction (Reply-To against From,
  list-set Reply-To excluded) and signature contact (addresses read from the UNREDACTED signature block or the end of the cleaned body).
  Authentication enters only through these claim-conditioned rules. Fixed numbers, never tuned: look-alike = equal after look-alike
  character mapping, or rapidfuzz ratio 80 or more with both names at least 6 letters.
- **Request verifier:** who is asking. Signals: look-alike sender, DMARC fail (high); free mailbox (medium, high when outside the recipient's
  organisation); Reply-To to another domain, display name showing another address, SPF fail (medium); no check passed (low). payment_change and
  gift_card +1 step, data_request -1, valid bank details +1. A bank-detail change is always 'not checkable: needs the thread'. Bank details are
  found by `bank.py` without regular expressions (IBAN mod 97 and country length, labelled account, routing and sort numbers, SWIFT) and
  shown masked.
- **Discipline:** rules written from definitions and train results only, in versions up to 0.3 (`VERSION_LOG` in `verify.py`);
  `build.py --train-only` never loads a validation email; the final run read validation once; the test split is unused. The train rates are
  development rates. The claims the Phase 7 extractor finds are cached in `data/processed/claims_cache/` (one file per split).
- **Results** (final run, `results/verifier_*.csv`, 31 PASS, 0 FAIL, 10 info). Train: 79590 claims routed to a verifier in
  32872 of 69542 emails; 11.5% could be checked and 79.5% of those were contradicted. Share of emails with at
  least one contradicted claim, train: ham 3.5%, spam 1.7%, phishing 18.4%, fraud 40.9%; validation: ham 3.2%,
  spam 1.4%, phishing 17.9%, fraud 41.3%. The checkable share runs from 0.0% (kaggle_enron) to 27.1% (spamassassin) across
  sources because the evidence differs by source. There are no contradiction labels, so these are rates, not precision or recall; the effect on
  detection is the Phase 13 N3 ablation. The per-type tables, per-source coverage and the reading are in Section 8.16.
- **Findings to carry forward:** (1) attacks and ham come from different corpora with different header evidence, so category contrasts are partly
  corpus contrasts; always report per source. (2) Real internal-affiliation evidence is thin (organisation domain known for 3.6% of
  phishing_pot and 9.8% of Nazario emails) and the extractor finds 13% of the labelled internal claims, so a missing claim is never evidence of
  honesty. (3) A sender that authenticates as its own domain is only 'consistent': a hijacked real account passes every check, which is
  what Phase 9 is for. (4) prior_relationship and payment_change are routed to the thread verifier; until it exists their rows are not checkable.
  (5) Brand domains: 51 organisations, 15 secondary domains flagged for a hand check (`CONFIRM` in `brands.py`), six left out as not certain.
- **Where things live:** results in `results/verifier_*.csv` (counts only); the claims cache in `data/processed/claims_cache/` (ignored by
  Git, exists only on the Mac). Claude Code on the web cannot reach the data: test code on hand-made header blocks and claims, as `selftest.py` does.
- **Docs:** `update_docs_phase8.py` (a download, run from `~/Downloads` inside the venv; it reads `results/` and stops if a check failed or the
  validation emails were not read) made master document v3.10, including a caveat in Section 8.15 on the synthetic validation macro-F1.

**Phase 9 in brief** (master document Section 8.17, `src/thread/README.md`, `data/threads/README.md`):
- **Code:** `src/thread`: `signals.py` (the four measurements as plain functions: `tactic_onset`, `bank_drift`, `request_novelty`, `sender_identity`, `path_drift`, `id_integrity`, `quote_integrity`; no model, no I/O), `builder.py` (Apache threads by union-find over Message-ID, In-Reply-To and References; Enron threads by normalised subject, 14-day runs and shared participants; `split_message` keeps the new text and the quoted history), `features.py` (cached tactic probabilities and claims), `build.py`, `selftest.py`, `evaluate.py`; `src/verifiers/thread_verifier.py` (44 `tv_` rules, `verify_thread_message(messages, index)`, `scan_thread(messages)` with the flip index, rule version 0.2); `src/data/hijack_benchmark.py`. `verify_claims(..., thread=(messages, index))` is optional and unchanged without it (RULES_VERSION 0.3). No new library. A message dictionary is described in `signals.py`.
- **Ledger rows of the thread verifier:** the same shape as Phase 8 with verifier 'thread'. Signal rows have claim_id 'thread' and claim_type tactic_onset, request_drift, sending_path, thread_integrity or single_email; claim rows (prior_relationship, the five request types) keep the claim's id. Severities are initial labels (Phase 10 calibrates them).
- **Threads:** 391 Apache threads (2309 messages) and 1200 Enron threads (5471 messages); a thread needs 3 to 50 messages and at least two senders; the thread split is by thread (70/15/15, SHA-256 of seed 42 and the thread id); threads with a message the tactic classifier trained on are kept out of validation and test. `data/processed/threads.parquet` has every message with `split`; test threads are built but were never scored.
- **Benchmark:** five cases per base thread (`neg_real`, `neg_synth`, `A` takeover = content signals only, `B` look-alike swap = sending path only (Apache), `C` forged = integrity only); the benign text is the body of neg_synth, B and C (style control); bank details are inserted by code as a valid fictional IBAN; the injected message ends the thread; texts were written through the free Gemini API (model in `data/threads/generator.csv`). `data/threads/cases.csv` is the manifest; `candidate_message` in `hijack_benchmark.py` rebuilds any case.
- **Discipline:** rules written from definitions and train results only, versions up to 0.2 (`THREAD_VERSION_LOG`); `--train-only` never scores a validation thread; the final runs read validation once; the test split is unused. False alarms on real threads (medium or high contradictions on messages with a past): train apache 0.4% of 1243 messages; train enron 3.6% of 3034 messages; validation apache 1.1% of 379 messages; validation enron 4.8% of 539 messages. Validation detection (rate, hits of n): apache A: N2 80.0% (32 of 40), Phase 8 17.5% (7 of 40); apache B: N2 100.0% (26 of 26), Phase 8 0.0% (0 of 26); apache C: N2 100.0% (40 of 40), Phase 8 0.0% (0 of 40); enron A: N2 100.0% (29 of 29), Phase 8 0.0% (0 of 29); enron C: N2 82.8% (24 of 29), Phase 8 0.0% (0 of 29). The full tables and the reading are in Section 8.17.
- **Findings to carry forward:** (1) the thread verifier is the only verifier that can see a hijacked real account whose headers are genuine (variant A: N3 and the request verifier see the same headers as for the real reply); (2) a hijacker with mailbox access can copy IDs, sending details and wording, so content signals are the last line and a calm, perfectly copied message cannot be caught; (3) Enron has no sending-path data or reply IDs, so it tests the content signals and the quote check only; (4) one change of server or mail program alone is weak (low), and the single-email rule is low severity because many real replies lack reply headers; (5) all numbers depend on the Phase 6 thresholds and the Phase 7 claim extractor, and the injected messages and headers are synthetic.
- **Where things live:** results in `results/thread_*.csv` and `results/hijack_*.csv` (counts only); the threads, features and the Enron index in `data/processed/` (ignored by Git, exist only on the Mac); the benchmark plan, injected synthetic texts, raw API replies and manifest in `data/threads/` (committed; the prompts are not). Claude Code on the web cannot load the model or the data: test code on hand-made threads, as `selftest.py` does.
- **Docs:** `update_docs_phase9.py` (a download, run from `~/Downloads` inside the venv; it reads `results/` and stops if a check failed or the validation threads were not scored) made master document v3.11 and rewrote this file.

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

# Annotation batches hold full email text (phishing_pot forbids redistribution); rebuilt by src/data/batches.py
data/labelled/batches/

# Thread-hijack prompts hold excerpts of real emails (Enron, Apache lists); rebuilt by src/data/hijack_benchmark.py
data/threads/prompts/

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

# Phase 2: cleaning and N1 redaction (HTML to text, public suffix list)
beautifulsoup4==4.15.0
tldextract==5.4.0

# Phase 3: header evidence (lookalike domain similarity)
RapidFuzz==3.14.6

# Phase 5: label agreement (Cohen's kappa cross-check)
scikit-learn==1.9.1

# Phase 6: tactic classifier (trained on Colab, run on the Mac's CPU)
torch==2.14.1
transformers==5.19.0

# Phase 7: claim extractor (spaCy). The English model is not on PyPI, so it is pinned by URL and SHA-256.
spacy==3.8.16
en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl#sha256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85
```

`.env.example` and `pytest.ini` are unchanged from Phase 0.

---

## 5. Next task: Phase 10, claim router, verdict ledger, risk score and LIME highlights (plan not yet approved)

**Already decided on 9 October 2026 (first Phase 10 chat; master document 3.11.1 records it; do not reopen):** (1) LIME for text is written by hand (random word removal, kernel weights, weighted ridge fit, fixed seed) and cross-checked once against the `lime` package; the package is not added to `requirements.txt` (it would install matplotlib and scikit-image). (2) The score takes points from the severity of a row, not from the claim type: the strongest row of each claim counts, each further claim counts half as much as the one before, consistent and not-checkable rows add nothing, urgency and secrecy multiply, a reliability factor per rule lowers a noisy rule, the result is capped at 100 (Section 6.6). (3) The first band is named Low risk, and the report carries a `coverage` block. (4) `header_findings` is the cleaned header evidence, not rows; the whole report shape is in Section 6.3. Still open for the plan: the exact initial numbers, the false-alarm budget, the LIME settings and the step plan.

Full detail: master document Sections 4.5 (the architecture contribution), 6.2 (claim router, ledger and risk score, LIME), 6.3 (the ledger row and the report shape), 6.4 (routing table), 6.6 (the score and the verdict bands), 6.7 (the worked example), 6.8 and 6.10 (the runtime steps), 6.11, 8.14 (the tactic classifier), 8.15 (claims), 8.16 and 8.17 (the rows the verifiers produce), 10, 11 (the architecture ablation), 12.6 (planned files `src/router/router.py`, `ledger.py`, `score.py`, `pipeline.py` and `src/explain/lime_explain.py`) and Section 15, items 4, 7, 10 to 14 and 15 to 18. Start by proposing the plan and the background concepts, then wait for "go". Fold the phase into as few steps as you can (two at most; Nagasai asked for as much as possible per step), deliver every file as a download, and verify his push by reading the repository.

**Goal.** One function, `analyze(raw_email_or_thread, org_domain=None)`, that runs the whole pipeline of Figure 3 for one request and returns the report of Section 6.3: parse (Phase 3), redact (Phase 2), tactic probabilities (Phase 6), claims (Phase 7), route every claim to its verifier (Phase 8, plus Phase 9 when a thread is given), collect the rows into the verdict ledger, turn the ledger and the tactic probabilities into a 0 to 100 score, a band and a recommended action, and add LIME highlights for the tactics. The API (Phase 11) calls `analyze` and nothing else.

**Notes the plan must handle**
- **Router and ledger.** `ROUTES` in `src/verifiers/rows.py` is the routing table of Section 6.4. `verify_claims(claims, facts, contact_text, body_text, thread=None)` returns the claim rows (with a thread, prior_relationship goes to the thread verifier and every request claim gets a second, thread row); `verify_thread_message(messages, index)` returns the thread signal rows (claim_id 'thread'; claim_type tactic_onset, request_drift, sending_path, thread_integrity or single_email) and `scan_thread(messages)` the flip index. A row has `contradiction` true/false/null and `severity` high/medium/low/none/not_checkable; a weak claim already lowers a severity one step; `check_row` validates a row.
- **Thread input.** A thread is a list of message dictionaries (`src/thread/signals.py`) built as `src/thread/builder.py` builds them (`split_message` for the new text and the quoted history, `record_from_table`/`message_record` for the fields); tactic probabilities come from `TacticClassifier.probabilities`, claims from `extract_many`, thresholds from `src/thread/features.py:load_thresholds`. At most 50 messages are examined. Single-email mode runs only the `tv_single_*` rule.
- **Score.** Severities are rule strengths, not probabilities. Points per severity, the modifiers (urgency, secrecy and the other tactics raise the weight of a contradiction found with them, Section 6.6), the cap at 100 and the bands (0-34, 35-69, 70-100) are initial and are calibrated on the validation split only, never on test. There are no contradiction labels: say what each calibration target can and cannot support (attack against ham on the validation emails, where the corpus confound of Section 8.16 means per-source reporting; the hijack benchmark's validation cases, Section 8.17; the labelled tactic data) and do not tune on the benchmark cases that Phase 13 will not see again. Rules that are noisy on real threads (see `results/thread_signal_rates.csv`) and rows that are 'not checkable' must not add points; 'consistent' is never a reason to lower the score of another row.
- **Tactics.** `TacticClassifier.thresholds` and `.predict`; reciprocity, social proof and liking have under 10 real positives in Phase 6 (counts only), so decide whether they modify the score at all.
- **LIME.** Written by hand, no new library (decided above); it needs a batch prediction function (`TacticClassifier.probabilities` over 2,000-character texts, about 20 emails a second on the Mac's CPU); one explanation per tactic that fired; cap the number of perturbation samples and the text length; the highlights are built from escaped text (Section 10, XSS) and the weights exist only for the tactic classifier, not for the verifiers (their explanation is the row's reason).
- **Architecture ablation (Phase 13).** The claim-routed pipeline is compared with a flat classifier on the same signals: keep the ledger rows and a flat feature vector of the same signals available so Phase 13 can build both.
- **Security.** Size caps (the API enforces them), nothing stored, reasons built from validated values only, output escaped. The report shape of Section 6.3 includes `thread` (flip index and signals, or null) and `request_id`.
- **Environment.** The model weights, the caches and the data exist only on Nagasai's Mac. Test the router, ledger and score code in Claude Code on the web on hand-made rows and thread messages (the Phase 8 and Phase 9 self-tests show how); LIME and the model need his run.

**Decisions for the plan to recommend:** the ledger format returned by `analyze` and where each row type comes from; the score formula (points per severity, tactic modifiers, caps, how not-checkable and noisy rules count); what is calibrated on validation and with what measure; the verdict bands and actions; the LIME settings and what is highlighted; the `analyze` signature for a single email and for a thread; what Phase 10 prints and saves in `results/`; the step plan.

**Background to teach in Phase 10:** the verdict ledger as a fact-checking record (claim, evidence, verdict, reason) and why the output is the explanation; routing as a lookup table; turning categorical severities into a score, saturating sums and why a cap; calibration without labels (what a surrogate target can and cannot say); the corpus confound in attack-versus-ham comparisons; LIME in plain words (remove words, watch the probability, fit a small linear model locally); why explanations of a classifier are not explanations of rules.

## 6. The rest of the build (details in the master document, Section 12; Phases 0 to 9 are done)

| Phase | Deliverable |
|---|---|
| 7 | Claim extractor (`src/claims`): done |
| 8 | Header verifier N3 and request verifier (`src/verifiers`): done |
| 9 | Thread builder, hijack benchmark, thread verifier N2 (`src/thread`, `src/verifiers`, `src/data`): done |
| 10 | Router, ledger, risk score, LIME (`src/router`, `src/explain`): next |
| 11 | FastAPI backend with all security controls (`src/api`) |
| 12 | React frontend: analyzer and dashboard (`frontend/`) |
| 13 | All experiments and charts (`src/eval`, `results/`) |
| 14 | Report, viva preparation, Review deck update (`docs/`) |

No paid APIs anywhere (annotation and synthetic data use free API tiers); no LLM at run time.
