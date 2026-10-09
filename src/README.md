# src/

All PretextGuard code. Each folder is a Python package (it has an `__init__.py`), one per module of the system.

## The one rule: run from the project root with `python -m`

```bash
cd ~/Desktop/pretextguard
source venv/bin/activate
python -m src.data.stage      # right
```

Never `cd src` and never `python src/data/stage.py`. With `-m`, Python treats the project root as the starting point, so imports such as `from src.data.paths import RAW_DIR` work the same in every script, in pytest and later in the API.

## Package map

| Package | Job | Built in phase | Status |
|---|---|---|---|
| `data/` | Datasets: unpacking, loading, staging, header coverage, split; annotation, labels and synthetic emails; later the thread-hijack benchmark | 1, 5, 9 | Phases 1 and 5 done (see `data/README.md`) |
| `preprocess/` | Cleaning (HTML, quotes, signatures) and N1 redaction | 2 | Done (see `preprocess/README.md`) |
| `headers/` | Email parser and header evidence extractor; organisation domain | 3 | Done (see `headers/README.md`) |
| `baseline/` | Keyword baseline (word lists per tactic, scorer) | 4 | Done (see `baseline/README.md`) |
| `models/` | DistilBERT tactic classifier: data preparation, training (Colab), prediction, validation | 6 | Done (see `models/README.md`) |
| `claims/` | Claim extractor: typed claims with text spans | 7 | Done (see `claims/README.md`) |
| `verifiers/` | Header verifier (N3), request verifier, thread verifier (N2) | 8, 9 | Phase 8 done (see `verifiers/README.md`); the thread verifier is Phase 9 |
| `thread/` | Thread builder and thread signals | 9 | Not started |
| `router/` | Claim router, verdict ledger, risk score, end-to-end pipeline | 10 | Not started |
| `explain/` | LIME word highlights | 10 | Not started |
| `api/` | FastAPI app with the security controls | 11 | Not started |
| `eval/` | Metrics, ablations and charts; writes to `results/` | 6 (metrics), 13 | `metrics.py` done (see `eval/README.md`); the experiments are Phase 13 |

Each package gets its own README in the phase that builds it.

## Conventions

- Every path comes from `src/data/paths.py`; no script types a folder name of its own.
- Scripts read from `data/raw/` and write to `data/processed/` or `results/`. They never change `data/raw/`.
- Every number that goes into the report is printed by a script and saved in `results/`.
- No unit tests per phase: each phase is checked by running its scripts and reading their printed output. `tests/test_environment.py` is the one setup check.
