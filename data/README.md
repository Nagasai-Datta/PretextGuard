# data/

Every dataset PretextGuard uses, where it came from, and how each stage is built. The code that reads these folders is in `src/data/` (see `src/data/README.md`).

> **Safety:** `nazario/` and `phishing_pot/` hold real phishing, with live malicious links and some malware attachments. Never open these files in a mail app (it would load remote images and tell the attacker your address is live) and never double-click attachments. The scripts only read them as text.

## Sources

| Folder in `data/raw/` | Source and origin | What we use | Messages | Licence or terms |
|---|---|---|---|---|
| `kaggle/` | "Phish No More" phishing email dataset by Naser Abdullah Alam on Kaggle (merge built for Al-Subaiey et al., 2024) | `CEAS_08.csv`, `Enron.csv`, `Ling.csv`, `Nigerian_Fraud.csv` | 75,112 rows read | As stated on the Kaggle dataset page; cite Al-Subaiey et al. (2024) |
| `spamassassin/` | SpamAssassin public corpus, spamassassin.apache.org/old/publiccorpus/ | `20030228_easy_ham`, `_easy_ham_2`, `_hard_ham`, `_spam`, `20050311_spam_2` | 6,046 | Public research corpus of the Apache SpamAssassin project; see its README on the download page |
| `nazario/` | Jose Nazario's phishing corpus, monkey.org/~jose/phishing/ | All 17 mbox files (`phishing0` to `phishing3`, `20051114`, `private-phishing4`, `phishing-2015` to `phishing-2025`) | 12,010 | Public research corpus; cite Nazario |
| `phishing_pot/` | rf-peixoto/phishing_pot on GitHub (honeypot .eml files; data only, no code) | `email/*.eml` from the `main` branch zip | 8,614 | CC BY-NC 4.0: non-commercial use with attribution. Last public commit 21 May 2026 |
| `enron/` | Enron email dataset, CMU, www.cs.cmu.edu/~enron/ (`enron_mail_20150507.tar.gz`) | The whole maildir | 517,401 | Public research corpus released through the FERC investigation and distributed by CMU |
| `apache/` | Public archives of users@tomcat.apache.org and users@kafka.apache.org (lists.apache.org), Oct 2024 to Sep 2026 | 48 monthly mbox files | 3,234 | Public mailing-list archives of the Apache Software Foundation; messages remain their authors' |

Files we deliberately do not use:
- Kaggle `phishing_email.csv`: a pre-merged copy of the other Kaggle files (text and label only); reading it would count every email twice.
- Kaggle `Nazario.csv` and `SpamAssasin.csv`: reprocessed copies of the raw Nazario and SpamAssassin corpora (line breaks collapsed, `<...>` stripped, some Nazario rows run into the next message). We use the originals, which keep their headers.
- Raw Enron is not in the single-email table: the Kaggle merge already holds Enron bodies. Raw Enron is used for the header coverage table and, in Phase 9, for real threads (guessed from subjects and participants; see `src/thread/README.md`).

None of these files is committed or redistributed in this repository.

## Stages

