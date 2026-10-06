# artifacts/

Trained model files: the only thing that crosses from build time to run time.

## What will be stored here

| Path | Contents | Phase |
|---|---|---|
| `artifacts/tactic_model/` | The fine-tuned DistilBERT tactic classifier: its weights (the learned numbers), configuration and tokenizer files | 6 |

Later phases may add small fitted files (for example score calibration) if they are too large or too derived to keep in `results/`; each will be listed here.

## Why it is not committed

- **Size:** a DistilBERT model is about 250 MB; Git and GitHub are not built for large binary files.
- **Derived data:** the weights are learned from licensed email datasets, so they are rebuilt locally rather than redistributed.
- `.gitignore` ignores everything in this folder except this README (`artifacts/*` with `!artifacts/README.md`), and also ignores `*.pt`, `*.bin` and `*.safetensors` anywhere.

## How to rebuild

1. Rebuild the data (see `data/README.md`) and run the Phase 2 to 5 scripts.
2. Run the Phase 6 training notebook on Google Colab (see `notebooks/README.md`).
3. Download the saved model folder into `artifacts/tactic_model/`.

Until Phase 6 this folder holds only this README.
