# docs/

Project documents.

| File | What it is |
|---|---|
| `master_document.md` | The living master document and single source of truth: problem, novelty, architecture, data plan, security, evaluation, build plan, decisions log. Updated at the end of every phase with a new version number |
| `PretextGuard_Master_Document.docx` | The Word copy of the master document (version 3.15.1), for readers who prefer Word. `master_document.md` is the source and wins if the two differ; the Word copy is rebuilt at the end of a phase (below) |
| `tools/build_docx.py` | Rebuilds the Word copy from `master_document.md` |
| `PretextGuard_Context.md` | The handover file for a new AI chat: working agreement, environment, current state and the exact next task. Every new chat starts from this file and the master document |
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

## Still to come (Phase 14)

The final report, viva preparation notes and the updated Review deck.
