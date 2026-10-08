# artifacts/

Trained model files: the only thing that crosses from build time to run time.

## What is stored here

| Path | Contents | Phase |
|---|---|---|
| `artifacts/tactic_model/` | The fine-tuned DistilBERT tactic classifier: `model.safetensors` (the weights, the learned numbers), `config.json` (names the seven outputs in order), the tokenizer files and `thresholds.json` (one cutoff per tactic) | 6 |

Later phases may add small fitted files (for example score calibration) if they are too large or too derived to keep in `results/`; each will be listed here.

## Why it is not committed

- **Size:** a DistilBERT model is about 250 MB; Git and GitHub are not built for large binary files.
- **Derived data:** the weights are learned from licensed email datasets, so they are rebuilt locally rather than redistributed.
- `.gitignore` ignores everything in this folder except this README (`artifacts/*` with `!artifacts/README.md`), and also ignores `*.pt`, `*.bin` and `*.safetensors` anywhere.

## Why safetensors

The weights are stored as `model.safetensors`, a format that holds only numbers. The older `.bin` and `.pt` formats are Python pickles, which can run code when loaded. `src/models/predict.py` loads with `use_safetensors=True` and `local_files_only=True` (no downloads, no remote code), and `python -m src.models.validate` fails if a pickle-style file sits in the model folder.

## How to rebuild

1. Rebuild the data (see `data/README.md`) and run the Phase 2 to 5 scripts.
2. `python -m src.models.dataset` builds the file for Colab, which you upload to Google Drive.
3. Run the Phase 6 training notebook on Google Colab (see `notebooks/README.md`).
4. Download `phase6_outputs.zip` and move the model folder into `artifacts/tactic_model/` (the exact commands are in `notebooks/README.md`, section 4).
5. `python -m src.models.validate` checks the model on the Mac.

Without step 4 this folder holds only this README.
