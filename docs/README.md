# docs/

Project documents.

| File | What it is |
|---|---|
| `master_document.md` | The living master document and single source of truth: problem, novelty, architecture, data plan, security, evaluation, build plan, decisions log. Updated at the end of every phase with a new version number |
| `PretextGuard_Master_Document.docx` | The Word copy of the master document (version 3.15.6), for readers who prefer Word. `master_document.md` is the source and wins if the two differ; the Word copy is rebuilt at the end of a phase (below) |
| `tools/build_docx.py` | Rebuilds the Word copy from `master_document.md` |
| `Project_Explained.docx`, `Project_Explained.pdf` | The whole project explained end to end, in 16 parts and a glossary, for a reader who knows only basic machine learning and web development: the background, the idea, how it works, one email and one thread followed through the code, the data, the security, how it was built, every result and what it means, the paper, and how to explain it. Start here to understand the project |
| `PretextGuard_Context.md` | The handover file for a new AI chat: working agreement, environment, current state and the exact next task. Every new chat starts from this file and the master document |
| `paper/` | The conference paper: the draft (Paper_Draft.docx and .pdf), the IEEE template, the verified source table, the literature notes and the drafting brief (see `paper/README.md`) |
| `figures/` | The five figures used in the master document, the README and the report; `figures/results/` holds the 13 result charts drawn from `results/` by `python -m src.eval.charts` (Phase 13) |

Figures:

| File | Shows |
|---|---|
| `figure1_attacker_positions.png` | Which verifier catches which attacker (outside impersonator vs inside a real account) |
| `figure2_architecture.png` | The claim-routed verification architecture |
| `figure3_runtime_workflow.png` | The eight steps of one analysis request |
| `figure4_module_map.png` | Code modules and how they feed each other |
| `figure5_build_vs_run.png` | Build time versus run time |

`CLAUDE.md` in the project root points Claude Code at the context file, so a Claude Code session loads it automatically.

## Exporting a .docx

```bash
brew install pandoc        # once
cd ~/Desktop/pretextguard
python -m pip install python-docx
python docs/tools/build_docx.py
```

The script runs pandoc on a prepared copy of the Markdown (the first table is converted, the title block is styled, duplicate figure captions are dropped), then styles the tables (header shading, column widths, small type) and adds page numbers. A plain `pandoc` export of the file works too but drops the first table and is unstyled.

## Status

The project is closed (master document version 3.15.6). The faculty evaluates it from the conference paper in `paper/`, so Phase 14 (the report, the viva preparation and the Review deck) was cancelled.
