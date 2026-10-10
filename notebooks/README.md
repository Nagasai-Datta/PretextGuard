# notebooks/

Google Colab notebooks for the one job the Mac cannot do quickly: training DistilBERT models (the tactic classifier in Phase 6, the two N1 models in Phase 13). Optional SemEval pretraining would be another notebook, only if time allows. Everything else runs as scripts in `src/`.

| Notebook | Phase | Job |
|---|---|---|
| `phase6_tactic_classifier.ipynb` | 6 | Clones the code, installs the pinned `transformers`, reads the data from Google Drive, runs `src/models/train.py` on the GPU, saves the results to Drive |
| `phase13_n1_models.ipynb` | 13 | The same, for the two N1 models: runs `src/eval/n1_train.py`, which trains model A on the raw view and model B on the redacted view of the email bodies |

## Why Colab

Fine-tuning DistilBERT needs a GPU. Colab gives one for free in the browser. The trained model is then downloaded and used on the Mac's CPU, which is fast enough for one email at a time. The training code is not in the notebook: it is `src/models/train.py`, committed to Git like all other code, so the training is part of the project history. The notebook only prepares the machine and starts it.

## The whole Phase 6 workflow

### 1. On the Mac: install, build the data file, check

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
python -m pip install -r requirements.txt
python -m src.eval.metrics
python -m src.models.dataset
```

`python -m src.models.dataset` writes `data/processed/tactic_data.parquet`: the train and validation emails (full text) with their seven labels, no test rows. Commit and push the code (not the data file; it is ignored by Git), because the notebook clones the code from GitHub.

### 2. Upload one file to Google Drive

In the browser: Google Drive, New, Folder, name it `pretextguard`, open it, then drag `tactic_data.parquet` in. In Terminal, `open data/processed` shows the file in Finder. The file holds full email text: it goes only to your own Drive.

### 3. On Colab

1. Open <https://colab.research.google.com>, File, Open notebook, tab GitHub, enter `Nagasai-Datta/PretextGuard`, choose `notebooks/phase6_tactic_classifier.ipynb` (or File, Upload notebook, and pick the file from the Mac).
2. Runtime, Change runtime type, **T4 GPU**, Save.
3. Runtime, Run all. Colab asks once for permission to read your Drive (cell 3). Cell 4 trains and takes the longest: about 30 to 45 minutes of GPU time (an estimate; three seeds of each of two conditions, with early stopping).
4. When the last cell has printed the zip path, open the `pretextguard` folder in Google Drive and download `phase6_outputs.zip` (about 250 MB; if Drive warns that it cannot scan the file for viruses, choose Download anyway).

### 4. Back on the Mac: put the files in place and validate

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
mkdir -p ~/Downloads/phase6_outputs
unzip -o ~/Downloads/phase6_outputs.zip -d ~/Downloads/phase6_outputs
mv ~/Downloads/phase6_outputs/tactic_model artifacts/tactic_model
mv ~/Downloads/phase6_outputs/tactic_training_log.csv results/tactic_training_log.csv
mv ~/Downloads/phase6_outputs/tactic_seed_summary.csv results/tactic_seed_summary.csv
mv ~/Downloads/phase6_outputs/tactic_val_probs.csv results/tactic_val_probs.csv
mv ~/Downloads/phase6_outputs/tactic_run_info.json results/tactic_run_info.json
python -m src.models.validate
```

`validate.py` prints the validation scores and the PASS/FAIL checks and writes `results/tactic_validation_scores.csv` and `results/tactic_checks.csv`. Commit the files in `results/` (counts, scores and probabilities, never email text); the model folder in `artifacts/` is ignored by Git.

## What each cell does

| Cell | Job |
|---|---|
| 1 (code) | Prints the PyTorch version and checks a GPU is attached; stops with a message if not |
| 2 (code) | Clones the public repository into `/content/PretextGuard`, reads the `transformers` pin from `requirements.txt` and installs exactly that version, prints the versions in use and the code's commit |
| 3 (code) | Mounts Google Drive, reads `tactic_data.parquet`, prints the number of emails per origin and split, and stops if a test row is in the file |
| 4 (code) | Runs `python -m src.models.train`: two conditions, three seeds, an epoch line each with the training loss, validation loss and validation macro-F1 |
| 5 (code) | Prints the seed table and the thresholds, and plots the chosen model's training and validation loss (the overfitting watch) |
| 6 (code) | Zips the output folder into `phase6_outputs.zip` in the Drive folder |

## Version pinning

