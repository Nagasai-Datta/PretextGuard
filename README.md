# PretextGuard

Payload-free pretexting detection through claim verification.

BCSE410L Cyber Security, VIT Vellore. Problem statement 37: Pretexting Pattern Classifier from Email Metadata.

PretextGuard reads what an email claims about itself (who is writing, which organisation they represent, what they are asking for) and checks each claim against evidence the email cannot easily fake: its own headers and its own conversation history. A claim that the evidence contradicts is the detection.

## Status

Phase 0 (environment and repository). The master document in `docs/` holds the full plan.

## Setup (macOS)

Needs Python 3.12 (Homebrew `python@3.12`) and Git.

```bash
cd ~/Desktop/pretextguard
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env    # then fill in real values
```

## Checks

```bash
pytest       # smoke tests and unit tests
pip-audit    # known vulnerabilities in installed packages
```

## Layout

| Folder | Holds |
|---|---|
| `src/` | All project code, one package per module |
| `tests/` | pytest tests |
| `data/` | Datasets; `raw/` and `processed/` are not committed |
| `artifacts/` | Trained model weights (not committed) |
| `results/` | Evaluation outputs and charts (committed) |
| `notebooks/` | Colab training notebooks |
| `frontend/` | React + Vite + Tailwind UI (Phase 12) |
| `docs/` | Master document, report, slides |

## Privacy

Submitted email content is processed in memory only. There is no database, and email content is never logged or written to disk.
