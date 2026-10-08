# PretextGuard: context for a new chat

Version: October 2026, written at the end of Phase 6, to go with master document v3.8.

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
   file together.
3. **You write all code.** Well-known libraries are fine; write the project logic fresh. Never copy
   code from GitHub repositories, and never open or adapt other students' PretextGuard-like projects.
4. **You never run Git.** No commit, push, branch or remote commands, even if you have tools that
   could. Nagasai commits and pushes. Suggest a short commit message after each working step. In
   Claude Code on the web, a stop hook may ask you to commit and push untracked files; this rule
   still wins (Nagasai confirmed it again: he always commits, you never do). Say so in
   one line and carry on. To verify that a push arrived, **read** the repository (GitHub tools or plain
   downloads from raw.githubusercontent.com) and compare files with what you sent; never write to it.
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
| Secrets in `.env` (names only here) | `PRETEXTGUARD_API_KEY`; `GEMINI_API_KEY`, `ANNOTATOR_1_MODEL`, `ANNOTATOR_2_MODEL`, `TIEBREAKER_MODEL` (Phase 5). `.env` is ignored; `.env.example` lists the names |
| Data on disk | `data/raw/` about 3 GB after unpacking, read-only (`chmod a-w`); `data/processed/staged.parquet` about 245 MB; `data/processed/cleaned.parquet` (Phase 2); `data/processed/tactic_data.parquet` (Phase 6, train and validation text for Colab); `artifacts/tactic_model/` (Phase 6, about 270 MB, ignored by Git, exists only on the Mac) |
| Rule | Always work from the project root, never from `src/` |

---

## 4. Current state of the repository (end of Phase 6)

```
pretextguard/
  README.md                  end-to-end overview
  CLAUDE.md                  points Claude Code at this file
  .vscode/settings.json      VS Code uses venv/bin/python; pytest enabled
  .gitignore  .env (local)  .env.example  pytest.ini  requirements.txt
  venv/                      Python 3.12.14 (ignored)
  data/README.md             every source, licence, stage and how to rebuild
  data/raw/                  downloads and unpacked archives, read-only (ignored)
  data/processed/            staged.parquet (1), cleaned.parquet (2), headers.parquet (3), tactic_data.parquet (6) (ignored)
  data/labelled/             README.md  sample.csv  annotators.csv  replies_log.csv  labels.csv
                             annotator_1/ annotator_2/ tiebreaker/ (raw replies)  batches/ (ignored)
  data/synthetic/            README.md  plan.csv  generator.csv  synthetic.csv  prompts/  replies/
  data/threads/.gitkeep
  artifacts/README.md        everything else in artifacts/ is ignored (tactic_model/ holds the Phase 6 weights, local only)
  results/README.md  staged_counts.csv  dedup_pairs.csv  header_coverage.csv  split_counts.csv
                     preprocess_summary.csv  preprocess_checks.csv
                     header_evidence_summary.csv  header_top_domains.csv  header_auth_formats.csv
                     keyword_hit_rates.csv  keyword_phrase_hits.csv  keyword_checks.csv
                     sample_counts.csv  label_validation.csv  label_agreement.csv  label_counts.csv
                     synthetic_counts.csv  semeval_mapping.csv
                     tactic_data_counts.csv  tactic_training_log.csv  tactic_seed_summary.csv
                     tactic_val_probs.csv  tactic_run_info.json  tactic_validation_scores.csv  tactic_checks.csv
  notebooks/README.md  phase6_tactic_classifier.ipynb  frontend/.gitkeep
  docs/README.md  master_document.md (v3.8)  PretextGuard_Master_Document_v3.2.docx (snapshot)
  docs/PretextGuard_Context.md (this file)  docs/figures/ (5 PNGs)
  src/README.md
  src/data/                  README.md  paths.py  unpack.py  fetch_apache.py  loaders.py  stage.py
                             coverage.py  split.py  label_schema.py  prompts.py  clipboard.py  llm_api.py
                             batches.py  annotate.py  validate_labels.py  agreement.py  labels.py
                             synthetic.py  semeval_map.py
  src/preprocess/            README.md  clean.py  redact.py  build.py
  src/headers/               README.md  parser.py  domains.py  evidence.py  build.py
  src/baseline/              README.md  lexicon.py  keywords.py  build.py
  src/models/                README.md  dataset.py  train.py  predict.py  validate.py
  src/eval/                  README.md  metrics.py
  src/{thread,claims,verifiers,router,explain,api}/__init__.py  (all empty)
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
```

`.env.example` and `pytest.ini` are unchanged from Phase 0.

---