The project's venv runs Python 3.12; Colab's own Python can differ (the Phase 6 run had Python 3.13), which does not matter for the saved weights. Cell 2 installs the `transformers` version pinned in `requirements.txt`, so the model files are written and read by the same library on both sides.

`torch` is the exception: it is **not** reinstalled on Colab. Colab already has a build that matches its GPU driver, and reinstalling the pinned version would be a download of several gigabytes that could mismatch the driver. The Mac pins `torch` 2.14.1, Colab used its own (2.11.0 in the Phase 6 run). Both versions are recorded in `results/tactic_run_info.json` and `results/tactic_checks.csv`, and the Mac check `mac_reproduces_colab` shows in practice that the two sides give the same predictions (the Phase 6 run: largest difference 0.000001). Weights are stored as plain numbers in `.safetensors`, so they do not depend on the torch version.

## If something goes wrong

| Symptom | Fix |
|---|---|
| Cell 1 stops: no GPU | Runtime, Change runtime type, T4 GPU, then Run all again. Free GPU time is limited per day; try again later if Colab refuses |
| Cell 2: `git clone` fails | The code must be pushed to GitHub first, on the branch named in `BRANCH` |
| Cell 3: file not found | The path is `MyDrive/pretextguard/tactic_data.parquet`; check the folder name and that the upload finished |
| `ModuleNotFoundError: No module named 'src'` | Run cell 2 first: it moves into `/content/PretextGuard`, where `src/` is |
| The session disconnects during cell 4 | Run all again; the run starts from scratch (a few minutes lost per finished seed) |
| Hugging Face warns about a newly initialised classifier | Expected: the seven-output layer is new and is what we train. `train.py` stops by itself if anything else failed to load |

## Phase 13: the two N1 models

The N1 ablation (master document Section 4.2) needs two DistilBERT models that differ only in what they read: **model A** the raw body (links, addresses and file names as they were), **model B** the redacted body (`[URL]`, `[EMAIL]`, `[DOMAIN]`, `[FILE]`). The training code is `src/eval/n1_train.py`; the notebook `phase13_n1_models.ipynb` follows the same seven steps as Phase 6, with these differences:

- **The data file** is `n1_data.parquet`, made on the Mac with `python -m src.eval.n1_data`: a training sample of at most 800 emails per source and category (about 9,000 emails) and a stratified validation sample of 3,000, with both views of every email. It holds train and validation rows only; the test split never goes to Colab. Upload it to the same Drive folder `pretextguard`.
- **The run** trains each model with seeds 42 and 43 for two epochs (fp16 on the T4) and keeps, for each model, the seed and epoch with the best attack-class F1 on the validation sample at the fixed threshold 0.5. Expect about 40 minutes (an estimate; the time per epoch is printed).
- **The output** is `phase13_outputs.zip` in the Drive folder: `n1_model_a/`, `n1_model_b/` (about 255 MB each), `n1_training_log.csv`, `n1_val_probs.csv` and `n1_run_info.json`.

### Phase 13: back on the Mac

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
mkdir -p ~/Downloads/phase13_outputs
unzip -o ~/Downloads/phase13_outputs.zip -d ~/Downloads/phase13_outputs
mv ~/Downloads/phase13_outputs/n1_model_a artifacts/n1_model_a
mv ~/Downloads/phase13_outputs/n1_model_b artifacts/n1_model_b
mv ~/Downloads/phase13_outputs/n1_training_log.csv results/n1_training_log.csv
mv ~/Downloads/phase13_outputs/n1_val_probs.csv results/n1_val_probs.csv
mv ~/Downloads/phase13_outputs/n1_run_info.json results/n1_run_info.json
```

The weights stay out of Git (`artifacts/` is ignored); the three small files in `results/` are committed. `python -m src.eval.ablation_n1` later checks that the Mac's CPU reproduces the probabilities Colab recorded (the check `mac_reproduces_colab`), as in Phase 6, with one difference: the N1 models are scored on the GPU in half precision (fp16) and on the Mac in full precision, so the tolerance is 0.005 instead of 0.001 (the first real run showed 0.0012, which is rounding; a wrong model or text would differ by tenths) and a second check requires that no decision at the cut of 0.5 differs unless Colab's probability lies within the tolerance of the cut. The files are part of the freeze record (`src/eval/freeze.py`), so run `python -m src.eval.freeze --write` only after they are in place.

## Rules

- Keep printed outputs short before committing; never commit outputs that contain email text.
- No email data and no model weights in this folder.