| Stage | Location | In Git? | Built by | Phase |
|---|---|---|---|---|
| Downloads, never modified (read-only) | `data/raw/<source>/` | No | You (browser) and `fetch_apache.py` | 1 |
| Unpacked archives, read-only | `data/raw/<source>/<archive name>/` | No | `unpack.py` | 1 |
| One table of every unique email, with the split | `data/processed/staged.parquet` | No | `stage.py`, `split.py` | 1 |
| The same rows plus clean and redacted bodies | `data/processed/cleaned.parquet` | No | `src/preprocess/build.py` | 2 |
| Header fields and evidence, one row per email (joins on `id`) | `data/processed/headers.parquet` | No | `src/headers/build.py` | 3 |
| Train and validation emails (full text) with the seven tactic labels, real and synthetic, uploaded to Colab; never any test row | `data/processed/tactic_data.parquet` | No (full email text) | `src/models/dataset.py` | 6 |
| The claims the Phase 7 extractor found per email, one file per split (train, validation), so later runs do not repeat its 20 minutes | `data/processed/claims_cache/` | No (claim text is email text) | `src/verifiers/build.py` | 8 |
| Annotation batch prompts (full email text) | `data/labelled/batches/` | No (phishing_pot's licence forbids redistribution) | `src/data/batches.py` | 5 |
| Sample list (ids only), raw chatbot replies, reply log, final labels | `data/labelled/` | Yes (small; proof of method) | `src/data/annotate.py`, `labels.py` | 5 |
| Synthetic emails (attack and benign twin pairs) and their prompts and replies | `data/synthetic/` | Yes | `src/data/synthetic.py` | 5 |
| The Enron index (one row per distinct message) | `data/processed/enron_index.parquet` | No | `src/thread/build.py` | 9 |
| Rebuilt threads (one row per message, with the quoted history and header facts) and their cached tactic probabilities and claims | `data/processed/threads.parquet`, `data/processed/thread_features/` | No (full email text) | `src/thread/build.py`, `src/thread/features.py` | 9 |
| The thread-hijack benchmark: plan, injected synthetic texts, raw API replies, manifest | `data/threads/` | Yes (synthetic text and ids only); the prompts are not | `src/data/hijack_benchmark.py` | 9 |

`data/raw/` and `data/processed/` are listed in `.gitignore`: they are large, separately licensed and full of real email text. Anything in `data/processed/` can be rebuilt from `data/raw/` by rerunning the scripts.

## Phase 1 result

99,324 unique emails (20,313 attacks: 17,086 phishing and 3,227 fraud) after dropping 208 emails with no readable text and 5,484 duplicates. Split: 69,542 train, 14,879 validation, 14,903 test. Per-source counts are in `results/staged_counts.csv`, `results/dedup_pairs.csv`, `results/header_coverage.csv` and `results/split_counts.csv`.

## How to rebuild from scratch

1. Download in the browser (Chrome, or Safari with "Open safe files after downloading" turned off):
   - Kaggle "Phish No More" dataset: the Download button gives `archive.zip`.
   - SpamAssassin: the five files listed above, each ending in `.tar.bz2`.
   - Enron: `enron_mail_20150507.tar.gz` from the CMU page.
   - phishing_pot: the green "Code" button, then "Download ZIP", gives `phishing_pot-main.zip`.
   - Nazario: the `.mbox` files from the page; the `phishing-20XX` files with curl, because browsers block them:
     ```bash
     cd ~/Downloads
     for f in $(curl -s https://monkey.org/~jose/phishing/ | grep -oE 'href="phishing-20[0-9]{2}[^"]*"' | sed -E 's/^href="//; s/"$//'); do
       curl -fL --retry 3 -o "$f" "https://monkey.org/~jose/phishing/$f"
     done
     ```
2. Move them into place and make them read-only:
   ```bash
   cd ~/Desktop/pretextguard
   mkdir -p data/raw/{kaggle,spamassassin,nazario,enron,phishing_pot}
   mv ~/Downloads/archive.zip data/raw/kaggle/phish_no_more.zip
   mv ~/Downloads/20030228_*.tar.bz2 ~/Downloads/20050311_spam_2.tar.bz2 data/raw/spamassassin/
   mv ~/Downloads/phishing0.mbox ~/Downloads/phishing1.mbox ~/Downloads/phishing2.mbox ~/Downloads/phishing3.mbox data/raw/nazario/
   mv ~/Downloads/20051114.mbox ~/Downloads/private-phishing4.mbox ~/Downloads/phishing-20* data/raw/nazario/
   mv ~/Downloads/enron_mail_20150507.tar.gz data/raw/enron/
   mv ~/Downloads/phishing_pot-main.zip data/raw/phishing_pot/
   chmod a-w data/raw/*/*
   ```
3. Run the scripts from the project root:
   ```bash
   python -m src.data.fetch_apache
   python -m src.data.unpack
   python -m src.data.stage
   python -m src.data.coverage
   python -m src.data.split
   python -m src.preprocess.build
   python -m src.headers.build
   ```

About 1 GB is downloaded; about 3 GB is used after unpacking (raw Enron alone is 517,401 small files).
