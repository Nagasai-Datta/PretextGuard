# notebooks/

Google Colab notebooks for the one job the Mac cannot do quickly: training the DistilBERT tactic classifier (Phase 6), and optional SemEval pretraining if time allows. Everything else runs as scripts in `src/`.

## Why Colab

Fine-tuning DistilBERT needs a GPU. Colab gives one for free in the browser. The trained model is then downloaded and used on the Mac's CPU, which is fast enough for one email at a time.

## Workflow (Phase 6)

1. The training notebook lives here and is committed to Git, so the training code is part of the project history.
2. The training data (labelled, redacted emails) is uploaded to your Google Drive, not to GitHub: it contains email text.
3. In Colab: open the notebook from GitHub, choose a GPU runtime, mount Google Drive, install the pinned libraries, train.
4. The notebook saves the model files; download them into `artifacts/tactic_model/` on the Mac (see `artifacts/README.md`).
5. The scores the notebook prints are saved into `results/` by a script, like every other number.

## Version pinning

Colab runs Python 3.12, the same as the project's venv. The first cell of every notebook installs `torch` and `transformers` with exactly the versions pinned in `requirements.txt` (`pip install torch==... transformers==...`). A model trained with one version and loaded with another can fail to load or give different predictions, so the two sides must always match.

## Rules

- Keep printed outputs short before committing; never commit outputs that contain email text.
- No email data and no model weights in this folder.
