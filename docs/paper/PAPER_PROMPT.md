# Drafting brief for the conference paper

This file is the prompt for drafting the paper. Open a new chat in the claude.ai project "cybersec", attach `conference-template-a4.docx` (the binary file from this folder, because the project holds only a text copy of it), and paste everything under "The prompt" below. The chat plans first and waits for a go-ahead before it writes.

Two notes that hold for the whole paper:

- **The repository is not put anywhere in the paper.** No GitHub link, no "code is available at", no repository or project name, no footnote pointing to it. The project's name, PretextGuard, does not appear either.
- **The title is for the paper only.** The repository and the project keep their names.

---

## The prompt

You are drafting an IEEE conference paper with Nagasai. Read this brief in full before doing anything else.

### 1. The paper

- **Title:** Detection of Payload-Free Pretexting Emails Through Claim-Routed Verification Against Email Headers and Thread History
- **Format:** IEEE conference paper, 6 pages including references, A4, two columns, written in the attached `conference-template-a4.docx` with its styles kept.
- **Name of the system:** "the claim-routed verification pipeline", or "the pipeline" for short. Never PretextGuard.
- **The repository is not mentioned anywhere in the paper:** no link, no availability statement, no repository or project name.
- **Authors, affiliations, e-mail addresses, the venue and whether review is double-blind:** ask Nagasai. Never invent them; leave a marked placeholder until he answers.

### 2. Sources, in order of authority

1. `docs/master_document.md` in the repository github.com/Nagasai-Datta/PretextGuard (version 3.15.3 or later). Read it; never commit, push or change anything there. If the copy in the claude.ai project differs, the repository wins.
2. The result files in `results/` named in master document Section 8.21 and in `src/eval/README.md`. Every number in the paper comes from one of these files or from Section 8.21, exactly as written there.
3. `docs/paper/Source_Table.docx` (text copy in the project: `claude/Source_Table_Pretexting_Paper.md`). The only references the paper may cite, each only for what its row says it supports. Prefer the rows marked Core.
4. `docs/paper/Literature_Notes.docx` (text copy: `claude/Literature_Notes_Pretexting_Paper.md`). What each close neighbour actually did, how the pipeline differs, a draft sentence for each, the plan for Section II, and the lines the paper must not cross (its Section 5).
5. The 13 charts in `docs/figures/results/` and the architecture figure `docs/figures/figure2_architecture.png` (corrected in 3.15.3: the tactic classifier sits beside the claim extractor).

Master document sections to read closely: 3 (problem and threat model; 3.3 has the two attacker positions), 4 (what is claimed and what is not), 5, 6.1 to 6.7 (architecture, routing table, header signals, risk score, worked example), 7 (tactics), 8.1 to 8.6 (data, labels, style confound, splits), 8.21 (all results, "Reading of the results" and "Known limits") and 15 items 26 to 28.

### 3. Binding rules

1. **Never fabricate.** No invented results, citations, statistics, sample sizes, user studies or comparisons.
2. **Never overstate.** Section 8.21 ("Reading of the results", "Known limits") and Section 15 items 26 to 28 are binding. Where an interval includes 0, no system is called better. The claim-routed score is not the best pooled detector, and the paper says so in the abstract, the results and the conclusion.
3. **State the sample wherever an evaluation number appears**, for example: 140 labelled test emails with LLM labels from one model family; 25 Apache and 51 Enron synthetic takeover cases on real threads; 31 synthetic colleague-impersonation pairs; one N1 training sample of 9,856 emails (2,400 attacks) and two seeds; corpus labels for N1.
4. **Numbers exactly as the files give them**, intervals included, for example F1 0.238 [0.204, 0.277]. Money in US dollars as the primary report gives it ($3,046,598,558 in BEC losses, IC3 2025).
5. **Cite only what the source table and the notes support.** IEEE style as the template asks: numbered in square brackets in order of first citation; all authors up to six, then et al.; titles in sentence case. The bracketed IDs of the notes (for example [A6]) are replaced by these numbers.
6. **Keep it at the level of the idea.** Libraries and frameworks appear in one short implementation paragraph at most. No web interface, API or deployment details beyond one sentence.
7. **Tone:** formal and plain. No em dashes. Avoid showcase, underscore, testament, leverage, seamless, robust, cutting-edge and delve. Run the humanizer skill as the last pass.
8. **Free sources only.** If a source is needed that is not in the source table, say so and ask Nagasai for a link or DOI; it is checked and added to the table before it is cited.

### 4. What the paper claims, and what it does not

Claims the evidence supports:

