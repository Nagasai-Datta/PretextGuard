# docs/paper/

The conference paper written on this project.

- **Title (for the paper only):** Detection of Payload-Free Pretexting Emails Through Claim-Routed Verification Against Email Headers and Thread History
- **Format:** IEEE conference paper, 6 pages, A4, two columns.
- **Name of the system in the paper:** the claim-routed verification pipeline ("the pipeline" for short).
- **The repository is not put anywhere in the paper:** no link, no availability statement, no repository or project name.

## Files

| File | What it is |
|---|---|
| `conference-template-a4.docx` | The IEEE A4 conference template the paper is written in |
| `Source_Table.docx` | Every reference the paper may cite: the IEEE citation, the DOI or link, how and where it was checked (free pages only), its status and what the paper may use it for. 31 references are marked Core |
| `Literature_Notes.docx` | For each close neighbour: what it built, what it showed, how the pipeline differs and the sentence the paper uses; the plan for the related-work section; the lines the paper must not cross |
| `PAPER_PROMPT.md` | The drafting brief: paste it into a new chat in the claude.ai project "cybersec" (with the template attached) to plan and draft the paper |
| `Paper_Draft.docx` | The paper (draft 4, 15 October 2026): 6 pages in the template, Fig. 1, Tables I to III, 28 references; author and venue placeholders |
| `Paper_Draft.pdf` | The same draft as PDF, rendered with a Times-metric font |

## Rules the paper follows

- Every number comes from `results/` through master document Section 8.21, with its sample stated.
- The limits in Section 8.21 ("Reading of the results", "Known limits") and Section 15 items 26 to 28 bind the paper: where an interval includes 0, no system is called better, and the claim-routed score is not described as the best pooled detector.
- A reference is cited only for what the source table and the literature notes say it supports, and only after it was read on a free page.
- The paper reports final results only. How the results were produced, including the logged reruns of 15 October 2026, is recorded in master document Section 8.21 and results/eval_test_log.csv, not in the paper.

The paper is drafted in the claude.ai project "cybersec". Files arrive as downloads and are moved here; Nagasai commits and pushes.