## 5. Next task: Phase 7, claim extractor (plan not yet approved)

Full detail: master document Sections 4.4 (what N3 checks), 6.2 (the claim extractor row), 6.3 (the claim object),
6.4 (routing table), 8.13 (what Phase 5 produced: 690 emails with claim labels), 11 (claim extraction row), 12.6
(planned files `src/claims/schema.py`, `patterns.py`, `extractor.py`) and Section 15. Start by proposing the plan
and the background concepts, then wait for "go". Deliver in two steps at most, every file as a download, and verify
his push by reading the repository.

**Goal.** A function `extract_claims(body_redacted, signature)` that returns typed claims in the Section 6.3 form
(claim_id, type, text, span, attributes, confidence) for the eleven claim types (affiliation_internal,
affiliation_external, authority, reply_direction, signature_contact, prior_relationship, payment_request,
payment_change, credential_request, gift_card, data_request), plus the tactic probabilities from `TacticClassifier`
as modifiers, so the verifiers (Phases 8 and 9) have claims to check. Measured against the Phase 5 claim labels with
precision and recall per claim type.

**Notes the plan must handle**
- **Data.** `data/labelled/labels.csv`, column `claims` (JSON: type, span, organisation) for 690 real emails; counts
  per claim type and split in `results/label_counts.csv` (kind = claim); agreement per type in
  `results/label_agreement.csv` (mean kappa 0.458; weakest: prior_relationship 0.187, data_request 0.287,
  payment_request 0.287, payment_change 0.330, affiliation_internal 0.336). Types with fewer than 10 positives in
  validation or test are counts only. The synthetic emails have a `claims` column too (their required claims were
  quoted from the body): extra positives for rare types, always reported apart from real emails.
- **Method (master document 6.2).** Regular-expression patterns + spaCy named-entity recognition (`en_core_web_sm`,
  a new library: pin it, run `pip-audit`, install the model without network access at run time) + the tactic
  classifier. No LLM at run time. Patterns run on attacker-written text, so the ReDoS rules of Phases 2 to 4 apply
  (bounded repeats, input caps, crafted-input self-test).
- **Inputs.** `body_redacted` through `model_text` (the 2,000 characters the annotators labelled; spans were quoted
  from it) and the `signature` column of `cleaned.parquet`.
- **affiliation_internal** cannot be decided from the body alone (it needs the organisation domain, Phase 8): the
  extractor finds phrasing like "this is David from Finance"; the verifier decides whether it is internal.
- **Leakage discipline** (as for the keyword baseline): write patterns from the definitions and the train split
  only; validation for tuning; the test split once, in Phase 13. Score spans by overlap (the annotator comparison
  in `src/data/agreement.py` already has a span-overlap rule) and precision and recall per type with
  `src/eval/metrics.py`. The labels are LLM labels from one model family: say so wherever a score appears.
- **Environment.** The model weights exist only on Nagasai's Mac. Test claim code in Claude Code on the web on
  hand-made samples; anything that calls `TacticClassifier` is run by him.

**Decisions for the plan to recommend:** which types are pattern-only and which need spaCy; the claim object and how
`confidence` is defined for rules; how spans stay relative to `body_redacted`; what Phase 7 prints and saves in
`results/` (hit rates on the train split first, as in Phase 4, then validation scores); how a claim's `attributes`
(person, organisation, department) are filled; the two-step delivery.

**Background to teach in Phase 7:** named-entity recognition and spaCy; rules versus learned extraction; regular
expressions again, with ReDoS; character offsets and span overlap; precision and recall per claim type; why a claim
differs from a tactic (a claim names who or what, a tactic describes how the writer pushes).

## 6. The rest of the build (details in the master document, Section 12; Phases 0 to 6 are done)

| Phase | Deliverable |
|---|---|
| 6 | DistilBERT tactic classifier on Colab; weights to `artifacts/` (`src/models`, `notebooks/`): done |
| 7 | Claim extractor (`src/claims`): next |
| 8 | Header verifier N3 and request verifier (`src/verifiers`) |
| 9 | Thread builder, hijack benchmark, thread verifier N2 (`src/thread`, `src/verifiers`, `src/data`) |
| 10 | Router, ledger, risk score, LIME (`src/router`, `src/explain`) |
| 11 | FastAPI backend with all security controls (`src/api`) |
| 12 | React frontend: analyzer and dashboard (`frontend/`) |
| 13 | All experiments and charts (`src/eval`, `results/`) |
| 14 | Report, viva preparation, Review deck update (`docs/`) |

No paid APIs anywhere (annotation and synthetic data use free API tiers); no LLM at run time.