- **The design.** Typed claims extracted from the body are routed to the header rules or the thread rules that can test them, and each finding is a ledger row naming the claim, the rule and the evidence. Every email the routed score flags has a claim, a rule and evidence behind it (442 of 442; the flat classifier's 1,819 flags name none). This is a property of the design, not a measured gain.
- **N1, the payload-free protocol.** Part of a raw-trained detector's accuracy is link-reading: A's drop minus B's drop is above 0 in all three model families (DistilBERT +0.073 [+0.061, +0.086]; corpus labels; one training sample of 9,856 emails, two seeds). Training on redacted text keeps most of the accuracy.
- **N2, thread consistency.** On takeover cases that change only the content, the thread verifier detects 18 of 25 Apache and 48 of 51 Enron cases, against 5 of 25 and 0 of 51 for the single-message verifiers; the cases are synthetic messages injected into real threads.
- **The evaluation discipline.** Frozen components and a test log before the test split was read, a bootstrap over groups, a matched false-alarm cut, per-source tables and a style-confound test.

Results the paper reports as they are:

- **Pooled detection (N3 and architecture).** The claim-routed score is behind every comparator: F1 0.238 against 0.639 (text only), 0.788 (headers only), 0.882 (parallel fusion) and 0.658 (flat classifier), and the lowest AUC (0.812 against 0.949 to 0.993), with the three limits Section 8.21 gives for this comparison.
- **Tactics.** The DistilBERT tactic classifier is not distinguishable from the tuned keyword baseline (macro-F1 0.479 against 0.500, difference -0.021 [-0.144, +0.091], 140 labelled test emails, LLM labels from one model family).
- **Synthetic colleague impersonation.** 19 of 31 attacks flagged with 0 of 31 twins, while headers only flags 31 of 31 twins (31 synthetic pairs, synthetic headers).
- **Score budget.** Within the false-alarm budget in 4 of 5 judged groups; kaggle_ceas08 is over.

Never claim: that the pipeline is the best detector; that it is the first to compare a claimed sender with the headers (ChatSpamDetector did so with a language model); that no thread-hijack detector exists (write "we did not find"); anything in Section 5 of the literature notes.

Take every number from the file or from Section 8.21 when it is written into the paper; the numbers in this brief show which results matter, they are not the source.

### 5. Structure and page budget (6 pages)

| Part | Space | Content |
|---|---|---|
| Title, authors, abstract (150 to 200 words), index terms | 0.35 page | Problem, idea, the honest headline results with samples, including that the pipeline is not the best pooled detector |
| I. Introduction | 0.6 page | Payload-free pretexting and BEC (IC3 2025, DBIR 2026); why SPF, DKIM and DMARC prove a domain, not a person; the gap; the contributions as in Part 4 |
| II. Related work | 0.6 page | The five paragraphs planned in Section 4 of the literature notes, each ending with how the pipeline differs |
| III. Problem and threat model | 0.35 page | The two attacker positions (master document 3.3), what is in scope, the assumption that only Authentication-Results added on the receiving side are trusted |
| IV. The claim-routed verification pipeline | 1.1 pages | Fig. 1; claim types; routing; header, request and thread rules; the verdict ledger; the risk score in brief; Table I with the worked example of Section 6.7; one implementation paragraph |
| V. Evaluation design | 0.65 page | Data (sources, split), labels (LLM labels, one model family, agreement), the N1, N2 and N3 set-ups and comparators, the protocol |
| VI. Results | 1.05 pages | Table II (N1, N2, N3 and architecture, with intervals and samples); the synthetic pairs; tactics and claims; the budget |
| VII. Discussion and limitations | 0.4 page | Section 8.21 "Known limits", stated plainly |
| VIII. Conclusion | 0.15 page | What holds, what does not, what would test it on real attacks |
| References | 0.65 page | About 22 to 26 entries from the Core rows |

Figures and tables: Fig. 1 is the pipeline, redrawn for the paper from figure 2 of the master document (no project name, no API or interface boxes, readable in greyscale at column width). Table I is the worked example. Table II holds the main results. Add a chart from `docs/figures/results/` only if space remains and it is legible at column width.

### 6. How to work

1. **Plan first.** Read the sources, then send Nagasai a short plan: the outline with word budgets, which number goes where (each with its file and row), which reference goes where, the figure and tables, and any question (authors, venue, blind review). Wait for the go-ahead.
2. **Draft** section by section in a working file, then build the paper in the attached template so its IEEE styles stay (use the docx skill).
3. **Check before delivering:** every number against its file; every citation against the source table and every claim about a cited work against the literature notes; no em dash and none of the avoided words; the humanizer pass; render to PDF and confirm 6 pages or fewer with legible figures and tables.
4. **Deliver** `Paper_Draft.docx` and its PDF as downloads, with the commands to move them into `docs/paper/`. Claude never runs Git; Nagasai commits and pushes.
5. **Be direct.** Say plainly when something is weak, missing or wrong, and recommend an option rather than listing choices.
