# docs/

Project documents.

| File | What it is |
|---|---|
| `master_document.md` | The living master document and single source of truth: problem, novelty, architecture, data plan, security, evaluation, build plan, decisions log. Updated at the end of every phase with a new version number |
| `PretextGuard_Master_Document_v3.2.docx` | A styled Word snapshot of version 3.2. It is not updated; export a fresh one when needed (below) |
| `PretextGuard_Context.md` | The handover file for a new AI chat: working agreement, environment, current state and the exact next task. Every new chat starts from this file and the master document |
| `figures/` | The five figures used in the master document, the README and the report |

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
pandoc docs/master_document.md --resource-path=docs -o docs/PretextGuard_Master_Document.docx
```

`--resource-path=docs` tells pandoc that the figure paths in the document (`figures/...`) are relative to `docs/`, so the figures end up inside the .docx.

## Still to come (Phase 14)

The final report, viva preparation notes and the updated Review deck.
