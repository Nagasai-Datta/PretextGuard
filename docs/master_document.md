<!-- Living master document (Markdown). docs/PretextGuard_Master_Document_v3.2.docx is a snapshot of version 3.2; export a fresh .docx with pandoc when needed (docs/README.md). -->

**PretextGuard**

Project Master Document

*Payload-free pretexting detection through claim verification*

**Problem statement:** No. 37, Pretexting Pattern Classifier from Email Metadata

**Course:** BCSE410L Cyber Security, VIT Vellore

**Student:** Marupaka Naga Sai Dattu (Nagasai), Reg. No. 23BCE0757

**Faculty:** Dr. Arun Prasath G

**Version:** 3.14, 10 October 2026

> **This is the single source of truth for the project.** Version 3.14 supersedes version 3.13 and every earlier version, PretextGuard_Project_Plan_v2.md, the novelty and architecture slides in both Review-I decks, and every earlier plan discussed in chat. If anything else disagrees with this document, this document wins.

**Contents**

1\. How to use this document

2\. Project snapshot

3\. Problem and threat model

4\. Novelty (final, locked 21 September 2026)

5\. Prior work and how PretextGuard differs

6\. System architecture

7\. Tactic taxonomy

8\. Data plan

9\. Technology stack

10\. Security design

11\. Evaluation plan

12\. Build plan

13\. Viva preparation

14\. Decisions log

15\. Open items and next actions

16\. Glossary

17\. References

# 1. How to use this document

This document is written so that a person or an AI assistant can pick up PretextGuard with no other context: what the project is, what is novel, how it is built, what data it uses, what has been decided, and what happens next.

## 1.1 Rules for anyone picking this up

- **This document wins conflicts.** Stale sources: PretextGuard_Project_Plan_v2.md (still lists SemEval transfer and the severity model as novelty claims; both were struck), the 16-slide and 11-slide Review-I decks (old novelty lineup), and older chat plans.

- **Suggested read order for a new assistant:** docs/PretextGuard_Context.md first (working agreement, environment, current state and the exact next task), then Section 2 (snapshot), Section 4 (novelty), Section 6 (architecture), Section 12 (build plan) and Section 15 (open items). A new chat has no memory of earlier chats; these two documents are all it needs.

- **Section 4.7 lists dead ideas.** Do not propose them again as novelty.

- **Keep it current.** When a decision changes, update the relevant section, bump the version number, and add a row to the decisions log (Section 14).

- **The project-files copy may be text only.** The claude.ai project can store this document as extracted text, so the figures do not come through. Every figure therefore has a text description directly below its caption.

## 1.2 Working agreement

- **Claude writes all the code and all the explanations, one phase at a time.** Nagasai places the files with the commands Claude provides, runs them in VS Code, and reports results or errors back. Claude never runs Git itself; Nagasai commits and pushes.

- **Every file and every function gets a plain-language explanation** before moving on, including the background theory. The rubric deducts 20 marks if the student cannot explain his own implementation.

- **No code copied from GitHub repositories** (30-mark penalty). Use well-known libraries; write the project logic fresh.

- **Assume little background** outside the MERN stack and basic ML/NLP. Explain Python tooling, FastAPI, DistilBERT and similar from the ground up.

- **Prefer the easiest path that still scores well.** Established libraries over custom implementations.

- **Plan first.** Before any large deliverable, share a short plan and wait for Nagasai's go-ahead.

- **Style for anything delivered to Nagasai:** direct and honest, no em dashes, no filler words such as "showcase" or "testament". Documents as .docx or PDF, not HTML.

- **Commit after each working step, not once per phase.** Small, frequent commits to the GitHub repo are the evidence of original, incremental work; one large commit per phase looks like a paste.

- **Two or three steps per phase.** Each phase is folded into a few larger steps; each step delivers several files at once, followed by one run, one check and one commit (Nagasai found Phase 1's five steps too long).

- **File workflow on macOS.** The project lives at ~/Desktop/pretextguard (iCloud Desktop sync is off). Files arrive as downloads in ~/Downloads whenever the interface can attach files (Nagasai's preference), with one block of mv commands per step that puts each file in its exact place; only when the interface cannot hand over files do they arrive as paste blocks that create each file in place (cat \> path \<\< 'PG_EOF' ... PG_EOF, preceded by setopt NO_BANG_HIST) when the interface cannot hand over files. Dotfiles and small config files are created in the terminal, and files that share a name (such as \_\_init\_\_.py) are created with touch, so no two downloads collide.

- **Change list at the end of every phase.** Claude lists what changed so this document can be kept current.

- **No unit tests per phase.** Each phase is verified by running its scripts and checking their printed output; tests/test_environment.py is the one setup check.

- **Fresh chats.** Any new chat, including Claude Code on the web, starts from docs/PretextGuard_Context.md and this document. Nothing carries over from earlier chats, so both files must stay current.

- **Harvest security marks.** When a design choice also improves security (for example, no database), say so explicitly.

# 2. Project snapshot

<table>
<colgroup>
<col style="width: 23%" />
<col style="width: 76%" />
</colgroup>
<thead>
<tr class="header">
<th><strong>Item</strong></th>
<th><strong>Details</strong></th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>Project name</td>
<td>PretextGuard</td>
</tr>
<tr class="even">
<td>Course</td>
<td>BCSE410L Cyber Security, VIT Vellore (final-year B.Tech CSE)</td>
</tr>
<tr class="odd">
<td>Problem statement</td>
<td>No. 37: Pretexting Pattern Classifier from Email Metadata (picked from a faculty list of 60)</td>
</tr>
<tr class="even">
<td>Type</td>
<td>Individual project. The student must present and explain the work independently.</td>
</tr>
<tr class="odd">
<td>One-line pitch</td>
<td>Pretexting emails carry no link or attachment, so scanners miss them. PretextGuard extracts what an email claims about itself and verifies each claim against the email's headers and its own conversation history. A claim that the evidence contradicts is the detection.</td>
</tr>
<tr class="even">
<td>What gets built</td>
<td>A web app: paste a raw email, or upload a .eml file or a whole thread, optionally give the organisation's domain, and get a 0-100 Pretext Risk Score, highlighted manipulation phrases, a findings table, and plain-English contradictions.</td>
</tr>
<tr class="odd">
<td>Novelty (locked 21 Sep 2026)</td>
<td><p>N1 payload-free evaluation protocol</p>
<p>N2 thread consistency verification</p>
<p>N3 claim-evidence contradiction engine (core)</p>
<p>Architecture contribution: claim-routed verification pipeline</p></td>
</tr>
<tr class="even">
<td>Current status</td>
<td>Phases 0 to 12 complete. Phase 1 built the staged table of 99,324 unique emails from nine sources (20,313 attacks), the header coverage table and a fixed 70/15/15 split. Phase 2 added clean and payload-free (N1) redacted bodies, with no detectable link or address left after redaction and 4,580 naturally link-free attacks. Phase 3 turned every email's headers into evidence for N3: authentication verdicts read only from trusted headers, freemail and lookalike checks, mailing-list and organisation-domain handling. Phase 4 built the keyword baseline: fixed word lists for the seven tactics and a scorer that reads body_redacted, checked by hit rates on the train split (results/keyword_*.csv). Phase 5 labelled 690 real emails for the seven tactics and eleven claim types with two LLM annotators and a tie-breaker (results/label_*.csv), wrote 222 synthetic attack-and-twin pairs for the rare tactics, and recorded the SemEval 23-to-7 mapping. Phase 6 fine-tuned DistilBERT on the seven tactics on Colab (real and synthetic training emails, three seeds, thresholds tuned on validation) and scored it against the keyword baseline on the validation emails, real and synthetic apart (results/tactic_*.csv, Section 8.14). Phase 7 built the claim extractor: spaCy name detection, 85 token patterns and organisation and signature rules turn an email into typed claims of the eleven types of Section 6.4; the patterns were written from the train split only, frozen at version 0.4 and scored once on the validation emails (results/claim_*.csv, Section 8.15). Phase 8 built the header verifier (N3) and the request verifier: 63 rules turn each claim and the header evidence of its email into a ledger row (contradiction, consistent or not checkable, with the evidence, the rule and a reason); the rules were frozen at version 0.3 before the validation emails were read once, 9134 of the 79590 train claims routed to a verifier could be checked, and the contradiction rates and checks are in results/verifier_*.csv (Section 8.16). Phase 9 built the thread verifier (N2): real threads rebuilt from raw Enron (subjects and participants) and the Apache lists (Message-ID, In-Reply-To, References); 44 rules measure tactic onset, request drift, sending-path drift and thread integrity of each message against its own thread and find the message where it flipped; a thread-hijack benchmark of five cases per base thread (real and synthetic negatives, account takeover, look-alike swap, forged thread) tests each signal in its own variant; the rules were frozen at version 0.2 before the validation threads were scored once (results/thread_*.csv and hijack_*.csv, Section 8.17). Phase 10 built the claim router, the verdict ledger, the 0-100 risk score and LIME highlights: analyze() turns a raw email or thread into the report of Section 6.3; score version 0.2 was calibrated against a false-alarm budget on the validation emails (the budget held in 5 of 6 groups; the one miss is a finding), the hijack benchmark and the attack corpora are reported and never fitted, and the LIME highlights passed a deletion test (results/score_*.csv and lime_checks.csv, Section 8.18). Phase 11 put analyze() behind a FastAPI service with five routes and the controls of Section 10 (the key in a header and compared in constant time, per-address rate limits, size caps counted as the bytes arrive, fixed error messages with a request id, a fixed-field audit log); 88 self-test checks passed with a stand-in classifier, the self-test noticed 37 of 37 controls broken on purpose, and a real session with the trained model passed 19 checks (results/api_checks.csv, api_mutations.csv and api_smoke.csv, Section 8.19). Phase 12 built the interface in React, Vite and Tailwind: an analyzer page that shows the score, the findings, the highlighted text, the tactics and how the score was built, and a dashboard of four charts and every result table, all drawn as text through a same-origin proxy that keeps the API key out of the browser and under a strict Content-Security-Policy; 96 static checks passed, the checks noticed 26 of 26 things broken on purpose, and the built app passed 93 checks in a real browser (results/frontend_checks.csv, frontend_mutations.csv and frontend_browser_checks.csv, Section 8.20). Phase 13 (all experiments and charts) is next.</td>
</tr>
<tr class="odd">
<td>Repository</td>
<td>github.com/Nagasai-Datta/PretextGuard (public); local folder ~/Desktop/pretextguard</td>
</tr>
<tr class="even">
<td>Next deadline</td>
<td>Not a planning constraint. Scope is fixed and will not be cut (decision, 22 Sep 2026).</td>
</tr>
</tbody>
</table>

## 2.1 Grading rubric (100 marks)

| **Criterion** | **Marks** | **Where PretextGuard earns it** |
|---|---|---|
| Novelty and innovation | 30 | N1, N2, N3 and the claim-routed architecture (Section 4) |
| Implementation quality | 25 | End-to-end pipeline, model, verifiers, API, UI (Sections 6, 12) |
| Security features | 15 | 27 controls mapped to OWASP (Section 10) |
| Literature survey | 10 | Twelve works, closest competitors cited first (Section 5) |
| System design | 10 | Claim-routed architecture, no-persistence design (Section 6) |
| Testing and performance | 5 | One ablation per claim, claim-extraction accuracy, robustness tests (Section 11) |
| Presentation and viva | 5 | Live demo and prepared answers (Section 13) |

**Penalties:** minus 30 for copied or unoriginal work (for example GitHub code); minus 20 for being unable to explain the implementation; minus 20 for fake or manipulated experimental results.

> **Faculty rule on novelty:** merely changing the user interface, programming language, framework, or database does not count as innovation. Stack choices are argued under System Design and Security Features, never under Novelty.

## 2.2 Review-I (completed)

Review-I ran from 29 July 2026: 20 marks, about 10 minutes per student, no code required. Marks: problem understanding 4, literature and existing work 4, novelty and research gap 6, proposed solution 4, planning 2. Delivered: a 16-slide deck with speaker notes, a prep-notes file, and a slide spec for AI design tools. Nagasai also presented his own edited 11-slide deck (review_1.pptx), with the annotated-email diagram on slide 7.

**Outcome:** the faculty struck the old N2 (SemEval cross-domain label transfer) and the old N4 (tactic-stacking severity model) and asked for at least one more core claim. N1 and N3 survived. Section 4 is the response.

# 3. Problem and threat model

## 3.1 What pretexting is

Pretexting is social engineering built on a made-up identity or scenario. The attacker pretends to be someone trusted ("this is the CFO", "this is your vendor") and the story itself is the attack. The victim does the damage personally: wires the money, changes the bank details, shares the data. Business Email Compromise (BEC) is pretexting aimed at company money.

Running example used throughout the project:

```
From: "David Chen - Finance Director" <d.chen.finance@gmail.com>
Reply-To: finance.dept.acme@protonmail.com
Date: Tue, 14 Jul 2026 02:47 AM
Authentication-Results: spf=pass dkim=pass dmarc=pass (all for gmail.com)

Hi Priya, this is David from Finance. I need you to process a wire
transfer before 3 PM today. I'm in meetings all day and can't take
calls. Please don't loop in anyone else - just get it done.
```

Priya works at acmecorp.com. The real David is her company's Finance Director. Note the authentication line: the attacker sent from a real Gmail account, so SPF, DKIM and DMARC all pass. They prove the message came from gmail.com. They say nothing about whether the sender is David from Acme. Catching that gap is N3's job.

## 3.2 Payload versus payload-free

A **payload** is the part of an email that does technical damage: a malicious link or attachment. Email security scanners are built around payloads: URL blacklists, link sandboxes, attachment detonation. A **payload-free** email has no link and no attachment, so those scanners find nothing. The example above has no link, no attachment, no malware and no typos. The entire attack is three phrases: authority ("this is David from Finance"), urgency ("before 3 PM today") and secrecy ("don't loop in anyone else").

## 3.3 Two attacker positions

![Figure 1. Which verifier catches which attacker](figures/figure1_attacker_positions.png)

*Figure 1. Which verifier catches which attacker*

*Text description: two columns. Left: the outside impersonator uses a fake display name and a freemail, lookalike or spoofed domain. Freemail and lookalike senders pass authentication, but for the wrong domain; an exact-domain spoof of the real company fails DMARC. Either way the headers do not back the claim, and N3 catches it because the body claims an organisation that the authenticated domain does not belong to. Right: the attacker inside a real account (account takeover, vendor compromise, thread hijack) passes authentication for the real domain, but the conversation suddenly changes; N2 catches it because the message contradicts its own thread history, and forged threads are caught there too.*

- **Outside impersonator:** fake display name, freemail account, lookalike domain, Reply-To redirection, or a spoof of the company's exact domain. A freemail or lookalike sender usually passes SPF, DKIM and DMARC for its own domain, so the giveaway is that the authenticated domain does not match the organisation the body claims. An exact-domain spoof fails DMARC when the real company publishes a DMARC policy. Either way the headers do not back the claim. **Caught by N3.**

- **Inside a real account:** account takeover, vendor email compromise, thread hijacking (the Emotet and Qakbot reply-chain style). Mail comes from the real account, so SPF, DKIM and DMARC pass and N3 has nothing to contradict. What changes is the conversation: new urgency, new bank details, a different sending path. **Caught by N2.**

- **Forged thread:** the attacker invents a quoted "previous conversation" that never happened. N2's thread-integrity check catches it, and N3 often fires too because the sender is external.

## 3.4 Why it matters

| **Figure** | **Source** | **Status** |
|---|---|---|
| 21,489 BEC complaints; about \$2.9 billion adjusted losses (2023) | FBI IC3 2023 report | Used in Review-I |
| About \$2.77 billion BEC losses (2024) | FBI IC3 2024, as reported by Abnormal AI | Check the primary IC3 report before citing |
| Pretexting volume more than doubled across recent reporting cycles | Verizon DBIR | Used in Review-I |
| 2026 DBIR classifies thread-based attackers building trust as pretexting | Verizon DBIR 2026, as quoted by IRONSCALES | Check the primary DBIR before citing |
| Under 8% of BEC incidents are found by technical controls | Industry reporting (earlier plan) | Source must be re-verified before the report |

## 3.5 Target users and deployment

Corporate email security teams, secure email gateway vendors, and finance or accounts-payable staff (the people BEC targets). Realistic deployment: an extra check at the mail gateway, or an analyst triage tool that explains why a message is suspicious.

## 3.6 Email and authentication basics (for beginners)

An email is a plain text file: headers (the envelope: who sent it, to whom, how it travelled), a blank line, then the body (the letter). The From line has a display name, which is free text anyone can type, and an address whose part after @ is the domain. Most mail apps show only the display name, which is exactly what pretexting exploits.

| Header | What it is | Analogy |
|---|---|---|
| From | Display name and address shown to the reader | The name printed on the letter |
| Reply-To | Where replies actually go, if different from From | "Please reply to this other address" |
| Return-Path | Where bounces go; the true envelope sender | The return address on the envelope |
| Received | One line added by every mail server on the way | Postmarks from each post office |
| Authentication-Results | The receiving server's SPF, DKIM and DMARC verdicts | The post office's inspection stamp |
| Message-ID | Unique ID of this email | A tracking number |
| In-Reply-To, References | IDs of the earlier emails in the conversation | "Re: your letter no. 123" |

**SPF:** the domain publishes the list of mail servers allowed to send for it, and the receiver checks the sending server against that list. **DKIM:** the sending server signs the message with a private key whose public half the domain publishes; a valid signature proves the domain signed it and nobody altered it. **DMARC:** passes when SPF or DKIM passed for a domain that matches the visible From domain, and tells receivers what to do on failure. The receiving server writes all three verdicts into Authentication-Results; PretextGuard reads them.

**The key idea:** authentication proves which domain sent an email, not who the person is. A real Gmail account passes all three checks, so an email claiming to be Acme's Finance Director that authenticates as gmail.com passed authentication for the wrong domain. Spotting that mismatch is N3's job.

# 4. Novelty (final, locked 21 September 2026)

## 4.1 Summary

| **ID** | **Name** | **What it does** | **How we prove it** |
|---|---|---|---|
| N1 | Payload-free evaluation protocol | Removes URLs, domains and attachment file names from email bodies before any model sees them. | Ablation on binary attack-vs-benign detection: model A (raw bodies) vs model B (redacted bodies), each tested on the raw, redacted and naturally link-free views of the same held-out set. A's drop from raw to redacted measures how much prior accuracy was link-reading. |
| N2 | Thread consistency verification | Checks a message against its own thread history (tactic onset, request drift, sending-path drift, thread integrity) and points to the message where the thread flipped. | Detection with vs without the thread verifier on the thread-hijack benchmark, plus hijack-point localisation accuracy. Content signals on real Enron threads, header signals on real Apache mailing-list threads. |
| N3 (core) | Claim-evidence contradiction engine | Checks affiliation, identity and authority claims in the body against what the headers can prove. The header check is conditioned on the claim. | Full system vs text-only vs headers-only vs parallel score fusion (BEC-Guard style). Real positives from affiliation claims in Nazario and Nigerian Fraud; colleague impersonation from synthetic BEC, reported separately. |
| Architecture | Claim-routed verification pipeline | Claims are typed and routed to the verifier that can check them. Output is a ledger of claim, evidence and contradiction. | Same signals wired as a flat classifier vs claim-routed: accuracy, false positives, share of findings with a traceable reason. |

> **Viva line:** "N3 catches the impersonator. N2 catches the attacker who does not need to impersonate, because he is already inside the account." Design principle: PretextGuard never trusts what an email says about itself, and authentication proves which domain sent a message, not who the person is.

## 4.2 N1: payload-free evaluation protocol

**What:** before training or inference, the body is redacted. URLs become \[URL\], email addresses become \[EMAIL\], attachment file names become \[FILE\], bare domains become \[DOMAIN\] (Section 8.10). Words such as "see attached" stay, because they are language, not payload.

**Why:** machine learning models take the cheapest shortcut to a correct answer. In phishing datasets, a suspicious link predicts the label, so a model can reach 97 to 99% by reading links instead of manipulation. Real pretexting has no link, so the shortcut does not exist in the real attack.

**Experiment:** the task is binary attack-vs-benign detection, because the shortcut claim is about phishing detectors. Train model A on raw bodies (prior-work style) and model B on redacted bodies, both DistilBERT; a TF-IDF plus logistic regression pair is a cheap second check. Test both on three views of the same held-out set: raw, redacted, and the naturally link-free subset (emails that had no URL before redaction). Phase 2 measured the test split: 696 attacks and 5,880 benign emails are naturally link-free (results/preprocess_checks.csv). The hypothesis is that A drops sharply from raw to redacted and B holds. Report the measured numbers whatever they are.

## 4.3 N2: thread consistency verification

**What:** when an email arrives inside a thread, it is compared with the earlier messages in that same thread. A legitimate thread changes gradually; a hijacked one flips at one message.

| **Signal** | **What is compared** | **Attack example** |
|---|---|---|
| Tactic onset | Tactic probabilities of the new message vs the average of earlier messages in the thread | Three weeks of calm invoice emails, then urgency and secrecy appear |
| Request drift | Payment details, account numbers and credential requests vs everything earlier in the thread | "We changed banks, please use this new account" |
| Sending-path drift | First Received hop, mail client (X-Mailer), sender domain vs the same sender's earlier messages | Same address but a different origin server and client; or a lookalike domain swapped in mid-thread |
| Thread integrity | In-Reply-To and References must point to real earlier Message-IDs; quoted history must match the real earlier text | A fabricated "previous conversation" with no matching Message-IDs |
| Style drift (optional, dropped first) | Greeting, sign-off and function-word profile vs the sender's earlier messages | The reply is suddenly written in a different voice |

**Output:** the index of the message where the thread flipped, and the signals that fired.

**Input modes:** thread mode needs the earlier messages (several .eml files or one .mbox). In single-email mode N2's history checks are skipped, but In-Reply-To and quoted-text integrity checks still run when that data is present.

**Evaluation data:** raw Enron has no In-Reply-To, References, Received or X-Mailer headers (0% of 517,401 messages, Phase 1 header coverage table), so its threads can only test the content signals (tactic onset, request drift). The header signals (sending-path drift, thread integrity) are tested on public Apache project mailing-list archives, which keep those headers. Both are real threads, and the report states the split. Phase 9 refined it: raw Enron has no reply IDs or sending-path data but its quoted history exists, so Enron threads test tactic onset, request drift and the quote check, while Apache threads test all four signals (Section 8.17).

**Why it is novel:** academic detectors classify single emails. The closest work on compromised accounts (Ho et al., USENIX Security 2019) is URL-based and needs organisation-wide mailbox data. Conversation-level social-engineering detection exists for chat (ConvoSentinel) but uses no email headers. Commercial tools (Abnormal AI, IRONSCALES) do behavioural thread analysis but are closed and depend on login telemetry. An open, explainable, payload-free detector that works at email-thread level with thread headers was not found.

## 4.4 N3: claim-evidence contradiction engine (core)

**What:** the body makes claims; the headers provide evidence. N3 checks each affiliation, identity or authority claim against the evidence that could confirm or contradict it. An affiliation claim is any statement that the sender represents an organisation: the recipient's own company (internal) or an outside one such as a bank, a vendor or a government office (external).

| **Claim in the body** | **Example** | **Evidence checked** | **Contradiction when** |
|---|---|---|---|
| Internal affiliation | "This is David from Finance"; signature says Acme | Authenticated From domain vs organisation domain; SPF, DKIM, DMARC; freemail list; lookalike distance | Claims to be internal but the authenticated domain is external, freemail or a lookalike; or the From shows the organisation's own domain but DMARC fails (exact-domain spoof) |
| External affiliation | "Director of Foreign Operations, Central Bank"; "PayPal Security Team" | Claimed organisation name vs sending domain (rapidfuzz); a small list of known brand domains; authentication | The sending domain does not belong to the claimed organisation |
| Authority or rank | "As CFO I need this today" | Display name vs address; lookalike distance to organisation domains | Rank claimed from a freemail, lookalike or unauthenticated sender |
| Reply direction | "Reply to me directly" | Reply-To vs From | Reply-To points to a different domain |
| Contact details in signature | Signature email or phone | Signature email vs From address | The signature address differs from the sending address |
| Prior relationship | "As we discussed on the call" | Handed to the thread verifier (N2) | No such conversation exists |

**Tactics without verifiers:** urgency, secrecy, scarcity, reciprocity, social proof and liking cannot be proven or disproven by headers. They act as modifiers: they raise the weight of any contradiction that is found.

**Conditioning, in two examples:** spf=fail on a newsletter is low risk. spf=fail on a message claiming to be the CFO and ordering a payment is high risk. The reverse also holds: dmarc=pass on a Gmail message is normal, but dmarc=pass on a Gmail message claiming to be Acme's Finance Director is a contradiction, because authentication passed for the wrong domain. Same header values, different meaning, and the only thing that changed is the claim. BEC-Guard runs a header classifier and a body classifier in parallel and combines their scores. Adding two scores cannot express "the body claims X and the headers disprove X", because the scores do not know they are about the same claim.

**Organisation domain:** internal-affiliation checks need the organisation's own domain(s). The UI and API take them as an optional field that defaults to the recipient's domain from the To header; datasets use the To domain. When it is missing or anonymised, internal-affiliation checks are recorded as not checkable instead of guessed. Phase 3 also treats collector mailboxes, placeholder domains and free mailboxes in To as giving no organisation domain (Section 8.11). External-affiliation checks do not need it.

## 4.5 Architecture contribution: claim-routed verification pipeline

Most detectors, including the old v1 plan, work as email to features to classifier to score, with an explanation added afterwards. PretextGuard works like a fact-checking pipeline (claim detection, evidence retrieval, verdict), applied to email, where the evidence is protocol metadata and conversation history instead of documents.

1.  **Claim-first evidence.** The body decides which evidence gets checked. Evidence is gathered per claim, not all at once and blended. This is the general form of N3's conditioning.

2.  **Explanation by construction.** The output is the reason: "claims to be Acme Finance; authenticates only as gmail.com". LIME is reduced to one job, highlighting which words triggered each tactic.

3.  **Extensible.** A new attack pattern means adding one verifier function. The NLP model does not need retraining.

| **Architecture style** | **Example** | **Weakness** |
|---|---|---|
| End-to-end classifier | Two-Stage Framework (MDPI Computers, 2025) | Score first, explanation bolted on afterwards |
| Parallel fusion | BEC-Guard (USENIX Security 2019) | Two scores added; a claim cannot be linked to the evidence against it |
| Claim annotation only | Mithun et al. (2024) | Marks claims but leaves verification to a future algorithm |
| Claim-routed verification | PretextGuard | (this project) |

It is presented on the architecture slide as the system design the three claims live inside, not as a fourth numbered claim, so it cannot be dismissed as padding.

## 4.6 Plain components (kept, not claimed as novelty)

- **Pretext Risk Score 0-100:** the old N4 idea, kept as the output the UI needs.

- **SemEval-2023 Task 3 pretraining:** the old N2 idea, optional; run only if time allows.

- **Isolation/Secrecy as a seventh tactic** (not a Cialdini principle; see Section 7): a design choice worth mentioning in the report, not a numbered claim.

- **LIME word highlights** and the **keyword baseline**.

## 4.7 Dead ideas: do not propose again

| **Idea** | **Status** | **Why** |
|---|---|---|
| v1: DistilBERT on LLM-generated emails labelled with Cialdini principles | Scrapped, July 2026 | Near-duplicate of the Two-Stage Framework paper (MDPI Computers 14(12):523, 2025) |
| Old N2: SemEval-2023 cross-domain label transfer as novelty | Struck by faculty after Review-I | Kept only as optional pretraining |
| Old N4: tactic-stacking severity model as novelty | Struck by faculty after Review-I | Kept only as the plain 0-100 score |
| Stack choices as novelty (FastAPI, React, no database) | Never valid | Excluded by the faculty rule |
| "Dual-reference verification" as a separate numbered claim | Merged | Became the architecture contribution |
| Tactic co-occurrence analysis as novelty | Not valid | Already done by Pan et al. (2026) and Ferreira and Teles (PPSE) |

# 5. Prior work and how PretextGuard differs

> **Gap statement:** existing persuasion-based detectors score single emails that usually carry payloads, and none verifies what an email claims against its own metadata or conversation history. The attacks that most need this, payload-free pretexting from spoofed senders and from hijacked accounts, are exactly the ones they do not isolate.

| **Work** | **What it does** | **Where PretextGuard differs** |
|---|---|---|
| Karki, Abri, Siami Namin, Jones (2022). IEEE Big Data, pp. 2841-2848 | BERT, RoBERTa and DistilBERT classify Cialdini principles in phishing emails | Payload-bearing phishing, body only; no metadata, no verification |
| Two-Stage Deep Learning Framework (2025). MDPI Computers 14(12):523 | 2,995 GPT-generated phishing emails labelled with Cialdini principles; DistilBERT then a dense network | Emails and labels both LLM-made; payload-bearing; body only. Closest competitor to the old v1 |
| Pan, Yang, Cole, Wilson, Woodard (2026). Expert Systems with Applications | 340,912 emails annotated by 4 LLMs under 3 prompting strategies; persuasion cue interactions | Analysis study, not a detector; no header or thread verification. Our precedent for LLM-assisted annotation |
| Valecha, Mandaokar, Rao (2022). IEEE TDSC 19(2):747-756 | Phishing email detection using persuasion cues | Content cues only; no claim verification against metadata |
| Aggarwal, Kumar, Sudarsan (2014). SIN '14, ACM, pp. 217-222 | Detects link-free phishing that baits the victim into replying with sensitive data, using content features such as no recipient name, a money offer and a reply prompt | Scores scam content only; does not check who the sender claims to be against headers or thread history; no colleague impersonation or hijacked threads. Closest prior work on the payload-free angle |
| Mithun, Bartlett, Mirkovic, Freedman (2024). arXiv:2405.12494 (USC ISI) | 940 emails annotated with 32 weak explainable phishing indicators, including sender affiliation claims; argues mismatches are stronger signals than content | Annotates claims but explicitly leaves verification to a future downstream algorithm and does not propose a detector. PretextGuard builds that verifier. Must be cited. |
| Cidon et al. (2019). BEC-Guard, USENIX Security | Header classifier and body classifier in parallel, scores combined | Additive fusion; no claim-conditioned checks; no thread consistency |
| Ho et al. (2019). Detecting and Characterizing Lateral Phishing at Scale, USENIX Security | Phishing sent from compromised enterprise accounts; 113M emails, 92 organisations | URL-based only and needs organisation-wide mailbox data; the authors state it misses narrow, stealthy content-level attacks |
| Ai et al. (2024). ConvoSentinel, arXiv:2406.12263 | Message-level and conversation-level social-engineering detection | Chat, not email; no header or thread-integrity evidence |
| Piskorski et al. (2023). SemEval-2023 Task 3 | 23 persuasion techniques, human span annotation, news | News domain; used only as optional pretraining data |
| Al-Subaiey et al. (2024). Computers and Electrical Engineering 120:109625 | Web platform on about 82.5k merged emails, interpretable phishing detection | Binary phishing vs legitimate; no tactics, no claim verification. Source of our merged corpus |
| Commercial tools (Abnormal AI, IRONSCALES, Darktrace) | Behavioural AI for thread hijacking and account takeover | Closed methods relying on login and device telemetry; not inspectable or reproducible |

**Background references for the report:** Cialdini, Influence (taxonomy); Stajano and Wilson (2011), principles of scam victims (source of the urgency tactic); Ferreira and Teles, PPSE framework; Lumen (2021), influence cues in text; Da San Martino et al. (2019), propaganda technique taxonomy; Stringhini and Thonnard (2015), IdentityMailer; Duman et al. (2016), EmailProfiler; SoK re-examination of phishing research (dataset quality).

# 6. System architecture

## 6.1 Architecture diagram

![Figure 2. Claim-routed verification architecture (gold border = novel part)](figures/figure2_architecture.png)

*Figure 2. Claim-routed verification architecture (gold border = novel part)*

*Text description: input (single email, thread, optional organisation domain) goes to the parser, which feeds three branches: header evidence, the body preprocessor (N1 redaction) and the thread builder. The claim extractor reads the redacted body and produces typed claims (affiliation, authority, relationship, requests) plus tactic probabilities. The claim router sends each claim to the header verifier (N3), the request verifier or the thread verifier (N2); header evidence feeds the header verifier and the thread builder feeds the thread verifier. All verifiers write rows to the verdict ledger, which drives the 0-100 risk score. LIME highlights explain the tactic classifier. Both outputs form the report returned through FastAPI to the React UI, with no database. Gold borders mark the novel parts: body preprocessor, claim router, both verifiers and the ledger.*

## 6.2 Components

| **Component** | **Input** | **Output** | **Implementation** | **Module** |
|---|---|---|---|---|
| Parser | Raw .eml bytes, pasted text, or a thread | Headers, body, thread links | Python email stdlib with its default legacy parser (the most forgiving with malformed spam headers), each header field parsed on its own; a fallback for From values the strict address parser rejects; mailbox for .mbox files (Section 8.11) | src/headers |
| Header evidence extractor | Headers + organisation domain(s) | Evidence dict: SPF, DKIM and DMARC verdicts (or unknown) from trusted Authentication-Results headers, the authenticated domain and its alignment with From, From name/address/domain, Reply-To divergence, envelope mismatch, Received hops and origin IP, send hour, freemail and open-platform flag, name-shows-address flag, list mail, lookalike score vs the organisation domain (vs claimed domains in Phase 8, same function) | email.utils, tldextract (offline), rapidfuzz, hand-written freemail list (Section 8.11) | src/headers |
| Body preprocessor | Body | Clean text (links kept), redacted text (N1), signature | BeautifulSoup HTML to text; list footer and quoted history removed; ReDoS-safe regular expressions; tldextract with its offline public suffix list (Section 8.10) | src/preprocess |
| Thread builder | Several messages | Ordered thread, per-message evidence, quoted history | Apache: union-find over Message-ID, In-Reply-To and References; Enron: normalised subject, 14-day runs and shared participants, copies removed by date, sender and subject; the new text and the quoted history of a message are cut as in Phase 2 and both kept; 3 to 50 messages, at least two senders (Section 8.17) | src/thread |
| Claim extractor | Redacted body and signature block | Typed claims (the eleven types of Section 6.4) with text span, attributes (person, organisation, department, rule, zone) and confidence | spaCy tokenizer and named-entity recogniser + 85 token patterns and organisation and signature rules (Section 8.15); nothing is trained, and no regular expression runs over email text; the tactic classifier (Section 8.14) runs beside the extractor, not inside it | src/claims |
| Claim router | Claims | Claim-to-verifier assignments | Rule table (Section 6.4) | src/router |
| Header verifier (N3) | Affiliation, authority, reply and signature claims + header evidence + organisation domain + the unredacted signature | Ledger rows | 50 Python rules, each row naming its rule; severities high, medium, low (initial labels, weights in Phase 10); brand domains in a data file (brands.py); no regular expression over email text (Section 8.16) | src/verifiers |
| Thread verifier (N2) | Relationship and request claims + thread | Ledger rows + hijack index | 44 Python rules over four measurements (src/thread/signals.py): tactic onset against the Phase 6 thresholds, request drift (set differences on bank details with bank_detail_keys), sending-path comparison (sender name at a look-alike domain, new server and mail program), Message-ID and quotation matching (5-word shingles); the flip point is the first message with a medium or high contradiction (Section 8.17) | src/verifiers |
| Request verifier | Request claims + sender evidence + the text the extractor read | Ledger rows | 12 rules; seven signals about the asker (look-alike, DMARC fail, free mailbox, Reply-To, display name, SPF fail, no check passed); IBAN checksum and labelled-number finder written without regular expressions (bank.py), values shown masked. Request drift against the thread belongs to the thread verifier (N2) | src/verifiers |
| Ledger + risk score | Ledger rows + tactic probabilities | Score 0-100, verdict band (Low risk, Suspicious, High risk), recommended action, coverage | Points by row severity with a reliability factor per rule; the strongest row of each claim counts and each further claim counts half as much; urgency and secrecy multiply; formula in Section 6.6; calibrated on validation data | src/router |
| LIME highlights | The redacted text the classifier reads + the classifier | Word weights and character offsets for each tactic that fired | LIME for text, written by hand (random word removal, kernel weights, weighted ridge fit, fixed seed; Ribeiro et al. 2016) and cross-checked once against the lime package; no new dependency | src/explain |
| API | HTTP request (email or thread, optional organisation domain) | JSON report | FastAPI, Pydantic, slowapi, uvicorn; five routes (POST /analyze, /analyze/thread, /explain; GET /results, /health); the key in a header, per-address rate limits, size caps counted as the bytes arrive, fixed error messages, a fixed-field audit log (Section 8.19) | src/api |
| UI | JSON report | Analyzer page (score, band, findings, the redacted text with highlighted words and claims, tactics, how the score was built, thread timeline) and evaluation dashboard (four charts with table views, every result table) | React 19.3.0, Vite 6.4.4, Tailwind 4.3.3, Recharts 3.10.1; same-origin proxy that adds the API key; every string drawn as text; strict Content-Security-Policy in the served build (Section 8.20) | frontend |

## 6.3 Data contracts

Claim object produced by the claim extractor:

```
{
  "claim_id": "c1",
  "type": "affiliation_internal",
  "text": "this is David from Finance",
  "span": [10, 36],
  "attributes": {"person": "David", "organisation": null, "department": "Finance", "pattern": "ai_this_is_from", "zone": "body"},
  "confidence": 0.9
}
```

The span points into the text the extractor read (the redacted body cut at 2,000 characters, or the redacted signature block named by zone), not into the raw email. Confidence is the strength of the rule that fired (0.9 strong, 0.6 weak), not a probability. attributes.pattern names the rule, so every claim can say why it exists.

Ledger row produced by a verifier:

```
{
  "claim_id": "c1",
  "claim_type": "affiliation_internal",
  "verifier": "header",
  "rule": "hv_int_freemail",
  "evidence": {"from_domain": "gmail.com", "org_domain": "acmecorp.com", "freemail": true,
               "spf": "pass", "dkim": "pass", "dmarc": "pass", "auth_state": "aligned"},
  "contradiction": true,
  "severity": "high",
  "reason": "Claims to be internal (Finance at acmecorp.com), but the message comes from gmail.com, a free mailbox provider anyone can use. Authentication passed for gmail.com."
}
```

`contradiction` has three values: true (severity high, medium or low), false (severity none) and null (severity not_checkable, the evidence the claim needs is missing). `rule` names the rule that produced the row and `claim_type` the type of the claim; severity is the strength of the rule, not a probability (Section 8.16).

Report returned by the API (shape, defined in Phase 10): `request_id`; `mode` ('email' or 'thread'); `score` (0 to 100), `verdict` (the band) and `action`; `org_domain` (as used, or null); `versions` (the score, rule, thread-rule and claim-pattern versions that produced the report); `text_read` (the redacted text the classifier and the claim extractor read; every highlight and claim span points into it); `tactics` (for each of the seven: name, probability, threshold, whether it fired, whether it counts in the score, and for a tactic that fired its highlights as character offsets with a weight); `claims` and `routing` (each claim and the verifier or verifiers it was sent to); `ledger` (rows as above, exactly as the verifiers return them, including the ones marked not checkable); `score_detail` (the points each counted row added, the multiplier and the tactic points); `coverage` (how many claims were found, checked, contradicted, consistent and not checkable, and a plain sentence when verification was incomplete, for example because no headers were pasted); `header_findings` (the cleaned header evidence the header verifier read: From name and domain, Reply-To, SPF, DKIM and DMARC verdicts, authentication state, freemail flag, look-alike score and the organisation domain used; evidence, not rows); and `thread` (the flip index and, per message, the worst severity and the rules that fired, or null for a single email). Email content is never stored after the response.

## 6.4 Routing table

| **Claim type** | **Routed to** | **Notes** |
|---|---|---|
| affiliation_internal, affiliation_external, authority | Header verifier | Core N3 checks; internal checks need the organisation domain |
| reply_direction, signature_contact | Header verifier | Reply-To and signature vs From |
| prior_relationship | Thread verifier | Does the claimed conversation exist? |
| payment_request, payment_change, credential_request, gift_card, data_request | Request verifier; plus thread verifier when a thread is present | The request verifier checks who is asking; the thread verifier checks request drift against earlier messages (N2) |
| urgency, secrecy, scarcity, reciprocity, social_proof, liking | No verifier | Modifiers that raise the weight of contradictions |

## 6.5 Header signals

| **Signal** | **Comes from** | **Normal** | **Attack** | **Meaning** |
|---|---|---|---|---|
| SPF | Authentication-Results | pass | fail on an exact-domain spoof; pass for freemail or lookalike senders | Did it come from a server the domain allows? Pass proves the domain, not the person |
| DKIM | Authentication-Results | pass | none / fail on a spoof; pass for freemail or lookalike senders | Is there a valid signature proving it was not forged? |
| DMARC | Authentication-Results | pass | fail on an exact-domain spoof; pass for freemail or lookalike senders | Final verdict aligning SPF and DKIM with the visible From domain. It shows which domain sent the message, not whether that domain matches the claim |
| Name vs address | From | Name and domain agree | "Finance Director" \<x@gmail.com\> | The display name is free text anyone can type |
| Freemail | From domain | Company domain | gmail, yahoo, proton; open platforms such as \<tenant\>.onmicrosoft.com | Executives do not send from personal accounts; anyone can get an address there |
| Lookalike distance | From domain vs organisation domains | Exact match | acme-corp.co; paypa1.com; acme-payroll.onmicrosoft.com | Very similar but not equal (rapidfuzz, after punycode decoding and look-alike character mapping) |
| Reply-To divergence | Reply-To vs From | Empty or same | Different domain | Replies are silently routed to the attacker |
| Envelope mismatch | Return-Path, Received | Consistent with From (mailing lists are the exception: they send bounces to the list server) | Unrelated server | The envelope and the letterhead disagree |
| Send-hour anomaly | Date | Business hours | 02:47 | Weak alone; meaningful when stacked |
| Signature vs From | Body signature block | Same address | Different address | Insight from Mithun et al. (2024) |

> PretextGuard reads the SPF, DKIM and DMARC verdicts written by the receiving mail server into the Authentication-Results header. It does not recompute them. When that header is missing (common in old corpora), the signal is recorded as **unknown**, never as pass, and the verifiers rely on the other evidence. Which sources carry which headers is measured in Phase 1 (the header coverage table, Section 8.1), and authentication signals are scored only where the header exists. Phase 1 found Authentication-Results on 99.5% of phishing_pot, about 100% of Apache list mail, 20.4% of raw Nazario and 0% of SpamAssassin, raw Enron and Kaggle rows. **Which Authentication-Results headers are trusted (Phase 3):** an attacker can write a fake one into the email they send, so only headers the receiving organisation added are read: the topmost one (servers add headers at the top), plus the headers directly below it from the same organisation, stopping at the first header from anyone else; a higher header always wins. RFC 8601 (Section 5) requires receivers to delete incoming headers that claim to come from inside their own organisation. Both formats are read: the standard one, which starts with the checking server's name, and Microsoft's, which leaves the name out. **Mailing lists:** every Apache message carries a Reply-To set by the list and a List-Id, so list membership is recorded and a list-set Reply-To is not Reply-To divergence; lists also send bounces to their own server, so envelope mismatch is normal for list mail. Phase 3 results: Section 8.11.

## 6.6 Pretext Risk Score (plain component)

The score is computed from the ledger and the tactic probabilities, and the points come from the severity of a row, not from the type of its claim: the severities of Phases 8 and 9 already say how strong each rule is, and a severity is a rule strength, not a probability (Section 8.16). Formula and numbers (version 0.2, frozen in Phase 10 after calibration on the validation split, never on the test split; the calibration is in Section 8.18):

1.  **Only contradictions add points.** A consistent row adds nothing and takes nothing away (authentication that passes for gmail.com says nothing about who the person is). A row marked not checkable adds nothing either: missing evidence is neither a contradiction nor proof of honesty. How many claims could not be checked is reported as coverage.

2.  **Points per severity:** high 60, medium 35, low 5, multiplied by a reliability factor of 1, 0.5 or 0 per rule, set from how often that rule fires on legitimate mail (ham) and on real thread messages in the train split: a rule that fires on more than 5% of the checked messages of a source, with at least 20 hits, counts 0.5, and above 10% it counts 0 (the rules that count 0: hv_sig_freemail_sender, hv_sig_other_domain, tv_path_origin; Section 8.18).

3.  **One claim counts once.** Rows are grouped by claim (claim id and type; each thread signal is its own group) and only the strongest row of a group counts.

4.  **Saturating sum.** The groups are sorted by points and the k-th counts half as much as the one before (weights 1, 0.5, 0.25 and so on): a second independent finding is strong evidence, a tenth adds almost nothing.

5.  **Pressure tactics multiply.** If urgency or secrecy fired, the contradiction points are multiplied by 1 plus 0.25 for each. A tactic raises the weight of a contradiction found with it; it never creates one.

6.  **Small tactic points.** Authority, urgency, scarcity and secrecy that fired add 4 points each, at most 12. Reciprocity, social proof and liking are shown but not scored: Phase 6 found fewer than 10 real positives for them and no usable detection.

7.  **Cap.** The result is rounded and capped at 100.

Verdict bands (frozen in Phase 10): **0-34 Low risk**, **35-69 Suspicious**, **70-100 High risk**. The first band was called Benign in earlier versions; 'Low risk' means that no contradiction was found among the claims that could be checked, never that the email is safe, and the report states how many claims could not be checked (the coverage block of Section 6.3). Each band maps to a recommended action built from fixed text keyed on the strongest finding, never from email text (for example: verify through a known phone number before acting). Worked values: a lone medium contradiction scores 35 (Suspicious), a lone high 60 (Suspicious), a lone high with urgency 75 (High risk), two highs 90 (High risk), twelve lows about 10 (Low risk).

There are no contradiction labels, so the shape of the formula is fixed by the meaning above and the validation split sets the scale: the weights are chosen so that legitimate validation mail (ham), reported per source, and real thread messages stay inside a false-alarm budget declared before the validation emails were read (High risk at most 1%, Suspicious or above at most 5%, judged from 20 emails with a checked claim). Spam is not legitimate mail: it is listed, not budgeted. Result (Section 8.18): the budget held in 5 of 6 groups; the one group over the budget is enron (real thread messages), a finding that is reported, not hidden (the initial numbers were kept). The attack corpora, the hijack benchmark and the labelled tactic data are reported against the chosen weights and never fitted (header evidence differs by corpus, and the benchmark cases are built to trigger the rules).

## 6.7 Worked example

```
Claims extracted from the David email
  c1 affiliation_internal  "this is David from Finance"
  c2 payment_request       "process a wire transfer"
  modifiers: urgency ("before 3 PM today"), secrecy ("don't loop in anyone else")

Ledger
  c1 -> header verifier : claims Acme Finance; From gmail.com (freemail),
                          authenticated as gmail.com (spf, dkim, dmarc pass),
                          org acmecorp.com                 -> CONTRADICTION (high)
  c1 -> header verifier : Reply-To protonmail.com != From   -> CONTRADICTION (medium)
  c2 -> request verifier: payment request from an external
                          freemail sender                   -> CONTRADICTION (high)

Score: high-severity contradictions x urgency and secrecy -> High risk band
Action: do not pay; call David on a number from the company directory.
```

**Variant, exact-domain spoof:** if the attacker had instead forged From: "David Chen" \<d.chen@acmecorp.com\> from his own server, the From would look internal, but Acme's DMARC policy would fail the message (dmarc=fail). The header verifier then records: claims internal, uses Acme's own domain, fails Acme's authentication, CONTRADICTION (high). Either way, N3 compares the claim with what authentication actually proved.

## 6.8 Runtime workflow

![Figure 3. Eight steps for one analysis request](figures/figure3_runtime_workflow.png)

*Figure 3. Eight steps for one analysis request*

*Text description: eight steps in two rows. 1 Receive (paste an email or upload a .eml or thread, plus an optional organisation domain); 2 Validate (API key, rate limit, size cap, type and structure checks); 3 Parse (headers, body, thread order); 4 Redact (remove URLs, domains and attachment references, N1); 5 Extract claims (tactics plus affiliation, relationship and request claims); 6 Route and verify (header verifier N3, thread verifier N2, request verifier); 7 Ledger and score (contradictions, 0-100 risk, verdict); 8 Report (highlights, findings table, plain-English reasons; the email content is then discarded).*

## 6.9 Module map

![Figure 4. Code modules; a build phase can fill more than one folder](figures/figure4_module_map.png)

*Figure 4. Code modules; a build phase can fill more than one folder*

*Text description: src/data (raw corpora, Kaggle merge, staged schema, header coverage table, splits, annotation batches, thread-hijack benchmark) feeds src/preprocess (cleaning and N1 redaction), src/headers (parser and header evidence) and src/thread (thread builder for Enron and Apache threads, thread signals). src/preprocess feeds src/models (DistilBERT classifier), which src/claims uses. Models, headers, claims and thread all feed src/verifiers plus src/router (header verifier N3, thread verifier N2 including request drift, request verifier, claim router, ledger, risk score). These feed src/explain (LIME), src/api (FastAPI and security controls) and the React frontend. src/baseline and src/eval sit alongside. artifacts/ holds trained weights (not committed); results/ holds evaluation outputs (committed).*

## 6.10 Build time and run time

The project has two halves. Build time happens once, on the Mac and on Colab, during Phases 1 to 13: collect and clean the data, label it, train the tactic classifier and run the experiments. Run time is the web app: it analyses one email at a time and stores nothing. The only thing that crosses from build time to run time is the trained model in artifacts/; the experiment numbers feed the report and the dashboard.

![Figure 5. Build time versus run time](figures/figure5_build_vs_run.png)

*Figure 5. Build time versus run time*

*Text description: two dashed columns. Left, build time, done once in Phases 1 to 13: collect datasets (real corpora plus synthetic emails), clean and redact (N1), label tactics and claims (two web-chat annotators plus a tie-break), train the tactic classifier (DistilBERT on Colab, saved to artifacts/), run the experiments (ablations to results/ and the report). Right, run time, every email in the web app: email arrives (paste, .eml or thread plus organisation domain), parse and redact, extract claims (using the trained model), route and verify (header N3, thread N2, request; gold border = novel), ledger, score and report, with nothing stored afterwards. A gold arrow carries the trained model from the training step to claim extraction.*

Run-time steps, mapped to the code that performs them:

| Step | What happens | David example | Code lives in |
|---|---|---|---|
| 1\. Receive | The browser sends the email and the optional organisation domain | Raw text of the David email | frontend/, src/api/ |
| 2\. Validate | API key, rate limit, size cap, type and structure checks | Passes | src/api/ |
| 3\. Parse | Headers, body and thread links; headers become an evidence dict | from_domain gmail.com, freemail, dmarc pass, Reply-To protonmail.com | src/headers/, src/thread/ |
| 4\. Redact (N1) | Links, domains and file names become placeholders | No links, body unchanged | src/preprocess/ |
| 5\. Extract claims | Tactic probabilities plus typed claims from patterns and name detection | c1 affiliation_internal, c2 payment_request; urgency 0.94, secrecy 0.91 | src/models/, src/claims/ |
| 6\. Route and verify | Each claim goes to the verifier that can check it | Header and request verifiers both find contradictions | src/router/, src/verifiers/ |
| 7\. Ledger and score | Contradictions add points; urgency and secrecy multiply them | High risk band | src/router/ |
| 8\. Report | JSON back to the browser; the email is discarded from memory | Highlights, findings table, recommended action | src/api/, src/explain/, frontend/ |

**API endpoints (Phase 11, Section 8.19):** POST /analyze (one email, optional organisation domain; no LIME), POST /analyze/thread (several emails; the newest is judged), POST /explain (one email or a thread, with LIME highlights; its own, smaller rate limit and no waiting for the classifier), GET /results (the evaluation tables the dashboard may read, from a fixed allow-list; ?name= picks one) and GET /health (whether the model is loaded). The three POST routes need the X-API-Key header and accept only application/json.

**Interface (Phase 12, Section 8.20):** the browser opens http://127.0.0.1:4173 (`npm run preview` in frontend/), which serves the built page and forwards /api to the API with the key added, so steps 1 and 8 above happen in React: the page calls POST /analyze, draws the report, then calls POST /explain for the highlights, and draws every string as text.

## 6.11 Machine learning parts in plain words

- **Classifier:** a program that learns patterns from labelled examples. Shown thousands of emails marked with the tactics they use, it learns what each tactic sounds like.

- **DistilBERT and fine-tuning:** DistilBERT is a smaller, faster version of BERT that has already read a huge amount of English. Fine-tuning shows it our labelled emails so it learns the seven tactics on top of what it knows. It outputs seven independent probabilities (multi-label), for example urgency 0.94 and liking 0.03.

- **Weights and Colab:** training needs a GPU, so it runs on Google Colab's free GPU. The result is a set of weight files (the learned numbers), downloaded into artifacts/ and used on the Mac's CPU, which is fast enough for one email at a time.

- **spaCy and token patterns:** spaCy cuts the text into words (tokens) and marks the names of people and organisations; hand-written patterns over tokens (not regular expressions over characters) catch phrases such as "this is X from Y" or "verify your account", and rules read the signature block. Together they turn an email into typed claims (Section 8.15). Nothing is trained for this step.

- **LIME:** takes the email text the classifier reads, hides a random set of its words many times, watches how each tactic probability changes and fits a small weighted linear model to those changes. The words with the largest weights are the ones that pushed that tactic up, and they are highlighted. It explains the classifier only; the explanation of a verifier is the reason in its ledger row. PretextGuard writes it by hand (Section 6.2). Removing one word at a time is a different method (occlusion).

- **Keyword baseline:** fixed word lists per tactic; it exists to show that DistilBERT beats simple rules (built in Phase 4, Section 8.12).

# 7. Tactic taxonomy

Seven labels, multi-label (one email can carry several). Five come from Cialdini's principles: authority, scarcity, reciprocity, social proof and liking. Urgency is not a Cialdini principle; it comes from Stajano and Wilson's time principle (2011), which phishing research treats separately from scarcity. The seventh, isolation/secrecy, comes from the BEC literature.

| **\#** | **Tactic** | **What it looks like** | **Example phrase** |
|---|---|---|---|
| 1 | Authority | Asserted rank, role or institutional power | "This is the CFO"; "IT Security requires" |
| 2 | Urgency | Manufactured deadline or time pressure (Stajano and Wilson's time principle, not Cialdini) | "Before 3 PM today"; "immediately" |
| 3 | Scarcity | Loss or finality framing | "Last chance"; "your account will be deleted" |
| 4 | Reciprocity | Debt framing | "I covered for you last month, now I need..." |
| 5 | Social proof | Everyone else has already done it | "The whole team has already signed off" |
| 6 | Liking / rapport | Manufactured warmth, flattery, false familiarity | "Great seeing you at the offsite, quick favour..." |
| 7 | Isolation / secrecy | Cut the victim off from verification (not in Cialdini) | "Keep this between us"; "don't loop in your manager" |

**Dropped:** commitment/consistency (rare in single emails, hard to annotate, would be a sparse label). **Urgency vs scarcity:** urgency is a deadline or time pressure; scarcity is loss or finality framing. An email can carry both ("reply by 5 PM or the account is deleted"), and then both labels apply. **Why secrecy matters most:** a legitimate business request almost never asks you to avoid verification.

# 8. Data plan

**Principle:** real data first; synthetic data only to fill gaps that are measured and documented.

## 8.1 Datasets

| **Dataset** | **Email?** | **Size (approx.)** | **Fields** | **Role** |
|---|---|---|---|---|
| Phish No More (Kaggle): Enron, Ling, CEAS-08, Nazario, Nigerian Fraud, SpamAssassin | Yes | 82,486 rows in six per-source files (42,891 phishing/spam, 39,595 legitimate), plus phishing_email.csv, a pre-merged copy that is not read | CEAS, Nazario, Nigerian, SpamAssassin: sender, receiver, date, subject, body, urls. Enron, Ling: subject, body | Main single-email corpus for body-level work. Four files are used (CEAS-08, Enron, Ling, Nigerian Fraud: 73,273 emails after deduplication); the Nazario and SpamAssassin files are replaced by the raw corpora (Section 8.8) |
| Enron raw (CMU maildir) | Yes | 517,401 messages | Message-ID (internal JavaMail IDs), Date, From, To, Subject, X-From, X-To, X-Folder; no In-Reply-To, References, Received or X-Mailer (0% each, Phase 1) | Not in the single-email table (the Kaggle merge holds Enron bodies); header check; real threads for N2 content signals (Phase 9) |
| Nigerian Fraud (inside the merge) | Yes | 3,332 rows (3,227 after deduplication) | As above | Real fraud positives (body level) and real external affiliation claims for N3. The merge's Nazario file (1,565 rows, not about 15k as earlier versions said) is not used: the raw Nazario corpus replaces it |
| CEAS-08 (inside the merge) | Yes | 39,154 rows (38,077 after deduplication) | sender, receiver, date, subject, body, urls only; no Reply-To, Received or Authentication-Results | Body-level ham and spam only. The merge's SpamAssassin file (5,809 rows) is not used: the raw SpamAssassin corpus replaces it |
| SpamAssassin public corpus (raw) | Yes | 6,046 messages from five archives (5,775 after deduplication) | Full raw headers (2002 to 2005, before DMARC; 0% Authentication-Results) | Header evidence extractor development; benign and spam headers |
| Nazario phishing corpus (raw mbox files) | Yes | 12,010 messages in 17 files up to 2025 (9,595 after deduplication) | Full raw headers; 20.4% carry Authentication-Results (the newer years) | Real attack positives with headers; external affiliation claims for N3 |
| phishing_pot (GitHub dataset of honeypot .eml files; data only, no code) | Yes | 8,614 files (7,491 after deduplication) | Full raw headers; 99.5% carry Authentication-Results; recipient addresses anonymised. Last public commit 21 May 2026; newer samples go only to individual researchers | Modern attack positives with real authentication headers. Licence CC BY-NC 4.0 (non-commercial use with attribution); never redistributed |
| Apache project mailing-list archives (monthly mbox export) | Yes | users@tomcat.apache.org and users@kafka.apache.org, Oct 2024 to Sep 2026: 3,234 messages (3,190 after deduplication) | Full headers: Message-ID, In-Reply-To (63 to 78%), References, Received, Authentication-Results (about 100%), List-Id; a Reply-To set by the list on every message | Modern legitimate mail with authentication headers (in the single-email table as ham); real threads for N2 header signals (sending-path drift, thread integrity) |
| SemEval-2023 Task 3, Subtask 3 | No (news) | 26,663 paragraphs, 23 techniques | Human span labels, multi-label | Optional pretraining (plain component) |
| Synthetic | Yes | About 500 emails + injected thread replies | Full | Modern BEC gap-fill; thread-hijack injections; matched benign continuations. Generated through free web chats from fixed prompt templates and stored in data/synthetic/ (committed) |

**Header coverage table (Phase 1, results/header_coverage.csv):** for every source, the share of messages carrying Message-ID, Date, Reply-To, Return-Path, Received, Authentication-Results, Received-SPF, DKIM-Signature, In-Reply-To, References, X-Mailer, User-Agent, List-Id and X-Original-From. Key results: Authentication-Results on 99.5% of phishing_pot, about 100% of Apache, 20.4% of Nazario and 0% of SpamAssassin and raw Enron; In-Reply-To on 63 to 78% of Apache, 30.2% of SpamAssassin and 0% of raw Enron; Kaggle rows carry no original headers. The table goes into the report. Authentication signals are scored only where the header exists; synthetic headers fill only the gaps this table shows, and that is disclosed. Modern authentication headers appear mostly on attacks (phishing_pot) and on one benign source (Apache), an imbalance the N3 evaluation must report. Phase 3 sharpened it: Apache's trusted headers carry DKIM verdicts only, so no benign source has SPF or DMARC verdicts (Section 8.11).

## 8.2 Why several datasets

The project needs five things and no single dataset has them all: examples of normal and attack email (Enron; Nazario and Nigerian Fraud), real header evidence (raw SpamAssassin, raw Nazario, phishing_pot; the Kaggle merge keeps only sender and date), tactic and claim labels (none of the email corpora have them; SemEval has human tactic labels but is news), threads for content signals (raw Enron), and threads with full headers for header signals (Apache mailing lists). Each source fills one gap.

## 8.3 Thread-hijack benchmark (for N2)

1.  Rebuild real threads from raw Enron using normalised "RE:" subjects, participants and quoted text, because raw Enron has no In-Reply-To or References (0%, Phase 1 header coverage table). Rebuild Apache mailing-list threads from Message-ID, In-Reply-To and References.

2.  Keep threads with at least three messages.

3.  Pick an injection point and generate an attacker reply in one of three variants: account-takeover reply (same sender, content drift; on Apache threads the sending details are copied from that sender's real messages), mid-thread lookalike domain swap, or forged thread (a new email with fabricated quoted history and no matching Message-IDs).

4.  Negatives: the real next reply from the same thread (Enron or Apache), plus a synthetic benign continuation generated with the same generator and prompt template (style-confound control).

5.  Labels: hijacked or not (thread level) and the hijack message index.

6.  Evaluation split: content signals (tactic onset, request drift) are scored on Enron threads; header signals (sending-path drift, thread integrity) on Apache threads.

7.  Disclose in the report that the injected replies are synthetic while the base threads are real.

## 8.4 Tactic labels and annotation

- **SemEval:** human labels, mapped from 23 techniques to our 7 with a documented mapping table (Phase 5).

- **Synthetic emails:** a script in src/data writes fixed prompt templates; Nagasai pastes them into a free web chat and saves the JSON replies in data/synthetic/. Labels are known from the prompt, and every synthetic attack has a benign twin from the same template.

- **Real emails:** a stratified random sample of 700 (450 attacks, 150 ham, 100 spam; a fixed number per source and category, split 60/20/20 across train, validation and test; Section 8.13) is labelled for the seven tactics and for claim types with text spans (affiliation, authority, relationship, request types), so the claim extractor can be evaluated too. Labelling uses gemini-3.1-flash-lite (annotator 1) and gemini-3.5-flash-lite (annotator 2), called through a free API tier at temperature 0 (src/data/llm_api.py); a third model, gemini-flash-lite-latest, breaks ties where they disagree; pasting batches into chat windows by hand is the fallback. No paid APIs. DeepSeek, z.ai and Mistral were considered, but their APIs are not free. All three models come from one family and one provider's free tier, so their agreement is agreement between models of one family, their errors are partly shared, and the labels are that family's judgement; kappa measures consistency between two models, not correctness. This is a limitation the report states. gemini-flash-lite-latest is a moving alias, not a pinned version: the provider's reply names the alias and not the model behind it, so the exact version is not recorded and it may be the same model as another annotator. Method follows Pan et al. (2026).

- **Procedure:** a script in src/data writes batch prompt files of about 20 redacted emails with fixed instructions and a fixed JSON output schema. One command per annotator (annotate.py auto) sends each batch to the model's API and saves the reply in data/labelled/\<annotator\>/ with the model name and time; pasting a batch into a fresh chat by hand does the same. A validation script checks every reply against the schema and lists items to re-ask.

- **Agreement:** Cohen's kappa per label (each tactic and each claim type), reported with the mean. Final labels: agreed labels stand; disagreements take the tie-breaker's label.

- **Limitations to state:** web chats give no temperature control and their models change over time, so labels are not exactly reproducible. Mitigations: one model per annotator for the whole run, fixed prompts, and every raw reply saved in the repo.

- **Decision recorded:** Nagasai chose not to hand-label, including a small human validation sample. Validation therefore rests on agreement between two LLM annotators; the report should state this as a limitation and describe the annotation method as it actually happened.

## 8.5 Style-confound control

If attacks are written by an LLM and legitimate emails are human-written from 2001, a model can learn "LLM vs 2001 human" instead of manipulation. Controls: real attack emails are the primary positives; every synthetic attack has a matched synthetic benign twin from the same generator and template; a source classifier (LLM vs Enron vs Nazario) is trained and its AUC is reported as a threat to validity.

## 8.6 Splits

The single-email table is split 70% train, 15% validation and 15% test in Phase 1 (src/data/split.py), after duplicates are removed. The cut is stratified by source and category. Inside a stratum, emails whose subjects match after removing "Re:"/"Fwd:" prefixes (a thread, or one spam campaign) go to the same split, so near-copies never sit on both sides; a subject shared by more than 2% of its stratum (and more than 25 emails) is too common to be one thread and is split email by email. Group order comes from SHA-256 of seed 42 and the group key, so the split is identical on every machine and library version. Result: 69,542 train, 14,879 validation and 14,903 test (results/split_counts.csv). The test split stays untouched until final evaluation in Phase 13; weights and thresholds are tuned on validation only. The thread benchmark is split by thread in Phase 9, so no thread appears in both training and test.

## 8.7 Unified schema

The schema is filled in stages, so no phase depends on a later one. The phase that fills each group is shown on the right.

```
id, source, category, is_attack, has_full_headers,
raw_ref, raw_headers, body_raw, split                      (Phase 1)
body_clean, body_redacted, has_url, signature              (Phase 2)
from_name, from_addr, from_domain, from_registered_domain,
reply_to, return_path, to_domain, subject, date,
message_id, in_reply_to, references, list_id, mailer,
spf, dkim, dmarc (or unknown), auth_source,
authenticated_domain, auth_aligned, received_hops,
origin_ip, send_hour, freemail, name_has_address,
list_mail, reply_to_divergence, envelope_mismatch,
org_domain, org_checkable, from_matches_org,
org_lookalike_score, parse_problems         (Phase 3, headers.parquet)
tactic_authority, tactic_urgency, tactic_scarcity,
tactic_reciprocity, tactic_social_proof, tactic_liking,
tactic_secrecy, claims (type, span, organisation),
label_source (semeval | synthetic | llm_annotated | none)  (Phase 5)
thread_id, thread_position, split (per thread)             (Phase 9, data/processed/threads.parquet)
```

## 8.8 Phase 1 staging decisions

- **Category and is_attack:** every email gets a category (ham, spam, phishing or fraud); is_attack is true only for phishing and fraud, so the attack-vs-benign task is not padded with ordinary spam.

- **Deduplication:** the Kaggle merge repeats Enron, Nazario and SpamAssassin emails that the raw downloads also contain. Each body gets a fingerprint, the SHA-256 of its lowercase letters and digits, so copies that differ only in spacing or punctuation match; one copy per fingerprint is kept, preferring full headers, before splitting. 5,484 copies were removed (results/dedup_pairs.csv); 15 groups of copies disagreed on category, and the kept copy's label is used. The same email in train and test would inflate every score.

- **Kaggle header block:** Kaggle rows get a minimal header block built from their sender, receiver, date and subject columns, so Phase 3 parses every source the same way. has_full_headers is false for them, and the coverage table shows it.

- **Raw Enron stays out of the single-email table.** The Kaggle merge already holds Enron bodies; raw Enron is used for the header check now and for threads in Phase 9.

- **Apache lists:** users@tomcat.apache.org and users@kafka.apache.org over 24 months (October 2024 to September 2026), chosen from a one-month sample of four user lists (spark and httpd had 3 messages that month; developer lists are flooded with bot notifications). Twelve months would have given only about 900 messages. Apache mail is in the single-email table as ham: it is the only modern benign source with authentication headers.

- **Storage:** Parquet files (a compressed, typed table format) in data/processed/; raw downloads stay untouched in data/raw/\<source\>/. raw_ref points every row back to its original file.

- **Scripts and libraries:** src/data/paths.py, unpack.py, fetch_apache.py, loaders.py, stage.py, coverage.py and split.py; libraries pandas 3.0.6, pyarrow 25.0.1, requests 2.34.2 and tqdm 4.70.1 (pinned). The downloads were made by hand in the browser (Nazario's yearly files with curl, because browsers block them) and moved into data/raw/; unpack.py checks each file's type by its first bytes and unpacks safely; fetch_apache.py fetches the 48 Apache months.

- **Checks (done 6 Oct 2026):** file names confirmed from the downloads; the Kaggle zip's seventh file, phishing_email.csv, is a pre-merged copy and is not read; the phishing_pot licence is CC BY-NC 4.0; raw Enron has 517,401 messages and unpacked on macOS without case clashes. About 1 GB was downloaded and about 3 GB used after unpacking.

- **Kaggle Nazario.csv and SpamAssasin.csv left out:** the body fingerprint matched only 63 of 1,565 Kaggle Nazario rows to raw Nazario, although the file comes from the same corpus. A check by sender, date and subject matched 98% (Nazario) and 96% (SpamAssassin) of the rows the fingerprint had missed: the merge had reprocessed the bodies (line breaks collapsed, \<...\> stripped, some Nazario rows run into the next message). Keeping them would leak copies of training emails into the test set, so the raw originals are used instead.

- **Kaggle labels:** label 1 is spam for CEAS-08, Enron and Ling, fraud for Nigerian Fraud; label 0 is ham. CEAS-08 spam includes some phishing its labels do not separate, so it stays spam.

- **Bodies:** text/plain parts are used, HTML only when there is no plain text; attachments are never decoded. 208 emails with no readable text were dropped.

- **Result:** data/processed/staged.parquet holds 99,324 unique emails from nine sources: 42,354 ham, 36,657 spam, 17,086 phishing and 3,227 fraud (20,313 attacks). Per-source counts: results/staged_counts.csv.

- **READMEs:** a root README with the complete end-to-end idea, plus one README each for src/, src/data/, data/, results/, notebooks/, docs/ and artifacts/. .gitignore ignores artifacts/\* with an exception for artifacts/README.md.

## 8.9 Where data lives

| Stage | Location | In Git? | Phase |
|---|---|---|---|
| Downloads, never modified | data/raw/\<source\>/ | No (large, separately licensed) | 1 |
| One table of every unique email, with the split column | data/processed/staged.parquet | No | 1 |
| Phase 1 count tables (staged counts, duplicates, header coverage, split) | results/ | Yes | 1 |
| Plus clean and redacted bodies (staged.parquet is never modified) | data/processed/cleaned.parquet | No | 2 |
| Phase 2 checks (per-source summary, leftover check, link-free counts) | results/preprocess_summary.csv, results/preprocess_checks.csv | Yes | 2 |
| Header fields and evidence, one row per email (joins to cleaned.parquet on id) | data/processed/headers.parquet | No | 3 |
| Phase 3 checks (per-source evidence, top domains, Authentication-Results formats) | results/header_evidence_summary.csv, results/header_top_domains.csv, results/header_auth_formats.csv | Yes | 3 |
| Phase 4 checks (train-split hit rates per tactic, hits per phrase, sanity checks) | results/keyword_hit_rates.csv, results/keyword_phrase_hits.csv, results/keyword_checks.csv | Yes | 4 |
| Annotation batch prompts (full email text; rebuilt from the fixed seed) | data/labelled/batches/ | No (phishing_pot's licence forbids redistribution) | 5 |
| Sample list (ids only), raw chatbot replies, reply log, final labels | data/labelled/ | Yes (small; proof of method) | 5 |
| Phase 5 checks (sample, reply validation, kappa, label counts, synthetic counts, SemEval mapping) | results/sample_counts.csv, label_validation.csv, label_agreement.csv, label_counts.csv, synthetic_counts.csv, semeval_mapping.csv | Yes | 5 |
| Synthetic emails | data/synthetic/ | Yes | 5 and 9 |
| Training notebook | notebooks/ (training data uploaded to Google Drive) | Notebook yes, data no | 6 |
| Trained model weights | artifacts/tactic_model/ | No (README only) | 6 |
| Training table: train and validation emails with their tactic labels, uploaded to Drive (never any test row) | data/processed/tactic_data.parquet | No (full email text) | 6 |
| Phase 6 results (data counts, training log, seed summary, validation probabilities, run record, validation scores, checks) | results/tactic_data_counts.csv, tactic_training_log.csv, tactic_seed_summary.csv, tactic_val_probs.csv, tactic_run_info.json, tactic_validation_scores.csv, tactic_checks.csv | Yes | 6 |
| Phase 7 results (train-split hit rates, hits per pattern, scores against the labels, checks and run details) | results/claim_hit_rates.csv, claim_pattern_hits.csv, claim_scores.csv, claim_checks.csv | Yes | 7 |
| The claims the extractor found per email, one file per split (train, validation), reused by Phases 8, 10 and 13 | data/processed/claims_cache/ | No (claim text is email text) | 8 |
| Phase 8 results (contradiction rates per split, category and source, hits per rule, checks and run details) | results/verifier_rates.csv, verifier_rule_hits.csv, verifier_checks.csv | Yes | 8 |
| The Enron index (one row per distinct message), cached | data/processed/enron_index.parquet | No (email headers and subjects) | 9 |
| Rebuilt threads, one row per message with text, quoted history, header fields and facts | data/processed/threads.parquet | No (full email text) | 9 |
| Tactic probabilities and claims of thread messages, cached | data/processed/thread_features/ | No (claim text is email text) | 9 |
| Benchmark plan, injected texts, raw API replies, manifest | data/threads/ | Yes (synthetic text and ids only); the prompts (excerpts of real emails) are not committed | 9 |
| Phase 9 results (threads found, false alarms on real threads, benchmark cases, detection scores, checks) | results/thread_counts.csv, thread_signal_rates.csv, thread_checks.csv, hijack_generation.csv, hijack_cases.csv, thread_scores.csv, hijack_checks.csv | Yes | 9 |
| Every experiment number and chart | results/ | Yes (rubric requirement) | 13 |
| Report and slides | docs/ | Yes | 14 |

At run time nothing is stored: the email lives in memory for one request, and logs hold only metadata (time, request ID, score), never content.

## 8.10 Phase 2 cleaning and redaction

- **Output:** data/processed/cleaned.parquet holds every staged column plus has_url, body_clean, body_redacted and signature. staged.parquet is never modified: each phase writes its own file, so a mistake in one phase cannot damage the output of an earlier one.

- **body_clean:** HTML converted to text with BeautifulSoup and Python's built-in parser (scripts, styles and \<blockquote\> replies dropped; each link's hidden target written after its text, so model A sees links that HTML hides); a mailing-list footer removed (it would mark a message as list mail, so ham); quoted history removed from the earliest reply marker and every line starting with "\>" (the whole text is kept if nothing readable remains); whitespace collapsed for every source. Links stay in: body_clean is N1 model A's raw view.

- **signature:** a "-- " line, or a closing such as "Best regards," near the end. It stays inside body_clean (affiliation claims live there) and is copied to its own column for Phase 7 (unredacted, because it is cut from body_clean; the claim extractor redacts it before reading it, Section 8.15).

- **body_redacted:** \[URL\], \[EMAIL\], \[FILE\] and \[DOMAIN\], applied in that order. URLs go first so a link's domain is not caught on its own; file names go before domains because some file endings are real top-level domains (invoice.zip). A domain must end in a real public suffix (tldextract, with its built-in list and no downloads), so Mr.Smith and e.g stay. \[EMAIL\] is a fourth placeholder added in Phase 2: an address hides a domain.

- **has_url:** a link in the raw body (text, HTML attributes or spaced out), or Kaggle's own urls column for CEAS-08 and Nigerian Fraud. That column flags 322 emails whose links Kaggle's cleanup had removed from the text; the text shows links in 594 emails the column does not flag (results/preprocess_checks.csv).

- **Pre-tokenised Kaggle text:** the Kaggle Enron and Ling files are stored lowercase with every punctuation mark set apart ("john @ enron . com", "http : / / site . com"). The first version left spaced links or addresses in 13,107 Enron and 2,192 Ling redacted bodies, and missed Enron's spaced quote markers. Each placeholder now has a spaced pattern that needs strong evidence (a scheme, www plus two labels, " @ " with a dotted domain, or one of .com .net .org .edu .gov .mil .info .biz), because in such text an ordinary sentence end also looks like " . ". Some phishing spaces out links on purpose, so the same patterns help there.

- **Results:** after redaction no body matches the URL, spaced URL, email or spaced email patterns; 45 bodies keep a stray "www.". 4,580 attacks are naturally link-free (3,224 train, 660 validation, 696 test) against 39,139 link-free benign emails (5,880 in test), so N1's third view is large enough to measure. 335 bodies are empty after cleaning (mostly image-only HTML phishing) and 233 were cut at 200,000 characters; both stay in the table. Per-source figures: results/preprocess_summary.csv.

- **Security:** see Section 10 (ReDoS-safe processing, offline suffix list, redaction before data leaves the machine).

## 8.11 Phase 3 header evidence

- **Output:** data/processed/headers.parquet holds one row per email with the Phase 3 columns (Section 8.7) and joins to cleaned.parquet on id; earlier files are never modified. Code: src/headers/parser.py, domains.py, evidence.py and build.py. parse_header_fields and header_evidence work on one email at a time, so the API (Phase 11) reuses them unchanged. New library: RapidFuzz 3.14.6.

- **Parsing:** Python's email package with its default (legacy) parser, the most forgiving with malformed spam headers. Every field is parsed on its own, so one broken header costs only its own field. 86 emails have a Date header that could not be parsed; the rest of their evidence is kept.

- **Strict address parser:** Python's address parser gives up on display names with an unquoted "@", "," or ";", such as service@paypal.com \<x@evil.ru\> or Temu, jehd \<service@stayfriends.de\>. Those are common in attacks: the first run (commit 44697a8) parsed only 72.0% of phishing_pot From headers. When the parser gives up, the last \<...\> address is taken as the address (replies go there) and the text before it as the name; phishing_pot From parsing is now 92.1%. An address hidden inside an encoded word (=?utf-8?B?...?=) is never taken as the sender.

- **Authentication verdicts:** read from Authentication-Results, never recomputed, and only from the headers the receiving organisation added (Section 6.5). Two formats exist: the standard one starts with the checking server's name (mx.google.com; spf=pass ...), Microsoft's leaves the name out (spf=pass (sender IP is ...) ...). Every phishing_pot mailbox is on Microsoft; the first run read the first part as a server name and lost the SPF verdict (0.9% SPF pass). Reading both formats gives 54.7% SPF pass, 38.7% DKIM pass and 38.3% DMARC pass. Without Authentication-Results, the topmost Received-SPF header gives SPF only.

- **Apache's internal headers:** the topmost Authentication-Results header on Apache mail only records an internal hand-over between ASF servers (auth=pass). The DKIM check of the author's message sits in the header below it, written by another apache.org server (results/header_auth_formats.csv). Reading the receiving organisation's own headers below the topmost gives verdicts for 85.1% of kafka and 71.1% of tomcat messages, all of them DKIM; SPF and DMARC stay unknown for Apache. Proton Mail splits its verdicts over several headers the same way.

- **Authenticated domain:** DMARC's header.from, else DKIM's header.d, else SPF's smtp.mailfrom, taken only from a check that passed; auth_aligned says whether it is the From domain. For the fake David it is gmail.com.

- **Freemail and open platforms:** a hand-written list of about 100 free and consumer mailbox providers, 36 of them added after reading the most common sender domains (for example virgilio.it, netscape.net, latinmail.com and tiscali.co.uk from Nigerian Fraud). Open platforms where anyone can create a sub-domain count as freemail too: onmicrosoft.com (Microsoft 365 tenants) and firebaseapp.com (Firebase projects), both common phishing_pot senders. On them the tenant name counts as the registered name, so acme-payroll.onmicrosoft.com is compared as acme-payroll and scores as a lookalike of acmepayroll.com.

- **Lookalike score:** rapidfuzz's ratio of the two registered names (0 to 100), after punycode (xn--...) is decoded and look-alike characters are mapped (0 to o, 1 to l, rn to m, Cyrillic letters to their Latin twins), so paypa1.com scores 100 against paypal.com. Scores against claimed organisations come in Phase 8, with the same function.

- **Organisation domain:** the registered domain of the To address, except where it says nothing about the recipient's organisation: corpus collector mailboxes (monkey.org for Nazario, ceas-challenge.cc for CEAS-08, taint.org, the personal domain of SpamAssassin's creator Justin Mason), placeholders written over real recipients (example.com and domain.com in Nazario) and free mailboxes (a gmail.com recipient is a person, not an organisation). Internal-affiliation checks for those emails are recorded as not checkable.

- **Mailing lists:** list_mail comes from List-Id. A list-set Reply-To is not Reply-To divergence. Lists also send bounces to their own server, so envelope mismatch appears on 55.8% of kafka and 50.2% of tomcat messages: for list mail it is normal.

- **Results** (results/header_evidence_summary.csv, % of each source's emails; Kaggle Enron and Ling carry only a Subject line, so they have no header evidence):

| **Source** | **Emails** | **From parsed** | **Any verdict** | **SPF pass** | **DKIM pass** | **DMARC pass** | **Freemail** | **Name shows address** | **Reply-To divergence** | **Envelope mismatch** | **Org checkable** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| phishing_pot (phishing) | 7,491 | 92.1 | 99.1 | 54.7 | 38.7 | 38.3 | 14.5 | 2.7 | 13.1 | 24.7 | 3.6 |
| Nazario (phishing) | 9,595 | 99.2 | 20.8 | 11.4 | 10.7 | 7.5 | 3.1 | 6.8 | 7.0 | 17.7 | 9.8 |
| Kaggle Nigerian Fraud (fraud) | 3,227 | 89.6 | 0.0 | 0.0 | 0.0 | 0.0 | 46.8 | 0.6 | 0.0 | 0.0 | 17.9 |
| SpamAssassin (ham, spam) | 5,775 | 99.8 | 0.0 | 0.0 | 0.0 | 0.0 | 15.4 | 1.0 | 5.7 | 54.9 | 59.3 |
| Kaggle CEAS-08 (ham, spam) | 38,077 | 98.6 | 0.0 | 0.0 | 0.0 | 0.0 | 10.1 | 1.0 | 0.0 | 0.0 | 35.2 |
| Apache tomcat (ham) | 2,135 | 100.0 | 71.1 | 0.0 | 67.6 | 0.0 | 15.9 | 0.1 | 0.1 | 50.2 | 80.7 |
| Apache kafka (ham) | 1,055 | 100.0 | 85.1 | 0.0 | 85.1 | 0.0 | 45.1 | 0.0 | 0.0 | 55.8 | 75.9 |

- **Authentication imbalance:** among benign sources only Apache has authentication verdicts, and only DKIM; SpamAssassin, CEAS-08 and the Kaggle Enron and Ling files have none. A learned model would read "has verdicts" as "attack". Authentication evidence is therefore never a learned feature: N3 uses it only through claim-conditioned rules, and Phase 13 reports authentication-based findings per source.

- **Security:** see Section 10 (untrusted header parsing, trusted authentication results).

## 8.12 Phase 4 keyword baseline

- **Output:** src/baseline/lexicon.py (the word lists, data only), keywords.py (normaliser, scorer, lexicon check, self-test) and build.py (train-split hit rates and checks). No new library: the scorer uses only the Python standard library, so requirements.txt is unchanged. Results: results/keyword_hit_rates.csv, keyword_phrase_hits.csv and keyword_checks.csv. Lexicon version 0.1 (546 phrases) produced the numbers below.

- **Lists:** seven tactics, each with strong phrases (one fires the tactic) and weak phrases (two different ones fire it), written from the Section 7 definitions and general knowledge of how BEC, phishing and advance-fee fraud are worded; no list was copied. Authority holds assertion phrases only ("this is the CFO", "on behalf of the CEO"): bare job titles are left out because every signature has one. Weak words that would obviously fire on business and technical mail were removed before any data was read.

- **Normalising:** NFKC, lowercase, zero-width characters removed, curly quotes straightened, pre-tokenised contractions glued back ("don ' t" to "don't") and apostrophes dropped, other punctuation turned into spaces; placeholders such as \[URL\] become single words. The phrases pass through the same function, so Kaggle's pre-tokenised Enron and Ling text and ordinary text match alike.

- **Matching and score:** whole words from a lookup keyed by each phrase's first word; phrase matching uses no regular expressions. When two phrases of one tactic overlap, the longer wins; each distinct phrase counts once, so repetition cannot inflate a score; score = sum of weights (strong 1.0, weak 0.5). A tactic fires at 1.0: one strong phrase or two different weak ones. The default threshold is fixed because no labels exist yet; Phase 13 tunes one threshold per tactic on validation labels, for the baseline and DistilBERT alike, and uses the test split once.

- **Leakage guard:** build.py reads only the train split (the Parquet filter never loads validation or test rows). The lists may be revised after reading its output, never after looking at validation or test emails, and each revision changes LEXICON_VERSION, which is saved in keyword_checks.csv. The lists are frozen before the Phase 5 labels come back.

- **Results** (train split, 69,542 emails; % of emails where the tactic fires; results/keyword_hit_rates.csv):

| **Tactic** | **Ham** | **Spam** | **Phishing** | **Fraud** | **All** |
|---|---|---|---|---|---|
| authority | 0.3 | 0.3 | 2.6 | 7.1 | 0.9 |
| urgency | 1.7 | 2.5 | 7.5 | 40.7 | 4.2 |
| scarcity | 1.2 | 1.9 | 8.9 | 0.9 | 2.8 |
| reciprocity | 0.1 | 0.3 | 0.2 | 0.3 | 0.2 |
| social proof | 0.3 | 0.7 | 0.1 | 0.1 | 0.4 |
| liking | 0.2 | 1.1 | 3.2 | 31.6 | 2.0 |
| secrecy | 0.1 | 0.8 | 1.5 | 27.8 | 1.5 |
| any tactic | 3.4 | 6.1 | 19.2 | 70.1 | 9.3 |

- **Sanity checks:** 20 of 20 passed (results/keyword_checks.csv). All of them passed. They show the lists behave sensibly across categories; they say nothing about accuracy, which needs the Phase 5 labels (F1 in Phase 13).

- **Bias control for Phase 13:** no keyword hit was used to pick any labelled email (Phase 5 drew a stratified random sample, Section 8.13), so the baseline has no selection advantage. Tactics with too few positives are reported with counts, not F1.

- **Known limits:** no negation, misspellings or paraphrase, and no sense of who is speaking; these are the gaps the learned model should close.

- **Security:** see Section 10 (phrase matching without regular expressions).

## 8.13 Phase 5 tactic and claim labels

- **Output:** code in src/data (label_schema.py, prompts.py, clipboard.py, llm_api.py, batches.py, annotate.py, validate_labels.py, agreement.py, labels.py, synthetic.py, semeval_map.py); results in results/sample_counts.csv, label_validation.csv, label_agreement.csv, label_counts.csv, synthetic_counts.csv and semeval_mapping.csv. Sample list, raw replies, reply log and final labels are in data/labelled/ (committed); the annotation batches in data/labelled/batches/ are not, because they hold full email text and phishing_pot's licence (CC BY-NC 4.0) forbids redistribution. New library: scikit-learn 1.9.1, used to cross-check the hand-written kappa.

- **Sample:** 700 real emails (450 attacks, 150 ham, 100 spam): a fixed number per source and category (150 each from phishing_pot, Nazario and Nigerian Fraud; the rest spread over the benign and spam sources), not proportional, so small sources are not drowned out. Each stratum is drawn from all three splits in 60/20/20 shares, ordered by SHA-256 of seed 42 and the id, so validation and test have labels too (labelling is not tuning). Emails under 8 words are not eligible. Ham and spam are labelled as well as attacks: a tactic classifier that never sees ordinary urgent mail would over-fire on it, and the claim extractor needs benign emails to measure false claims.

- **Protocol:** 35 batches of 20 emails, each sent as its own fresh request: by API call at temperature 0 where the model name in annotators.csv says (API), otherwise pasted by hand into a chat window. The text is body_redacted cut at 2,000 characters (what DistilBERT reads); the subject and headers are not shown. Annotator 1 is gemini-3.1-flash-lite (API, temperature 0), annotator 2 is gemini-3.5-flash-lite (API, temperature 0), the tie-breaker is gemini-flash-lite-latest (API, temperature 0) (names from data/labelled/annotators.csv; every reply is logged with its time in replies_log.csv, and the raw reply is kept). A reply must be a JSON array with exactly the batch's ids, the seven tactics as 0 or 1, and claims of the eleven Section 6.4 types whose span appears in the email; an item that fails is re-asked once and then dropped. Dropped: 6 for annotator 1, 6 for annotator 2, 2 for the tie-breaker.

- **Agreement** (two annotators, Cohen's kappa per label, hand-written and cross-checked against scikit-learn; results/label_agreement.csv). Mean kappa over the tactics 0.501 (moderate), over the claim types 0.458 (moderate):

| **Tactic** | **Positives (annotator 1 / 2)** | **Agreement** | **Kappa** | **Reading** |
|---|---|---|---|---|
| authority | 218 / 76 | 78.6% | 0.399 | fair |
| urgency | 245 / 178 | 86.8% | 0.694 | substantial |
| scarcity | 141 / 156 | 92.9% | 0.790 | substantial |
| reciprocity | 28 / 14 | 95.7% | 0.266 | fair |
| social proof | 12 / 3 | 98.4% | 0.262 | fair |
| liking | 39 / 13 | 95.7% | 0.406 | moderate |
| secrecy | 107 / 66 | 93.2% | 0.692 | substantial |

| **Claim type** | **Positives (annotator 1 / 2)** | **Kappa** | **Span overlap** |
|---|---|---|---|
| affiliation_internal | 72 / 84 | 0.336 | 91% |
| affiliation_external | 191 / 186 | 0.617 | 91% |
| authority | 83 / 71 | 0.620 | 84% |
| reply_direction | 67 / 57 | 0.699 | 83% |
| signature_contact | 193 / 143 | 0.493 | 88% |
| prior_relationship | 28 / 11 | 0.187 | 75% |
| payment_request | 20 / 13 | 0.287 | 60% |
| payment_change | 10 / 2 | 0.330 | 50% |
| credential_request | 135 / 87 | 0.681 | 82% |
| gift_card | 2 / 2 | 0.499 | 100% |
| data_request | 103 / 29 | 0.287 | 77% |

- **Final labels:** 690 of 700 emails are labelled (data/labelled/labels.csv). A label both annotators gave stands; where they disagree the tie-breaker decides (majority of three); a claim type is kept when at least two annotators listed it. Positive tactic labels per split (results/label_counts.csv):

| **Tactic** | **Train** | **Validation** | **Test** |
|---|---|---|---|
| authority | 71 | 21 | 25 |
| urgency | 122 | 39 | 44 |
| scarcity | 91 | 27 | 26 |
| reciprocity | 5 | 2 | 0 |
| social proof | 2 | 0 | 0 |
| liking | 11 | 3 | 4 |
| secrecy | 41 | 12 | 16 |
| items | 413 | 137 | 140 |

Tactics with fewer than 10 positives in validation or test, reported as counts and not as F1: reciprocity, social proof, liking.

- **No keyword top-up (reverses the Phase 4 plan):** no keyword hit was used to pick any labelled email, so the baseline has no selection advantage and the sample_origin column was dropped. The Phase 4 results show why a top-up would have failed: reciprocity fires on 0.18% of phishing and social proof on 0.14%, and 78% of the 128 reciprocity and 94% of the 304 social-proof train firings are on ham or spam, so selecting by them would have picked false positives. Rare tactics come from the synthetic emails.

- **Synthetic emails:** 222 of 240 planned pairs are valid (18 dropped after a re-ask), written by generativelanguage.googleapis.com gemini-3.1-flash-lite (API, temperature 0.8): an attack and a benign twin from the same template over 12 situations, with the attack's tactics fixed by the plan and confirmed by a quoted cue for each. Every email is checked: no link, 20 to 260 words, every required claim quoted from the body, and the twin must not make the frozen keyword baseline fire. Attack emails per tactic: authority 82, urgency 79, scarcity 74, reciprocity 78, social proof 80, liking 78, secrecy 77. Pairs are split by pair (70/15/15), so a pair never straddles train and test. Synthetic results are always reported separately from real-email results (Section 8.5). Two limits: because a twin that made the keyword baseline fire was dropped, the baseline's false-positive rate on synthetic twins is zero by construction and must never be reported as its precision; and only authority, scarcity and social proof have 10 or more synthetic attack emails in both validation and test (test has 6 for urgency, 7 for liking, 8 for secrecy and 9 for reciprocity, and validation has 9 for reciprocity), so for the other tactics synthetic results are counts or pooled validation plus test, labelled as such.

- **SemEval mapping:** results/semeval_mapping.csv maps the 23 techniques to the seven tactics: 3 direct, 5 partial, 15 with no counterpart. Reciprocity has no matching technique at all. For any pretraining the tactic_labels function gives 1 when a mapped technique is present, a real 0 only for tactics that have a direct technique (authority, urgency, social proof), and None (masked, left out of the loss) otherwise. The technique names were written from the task description and have not been checked against the registered data yet; semeval_map.py --check does that and lists names it does not know.

- **Known limits:** no human validation sample (a decision, July 2026), so the labels measure agreement with LLM annotators; chat windows give no temperature control (API calls fix it at 0) and providers update their models, so labels are not exactly reproducible (mitigated by one model per annotator, fixed prompts, logged model names and every raw reply kept); All three models come from one family and one provider's free tier, so their agreement is agreement between models of one family, their errors are partly shared, and the labels are that family's judgement; kappa measures consistency between two models, not correctness. This is a limitation the report states. gemini-flash-lite-latest is a moving alias, not a pinned version: the provider's reply names the alias and not the model behind it, so the exact version is not recorded and it may be the same model as another annotator; the emails sent to free-tier APIs are public-corpus text with links, addresses and domains already replaced, and a free tier may let the provider use them, which is stated here; the annotators see the body only; names and phone numbers in the public corpora are not redacted; synthetic emails are one or two LLMs' writing style; the first two rows of replies_log.csv (annotator gemini, batches 001 and 002, model "Gemini 3.1 Pro") are a by-hand test in a chat window that was discarded before the API runs, and no final label uses them.

- **Security:** see Section 10 (annotation prompt hardening).

## 8.14 Phase 6 tactic classifier

- **Output:** src/models (dataset.py, train.py, predict.py, validate.py), src/eval/metrics.py (precision, recall, F1 and threshold tuning written by hand and cross-checked against scikit-learn) and notebooks/phase6_tactic_classifier.ipynb. Results in results/tactic_data_counts.csv, tactic_training_log.csv, tactic_seed_summary.csv, tactic_val_probs.csv, tactic_run_info.json, tactic_validation_scores.csv and tactic_checks.csv; the weights are in artifacts/tactic_model/ and are not committed. New libraries: torch 2.14.1 and transformers 5.19.0 (pip-audit reported no known vulnerability in them or their dependencies when they were added).

- **Data:** one table, data/processed/tactic_data.parquet, holds the train and validation emails only, so test emails and test labels cannot reach the training code. Real: 413 train and 137 validation emails (data/labelled/labels.csv, text from cleaned.parquet). Synthetic: 306 train and 76 validation emails (attack and benign-twin pairs). The text is what the annotators saw: body_redacted cut at 2,000 characters, without the truncation note (which only marks long emails and could become a shortcut). The table is checked against the Phase 5 counts before it is written, and the upload file stays out of Git (full email text).

- **Model and training:** distilbert/distilbert-base-uncased, uncased because the Kaggle Enron and Ling text is lowercase; seven outputs with one sigmoid each (multi-label), loss binary cross-entropy with pos_weight per tactic (negatives divided by positives, at most 10). Settings: 512 tokens with dynamic padding, batch size 16, AdamW at learning rate 3e-5 with a 10% warm-up and linear decay, weight decay 0.01, gradient clipping at 1.0, at most 8 epochs, stop after 3 without improvement, seeds 42, 43, 44. Two conditions: mix (real and synthetic training emails; the model) and real_only (real emails alone; a comparison that measures whether the synthetic emails help, its weights are not kept).

- **Selection and thresholds:** each epoch is scored by macro-F1 over authority, urgency, scarcity and secrecy on the real validation emails at threshold 0.5 (ties go to the lower validation loss); the best epoch of each seed is kept and the best seed becomes the model. Thresholds for those four tactics are tuned on the real validation emails (grid 0.05 to 0.95, step 0.05); reciprocity, social proof and liking stay at 0.5 and are reported as counts, because each has fewer than 10 real positives in validation or test. Chosen thresholds: authority 0.55, urgency 0.45, scarcity 0.65, reciprocity 0.50, social_proof 0.50, liking 0.50, secrecy 0.90. Validation picked the epoch, the seed and the thresholds, so the validation scores are slightly optimistic; the test split is used once, in Phase 13.

- **Run:** Tesla T4, 22.2 minutes, Python 3.13.15, transformers 5.19.0 on Colab; code commit 407861e7, base-model revision 12040acc, finished 2026-10-08 14:38:30 (UTC). Colab's own preinstalled torch was used (2.11.0+cu130 on Colab, 2.14.1 on the Mac) and only transformers was pinned to the Mac's version; the check mac_reproduces_colab shows the difference does not matter in practice. The project's venv runs Python 3.12; Colab's Python was 3.13.15, which does not affect the saved weights (plain numbers in a safetensors file).

- **Seeds** (results/tactic_seed_summary.csv; macro-F1 over authority, urgency, scarcity and secrecy on real validation emails at threshold 0.5):

| **Condition** | **Seed** | **Best epoch** | **Epochs run** | **Validation macro-F1** | **Chosen** |
|---|---|---|---|---|---|
| mix | 42 | 8 | 8 | 0.554 |  |
| mix | 43 | 8 | 8 | 0.571 | yes |
| mix | 44 | 3 | 6 | 0.539 |  |
| real_only | 42 | 8 | 8 | 0.554 |  |
| real_only | 43 | 8 | 8 | 0.596 | yes |
| real_only | 44 | 7 | 8 | 0.554 |  |

- **Real validation emails** (137 emails; results/tactic_validation_scores.csv). F1 is reported only for a tactic with 10 or more positives; otherwise the counts (true positives, false positives, false negatives) are shown. The keyword baseline appears twice: with its default threshold (every tactic fires at score 1.0) and with one threshold per main tactic tuned on these same validation emails (authority 0.5, urgency 0.5, scarcity 0.5, secrecy 0.5), so the comparison with the tuned DistilBERT is fair. The final comparison is Phase 13, on the test split.

| **Tactic** | **Positives** | **DistilBERT** | **DistilBERT, real emails only** | **Keyword baseline, default** | **Keyword baseline, tuned** |
|---|---|---|---|---|---|
| authority | 21 | 0.593 | 0.667 | 0.148 | 0.316 |
| urgency | 39 | 0.606 | 0.600 | 0.267 | 0.492 |
| scarcity | 27 | 0.552 | 0.603 | 0.368 | 0.654 |
| reciprocity | 2 | tp 0, fp 1, fn 2 | tp 0, fp 0, fn 2 | tp 0, fp 0, fn 2 | tp 0, fp 0, fn 2 |
| social proof | 0 | tp 0, fp 0, fn 0 | tp 0, fp 0, fn 0 | tp 0, fp 0, fn 0 | tp 0, fp 0, fn 0 |
| liking | 3 | tp 0, fp 2, fn 3 | tp 0, fp 0, fn 3 | tp 0, fp 14, fn 3 | tp 0, fp 14, fn 3 |
| secrecy | 12 | 0.700 | 0.600 | 0.400 | 0.518 |
| macro-F1 (authority, urgency, scarcity, secrecy) |  | 0.613 | 0.617 | 0.296 | 0.495 |

- **Synthetic validation emails** (76 emails, reported apart from the real ones because they carry one LLM's writing style). Counts only for a tactic with fewer than 10 positives. The keyword baseline gets recall only: twins that made it fire were dropped when the synthetic emails were made, so its precision there would be fake.

| **Tactic** | **Positives** | **DistilBERT** | **DistilBERT, real emails only** | **Keyword baseline, default** | **Keyword baseline, tuned** |
|---|---|---|---|---|---|
| authority | 14 | 0.571 | 0.286 | recall 0.14 (2 of 14) | recall 0.43 (6 of 14) |
| urgency | 16 | 0.566 | 0.372 | recall 0.31 (5 of 16) | recall 0.94 (15 of 16) |
| scarcity | 18 | 0.320 | 0.259 | recall 0.72 (13 of 18) | recall 0.72 (13 of 18) |
| reciprocity | 9 | tp 8, fp 22, fn 1 | tp 0, fp 0, fn 9 | recall 0.33 (3 of 9) | recall 0.33 (3 of 9) |
| social proof | 12 | 0.727 | 0.000 | recall 0.50 (6 of 12) | recall 0.50 (6 of 12) |
| liking | 14 | 0.778 | 0.000 | recall 0.36 (5 of 14) | recall 0.36 (5 of 14) |
| secrecy | 16 | 0.222 | 0.160 | recall 0.75 (12 of 16) | recall 0.94 (15 of 16) |
| macro-F1 (authority, urgency, scarcity, secrecy) |  | 0.420 | 0.269 | - | - |

- **Reading of the tables** (every number below is computed from them by the script that wrote this section): on the real validation emails the macro-F1 over authority, urgency, scarcity and secrecy is 0.613 for DistilBERT, 0.495 for the keyword baseline with tuned thresholds and 0.296 with its default thresholds; DistilBERT is ahead of the tuned baseline on authority, urgency, secrecy and behind it on scarcity; trained without the synthetic emails the model scores 0.617, a difference of -0.005 from the mix model, against a spread of 0.539 to 0.571 between the three mix seeds at threshold 0.5, so on real emails the synthetic training emails made no measurable difference; on the synthetic validation emails the macro-F1 is 0.420 with and 0.269 without synthetic training emails; of the 5 real validation positives of reciprocity, social proof and liking the model found 0 (the counts are too small to conclude anything about these three tactics). Each tactic has only 12 to 39 real validation positives, so differences of a few points are within noise; these are validation readings, and Phase 13 repeats the comparison once on the test split, with confidence intervals.

- **Checks** (results/tactic_checks.csv): 60 PASS, 0 FAIL, 3 info. The Mac's CPU reproduced Colab's probabilities on every validation email to within 0.000001 (limit 0.001). The checks cover the data (no test rows, counts equal to Phase 5), the model files (safetensors only, thresholds valid, output order), the run (same data file as Colab, same transformers version, training loss fell, no tactic flagged on all or none of the real validation emails) and the reproduction on the Mac.

- **Known limits:** the labels are LLM labels from one model family and no human validated them, so every F1 is agreement with those labels; the three rare tactics have almost no real positives, so on real emails they are counts only and the model learns them mostly from synthetic text; validation scores are optimistic (validation chose the epoch, the seed and the thresholds); GPU arithmetic is not bit-exact, so a rerun is similar, not identical; SemEval pretraining was skipped.

- **Security:** see Section 10 (model files and offline inference).

## 8.15 Phase 7 claim extractor

- **Output:** src/claims (schema.py, patterns.py, extractor.py, build.py, README.md). `extract_claims(body_redacted, signature, min_confidence)` returns the claim objects of Section 6.3 for the eleven types of Section 6.4; `extract_many` does a batch. Results in results/claim_hit_rates.csv, claim_pattern_hits.csv, claim_scores.csv and claim_checks.csv. New libraries: spaCy 3.8.16 and its English model en_core_web_sm 3.8.0 (the model is not on PyPI, so requirements.txt pins it by URL and SHA-256 hash and pip refuses a different file; pip-audit reported no known vulnerability in spaCy or its dependencies and says it cannot audit the model itself).

- **What is read:** model_text(body_redacted), the same text the annotators labelled and DistilBERT reads (2,000 characters), plus the signature block. The signature column of cleaned.parquet is cut from body_clean in Phase 2, so it still holds raw addresses and links; extract_claims redacts it with the Phase 2 redact function first and cuts it at 1,000 characters. A claim's span points into the text that was read, and its zone says whether that was the body or the signature.

- **Method:** no model is trained and no LLM runs. spaCy (only the tokenizer and the named-entity recogniser, which keeps it fast) cuts the text into tokens and marks people and organisations. Then three kinds of rule: (1) 85 phrase patterns in a small token-pattern language compiled to spaCy's Matcher (words, word starts, alternatives, exact-case words such as IT, optional words, up to 6 free tokens, digits, person and organisation entities), one or more for each of the eleven types; (2) an organisation rule for affiliation_external (an organisation name next to a cue word such as Team, Bank or Security; the name after a copyright sign; a short list of often-imitated organisations, KNOWN_ORGS, which Phase 8 will attach real domains to) with filters for greetings, job titles, department words, placeholders and spans made only of generic words; (3) a signature rule for signature_contact (labelled phone numbers and addresses anywhere, unlabelled ones in the signature or the last 350 characters, postal addresses, disclaimers and a name after a closing word as weak claims). Within a type overlapping candidates keep the longest, with at most 3 claims per type and 12 per email. **Confidence is the strength of the rule that fired** (0.9 strong, 0.6 weak), not a probability, and nothing calibrates it; every result is reported at two operating points, all claims and strong claims only (min_confidence 0.0 and 0.9). Token patterns replace the regular expressions planned in Section 6.2: their cost grows with the number of tokens and cannot blow up, each word is one whole token, and the same patterns read Kaggle's pre-tokenised text.

- **Protocol (no leakage):** the patterns were written from the claim definitions, general knowledge of how business email compromise, phishing and advance-fee fraud are worded, and the train split only; they exist in four versions (0.1 to 0.4, below), each revision made by reading train results, and `build.py --train-only` never loads a validation email or label. Version 0.4 was frozen and committed (8633c4f) before the validation emails were scored once by `python -m src.claims.build`; no pattern changed afterwards, and the test split is not used until Phase 13. Scores on the real train emails are development scores: the patterns were written while reading them.

| **Version** | **What the train results showed, and the change** |
|---|---|
| 0.1 | First patterns. A bare organisation name from spaCy made affiliation_external fire on 57% of all emails (the attack-versus-ham check failed); "make money" fired payment_request, the pronoun "it" fired affiliation_internal, the stem promis* fired prior_relationship, gift vouchers fired gift_card. Only 43% of labelled signatures were found |
| 0.2 | Bare organisations count only when known or cued; IT matched in capitals only; weak "send money"; whole-word "as discussed"; data_request needs "your"; signature rule extended to postal addresses, disclaimers, copyright lines and a name after a closing word (the train labels show annotators marked those); --diagnose added |
| 0.3 | Name after a copyright sign is an organisation; spans of generic words are not; labelled phone or address counts anywhere; internal-affiliation and data-request patterns tightened ("I am a social worker with", "charged to your credit card" no longer fire) |
| 0.4 | Redaction placeholders no longer match pattern words (the EMAIL of [EMAIL] matched "email"); "called me on" no longer matches the contact verb; official, advisor and spokesman count as titles. Frozen here |

- **Hit rates on the train split** (69,542 emails; results/claim_hit_rates.csv; percentage of emails in which a claim of the type is found, no labels involved). A claim type should fire far more on the attacks it belongs to than on ordinary mail. All claims:

| **Claim type** | **All emails** | **Ham** | **Spam** | **Phishing** | **Fraud** |
|---|---|---|---|---|---|
| affiliation_internal | 2.63 | 1.42 | 0.43 | 9.87 | 5.18 |
| affiliation_external | 22.83 | 12.46 | 19.39 | 50.34 | 52.15 |
| authority | 3.53 | 1.64 | 1.63 | 3.09 | 52.32 |
| reply_direction | 2.38 | 2.51 | 1.03 | 1.04 | 23.11 |
| signature_contact | 32.44 | 34.82 | 17.87 | 50.92 | 68.75 |
| prior_relationship | 1.52 | 2.03 | 0.41 | 2.28 | 3.54 |
| payment_request | 2.01 | 0.48 | 0.82 | 4.04 | 24.83 |
| payment_change | 0.67 | 0.04 | 0.10 | 3.41 | 1.02 |
| credential_request | 6.29 | 0.97 | 1.01 | 31.74 | 1.06 |
| gift_card | 0.18 | 0.15 | 0.17 | 0.34 | 0.00 |
| data_request | 5.19 | 2.56 | 3.14 | 13.62 | 18.24 |

Strong claims only:

| **Claim type** | **All emails** | **Ham** | **Spam** | **Phishing** | **Fraud** |
|---|---|---|---|---|---|
| affiliation_internal | 2.46 | 1.34 | 0.38 | 9.56 | 3.23 |
| affiliation_external | 19.91 | 9.85 | 17.65 | 44.10 | 49.40 |
| authority | 1.70 | 0.51 | 0.72 | 0.23 | 36.39 |
| reply_direction | 1.22 | 1.00 | 0.67 | 0.45 | 14.25 |
| signature_contact | 12.28 | 15.15 | 4.69 | 18.23 | 29.22 |
| prior_relationship | 1.18 | 1.57 | 0.26 | 2.10 | 1.64 |
| payment_request | 1.03 | 0.37 | 0.42 | 2.96 | 6.15 |
| payment_change | 0.31 | 0.02 | 0.04 | 1.48 | 1.02 |
| credential_request | 5.29 | 0.34 | 0.71 | 28.30 | 0.40 |
| gift_card | 0.13 | 0.07 | 0.14 | 0.26 | 0.00 |
| data_request | 0.57 | 0.21 | 0.33 | 0.44 | 8.68 |

- **Real labelled emails** (137 validation emails, 413 train; results/claim_scores.csv). Email level: does the email contain a claim of the type, as the annotators say. F1 is reported only for a type with 10 or more positives in the set, otherwise the counts (true positives, false positives, false negatives). The last column is the F1 of annotator 2's labels against annotator 1's, computed from results/label_agreement.csv, to show what agreement the labels themselves support. All scores are agreement with LLM labels from one model family.

| **Claim type** | **Positives (train / validation)** | **Train, all claims (development set)** | **Validation, all claims** | **Validation, strong claims only** | **Annotator 1 against annotator 2 (F1)** |
|---|---|---|---|---|---|
| affiliation_internal | 32 / 15 | 0.492 | 0.167 | 0.087 | 0.410 |
| affiliation_external | 116 / 38 | 0.693 | 0.703 | 0.651 | 0.721 |
| authority | 45 / 15 | 0.707 | 0.621 | 0.500 | 0.662 |
| reply_direction | 35 / 9 | 0.585 | tp 5, fp 3, fn 4 | tp 4, fp 0, fn 5 | 0.726 |
| signature_contact | 87 / 26 | 0.465 | 0.505 | 0.510 | 0.613 |
| prior_relationship | 8 / 1 | tp 4, fp 11, fn 4 | tp 0, fp 4, fn 1 | tp 0, fp 1, fn 1 | 0.205 |
| payment_request | 8 / 0 | tp 2, fp 38, fn 6 | tp 0, fp 11, fn 0 | tp 0, fp 5, fn 0 | 0.303 |
| payment_change | 1 / 1 | tp 0, fp 7, fn 1 | tp 1, fp 3, fn 0 | tp 1, fp 2, fn 0 | 0.333 |
| credential_request | 62 / 25 | 0.727 | 0.783 | 0.683 | 0.730 |
| gift_card | 1 / 0 | tp 1, fp 1, fn 0 | tp 0, fp 1, fn 0 | tp 0, fp 0, fn 0 | 0.500 |
| data_request | 23 / 5 | 0.416 | tp 2, fp 13, fn 3 | tp 1, fp 2, fn 4 | 0.333 |
| macro-F1 (5 types with enough real positives) |  | 0.617 | 0.556 | 0.486 | 0.627 |

Validation, the five types with enough positives; span precision and recall use the Phase 5 overlap rule (one span contains the other, or at least half the words are shared) and are stricter than the email-level scores:

| **Claim type** | **Precision** | **Recall** | **Span precision** | **Span recall** | **Precision, strong only** | **Recall, strong only** |
|---|---|---|---|---|---|---|
| affiliation_internal | 0.22 | 0.13 | 0.20 | 0.13 | 0.12 | 0.07 |
| affiliation_external | 0.60 | 0.84 | 0.47 | 0.71 | 0.60 | 0.71 |
| authority | 0.64 | 0.60 | 0.30 | 0.33 | 0.67 | 0.40 |
| signature_contact | 0.35 | 0.92 | 0.24 | 0.73 | 0.52 | 0.50 |
| credential_request | 0.86 | 0.72 | 0.55 | 0.56 | 0.88 | 0.56 |

- **Synthetic emails** (76 validation emails, 306 train; always apart from the real ones, Section 8.5). Their labels list only the claims the generator was required to include, so precision is a lower bound and recall is the meaningful number. They are the only place the rarest request types can be measured at all.

| **Claim type** | **Positives (train / validation)** | **Train, all claims** | **Validation, all claims** | **Validation, strong claims only** |
|---|---|---|---|---|
| affiliation_internal | 142 / 44 | 0.575 | 0.557 | 0.486 |
| affiliation_external | 80 / 18 | 0.147 | 0.370 | 0.370 |
| authority | 81 / 17 | 0.804 | 0.739 | 0.757 |
| reply_direction | 49 / 12 | 0.851 | 0.783 | 0.667 |
| signature_contact | 52 / 12 | 0.693 | 0.615 | 0.783 |
| prior_relationship | 101 / 33 | 0.828 | 0.885 | 0.885 |
| payment_request | 115 / 32 | 0.792 | 0.867 | 0.848 |
| payment_change | 42 / 14 | 0.950 | 0.963 | 0.880 |
| credential_request | 15 / 1 | 0.857 | tp 1, fp 3, fn 0 | tp 1, fp 1, fn 0 |
| gift_card | 30 / 2 | 0.984 | tp 2, fp 0, fn 0 | tp 1, fp 0, fn 1 |
| data_request | 52 / 14 | 0.661 | 0.540 | 0.600 |
| macro-F1 (the same 5 types) |  | 0.616 | 0.536 | 0.613 |

- **Reading of the tables** (every number and comparison below is computed from them by the script that wrote this section):

    - on the 137 real validation emails, the first unbiased reading of this version, the macro-F1 over the five types with enough real positives is 0.556 for all claims and 0.486 for strong claims only, against 0.617 and 0.605 on the real train emails (the development set the patterns were written from); the five validation F1 values run from 0.167 to 0.783.
    - the fall comes mostly from one type: affiliation_internal went from 0.492 on train to 0.167 on validation (15 validation positives, 2 found, 7 wrong, 13 missed), while the other four types moved between -0.086 and +0.055.
    - the two annotators' labels agree with each other at F1 0.410 to 0.730 on these five types (last column of the real table); the extractor is within 0.1 of the annotators' own agreement on 3 of 5 (affiliation_external, authority and credential_request) and lower by more than 0.1 on affiliation_internal and signature_contact; labels that two annotators only partly share set a level that a rule-based extractor cannot be expected to pass by much.
    - affiliation_internal has the lowest validation precision (0.22 at recall 0.13).
    - strong claims only raise precision on 3 of 5 types (authority, signature_contact and credential_request) and lower F1 on 4 of 5 (affiliation_internal, affiliation_external, authority and credential_request); the per-type choice between the two operating points is made on validation in Phase 13.
    - the five types have only 15 to 38 validation positives each, so differences of a few points are within noise (Phase 13 adds confidence intervals); 6 of the 11 types (reply_direction, prior_relationship, payment_request, payment_change, gift_card and data_request) have fewer than 10 real validation positives and are counts only.
    - on the synthetic validation emails the macro-F1 is 0.536 for all claims and 0.613 for strong claims only, and recall is below 0.5 for affiliation_external, because the rule that rejects organisation names made only of generic words (a choice made to stop false positives on real mail) also rejects most of the generic-sounding company names the generator invented; credential_request and gift_card have fewer than 10 synthetic validation positives and are counts only; synthetic precision is a lower bound because the labels list only the claims the generator was required to include; one correction made in Phase 8: those two macro values average five types, and one of them, credential_request, has a single positive in the synthetic validation set (1 positive; tp 1, fp 3, fn 0 for all claims), so the table shows it as counts while the macro still includes its F1; without that type the macro-F1 is 0.570 for all claims and 0.599 for strong claims only; the real-email macros and the synthetic train macros are not affected, nothing was re-run, and the scorer of Phase 13 applies the 10-positive rule to macros too.

- **Checks** (results/claim_checks.csv): 31 PASS, 0 FAIL, 11 info. They cover the patterns (they compile and every word is one token), 5 attack-versus-ham contrasts (credential requests on phishing, outside organisations on phishing, reply directions, authority and data requests on fraud: each at least twice the ham rate), the claim objects (every claim's text is exactly the slice of its span, at most 12 per email and 3 per type), speed (slowest of eight crafted 200,000-character inputs 0.54 s), leakage (hit rates read the train split only; scoring read train and validation only) and coverage. Findings that are not failures: affiliation_internal: ai_dept_role (79.8% of its hits); affiliation_external: ae_org_cue (68.0% of its hits); payment_change: pc_details_changed (53.8% of its hits); gift_card: gc_gift_card (67.7% of its hits). The full run took 1197 seconds (about 20 minutes) on the Mac for 69,542 train emails plus the labelled sets (413 / 137 train / validation); the mean is 2.42 claims per labelled real email.

- **Known limits:** English only (the corpora contain Portuguese, German, Italian and other mail); patterns do not understand negation ("never send your password" can still match) or paraphrase; spaCy's small model misses some organisations and mislabels some words, and the claim attributes inherit its mistakes; the labels are LLM labels from one model family and the annotators agreed only moderately (mean kappa 0.458 over the claim types), so a score is agreement with those labels; affiliation_internal cannot be decided from the body alone (it needs the organisation domain, Phase 8) and is the weakest type here; six of the eleven types have fewer than 10 real positives and are counts only; real train scores are development scores; validation was read once and not used to change anything, but Phase 13 will choose the operating point per type on it, so the validation scores of that choice are slightly optimistic.

- **Security:** see Section 10 (claim extraction).

## 8.16 Phase 8 header and request verifiers

- **Output:** src/verifiers (rows.py, facts.py, brands.py, bank.py, header_verifier.py, request_verifier.py, verify.py, selftest.py, build.py, README.md). `verify_claims(claims, {**fields, **evidence}, contact_text, body_text)` returns the ledger rows of Section 6.3 for the claims of one email; the API (Phase 11) reuses it unchanged. Results in results/verifier_rates.csv, verifier_rule_hits.csv and verifier_checks.csv. No new library (RapidFuzz, tldextract and pandas were already pinned). The claims the Phase 7 extractor finds are cached in data/processed/claims_cache/ (ignored by Git, one file per split, rebuilt when the pattern version or the spaCy model changes) so later runs, Phase 10 and Phase 13 do not repeat its 20 minutes.

- **The ledger row** (Section 6.3, with `claim_type` and `rule` added): three values, never two. `contradiction` is true (severity high, medium or low: the evidence disagrees with the claim), false (severity none: the evidence was there and does not disagree) or null (severity not_checkable: the evidence the claim needs is missing). Missing evidence is never turned into 'no contradiction': a source without authentication verdicts gets 'not checkable' for every rule that reads one. Severity is the strength of the rule, not a probability or a score; a weak claim (confidence 0.6) lowers it by one step; Phase 10 turns severities into points. Every row names the rule that produced it (63 rules: 50 for the header verifier, 12 for the request verifier, one placeholder that sends prior_relationship to the thread verifier of Phase 9). A reason is built from templates and validated values only; anything that came from the email (a claimed organisation, a department) goes through clean_text, every domain through clean_domain, and check_row rejects a reason with markup.

- **Header verifier (N3).** Three domains: the From domain (what the reader sees), the authenticated domain (what SPF, DKIM or DMARC vouched for) and the claimed domain (the organisation domain, or a brand's real domains). A contradiction is a mismatch between them that the claim makes meaningful, which is why the same headers give different rows under different claims (spf=fail on a newsletter that claims nothing gives no row at all; under a payment request it is medium; dmarc=pass for gmail.com is normal for a Gmail user and high under 'this is David from Finance'). `auth_state` reduces SPF, DKIM and DMARC to one word (aligned, failed, spf_failed, other_domain, no_pass, list_relayed, unknown), and authentication is read only through these claim-conditioned rules, never as a learned feature. The rules:

| **Claim** | **Contradiction when** | **Severity** |
|---|---|---|
| affiliation_internal | the sender is a free mailbox or a look-alike of the organisation domain; the From shows the organisation's own domain but DMARC failed (exact-domain spoof) | high |
| | the organisation's name under another suffix; the From shows the organisation's domain but SPF failed or authentication vouched for another domain | medium |
| | an unrelated domain (weak: where there is no List-Id the recipient domain is often a mailing list, or a partner) | low |
| | not checkable: no organisation domain, mailing-list mail (the recipient domain is the list's), no From address, or the From shows the organisation's domain and there is no verdict | |
| affiliation_external | checked only if the claim's own words name the organisation and say the sender is that organisation (a team, department, support, security, customer, billing, a footer or 'on behalf of'); a reference such as 'your Microsoft account' or 'SharePoint Services' is not a claim of identity and is not checkable; the organisation is read from the claim text, not from the nearest organisation in the email | |
| | the named organisation is in brands.py and the sender is a free mailbox, a look-alike of its domain, or has a display name showing another e-mail address; the brand's own domain but DMARC failed | high |
| | an unrelated domain (brand mail sometimes goes through a third-party mailer); the same name under another suffix | medium |
| | consistent: the brand's own domain authenticated as itself, or the brand's domain authenticated the message although it was sent through a mailer. A claim that names no organisation, or an organisation with no domain on file (low if the sender is a free mailbox, because the name comes from a name recogniser), is not checkable | |
| authority | display name shows another e-mail address, look-alike of the organisation domain, DMARC failed | high |
| | free mailbox, SPF failed | medium |
| reply_direction | Reply-To points to another domain (a free mailbox while the sender is not one, or a look-alike, is high); a list-set Reply-To is excluded; no Reply-To header is not checkable | medium |
| signature_contact | checked only for contact claims (a name with a phone or address, a labelled contact, a bare contact in the signature); a postal address, disclaimer, copyright line or sign-off name is not checkable. The sender's block ends at the first footer or quoted-header marker (unsubscribe, mailing list, on behalf of, Sent:), an address on the recipient's domain is ignored when the recipient has no organisation, and a match on the same free mailbox provider is not checkable | |
| | no e-mail address in the sender's unredacted signature block is on the From domain (an address that looks like the sender's own is high; a company address while the sender is a free mailbox is medium) | low |

  The thresholds are fixed numbers set from definitions and never tuned: two registered names are look-alikes when they differ only by look-alike characters (paypa1, a Cyrillic a, rn for m), or have a rapidfuzz ratio of 80 or more and both names have at least 6 letters (visa and vista are too short to count); the same name under another suffix (paypal.net) is a separate, weaker relation. The addresses of a signature are read from the unredacted signature block (the signature column, or the end of the cleaned body when there is none), because the redacted text holds only the placeholder [EMAIL]; mailing-list mail has no organisation domain (apache.org is the list's host, not an employer) and cannot be an internal-affiliation finding.

- **Brands.** brands.py attaches to 51 of the 55 names in KNOWN_ORGS (three more are spellings of those, and Yahoo has no domain yet) the registered domains they send mail from: only domains that are certain, none of them a free-mailbox domain (outlook.com, yahoo.com, icloud.com), none a third-party mailer. A missing domain makes the verifier more suspicious of a genuine message (medium, never high), so a gap costs a little precision and opens no hole; 15 secondary domains are listed in CONFIRM for a hand check (command in src/verifiers/README.md).

- **Request verifier.** A request is not false the way a claim of identity can be, so it asks who is asking. Signals: look-alike sender (of the organisation or of the brand the request names) and DMARC fail are high; a free mailbox is medium, and high when the sender is outside the recipient's organisation; a Reply-To to another domain, a display name showing another e-mail address and SPF fail are medium; a display name that shows only a bare domain name (brands write 'Brand.com') and no check passed is low. The strongest signal sets the severity; payment_change and gift_card move it up one step, data_request down one, and valid bank details in a payment message up one (bank.py: IBANs with the mod 97 checksum and the country's length, labelled account, routing and sort numbers and SWIFT codes, found by word lookup without regular expressions and shown masked, for example DE**3000). With no signal the row is consistent only if authentication passed for the sender's own domain; a bank-detail change is always 'not checkable: needs the thread' because headers can never confirm it (the thread verifier of Phase 9 compares the new details with the earlier messages, using bank_detail_keys).

- **Protocol (no leakage).** The rules were written from master document Sections 4.4 and 6.5, the Phase 3 and Phase 7 notes and the claim definitions, and revised only after reading train results; `build.py --train-only` never loads a validation email; the final run reads the validation emails once for the frozen version 0.3; the test split is not used until Phase 13. The train rates are development rates. Rule versions:

| **Version** | **What the train results showed, and the change** |
|---|---|
| 0.1 | First version: rules written from master document Sections 4.4 and 6.5, the Phase 3 and Phase 7 notes and the claim definitions; thresholds fixed (look-alike score 80, names of 6 or more letters); severities are initial labels. No real email had been read |
| 0.2 | Read off the first train run (6,000 emails): affiliation_external was contradicted in 98% to 100% of its checkable claims in every category, because claims that only MENTION a brand (your Microsoft account, SharePoint Services) were treated as claims of identity, and the claimed organisation was taken from the nearest organisation in the text (Lloyds next to the Financial Services Authority). Now an external claim is checked only if the claim's own words name the organisation and say the sender is that organisation (a team, department, support, security ... or a footer or 'on behalf of'); a mere reference is not checkable. An unrelated domain under an internal claim is low (in sources without a List-Id the recipient domain is often a mailing list, as in the opensuse.org and linux.ie ham examples); an unknown organisation from a free mailbox is low (the name comes from a name recogniser: 'Hi team'). A display name that holds only a bare domain name (brands write their site name, such as Brand.com, in the display name and send through mailers) is now low; only a shown e-mail address is medium. signature_contact compares addresses only for contact claims, not for postal addresses, disclaimers, copyright lines or sign-off names. The attack-versus-ham check now compares the share of EMAILS with a contradicted claim, because the rate among checkable claims is close to 100% in every category when 'checkable' mostly means 'contradicted' |
| 0.3 | Read off the second train run (6,000 emails): the fix of 0.2 removed the external-affiliation false alarms (share of emails with a contradicted external claim 7.1% in phishing against 0.1% in ham), but signature_contact still failed its contrast (7.9% against 4.9%), and its ham alarms were list footers ('List maintainer', 'To unsubscribe from this group', 'For additional commands'), quoted headers ('On Behalf Of', 'Sent:', X-Spam lines) and the reader's own address on a collector domain (ceas-challenge.cc, monkey.org). Now the signature text is cut at the first footer or quoted-header marker, an address on the recipient's domain is ignored when the recipient has no organisation (collector, free mailbox, mailing list), and a signature address on the same free mailbox provider as the sender is not checkable (everyone at hotmail.com matches). 'Office' is no longer a speaker cue ('Microsoft Office' is a product; the digitalriver.com reseller mail in ham). An attack-versus-ham contrast that is above ham but below 2x is now a finding (info), not a failure; only a rate that is not above ham fails |

- **How it is verified without contradiction labels.** Nobody marked which emails contain a contradicted claim, so there is no precision or recall for contradictions; the effect on detection is the N3 ablation of Phase 13. Instead: (1) a self-test of 67 checks (hand-made emails with real header blocks, among them the David email of Section 6.7, the exact-domain spoof, an honest internal mail, a newsletter with spf=fail, mailing-list mail, a display name showing service@paypal.com and paypa1.com; helper checks; eight crafted inputs of 60,000-character fields and floods of '@', each finishing in 0.01 s at most); (2) contradiction rates per category and per source on the train split; (3) the contradictions found in ordinary mail were printed and read; (4) one read of the frozen rules on validation. Claim types are those the Phase 7 extractor found; those claims are agreement-with-LLM-labels quality (Section 8.15), and affiliation_internal claims were found with recall 0.13 on validation, so a missing claim is never evidence of honesty.

- **Results: share of emails with a contradicted claim, train split** (the measure a detector would see; the number in brackets is how many emails; the groups differ in size and in the evidence their sources carry, so read it together with the per-source tables):

| **Claim type** | **Ham** | **Spam** | **Phishing** | **Fraud** |
|---|---|---|---|---|
| all types together | 3.5% (1040) | 1.7% (425) | 18.4% (2202) | 40.9% (923) |
| affiliation_internal | 0.2% (53) | 0.0% (7) | 1.5% (178) | 0.6% (13) |
| affiliation_external | 0.1% (45) | 0.1% (38) | 7.7% (925) | 4.7% (107) |
| authority | 0.0% (12) | 0.1% (26) | 0.3% (41) | 24.4% (551) |
| reply_direction | 0.0% (0) | 0.0% (4) | 0.2% (22) | 0.0% (0) |
| signature_contact | 3.0% (882) | 1.2% (308) | 3.2% (388) | 11.9% (269) |
| prior_relationship | 0.0% (0) | 0.0% (0) | 0.0% (0) | 0.0% (0) |
| payment_request | 0.0% (9) | 0.1% (21) | 0.8% (94) | 12.3% (279) |
| payment_change | 0.0% (0) | 0.0% (1) | 0.3% (32) | 0.6% (13) |
| credential_request | 0.1% (29) | 0.0% (5) | 7.3% (880) | 0.4% (10) |
| gift_card | 0.0% (1) | 0.0% (0) | 0.1% (17) | - |
| data_request | 0.1% (24) | 0.2% (48) | 2.1% (252) | 7.8% (176) |

- **Results: contradicted share of the checkable claims, train split** (results/verifier_rates.csv; 'all types together' is every type counted at once; the second number is how many claims could be checked; a type or category with nothing checkable says so; where 'checkable' mostly means 'contradicted' this rate is close to 100 percent in every category, as the first train read showed, so the email-level table above is the fair comparison; counts only, no email text):

| **Claim type** | **Ham** | **Spam** | **Phishing** | **Fraud** |
|---|---|---|---|---|
| all types together | 52.0% of 2121 | 90.6% of 544 | 83.9% of 4600 | 96.8% of 1869 |
| affiliation_internal | 100.0% of 61 | 100.0% of 7 | 99.0% of 208 | 100.0% of 14 |
| affiliation_external | 100.0% of 49 | 100.0% of 39 | 98.5% of 1199 | 100.0% of 128 |
| authority | 73.7% of 19 | 100.0% of 30 | 58.6% of 87 | 100.0% of 751 |
| reply_direction | 0.0% of 11 | 45.5% of 11 | 38.6% of 70 | none checkable (634) |
| signature_contact | 47.7% of 1899 | 87.5% of 360 | 79.6% of 511 | 84.5% of 388 |
| prior_relationship | none checkable (642) | none checkable (107) | none checkable (280) | none checkable (81) |
| payment_request | 100.0% of 9 | 100.0% of 26 | 63.5% of 178 | 100.0% of 346 |
| payment_change | none checkable (12) | 100.0% of 1 | 100.0% of 37 | 100.0% of 13 |
| credential_request | 94.4% of 36 | 100.0% of 9 | 79.8% of 1866 | 100.0% of 10 |
| gift_card | 100.0% of 1 | none checkable (58) | 68.6% of 35 | - |
| data_request | 80.6% of 36 | 100.0% of 61 | 79.0% of 409 | 100.0% of 219 |

- **Results: per source** (all claim types together; a claim is checkable when the evidence its rule needs exists):

| **Source** | **Split** | **Emails** | **Claims routed** | **Checkable (%)** | **Contradicted of checkable (%)** | **Emails with a contradiction (%)** | **Emails with a high contradiction (%)** |
|---|---|---|---|---|---|---|---|
| apache_kafka_users | train | 735 | 555 | 8.5 | 74.5 | 4.3 | 0.1 |
| apache_tomcat_users | train | 1496 | 812 | 13.9 | 78.8 | 5.7 | 0.0 |
| kaggle_ceas08 | train | 26654 | 17205 | 9.4 | 55.0 | 3.1 | 0.1 |
| kaggle_enron | train | 20383 | 14587 | 0.0 | - | 0.0 | 0.0 |
| kaggle_ling | train | 1995 | 1522 | 0.0 | - | 0.0 | 0.0 |
| kaggle_nigerian_fraud | train | 2259 | 8063 | 23.2 | 96.8 | 40.9 | 1.2 |
| nazario | train | 6716 | 26490 | 11.8 | 87.0 | 22.4 | 2.3 |
| phishing_pot | train | 5262 | 7106 | 20.9 | 77.4 | 13.3 | 1.2 |
| spamassassin | train | 4042 | 3250 | 27.1 | 65.7 | 12.6 | 0.2 |
| apache_kafka_users | validation | 162 | 136 | 11.0 | 73.3 | 6.8 | 0.0 |
| apache_tomcat_users | validation | 315 | 185 | 18.4 | 47.1 | 4.8 | 0.0 |
| kaggle_ceas08 | validation | 5709 | 3534 | 8.3 | 58.3 | 2.8 | 0.0 |
| kaggle_enron | validation | 4368 | 2995 | 0.0 | - | 0.0 | 0.0 |
| kaggle_ling | validation | 427 | 304 | 0.0 | - | 0.0 | 0.0 |
| kaggle_nigerian_fraud | validation | 482 | 1730 | 21.7 | 97.1 | 41.3 | 0.6 |
| nazario | validation | 1440 | 5486 | 11.4 | 88.6 | 20.9 | 2.3 |
| phishing_pot | validation | 1109 | 1488 | 20.6 | 72.5 | 13.9 | 0.9 |
| spamassassin | validation | 867 | 693 | 28.3 | 58.2 | 11.2 | 0.2 |

- **Results: how much of each type could be checked, per source (train)** (share of claims checkable, and the number of claims):

| **Source** | **affiliation_internal** | **affiliation_external** | **authority** | **reply_direction** | **signature_contact** | **payment_request** | **credential_request** |
|---|---|---|---|---|---|---|---|
| apache_kafka_users | - | 6% of 109 | 50% of 2 | 0% of 1 | 8% of 413 | - | 0% of 1 |
| apache_tomcat_users | 0% of 21 | 3% of 215 | 60% of 10 | - | 17% of 510 | - | 50% of 6 |
| kaggle_ceas08 | 30% of 198 | 0% of 9454 | 8% of 181 | 0% of 140 | 23% of 6396 | 13% of 97 | 15% of 202 |
| kaggle_enron | 0% of 344 | 0% of 3440 | 0% of 801 | 0% of 801 | 0% of 6845 | 0% of 256 | 0% of 450 |
| kaggle_ling | 0% of 15 | 0% of 262 | 0% of 18 | 0% of 82 | 0% of 1035 | 0% of 13 | 0% of 4 |
| kaggle_nigerian_fraud | 10% of 144 | 6% of 2258 | 47% of 1604 | 0% of 634 | 19% of 2073 | 50% of 689 | 42% of 24 |
| nazario | 16% of 1236 | 8% of 10615 | 14% of 370 | 38% of 74 | 5% of 5017 | 22% of 482 | 22% of 5993 |
| phishing_pot | 3% of 173 | 12% of 2919 | 71% of 49 | 67% of 63 | 10% of 2768 | 80% of 90 | 75% of 768 |
| spamassassin | 20% of 40 | 3% of 920 | 30% of 93 | 42% of 53 | 40% of 1757 | 54% of 41 | 17% of 72 |

- **Results: train against validation** (the contradicted share of the checkable claims, with the number of checkable claims):

| **Claim type** | **Ham, train** | **Ham, validation** | **Phishing, train** | **Phishing, validation** | **Fraud, train** | **Fraud, validation** |
|---|---|---|---|---|---|---|
| all types together | 52.0% of 2121 | 50.7% of 432 | 83.9% of 4600 | 83.3% of 930 | 96.8% of 1869 | 97.1% of 375 |
| affiliation_internal | 100.0% of 61 | 100.0% of 8 | 99.0% of 208 | 96.0% of 50 | 100.0% of 14 | 100.0% of 2 |
| affiliation_external | 100.0% of 49 | 100.0% of 11 | 98.5% of 1199 | 99.5% of 218 | 100.0% of 128 | 100.0% of 32 |
| authority | 73.7% of 19 | 28.6% of 14 | 58.6% of 87 | 50.0% of 20 | 100.0% of 751 | 100.0% of 154 |
| reply_direction | 0.0% of 11 | none checkable (119) | 38.6% of 70 | 47.1% of 17 | none checkable (634) | none checkable (121) |
| signature_contact | 47.7% of 1899 | 47.0% of 383 | 79.6% of 511 | 70.0% of 120 | 84.5% of 388 | 82.8% of 64 |
| prior_relationship | none checkable (642) | none checkable (114) | none checkable (280) | none checkable (68) | none checkable (81) | none checkable (18) |
| payment_request | 100.0% of 9 | 100.0% of 2 | 63.5% of 178 | 79.2% of 24 | 100.0% of 346 | 100.0% of 72 |
| payment_change | none checkable (12) | none checkable (1) | 100.0% of 37 | 100.0% of 15 | 100.0% of 13 | none checkable (2) |
| credential_request | 94.4% of 36 | 100.0% of 8 | 79.8% of 1866 | 80.2% of 379 | 100.0% of 10 | 100.0% of 3 |
| gift_card | 100.0% of 1 | none checkable (8) | 68.6% of 35 | 100.0% of 5 | - | - |
| data_request | 80.6% of 36 | 100.0% of 6 | 79.0% of 409 | 79.3% of 82 | 100.0% of 219 | 100.0% of 48 |

- **Most frequent rules on the train emails** (results/verifier_rule_hits.csv):

| **Rule** | **Claim type** | **Rows** | **Contradiction** | **Consistent** | **Not checkable** | **Meaning** |
|---|---|---|---|---|---|---|
| hv_sig_not_contact | signature_contact | 13863 | 0 | 0 | 13863 | a postal address, disclaimer, copyright line or sign-off name is not a contact address to compare |
| hv_ext_reference | affiliation_external | 13117 | 0 | 0 | 13117 | names an organisation without saying the sender is that organisation (your PayPal account) |
| rv_no_proof | any request | 8361 | 0 | 0 | 8361 | nothing contradicts the asker, but nothing proves who they are |
| hv_ext_no_org | affiliation_external | 5155 | 0 | 0 | 5155 | the claim names no organisation |
| hv_sig_no_from | signature_contact | 5027 | 0 | 0 | 5027 | no usable From address |
| hv_sig_no_address | signature_contact | 4530 | 0 | 0 | 4530 | the sender's signature block holds no e-mail address (list footers, quoted headers and the reader's own address are ignored) |
| hv_ext_unknown_org | affiliation_external | 4446 | 0 | 0 | 4446 | the claimed organisation has no known domain |
| hv_ext_no_from | affiliation_external | 4430 | 0 | 0 | 4430 | no usable From address |
| rv_no_from | any request | 2173 | 0 | 0 | 2173 | no usable From address |
| hv_reply_no_header | reply_direction | 1756 | 0 | 0 | 1756 | no Reply-To header to compare |
| hv_int_no_org | affiliation_internal | 1712 | 0 | 0 | 1712 | no organisation domain is known for the recipient |
| hv_sig_other_domain | signature_contact | 1711 | 1711 | 0 | 0 | no signature address belongs to the sender's domain |
| hv_ext_brand_no_auth | affiliation_external | 1629 | 0 | 0 | 1629 | From shows the brand's domain, but no authentication verdict exists |
| hv_auth_no_evidence | authority | 1258 | 0 | 0 | 1258 | rank claimed, nothing to compare it with |

- **Reading of the tables** (every number and comparison below is computed from the results files by the script that wrote this section):

    - on the 69542 train emails, 79590 claims were routed to a verifier (32872 emails had at least one); 11.5% of them could be checked and 79.5% of the checkable ones were contradicted; on the validation emails 11.2% could be checked and 78.7% of those were contradicted.
    - share of emails with at least one contradicted claim, train: ham 3.5%, spam 1.7%, phishing 18.4%, fraud 40.9%; with a high-severity contradiction: ham 0.1%, spam 0.0%, phishing 1.8%, fraud 1.2%; validation: ham 3.2%, spam 1.4%, phishing 17.9%, fraud 41.3%.
    - attack-versus-ham contrasts on the train split (the share of emails with a contradicted claim of the type at least twice the ham share): 5 of 6 pass (affiliation_external on phishing: 7.7% vs ham 0.1%; authority on fraud: 24.4% vs ham 0.0%; credential_request on phishing: 7.3% vs ham 0.1%; payment_request on fraud: 12.3% vs ham 0.0%; data_request on fraud: 7.8% vs ham 0.1%), 1 not judged for lack of 20 checkable claims in the attack category (signature_contact on phishing); attacks and ham come from different corpora with different header evidence, so a contrast is partly a difference between corpora, and the per-source rows of the tables show it.
    - the share of claims that could be checked runs from 0.0% (kaggle_enron) to 27.1% (spamassassin) across the sources, because the evidence differs by source (Section 8.11); a source without the evidence a rule needs shows 'not checkable', never 'no contradiction'.
    - from train to validation the contradicted share of checkable claims (all types) moved, in percentage points: ham -1.3, spam -3.6, phishing -0.6, fraud +0.3; the rules were frozen before validation was read, so this is the first unbiased reading of this version.
    - header verifier: hv_sig_other_domain (37.9% of its contradictions).
    - request verifier: rv_freemail (34.1% of its contradictions).
    - 7 of the 63 rules never fired on the train emails (a finding, not a failure: some rules guard rare situations such as a forged brand domain).

- **Checks** (results/verifier_checks.csv): 31 PASS, 0 FAIL, 10 info. They cover the self-test, the brand file (no free-mailbox domain, every KNOWN_ORGS name covered, every domain a registered domain), every ledger row (keys, severity fits the contradiction value, known rule, safe reason), that contradiction + consistent + not checkable add up to the claims in every group, that no rule that reads authentication fires without a verdict, that no internal-affiliation row is decided without an organisation domain or on mailing-list mail, that no weak-claim contradiction has severity high, the attack-versus-ham contrasts, crafted inputs, and the splits read (train, and validation in the final run; never test). The full run took 90 seconds.

- **Known limits:** brand domains are written by hand for 51 organisations; a brand that is not listed can only be compared when the sender is a free mailbox (medium) and is otherwise not checkable; internal-affiliation checks need the recipient's organisation domain, which exists for only 3.6% of phishing_pot and 9.8% of Nazario emails (Section 8.11), so real internal-affiliation evidence is thin; a sender that authenticates as its own domain is 'consistent' only in the sense that nothing contradicts it, and a compromised real account passes every check here (that is what the thread verifier is for); prior_relationship claims are not checkable until Phase 9; attacks and ham come from different corpora, so the category contrasts are partly corpus contrasts; the claim extractor works on English only; severities are initial labels, calibrated in Phase 10 on validation; the synthetic emails have no headers, so Phase 13 will generate clearly synthetic header blocks for the N3 ablation only (generating them now would mean tuning the rules on headers written by the same person), reported apart from the real results.

- **Security:** see Section 10 (verifiers).

## 8.17 Phase 9 thread builder, thread-hijack benchmark and thread verifier

- **Output:** src/thread (signals.py, builder.py, features.py, build.py, selftest.py, evaluate.py, README.md), src/verifiers/thread_verifier.py, src/data/hijack_benchmark.py and data/threads/ (plan, injected texts, raw replies, manifest, README). `verify_claims` gained an optional `thread=(messages, index)` argument (default None: the Phase 8 behaviour is unchanged, RULES_VERSION stays 0.3); `verify_thread_message(messages, index)` and `scan_thread(messages)` return the thread verifier's rows and the flip index. Results in results/thread_counts.csv, thread_signal_rates.csv, thread_checks.csv, hijack_generation.csv, hijack_cases.csv, thread_scores.csv and hijack_checks.csv. No new library. The thread rules are version 0.2 (44 rules).

- **Finding the threads.** Apache list mail keeps Message-ID, In-Reply-To and References, so two messages join a thread when one names the other (union-find; cycles and missing parents are harmless) and messages are ordered by date. Raw Enron has none of these (0%, Section 8.1), so its threads are guessed as old mail clients did: the subject without Re:/Fw: prefixes, cut into runs (a gap of more than 14 days starts a new run), and messages in a run join when they share a participant; copies of one message in several folders (they carry different Message-IDs in this dump) are removed by date, sender and subject. A thread needs 3 to 50 messages and at least two senders; an Enron thread also needs two reply subjects. The Enron index covered 517432 files (251755 distinct messages after removing copies, 125659 subject groups, 140391 runs, 15444 candidate threads; the full text of 2000 candidates was read, in hash order, until 1200 threads were kept). The new text of a message is cut exactly as Phase 2 cuts a body; the quotation (the lines marked > and, after an Outlook-style marker, everything that follows) and the whole text are kept as well, because the thread verifier compares a quotation with the whole text of the earlier messages (an inline answer is quoted back by the next reply). A thread is the unit of the split (70/15/15 from the SHA-256 of seed 42 and the thread id), so no thread stands in two splits.

| **Source** | **Train threads** | **Validation threads** | **Test threads** | **Messages (all splits)** |
|---|---|---|---|---|
| apache | 253 | 72 | 66 | 2309 |
| enron | 851 | 161 | 188 | 5471 |

Groups dropped, and why (all splits; results/thread_counts.csv):

| **Source** | **Candidate groups** | **One message** | **Under 3 messages** | **Over 50 messages** | **One sender only** | **Under 2 reply subjects** | **Messages without a date** | **Kept** |
|---|---|---|---|---|---|---|---|---|
| apache | 937 | 362 | 179 | 1 | 4 | 0 | 0 | 391 |
| enron | 2000 | 0 | 0 | 0 | 507 | 241 | 0 | 1200 |

- **The thread verifier (N2).** src/thread/signals.py measures; src/verifiers/thread_verifier.py judges. Four signals (Section 4.3), each message judged against the messages before it:

| **Signal** | **What is compared** | **Rules (initial severity)** |
|---|---|---|
| Tactic onset | the tactic probabilities of the message against every earlier message, for authority, urgency, scarcity and secrecy (the only tactics with enough real positives in Phase 6); needs two earlier messages | a tactic reaches its Phase 6 threshold here, in no earlier message, and is at least 0.40 above the average of the earlier messages: tv_onset_one (medium); two or more at once: tv_onset_many (high) |
| Request drift | the bank details of the message against all earlier text of the thread (a set difference, bank_detail_keys), and request types against earlier requests | tv_bank_changed (high: a different detail of the same kind), tv_bank_new (medium); first credential, gift-card or payment-change request tv_req_*_new (medium); first payment or data request (low) |
| Sending-path drift | the sender against the earlier senders (same address, or the name or local part of an earlier sender at another domain); for the same address, the network of the first public IP of the Received chain (the first three numbers) and the mail program with its version dropped | tv_who_lookalike (high), tv_who_suffix (medium), tv_who_other_domain (low); tv_path_origin_mailer (medium), tv_path_origin and tv_path_mailer (low) |
| Thread integrity | In-Reply-To and References against the Message-IDs of the thread; the quotation (lines marked >, or everything after an Outlook-style marker) against the whole text of the earlier messages (5-word shingles); forwards are not checked | tv_int_ids_unknown (medium), tv_int_parent_missing (low); tv_quote_mismatch (high: a quotation of 20 words or more of which under 30% of the shingles occur in the earlier messages) |
| prior_relationship claim | did this sender take part earlier in the thread? (a call outside the thread cannot be disproved) | tv_prior_other_address, tv_prior_stranger (low); tv_prior_ok consistent |
| Single-email mode | a Re: subject with quoted history but no In-Reply-To or References | tv_single_no_reply_ids (low) |

Rows have three values as in Phase 8 (contradiction, consistent, not checkable); missing evidence is never 'no contradiction' (raw Enron replies carry no IDs, so tv_int_no_ids says not checkable there and the quote rule still runs). The flip point is the first message with a medium or high contradiction, judged message by message against its own past (change-point detection in its simplest form). Style drift, the optional fifth signal of Section 4.3, was not built (first to drop, Section 12.4). Fixed numbers: the Phase 6 thresholds, a rise of 0.40 over the earlier average for a tactic onset (added in version 0.2), a quotation of 20 words matched by 30% of its 5-word shingles, a person identified by 5 letters of name or local part, the /24 network of an IP address (version 0.2). Severities are initial labels; Phase 10 turns them into points.

- **The benchmark.** Nobody has labelled real hijacks, so they are made: a real thread is cut before message k (k at least 2) and an attacker's message takes its place. The base threads are real; the injected texts are synthetic (the free Gemini API, as in Phase 5; one call per four threads gives an attack reply, a benign reply and a fabricated quotation, checked word by word; bank details are inserted by code as a valid fictional IBAN). Five cases per thread: **neg_real** (the real next reply), **neg_synth** (the benign text with the sender's real details, genuine IDs and quotation: the style control), **A takeover** (the attack text from the real sender with the same server, mail program and IDs: only the content signals can see it, and N3 sees the same headers as for the real reply), **B swap** (the benign text from a look-alike of the sender's domain with a new server and mail program; Apache only) and **C forged** (the benign text with a fabricated quotation and, on Apache, Message-IDs that do not exist). B and C use the benign text, so the same words appear as a negative and as a positive and a detector cannot win by recognising the generator's style (Section 8.5); each signal is tested in its own variant, and an attacker who changes everything at once is easier to catch. The injected message ends the thread (the later real messages quote the real reply, not the injected one). Of 300 planned Enron threads 294 were valid and of 200 planned Apache threads 198 (results/hijack_generation.csv).

| **Split** | **Source** | **Threads** | **A takeover** | **B swap** | **C forged** | **neg_real** | **neg_synth** |
|---|---|---|---|---|---|---|---|
| test | apache | 25 | 25 | 17 | 25 | 25 | 25 |
| test | enron | 51 | 51 | 0 | 51 | 51 | 51 |
| train | apache | 133 | 133 | 91 | 133 | 133 | 133 |
| train | enron | 214 | 214 | 0 | 214 | 214 | 214 |
| validation | apache | 40 | 40 | 26 | 40 | 40 | 40 |
| validation | enron | 29 | 29 | 0 | 29 | 29 | 29 |

- **Protocol (no leakage).** The rules were written from Sections 4.3 and 6.4 and the Phase 3, 7 and 8 notes, and revised only after reading TRAIN results; `build.py --train-only` and `evaluate.py --train-only` never score a validation thread; the final runs score the validation threads once for the frozen version; the test threads are built but never scored (Phase 13). Threads containing a message the tactic classifier trained on are kept out of validation and test (Apache by id; raw Enron cannot be matched to the Kaggle copy, and only 80 of the 29,119 Kaggle Enron emails were labelled). The train numbers are development numbers. Rule versions:

| **Version** | **What the train results showed, and the change** |
|---|---|
| 0.1 | First version: rules written from master document Sections 4.3 and 6.4 and the Phase 3, 7 and 8 notes. Fixed numbers: the Phase 6 thresholds, a quotation of 20 words matched by 30% of its 5-word shingles, a person identified by 5 letters of name or local part. Severities are initial labels. No real thread had been read |
| 0.2 | Read off the first train run (1,104 threads, no benchmark yet; false alarms on real threads: Apache 29 of 1,243 messages, Enron 158 of 3,034). (1) tv_quote_mismatch fired 27 times on Apache and 98 on Enron, and the examples were Apache replies that answer INLINE: the code counted the sender's own answers between the quoted paragraphs as 'quoted history', and compared the quotation only with the earlier messages' new text, so the earlier inline answers a reply quotes back were missing. Now the quotation is only the lines marked '>' (plus everything after an Outlook-style marker, which has no '>' marks), it is compared with the WHOLE text of every earlier message, and a forward (a Fw: subject) is not checked, because it quotes a message from outside the thread (new rule tv_quote_forward, not checkable). (2) tv_onset_one fired 45 times and tv_onset_many 15 times on Enron, mostly urgency crossing its threshold of 0.45 by a hair (0.46 after 0.45, 0.47 after 0.27); now a tactic also has to be at least 0.40 above the AVERAGE of the earlier messages (the wording of master document Section 4.3), because an attack jumps (0.1 to 0.9). (3) tv_path_origin fired on 402 of 1,243 Apache messages because IP addresses rotate; now the network (the first three numbers of an IPv4 address) is compared, not the exact address. Not changed: tv_path_origin_mailer fired once, tv_who_lookalike and tv_int_ids_unknown never on real threads |

- **How it is verified.** (1) A self-test of hand-made threads, one for every rule, with the rules each must fire and must not fire, the scan and API checks and nine crafted hostile inputs (src/thread/selftest.py). (2) False alarms on real, unmodified threads: every medium or high contradiction there is a false alarm, and the contradictions were printed and read. (3) The benchmark: detection per variant and source against the header and request verifiers alone, the signal that caught each case, false alarms on the real and the synthetic negatives, and whether the scan flips at the injected message. Rates carry a 95% bootstrap interval that resamples threads, not cases (the cases of one thread share its history), and a cell with fewer than 10 cases is reported as a count only.

- **Results: false alarms on real threads** (messages with a past; nobody hijacked these; results/thread_signal_rates.csv):

| **Split** | **Source** | **Threads** | **Messages with a past** | **With a medium or high contradiction** | **Share** | **With a high one** |
|---|---|---|---|---|---|---|
| train | apache | 253 | 1243 | 5 | 0.4% | 3 |
| train | enron | 851 | 3034 | 108 | 3.6% | 98 |
| validation | apache | 72 | 379 | 4 | 1.1% | 3 |
| validation | enron | 161 | 539 | 26 | 4.8% | 25 |

- **Results: the rules that fire most often on real train threads** (results/thread_signal_rates.csv):

| **Rule** | **Signal** | **Rows** | **Contradiction** | **Consistent** | **Not checkable** | **Meaning** |
|---|---|---|---|---|---|---|
| tv_path_origin | sending_path | 299 | 299 | 0 | 0 | the same address from a new server |
| tv_quote_mismatch | thread_integrity | 89 | 89 | 0 | 0 | the quoted history is not what the earlier messages said |
| tv_single_no_reply_ids | single_email | 89 | 89 | 0 | 0 | a reply with quoted history but no In-Reply-To or References |
| tv_req_data_new | data_request | 37 | 37 | 0 | 0 | the first request for personal or company data in the thread |
| tv_prior_stranger | prior_relationship | 20 | 20 | 0 | 0 | this sender wrote none of the earlier messages of a longer thread |
| tv_int_parent_missing | thread_integrity | 15 | 15 | 0 | 0 | In-Reply-To names a message not in the thread, References name known ones |
| tv_req_payment_new | payment_request | 14 | 14 | 0 | 0 | the first payment request in the thread |
| tv_onset_many | tactic_onset | 11 | 11 | 0 | 0 | two or more tactics jump above their thresholds together in this message |
| tv_onset_one | tactic_onset | 11 | 11 | 0 | 0 | one tactic jumps above its threshold here and in no earlier message |
| tv_req_credential_new | credential_request | 7 | 7 | 0 | 0 | the first request for login details in the thread |

- **Results: detection on hijacked cases** (rate with a 95% interval over threads, then hits of n; results/thread_scores.csv):

train, apache threads:

| **Hijacked case** | **N2 (thread verifier)** | **Header and request verifiers (Phase 8)** | **Either** | **Found by N2 only** |
|---|---|---|---|---|
| A | 79.7% [72.2, 86.5] (106 of 133) | 25.6% [18.0, 33.1] (34 of 133) | 86.5% [80.5, 91.7] (115 of 133) | 60.9% [52.6, 69.2] (81 of 133) |
| B | 100.0% [100.0, 100.0] (91 of 91) | 0.0% [0.0, 0.0] (0 of 91) | 100.0% [100.0, 100.0] (91 of 91) | 100.0% [100.0, 100.0] (91 of 91) |
| C | 100.0% [100.0, 100.0] (133 of 133) | 0.0% [0.0, 0.0] (0 of 133) | 100.0% [100.0, 100.0] (133 of 133) | 100.0% [100.0, 100.0] (133 of 133) |
| attacks (A+B+C) | 92.4% [89.7, 94.7] (330 of 357) | 9.5% [7.0, 12.2] (34 of 357) | 95.0% [92.6, 97.0] (339 of 357) | 85.4% [82.4, 88.4] (305 of 357) |

train, enron threads:

| **Hijacked case** | **N2 (thread verifier)** | **Header and request verifiers (Phase 8)** | **Either** | **Found by N2 only** |
|---|---|---|---|---|
| A | 89.7% [85.5, 93.5] (192 of 214) | 4.7% [2.3, 7.5] (10 of 214) | 90.2% [86.0, 93.9] (193 of 214) | 85.5% [80.8, 90.2] (183 of 214) |
| C | 88.3% [84.1, 92.5] (189 of 214) | 0.5% [0.0, 1.4] (1 of 214) | 88.3% [83.6, 92.5] (189 of 214) | 87.9% [83.2, 92.5] (188 of 214) |
| attacks (A+B+C) | 89.0% [85.5, 91.8] (381 of 428) | 2.6% [1.2, 4.2] (11 of 428) | 89.3% [86.0, 92.1] (382 of 428) | 86.7% [83.4, 89.7] (371 of 428) |

validation, apache threads:

| **Hijacked case** | **N2 (thread verifier)** | **Header and request verifiers (Phase 8)** | **Either** | **Found by N2 only** |
|---|---|---|---|---|
| A | 80.0% [67.5, 90.0] (32 of 40) | 17.5% [7.5, 30.0] (7 of 40) | 82.5% [70.0, 92.5] (33 of 40) | 65.0% [50.0, 80.0] (26 of 40) |
| B | 100.0% [100.0, 100.0] (26 of 26) | 0.0% [0.0, 0.0] (0 of 26) | 100.0% [100.0, 100.0] (26 of 26) | 100.0% [100.0, 100.0] (26 of 26) |
| C | 100.0% [100.0, 100.0] (40 of 40) | 0.0% [0.0, 0.0] (0 of 40) | 100.0% [100.0, 100.0] (40 of 40) | 100.0% [100.0, 100.0] (40 of 40) |
| attacks (A+B+C) | 92.5% [87.5, 96.4] (98 of 106) | 6.6% [2.8, 11.1] (7 of 106) | 93.4% [88.7, 97.2] (99 of 106) | 86.8% [81.5, 91.7] (92 of 106) |

validation, enron threads:

| **Hijacked case** | **N2 (thread verifier)** | **Header and request verifiers (Phase 8)** | **Either** | **Found by N2 only** |
|---|---|---|---|---|
| A | 100.0% [100.0, 100.0] (29 of 29) | 0.0% [0.0, 0.0] (0 of 29) | 100.0% [100.0, 100.0] (29 of 29) | 100.0% [100.0, 100.0] (29 of 29) |
| C | 82.8% [69.0, 96.6] (24 of 29) | 0.0% [0.0, 0.0] (0 of 29) | 82.8% [69.0, 96.6] (24 of 29) | 82.8% [69.0, 96.6] (24 of 29) |
| attacks (A+B+C) | 91.4% [84.5, 98.3] (53 of 58) | 0.0% [0.0, 0.0] (0 of 58) | 91.4% [84.4, 98.3] (53 of 58) | 91.4% [84.5, 98.3] (53 of 58) |

- **Results: which signal caught the hijacked cases, and where the scan flips** (validation):

validation, apache threads:

| **Variant** | **Tactic onset** | **Request drift** | **Sending path** | **Thread integrity** | **Scan flips at the injected message** | **Scan flips earlier** |
|---|---|---|---|---|---|---|
| A | 30.0% (12 of 40) | 67.5% (27 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) | 77.5% (31 of 40) | 2.5% (1 of 40) |
| B | 0.0% (0 of 26) | 0.0% (0 of 26) | 100.0% (26 of 26) | 0.0% (0 of 26) | 100.0% (26 of 26) | 0.0% (0 of 26) |
| C | 0.0% (0 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) | 100.0% (40 of 40) | 97.5% (39 of 40) | 2.5% (1 of 40) |

validation, enron threads:

| **Variant** | **Tactic onset** | **Request drift** | **Sending path** | **Thread integrity** | **Scan flips at the injected message** | **Scan flips earlier** |
|---|---|---|---|---|---|---|
| A | 37.9% (11 of 29) | 82.8% (24 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) | 93.1% (27 of 29) | 6.9% (2 of 29) |
| C | 0.0% (0 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) | 82.8% (24 of 29) | 79.3% (23 of 29) | 6.9% (2 of 29) |

- **Results: false alarms on the negative cases:**

train, apache threads:

| **Negative case** | **N2** | **Header and request verifiers** | **Either** | **Scan flags some message** |
|---|---|---|---|---|
| neg_real | 1.5% [0.0, 3.8] (2 of 133) | 0.0% [0.0, 0.0] (0 of 133) | 1.5% [0.0, 3.8] (2 of 133) | 3.0% [0.8, 6.0] (4 of 133) |
| neg_synth | 0.0% [0.0, 0.0] (0 of 133) | 0.0% [0.0, 0.0] (0 of 133) | 0.0% [0.0, 0.0] (0 of 133) | 1.5% [0.0, 3.8] (2 of 133) |

train, enron threads:

| **Negative case** | **N2** | **Header and request verifiers** | **Either** | **Scan flags some message** |
|---|---|---|---|---|
| neg_real | 1.4% [0.0, 3.3] (3 of 214) | 0.0% [0.0, 0.0] (0 of 214) | 1.4% [0.0, 3.3] (3 of 214) | 7.9% [4.7, 11.7] (17 of 214) |
| neg_synth | 0.0% [0.0, 0.0] (0 of 214) | 0.5% [0.0, 1.4] (1 of 214) | 0.5% [0.0, 1.4] (1 of 214) | 6.5% [3.3, 10.3] (14 of 214) |

validation, apache threads:

| **Negative case** | **N2** | **Header and request verifiers** | **Either** | **Scan flags some message** |
|---|---|---|---|---|
| neg_real | 0.0% [0.0, 0.0] (0 of 40) | 0.0% [0.0, 0.0] (0 of 40) | 0.0% [0.0, 0.0] (0 of 40) | 2.5% [0.0, 7.5] (1 of 40) |
| neg_synth | 0.0% [0.0, 0.0] (0 of 40) | 0.0% [0.0, 0.0] (0 of 40) | 0.0% [0.0, 0.0] (0 of 40) | 2.5% [0.0, 7.5] (1 of 40) |

validation, enron threads:

| **Negative case** | **N2** | **Header and request verifiers** | **Either** | **Scan flags some message** |
|---|---|---|---|---|
| neg_real | 6.9% [0.0, 17.2] (2 of 29) | 0.0% [0.0, 0.0] (0 of 29) | 6.9% [0.0, 17.2] (2 of 29) | 13.8% [3.4, 27.6] (4 of 29) |
| neg_synth | 0.0% [0.0, 0.0] (0 of 29) | 0.0% [0.0, 0.0] (0 of 29) | 0.0% [0.0, 0.0] (0 of 29) | 6.9% [0.0, 17.2] (2 of 29) |

- **Reading of the tables** (every number and comparison below is computed from the results files by the script that wrote this section):

    - 1591 threads were rebuilt (391 apache, 1200 enron); the thread split puts 1104 in train, 233 in validation and 254 in test.
    - false alarms on real, unmodified apache threads (train): 5 of 1243 messages with a past got a medium or high contradiction (0.4%).
    - false alarms on real, unmodified enron threads (train): 108 of 3034 messages with a past got a medium or high contradiction (3.6%).
    - false alarms on real, unmodified apache threads (validation): 4 of 379 messages with a past got a medium or high contradiction (1.1%).
    - false alarms on real, unmodified enron threads (validation): 26 of 539 messages with a past got a medium or high contradiction (4.8%).
    - the contradiction that fires most often on real train threads is tv_path_origin (299 rows), followed by tv_quote_mismatch (89), tv_single_no_reply_ids (89), tv_req_data_new (37).
    - validation, apache, account takeover (A): N2 found 80.0% (32 of 40); the Phase 8 verifiers alone found 17.5% (7 of 40); N2 found 65.0% (26 of 40) that they missed.
    - validation, apache, look-alike swap (B): N2 found 100.0% (26 of 26); the Phase 8 verifiers alone found 0.0% (0 of 26); N2 found 100.0% (26 of 26) that they missed.
    - validation, apache, forged thread (C): N2 found 100.0% (40 of 40); the Phase 8 verifiers alone found 0.0% (0 of 40); N2 found 100.0% (40 of 40) that they missed.
    - validation, enron, account takeover (A): N2 found 100.0% (29 of 29); the Phase 8 verifiers alone found 0.0% (0 of 29); N2 found 100.0% (29 of 29) that they missed.
    - validation, enron, forged thread (C): N2 found 82.8% (24 of 29); the Phase 8 verifiers alone found 0.0% (0 of 29); N2 found 82.8% (24 of 29) that they missed.
    - validation, apache, the real next reply (neg_real): N2 flagged 0.0% (0 of 40); the Phase 8 verifiers flagged 0.0% (0 of 40).
    - validation, enron, the real next reply (neg_real): N2 flagged 6.9% (2 of 29); the Phase 8 verifiers flagged 0.0% (0 of 29).
    - from train to validation (apache, variant A) the N2 detection rate moved by +0.3 percentage points; the rules were frozen before validation was read, so this is the first unbiased reading.
    - from train to validation (apache, variant B) the N2 detection rate moved by +0.0 percentage points; the rules were frozen before validation was read, so this is the first unbiased reading.
    - from train to validation (apache, variant C) the N2 detection rate moved by +0.0 percentage points; the rules were frozen before validation was read, so this is the first unbiased reading.
    - from train to validation (enron, variant A) the N2 detection rate moved by +10.3 percentage points; the rules were frozen before validation was read, so this is the first unbiased reading.
    - from train to validation (enron, variant C) the N2 detection rate moved by -5.5 percentage points; the rules were frozen before validation was read, so this is the first unbiased reading.
    - each signal is tested in its own variant by construction: variant A copies the sender's server, mail program and IDs, B changes the domain and path only and C the IDs and the quotation only; the isolation checks of results/hijack_checks.csv confirm that no signal fired where the injection copied its details.
    - a detection rate here says the rules do what they are defined to do against this construction; it does not say how often real attackers behave this way, and every number depends on the threshold choices of Section 8.14 and the claim extractor of Section 8.15.

- **Checks** (results/thread_checks.csv and results/hijack_checks.csv): thread_checks.csv: 16 PASS, 0 FAIL, 7 info; hijack_checks.csv: 15 PASS, 0 FAIL, 4 info. They cover the self-test, every ledger row (keys, severity fits contradiction, known rule, safe reason), the thread structure (positions, sizes, no thread in two splits), the splits scored (train, and validation in the final run; never test), the construction invariants (no sending-path or integrity signal fires on variant A or on the genuine synthetic negatives, no integrity signal on B, no sending-path signal on C), the false-alarm rate of N2 on the real next reply and the crafted inputs.

- **Known limits:** the injected texts and headers are synthetic and written from the same fields the signals read, so the detection rates test the rules against the construction, not real attackers; the false alarms on real threads are the honest measure of noise. A hijacker who has read the mailbox can copy real Message-IDs, sending details and wording; then only the content signals can catch the message (variant A), and an attacker who also keeps the content calm cannot be caught by this verifier at all. Enron threads are guessed from subjects and participants and carry no sending-path data or reply IDs, so they test the content signals and the quote check; Apache threads test all four, but the list's own relay hops are not the author's, and the origin IP and mail program change for harmless reasons (a new phone, a trip), so one change alone is low. Tactic probabilities come from a model trained on LLM labels from one model family and claims from a rule-based extractor (recall 0.13 on affiliation_internal), so a missing claim is never evidence of honesty; request drift also depends on that extractor finding the earlier requests. The prompts leave the machine as redacted excerpts of public corpora and a free API tier may keep them; one model family wrote all injected texts; the benchmark threads are those with an eligible injection point. The single-email rule (tv_single_no_reply_ids) is low severity because many real replies lack reply headers (the rate on Apache is in results/thread_checks.csv). Severities are initial labels, calibrated in Phase 10 on validation, never on test. The N2 ablation with the risk score is Phase 13.

- **Security:** see Section 10 (thread verifier).

## 8.18 Phase 10 claim router, verdict ledger, risk score and LIME highlights

- **Output:** src/router (router.py, ledger.py, score.py, reliability.json, pipeline.py, selftest.py, build.py, build_selftest.py, README.md), src/explain (lime_explain.py, check.py, README.md) and results/score_*.csv and lime_checks.csv. `analyze(raw_email_or_thread, org_domain=None, explain=True, request_id=None)` in src/router/pipeline.py runs the whole pipeline of Figure 3 for one request and returns the report of Section 6.3; the API (Phase 11) calls it and nothing else. No new library: LIME is written by hand (numpy and pandas were already installed). Self-tests: router, ledger, score and pipeline 108 PASS (103 in Phase 10; Phase 11 added five for nested MIME, Section 8.19); LIME 33; build.py on a made-up dataset 38; the LIME check's own self-test 6.

- **The router.** `ROUTES` in src/verifiers/rows.py is the table of Section 6.4 (claim type to verifier). `assign(claims, has_thread)` gives every claim the verifier or verifiers that can check it (with a thread, the five request types also go to the thread verifier and prior_relationship goes to it), reports a claim of an unknown type as skipped and never drops one silently; `check_routing` finds a claim that got no row and a row that names no claim. In JavaScript terms the router is an Express route table.

- **The ledger.** `build_ledger` collects the claim rows (`verify_claims`, Phases 8 and 9) and the thread signal rows (`verify_thread_message`, Phase 9) and checks them: every row passes `check_row`, every rule is filed under its verifier, no claim is lost, no claim has two rows from one verifier. `coverage` counts the claims found, checked, contradicted, consistent and not checkable and says in one fixed sentence what could not run and why (no headers, no organisation domain, no thread). `flat_features` gives the same signals as one fixed-length vector, so Phase 13 can build the flat classifier of the architecture ablation from exactly the signals the routed pipeline used.

- **analyze().** Parse (Phase 3; headers are optional: a pasted body is analysed as a body, every check that needs the sender is not checkable and the coverage says so), clean and redact (Phase 2), tactic probabilities (Phase 6), claims (Phase 7), route and verify (Phases 8 and 9), ledger, score, LIME for the tactics that fired. A thread is a list of messages in any order, sorted by Date when every message has one, at most 50 (the last 50), and the newest is judged against the earlier ones; a list of one is a single email. `check_report` runs on every report before it is returned: it recomputes the score and the coverage from the ledger and the tactics, checks that the verdict fits the score, that every claim span and every highlight is the slice of the text it names, and that no string holds markup. A mismatch raises `ReportError`, which is a bug and never a result.

- **The score (version 0.2).** Section 6.6 gives the formula. The frozen numbers (results/score_config.csv):

| **Setting** | **Value** |
|---|---|
| Points per severity: high / medium / low | 60 / 35 / 5 |
| Weight of each further claim group (the k-th counts this much times the one before) | 0.5 |
| Pressure multiplier: urgency / secrecy (each adds this to 1) | 0.25 / 0.25 |
| Tactic points each / at most | 4 / 12 |
| Bands: Suspicious from / High risk from | 35 / 70 |
| Rules with a reliability factor below 1 | 3 |

  The self-test checks the worked values: a lone medium 35, a lone high 60, a lone high with urgency 75 (79 with its 4 tactic points), two highs 90, twelve lows 10, the cap at 100, and that adding a contradiction or a fired tactic never lowers the score (400 random cases). Reciprocity, social proof and liking are shown but not scored (Phase 6: fewer than 10 real positives and no usable detection).

- **Calibration without labels.** Nobody labelled contradictions, so the score has no precision or recall here and nothing can be fitted to attack detection. What is calibrated is the false-alarm side, against a budget that was declared in build.py before the validation emails were read: per source of legitimate mail (ham) and per source of real unmodified thread messages, with at least 20 messages that had a checked claim, High risk at most 1% and Suspicious or above at most 5%. The budget is a policy choice, not something the data decide, and it is a security choice too: a tool that cries wolf gets switched off. Three things are fixed by hand before any data are read: the meaning (a lone high is Suspicious but not High risk, a lone medium is Suspicious, a lone high with one pressure tactic is High risk, a low alone stays under the Suspicious cut), the grid of 27 points (high 50, 60, 70; medium 25, 35, 45; pressure step 0.15, 0.25, 0.35) and the rule for choosing: among the points that keep the meaning and meet the budget the one nearest to the initial numbers; if there is none the initial numbers are kept and the miss is reported. The attack corpora, the hijack benchmark and the labelled tactics are reported against the chosen numbers and never used to choose them (the benchmark cases are built to trigger the rules, so fitting on them would be circular; attacks and legitimate mail come from different corpora).

- **Reliability factors** (src/router/reliability.json, written by `python -m src.router.build --weights-only --write-reliability` from every train email, 69542 scored). A rule that fires on more than 5% of the checked legitimate mail (ham) of a source, or of the real thread messages of a source, with at least 20 hits, counts 0.5; above 10% it counts 0. 5% is the Suspicious budget: such a rule would breach it on its own. Result:

  - `hv_sig_freemail_sender` counts 0: it fired on 28.71% of the checked legitimate messages of apache_tomcat_users (29 of 101).
  - `hv_sig_other_domain` counts 0: it fired on 45.54% of the checked legitimate messages of apache_tomcat_users (46 of 101).
  - `tv_path_origin` counts 0: it fired on 24.05% of the checked thread messages of apache (299 of 1243).

  Rules that came near but stayed at 1.0 (largest rate per rule, at least 20 hits): hv_int_other_domain 3.48% of kaggle_ceas08 (48 of 1378); tv_single_no_reply_ids 2.87% of enron (87 of 3034); tv_quote_mismatch 2.83% of enron (86 of 3034); rv_freemail 2.39% of kaggle_ceas08 (33 of 1378); hv_ext_unknown_freemail 1.67% of kaggle_ceas08 (23 of 1378); tv_req_data_new 1.02% of enron (31 of 3034). The factors are data in a committed file, like thresholds.json next to the model weights; the final run fails if the file differs from the factors computed from every train email, and the end-to-end self-test also guards the shipped file (a payment request from a free mailbox must still reach Suspicious under it).

- **What changed after the validation emails were read (disclosed).** Score version 0.1 (the initial numbers) was run on 6,000 train emails only. Version 0.2 added the reliability factors. The first validation run (commit 32943b2) counted ham and spam together as ordinary mail for the budget and for the reliability factors. It showed `rv_freemail`, the core business-email-compromise rule, at half weight (it fired on 7.2% of spamassassin, 57 of 792, because spam asks for money from free mailboxes), a lone payment request from a free mailbox scoring 30 (Low risk), and a spamassassin High risk share of 1.16% decided by two emails. Spam is not legitimate mail, so flagging it is not a false alarm: the definition was corrected to ham only (the constant `ORDINARY` in build.py) and the run was repeated (commit 359246a). **That correction was made after the validation emails had been read, so the validation figures below are a check, not an independent test; the clean measurement is the test split in Phase 13.** No other number was changed after validation was read: the points, the pressure step, the cuts and the budget are the initial ones. The first LIME check (random words of any frequency as the baseline) was unfair to the random words and its numbers are not used; the check below replaced it.

- **Results: the grid and the choice** (results/score_grid.csv, validation). 8 of the 27 points keep the meaning; 0 of them also meet the budget. No point meets it, so the initial numbers (60, 35, 0.25) are kept. The best any point does on its worst group is 5.18% Suspicious or above (the meaning-preserving points: 5.38%), so the miss does not depend on the numbers inside the grid; it comes from the rule behind it.

- **Results: the false-alarm budget** (results/score_budget.csv, validation, 95% Wilson intervals; spam is listed for information and is not budgeted):

| **Group** | **Checked** | **High risk (95% interval)** | **Suspicious or above (95% interval)** | **Budget** |
|---|---|---|---|---|
| apache_kafka_users (legitimate mail) | 15 | 0 (0.0%, 0.0 to 20.39) | 0 (0.0%, 0.0 to 20.39) | info (fewer than 20) |
| apache_tomcat_users (legitimate mail) | 24 | 0 (0.0%, 0.0 to 13.8) | 0 (0.0%, 0.0 to 13.8) | PASS |
| kaggle_ceas08 (legitimate mail) | 256 | 0 (0.0%, 0.0 to 1.48) | 8 (3.12%, 1.59 to 6.04) | PASS |
| spamassassin (legitimate mail) | 108 | 1 (0.93%, 0.16 to 5.06) | 1 (0.93%, 0.16 to 5.06) | PASS |
| kaggle_ceas08 (spam, not budgeted) | 23 | 0 (0.0%, 0.0 to 14.31) | 1 (4.35%, 0.77 to 20.99) | info (spam: not budgeted) |
| spamassassin (spam, not budgeted) | 64 | 1 (1.56%, 0.28 to 8.33) | 6 (9.38%, 4.37 to 18.98) | info (spam: not budgeted) |
| apache_kafka_users (real thread messages) | 85 | 0 (0.0%, 0.0 to 4.32) | 1 (1.18%, 0.21 to 6.37) | PASS |
| apache_tomcat_users (real thread messages) | 294 | 0 (0.0%, 0.0 to 1.29) | 3 (1.02%, 0.35 to 2.96) | PASS |
| enron (real thread messages) | 483 | 2 (0.41%, 0.11 to 1.5) | 26 (5.38%, 3.7 to 7.77) | OVER |

  Of the 6 groups with at least 20 checked messages, 5 stayed inside the budget and 1 did not. The group over: enron (real thread messages): Suspicious or above 5.38% of 483 checked (26 messages), against a budget of 5%; the 95% interval is 3.7 to 7.77, so it still includes the budget; 23 of the 26 alarms are tv_quote_mismatch. A miss is a finding, not a failure of the run: it is reported as OVER. Groups with fewer than 20 checked messages are listed but not judged: apache_kafka_users, legitimate mail (15 checked).

- **The trade-off behind the miss.** The rule behind most alarms in the group that is over the budget, `tv_quote_mismatch`, is also the only rule that can find a forged thread on Enron (variant C): raw Enron replies carry no Message-IDs, so the ID checks are not checkable there and the quote check is the one integrity rule that runs. As a lone high contradiction it scores 60. A lone high that counted half (a reliability of 0.5) would score 30, below the Suspicious cut of 35, so an alarm or a detection that rests on that rule alone would fall to Low risk. That was not run: reliability factors are set from train rates, and a factor chosen to make a validation number pass would be fitting on validation. The choice is a policy one: the budget is kept and the miss is reported.

- **Results: bands on the validation emails** (results/score_distribution.csv; both denominators, because most emails have no checked claim):

| **Group** | **Emails** | **With a checked claim** | **Suspicious or above, % of the checked** | **High risk, % of the checked** | **Suspicious or above, % of all** | **High risk, % of all** |
|---|---|---|---|---|---|---|
| fraud | 482 | 206 | 45.15 | 10.19 | 19.29 | 4.36 |
| ham | 6352 | 403 | 2.23 | 0.25 | 0.14 | 0.02 |
| phishing | 2549 | 550 | 47.09 | 16.18 | 10.16 | 3.49 |
| spam | 5496 | 87 | 8.05 | 1.15 | 0.13 | 0.02 |

| **Group** | **Emails** | **With a checked claim** | **Suspicious or above, % of the checked** | **High risk, % of the checked** | **Suspicious or above, % of all** | **High risk, % of all** |
|---|---|---|---|---|---|---|
| apache_kafka_users | 162 | 15 | 0.0 | 0.0 | 0.0 | 0.0 |
| apache_tomcat_users | 315 | 24 | 0.0 | 0.0 | 0.0 | 0.0 |
| kaggle_ceas08 | 5709 | 279 | 3.23 | 0.0 | 0.16 | 0.0 |
| kaggle_enron | 4368 | 0 | counts only (0) | counts only (0) | 0.0 | 0.0 |
| kaggle_ling | 427 | 0 | counts only (0) | counts only (0) | 0.0 | 0.0 |
| kaggle_nigerian_fraud | 482 | 206 | 45.15 | 10.19 | 19.29 | 4.36 |
| nazario | 1440 | 348 | 49.71 | 20.4 | 12.01 | 4.93 |
| phishing_pot | 1109 | 202 | 42.57 | 8.91 | 7.75 | 1.62 |
| spamassassin | 867 | 172 | 4.07 | 1.16 | 0.81 | 0.23 |

  Among the validation emails that had at least one checked claim (1246 of 14879, 8.37%), the share reaching Suspicious or above was: ham 2.23% (High risk 0.25%) of 403 checked; spam 8.05% (High risk 1.15%) of 87 checked; phishing 47.09% (High risk 16.18%) of 550 checked; fraud 45.15% (High risk 10.19%) of 206 checked. These are shares of the checked emails; the shares of all emails are in the table, and most emails have no checkable claim (two sources have none at all: kaggle_enron, kaggle_ling). Attacks and legitimate mail come from different corpora with different header evidence (Section 8.16), so the gap between ham and the attack categories is partly a gap between corpora; read it per source. There are no contradiction labels, so none of this is precision or recall.

- **Results: the hijack benchmark under the frozen numbers** (results/score_benchmark_check.csv, validation cases, with and without the thread verifier in the ledger; cells under 10 cases are counts only):

| **Source** | **Case** | **Cases** | **Suspicious or above, full** | **High risk, full** | **Suspicious or above, Phase 8 verifiers only** | **High risk, Phase 8 verifiers only** |
|---|---|---|---|---|---|---|
| apache | A takeover | 40 | 82.5% (33 of 40) | 25.0% (10 of 40) | 17.5% (7 of 40) | 0.0% (0 of 40) |
| apache | B look-alike swap | 26 | 100.0% (26 of 26) | 0.0% (0 of 26) | 0.0% (0 of 26) | 0.0% (0 of 26) |
| apache | C forged thread | 40 | 100.0% (40 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) |
| apache | neg_real (the real next reply) | 40 | 0.0% (0 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) |
| apache | neg_synth (benign synthetic text) | 40 | 0.0% (0 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) | 0.0% (0 of 40) |
| enron | A takeover | 29 | 100.0% (29 of 29) | 37.9% (11 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) |
| enron | C forged thread | 29 | 82.8% (24 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) |
| enron | neg_real (the real next reply) | 29 | 6.9% (2 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) |
| enron | neg_synth (benign synthetic text) | 29 | 0.0% (0 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) | 0.0% (0 of 29) |

  Suspicious or above with the thread verifier in the ledger: apache A 82.5%, B 100.0%, C 100.0%; enron A 100.0%, C 82.8%. With the Phase 8 verifiers alone: apache A 17.5%, B 0.0%, C 0.0%; enron A 0.0%, C 0.0%. High risk is reached only by the takeover cases (apache A 25.0%, enron A 37.9%): variants B and C produce one claim group of calm text, so no pressure tactic multiplies it. The real next reply is a false alarm (Suspicious or above) in 0.0% of apache cases and 6.9% of enron cases. These cases were built to trigger the rules and were not used to choose any number.

- **Parity.** `build.py --parity 300` rebuilds 300 validation emails from staged.parquet, runs the real `analyze()` and compares it with the batch code that produced the numbers above, so the number calibrated is the number the product computes: the same band for 100.0% of the emails and the same score for 91.7%; score differences not explained by the rule below: 0 of 300. Every score difference is the 5 points of `tv_single_no_reply_ids` (low severity), which only `analyze()` runs because Phase 2 threw away the quoted text the batch code would need.

- **LIME.** Written by hand (Ribeiro et al. 2016): the words of the 2,000 characters the classifier reads are the features; 300 copies with random words hidden (the first copy is the email itself) are scored in one batch; copies near the original weigh more (kernel sqrt(exp(-d^2 / 25^2)) on the cosine distance); a ridge fit chooses the top words and a final ridge fit (alpha 1) gives the weights; a word is highlighted when its weight is at least 0.02 and at least a quarter of the strongest; seed 42; one run serves every tactic that fired. The self-test plants a classifier with known behaviour and checks that the words found are exactly the planted ones. The faithfulness check (src/explain/check.py, results/lime_checks.csv) is a deletion test on the first 20 real validation emails where a main tactic fires: remove the LIME words and ask the classifier again. Its baseline removes, for each LIME word, a random other word that occurs the same number of times in the email, because the words LIME names are often frequent ones and removing frequent words removes more text:

| **Copies** | **Explanations** | **Seconds each (mean / slowest)** | **Mean drop: LIME words / matched random words** | **LIME drop larger in** | **Tactic stops firing: LIME / random** |
|---|---|---|---|---|---|
| 150 | 33 | 4.9 / 10.1 | 0.258 / -0.011 | 94% of 33 | 67% / 4% |
| 300 | 33 | 10.6 / 22.2 | 0.269 / -0.010 | 97% of 33 | 67% / 6% |
| 600 | 33 | 20.7 / 42.3 | 0.310 / -0.012 | 100% of 33 | 67% / 6% |

  LIME names at least one word in 33 of 33 explanations at 300 copies; removing the words it names lowers the tactic probability by 0.269 on average against -0.010 for matched random words, in 97% of 33 explanations, and the tactic stops firing in 67% against 6%. 150 copies cost 4.9 seconds against 10.6 at 300 and are almost as faithful, so the API can use fewer copies. The top 3 words under another seed overlap 0.42 (12 explanations), and with the lime package 0.39 (10 explanations; the two use different random numbers), so the exact words are not stable but the faithfulness holds. On the printed examples, many highlighted words are function words (I, to): LIME says what the classifier reacts to, which is not always what a human would underline. It explains the classifier only; the explanation of a verifier is the reason in its ledger row. The check says nothing about whether the classifier is right (urgency precision on real validation emails is 0.50).

- **Checks** (results/score_checks.csv and results/lime_checks.csv): score_checks.csv 19 PASS, 0 FAIL, 13 info; lime_checks.csv 8 PASS, 0 FAIL, 18 info. They cover the self-tests, every ledger row, score range and band fit, the evidence rule (no contradiction without a checked claim), the splits read (train and validation; never test), the budget groups, the frozen numbers against the chosen point, the reliability file against the train factors, parity, the benchmark false alarms and the run details (score 0.2, rules 0.3, thread rules 0.2, claim patterns 0.4, tactic model run 2026-10-08 14:38:30).

- **Known limits:** there are no contradiction labels, so every rate here describes the rules and the corpora and none is precision or recall; the budget is a policy choice and is judged on only 6 groups of legitimate mail and real threads (the Kaggle Enron and Ling emails carry no header evidence and have no checked claims); a calm, well-copied hijack (a hijacker with mailbox access who copies the IDs, the sending details and the wording) cannot be caught by any rule; a pasted body with no headers can only be scored on tactics, which add at most 12 points, so a classic BEC body without headers is Low risk with a coverage note saying nothing could be checked, which the interface must explain; the score depends on the Phase 6 thresholds and the Phase 7 extractor, which were scored against LLM labels from one model family; the hijack cases are synthetic; the validation figures are a check after the ham-only correction. The risk score and its ablations on the test split are Phase 13.

- **Security:** see Section 10 (router, ledger and score; LIME).

## 8.19 Phase 11 FastAPI backend and security controls

- **Output:** src/api (settings.py, schemas.py, security.py, results.py, main.py, selftest.py, mutation_check.py, smoke.py, README.md), results/api_checks.csv, api_mutations.csv and api_smoke.csv, one fix in src/router/pipeline.py (nested MIME, below) and the pins in requirements.txt (FastAPI 0.141.1 (Starlette 1.7.0), Pydantic 2.13.5, slowapi 0.1.10, uvicorn 0.53.0; httpx 0.28.1 only for FastAPI's TestClient; limits 5.8.0). `python -m src.api.main` serves `analyze()` on http://127.0.0.1:8000; the interface of Phase 12 talks only to it. Nothing is stored: the email lives in memory for the request, and the audit log has no field that could hold content.

- **The routes.**

| **Route** | **Key** | **What it does** |
|---|---|---|
| POST /analyze | yes | One email (`{"email": "...", "org_domain": "..."}`), no LIME, about 0.05 s: the report of Section 6.3 unchanged |
| POST /analyze/thread | yes | 1 to 50 messages in any order; the newest by Date is judged against the earlier ones |
| POST /explain | yes | Exactly one of `email` or `messages`; the same report with LIME highlights (150 copies, about 5 s); its own, smaller rate limit and it never waits for the classifier |
| GET /results | no | The evaluation tables the dashboard may read, as JSON, from a fixed allow-list (`?name=` picks one) |
| GET /health | no | Whether the model is loaded (503 if loading failed) |

  The interface shows the score from /analyze first and asks /explain for the highlights afterwards: the score does not depend on LIME, and LIME costs about 100 times a normal analysis. The section 6.8 plan listed four routes; /explain is the fifth because slowapi limits are per route and the expensive path needs a tighter one.

- **A bug found while planning, in Phase 10 code.** `parse_message` is documented never to raise, yet an email with 3,000 nested multipart levels (150 KB, under the byte cap) ended in `RecursionError`, because Python's email parser and walker recurse once per level. The Phase 10 crafted-input tests missed nesting. `read_body` in src/router/pipeline.py now counts the depth without recursion (`mime_depth`) and, over `MAX_MIME_DEPTH` (20) or if the parser itself gives up, reads the text after the header block as plain text; the coverage says `mime_too_deep`. Router self-test: 103 to 108 checks (nested 8 levels read normally, 3,000 levels flagged and in time, 5,000 flat parts not flagged).

- **The decisions and why.** JSON only, no multipart upload: the browser reads a .eml as text and sends it in a JSON field, so there is no multipart parser (and no python-multipart), and a request that is not application/json is refused with 415, which also stops a cross-site form post. 300,000 bytes per email, the pipeline's own cap, so the API never accepts what the pipeline would cut (Section 10 had suggested 100 KB, but real .eml files with attachments are mostly base64 text). 4,000,000 bytes per request, counted as the bytes arrive because Content-Length can lie or be missing; 50 messages and 1,500,000 bytes per thread, refused rather than cut. The key is checked before the body is read, so the routes read and check the body themselves (FastAPI would parse a declared body before running the key check). Wrong keys are counted by the strict rate limit, because that limit runs before the key check. One analysis at a time behind a lock: /analyze waits 2 s and then answers 503 with Retry-After, /explain does not wait. No CORS in the design: the interface calls the API through a same-origin dev proxy, so the key stays out of the browser; a marked temporary switch (`CORS_ALLOW_ANY_ORIGIN` at the top of src/api/main.py) opens CORS to every origin for testing and must be False before any deployment (the self-test checks both settings). The server refuses to start with a missing key, the placeholder, fewer than 24 characters or fewer than 8 different characters.

- **The controls** are listed in Section 10 (input validation, safe parsing, rate limiting, authentication, audit logging, API response hardening, concurrency and exposure, secrets). The layers, outside to inside: OuterGuard (request id, response headers, last-resort 500), TrustedHost (Host header), slowapi (global limit, counted before anything is read), BodyGuard (Content-Length, content type, byte count), routing, the route's dependencies (strict rate limit, then the key), the body read and checked by Pydantic, the analysis in a worker thread behind the lock.

- **Results: the self-test** (results/api_checks.csv, 88 PASS, 0 FAIL, run with the stand-in classifier of Section 8.18 and the real settings, middleware, rate limiter, schemas, routes, error handlers, audit log, results store and `analyze()` with the real spaCy extractor; Python 3.12.14; fastapi 0.141.1, starlette 1.7.0, pydantic 2.13.5, slowapi 0.1.10, uvicorn 0.53.0, httpx 0.28.1, limits 5.8.0):

| **Group** | **Checks passed** |
|---|---|
| Settings and start-up | 12 |
| Routes and results | 17 |
| Authentication | 8 |
| Validation | 11 |
| Size limits | 6 |
| Rate limits | 7 |
| Concurrency | 3 |
| Errors and start-up failures | 8 |
| Response headers | 7 |
| Markup and scripts | 2 |
| Audit log and canary | 7 |
| **Total** | **88** |

  Every route returns what `analyze()` returns, passed through the typed `Report` model with the same dictionary back; real `analyze()` output of every mode (email, thread, LIME) goes through the model. A canary string sent in the email text, a header name and value, the Host header, the URL path and query, the content type, a field name, a domain and as a wrong key reached the pipeline but appears in no audit line, no other log record and no error response, and neither the key nor any '@' is in a log line.

- **Results: do the checks test anything?** `python -m src.api.mutation_check` breaks 37 controls one at a time in a scratch copy of the code (the key check accepts anything, the key compared with ==, the body not counted while streaming, Content-Length not compared, no lock, the lock not released, the log not cleaned, X-Forwarded-For trusted, the limiter switchable from the environment, the Host check removed, the docs on, and so on); the self-test failed for 37 of 37 (results/api_mutations.csv). This is mutation testing with hand-picked mutations.

- **Results: a real session** (results/api_smoke.csv, 19 PASS, 0 FAIL; the trained model, real HTTP through uvicorn, the server's output saved and searched for the canary and the key). Timings: 5 analyses of the David email, no LIME: mean 0.026, slowest 0.027; one explanation: 1.0.

| **Check (real server, trained model)** | **Result** |
|---|---|
| GET /health: 200, model loaded, versions listed | PASS (200, model_loaded True) |
| GET /results lists the tables and GET /results?name=score_budget returns one | PASS (37 tables) |
| no key and a wrong key are 401 | PASS ([401, 401]) |
| POST /analyze with the real model: 200, the report passes check_report and the typed Report model | PASS (200) |
| 5 analyses of the David email, no LIME: mean and slowest seconds (the server was warm) | PASS (mean 0.026, slowest 0.027) |
| POST /explain: 200, LIME ran when a tactic fired, highlights fit the text, the score equals the one without LIME | PASS (200 fired 1) |
| one explanation (150 LIME copies), seconds (the Phase 10 figure on the Mac was 4.9) | PASS (1.0) |
| POST /analyze/thread: 200, thread mode, 5 messages | PASS |
| 3,000 nested MIME levels (the email that crashed the Phase 10 parser): 200 with the depth limit noted, in time | PASS (200 0.43 s) |
| a 5 MB body with a Content-Length: 413 | PASS (413) |
| a streamed 4.3 MB body with no Content-Length: refused with 413 (or the connection is closed once the limit is passed) | PASS (413) |
| a streamed 6 MB body with no key: refused with 401 without being read (or the connection is closed) | PASS (401) |
| the server still answers after the oversize bodies | PASS |
| 4 analyses at once: each answered 200 (queued behind the lock) or 503 busy, nothing else | PASS ([200, 200, 200, 200] in 0.10 s) |
| the canary SMOKECANARY7788 (sent in an email body, a Subject, a header, a field name, a domain and a wrong key) is in the successful report but not in the server log /tmp/pg_server.log | PASS (log 9129 characters, canary in log: False, key in log: False) |
| the log holds JSON audit lines for the analyses of this run | PASS (27 audit lines, 16 analyses) |
| 3 real emails from the corpus that contain script-like payloads: all analysed, and no response holds '<', '>' or a backtick | PASS (statuses [200], markup in responses: 0) |
| wrong keys on /explain are counted: 429 appears within 8 tries (the allowance is 6 a minute and earlier explanations used some) | PASS ([401, 401, 401, 429, 429, 429, 429, 429]) |
| the 429 carries Retry-After (seconds) and the fixed message | PASS (retry-after 60) |

- **Known limits.** (1) uvicorn has no timeout for a request whose headers never finish: 25 half-open connections made every other request 503 until they closed (tested by hand against a stand-in server); the server listens on the loopback address only, and an exposed deployment needs a reverse proxy with request timeouts. (2) The rate limits and the lock live in memory, so they hold for one worker; run one. (3) Behind the Vite proxy every request comes from 127.0.0.1, so all users of one proxy share one allowance; fine for a single-user demo. (4) A worker thread cannot be stopped from outside: one input can hold the lock for as long as the pipeline needs it (the crafted inputs of Phases 2 to 10 take under 5 seconds), and only holders of the key can try. (5) The lock is not first come, first served. (6) The server speaks plain HTTP; a deployment terminates TLS in a reverse proxy and sets --forwarded-allow-ips deliberately. (7) The self-test uses a stand-in classifier; the real model is covered only by the smoke test, which sends a handful of requests. (8) Starlette's TestClient prefers the httpx2 package and prints a deprecation notice about httpx, which the self-test hides; httpx 0.28.1 is pinned because it is the established package. (9) **CORS is wide open at the end of Phase 11**: CORS_ALLOW_ANY_ORIGIN at the top of src/api/main.py is True, a marked temporary setting for local testing (any origin, method and header, no credentials). The key is still required on the three POST routes and the Host check still applies, but any web page in the browser can send requests to the API; it must be set to False before any deployment (Section 15 item 23).

- **Security:** see Section 10 (input validation, safe parsing, rate limiting, authentication, audit logging, API response hardening, concurrency and exposure, secrets).

## 8.20 Phase 12 React interface: analyzer and dashboard

- **Output:** frontend/ (package.json, package-lock.json, vite.config.js, index.html, README.md; src/main.jsx, App.jsx, api.js, index.css; pages/AnalyzerPage.jsx and DashboardPage.jsx; components for the form, the nine blocks of a result, the error banner, the result tables and the four charts; lib/segments.js, limits.js, format.js, useAnalysis.js, useResult.js and the generated examples.js; scripts/check.mjs, mutation_check.mjs, browser_check.mjs and make_examples.py), results/frontend_checks.csv, frontend_mutations.csv and frontend_browser_checks.csv, and three names added to RESULT_FILES in src/api/results.py. Packages, all with exact versions (189 packages in package-lock.json; `npm audit` found 0 vulnerabilities in the 189 packages it examined): react 19.3.0, react-dom 19.3.0, react-is 19.3.0, recharts 3.10.1, vite 6.4.4, @vitejs/plugin-react 4.7.0, tailwindcss 4.3.3, @tailwindcss/vite 4.3.3, and playwright-core 1.63.0 (for the browser check only). Node v22.14.0. Plain JavaScript (no TypeScript), no router library, no state library, no CDN and no web fonts: everything the page loads comes from its own server. The built bundle is 709 KB. Nothing is stored: the email lives in the page's memory until the tab closes.

- **The analyzer.** Input is one email or a thread (paste, or load .eml files that the browser reads as text), seven hand-made examples (generated from the self-test emails of src/router/selftest.py, ASCII only), an optional organisation domain and a switch for the word highlights. The result is drawn in the order a reader needs it:

| **Block** | **What it shows** |
|---|---|
| Result | The score as a large number, the band as a word on a coloured chip, a meter with ticks at 35 and 70, the recommended action and the versions. 'Low risk' is blue, never green: it does not mean safe |
| What could be checked | Claims found, checked, contradicted, consistent and not checkable; the limits that applied (no headers, no organisation domain, single email, ...); the API's sentence; a note when the band is Low risk but little or nothing could be checked |
| Findings | One row per contradiction, strongest first: the claim, the reason, the points it added; the rule and its evidence one click away; consistent and not-checkable rows in a closed block |
| The conversation | (thread) one card per message with its worst finding and the flip point |
| The text that was read | The redacted text with the words behind each detected tactic marked in that tactic's colour (LIME) and each claim underlined; a list of the words that weighed most |
| Pressure tactics | The seven probabilities with the threshold as a tick; reciprocity, social proof and liking shown but not scored |
| How the score was built | The counted rows, then the four steps of Section 6.6: contradiction points, pressure multiplier, tactic points, cap |
| Claims found; What the headers say | The claims with strength, place and outcome; the header facts the checks used |

  The score and findings come from POST /analyze and appear at once; the highlights come from POST /explain, about five seconds later (Section 8.19). If that call fails the score stays and a button offers a retry; a refused request shows the API's own sentence, its code and request id, the fields it refused (422) and a counter on the button for Retry-After (429, 503).

- **The dashboard.** Four charts, each with a table view that holds exactly the numbers drawn: the F1 of DistilBERT against the keyword baseline per tactic (real validation emails); where the validation emails land in the three bands per category; detection of the hijack benchmark with every check against the sender checks alone, with 95% intervals; and the false-alarm budget per group with the 1% and 5% lines. Each chart prints what it cannot show under it (validation only, labels from language models of one family, synthetic hijacks, attacks and ordinary mail from different collections, the budget rule corrected after validation was read). Then every result file the API serves, grouped by phase, each loaded when opened and filterable. The dashboard and its charts load only when its tab is first opened.

- **The decisions and why.** (1) **A same-origin proxy adds the key.** The interface server forwards /api to http://127.0.0.1:8000 and adds the X-API-Key header, read inside vite.config.js with loadEnv from the project's .env; Vite hands the browser only variables that start with VITE_ (the key does not), so the key is not in the bundle (the static check searches for it), and because the browser only ever talks to its own origin no CORS is needed. The server refuses to start with a short or placeholder key. (2) **Every string is a text node.** No dangerouslySetInnerHTML, innerHTML, markdown, link or eval anywhere in src/ (the static check scans for each); the API already replaces < > and backticks, so this is a second line of defence. (3) **Offsets are code points.** The API counts Python characters; a JavaScript string counts UTF-16 units, where an emoji is two; slicing at the API's offsets would cut an emoji in half and shift the rest. `buildSegments` splits with Array.from, cuts at every span boundary, returns pieces that give back the text exactly and skips and counts a span that does not fit; the browser check compares the drawn text with `text_read` character for character. (4) **Two calls, one at a time.** /analyze first, /explain second, a new analysis cancels the old one (AbortController), and the buttons count down Retry-After. (5) **A strict Content-Security-Policy on `npm run preview`** (default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; also nosniff, no-referrer, X-Frame-Options DENY and Cross-Origin-Resource-Policy same-origin), so even an injected script could not run or send anything out; the development server cannot send it (hot reload needs inline scripts), so the demo uses preview, and the browser check fails if the policy is missing. (6) **Nothing is stored in the browser and nothing is logged to the console**; files are read as text after a size check and never uploaded as files. (7) **The limits of the API are checked first** (300,000 bytes an email, 50 messages and 1,500,000 bytes a thread, the domain shape), so a request the API would refuse is not sent; the API stays the authority. (8) **Colour rules.** Status colours are reserved for bands and severities and always sit beside a word; each tactic has one fixed colour; in the charts one colour per entity on every chart (our system blue, the comparison orange, the second comparison aqua, the bands in their own colours), a legend on every chart with two or more series, a table view, a hairline grid, and a dark scheme with its own steps. (9) **No router, no state library, no UI kit:** two pages switched by state, plain useState, so every line can be explained.

- **Results: the static checks** (results/frontend_checks.csv, 96 PASS, 0 FAIL; Node v22.14.0; 30 source files read):

| **Group** | **Checks passed** |
|---|---|
| Source (no HTML injection, links, storage, console output or outside addresses) | 16 |
| Pins (exact versions, the lock file, npm audit) | 20 |
| Built bundle (no key, no outside host, no inline script or style) | 16 |
| Logic (offsets to pieces of text, size limits, domain shape, labels) | 44 |
| **Total** | **96** |

  The logic group runs the pure functions of src/lib on hand-made cases: pieces of text for no span, one span, an emoji before a span (and the proof that a plain JavaScript slice gets it wrong), overlapping spans, seven kinds of crooked span, and 300 random texts with random spans that must always rebuild the text exactly; the size limits at, one byte over and far over the limit, bytes against characters, a thread of 0, 50 and 51 messages; the domain shape; a tactic class that refuses a name it does not know.

- **Results: do the static checks test anything?** `npm run mutation-check` breaks 26 things one at a time in a scratch copy of the interface and runs the static checks there (after a control run with nothing broken that must pass): the action text is put in with innerHTML; a component uses dangerouslySetInnerHTML; a link element is added; the result is kept in localStorage; the email text is logged to the console; a fetch to an outside address; eval is used; a non-ASCII character is hidden in an example email; the API key is written into the bundle; the header name X-API-Key is in the bundle; an inline script is added to index.html; a style attribute is added to index.html; an outside script is added to index.html; the CSS imports an outside file; a source map is shipped; dist/index.html is gone; segments are cut in UTF-16 units (an emoji is cut in half); segments drop a valid span at the end of the text; segments accept a span that runs past the text; segments lose a space at the edge of a piece; an email exactly at the size limit is refused; the size limit counts characters instead of bytes; a domain with a space is accepted; a tactic class is built from any name the API sends; a package version becomes a range; the lock file holds another version of react. The checks failed for 26 of 26 (results/frontend_mutations.csv). The mutations are hand-picked, so this shows that the checks notice these changes, not every possible change.

- **Results: the browser** (results/frontend_browser_checks.csv, 93 PASS, 0 FAIL; the built app served by `npm run preview` with its Content-Security-Policy, against the API started with `python -m src.api.main`, Chromium-based browser 154.0.8037.98, 24 seconds). The checks compare what is drawn with what the API answered, so they hold whichever model is loaded; the scores below are reported, not asserted. The error states are produced by answering the page's own requests with made-up responses, so they test the page, not the API.

| **Group of checks (built app in a real browser, against the running API)** | **Passed** |
|---|---|
| The page, its security headers and the proxy | 9 |
| Five real analyses through the page: what is drawn equals what the API answered | 44 |
| The second call on demand (Find the words) | 4 |
| 429 with its counter, 422, 503, 413, 401, an unreachable API and a failed explanation (made-up answers) | 11 |
| Size limit and malformed domain: refused and nothing sent | 4 |
| Files, threads, one request at a time | 6 |
| Charts and tables against the API's own tables | 8 |
| A 375 px wide screen: no sideways scroll | 2 |
| Dark colour scheme | 1 |
| No Content-Security-Policy violation, script error, console error or alert box anywhere | 4 |
| **Total** | **93** |

| **Example** | **What the model and verifiers made of it (reported by the check, not asserted)** |
|---|---|
| The David email (free mailbox, urgency and secrecy) | High risk 100; fired: urgency; contradictions 3 |
| The David email with script payloads in every part | High risk 99; fired: none; contradictions 3 |
| An honest internal email | Low risk 0; fired: none; contradictions 0 |
| A body pasted without headers | Low risk 0; fired: none; contradictions 0 |
| Account takeover in a thread of five messages | High risk 100; fired: authority, urgency, scarcity; contradictions 3 |

- **A bug the first run on the real model found.** The page decided that the highlights had been fetched from the report's `explained` flag, but the API sets that flag only when LIME ran, and LIME does not run when no tactic fired. With the stand-in classifier of the sandbox tests every example fired a tactic, so the page passed there; on the real model the email carrying script payloads fired none, the page kept saying that the highlights were not asked for after a successful second call and offered to ask again, and the browser check timed out waiting for the answer. `useAnalysis` now records that the second call finished (`explainDone`) and the page says that no tactic was detected. The browser check gained a test that does not depend on the model (the real second call with its answer rewritten to `explained: false`); with the fix removed it fails in the same way, and it passes with a classifier that fires nothing and with one that fires.

- **Known limits.** (1) The Content-Security-Policy is sent only by `npm run preview`, not by the development server. (2) Everything the proxy forwards comes from one address, so all users of one interface server share one rate-limit allowance; fine for a single-user demo. (3) Only a Chromium-based browser was driven; Safari and Firefox were not tested, and neither a screen reader nor an automated accessibility audit was run (labels, roles, keyboard focus and a word beside every colour are in place). (4) The mutation check covers the static checks only; the browser check needs a running API and a rebuilt bundle for each change, so it is not mutated. (5) The examples are hand-made and the scores shown for them depend on the Phase 6 thresholds and the Phase 7 extractor. (6) The dashboard shows validation results; Phase 13 adds the test-split results, and a new result file appears only after its name is added to RESULT_FILES (src/api/results.py) and its prefix to GROUPS (src/pages/DashboardPage.jsx), otherwise it is listed under Other. (7) The interface mirrors the API's size limits in src/lib/limits.js; a change to src/api/settings.py must be copied there. (8) The browser check counts the API's explanation allowance (6 a minute) and waits when needed, so two runs need a minute between them. (9) A result is not kept across a reload, on purpose.

- **Security:** see Section 10 (output encoding, interface hardening).

# 9. Technology stack

| **Layer** | **Choice** | **Why** |
|---|---|---|
| Language | Python 3.12 (Homebrew python@3.12) in a venv | Python 3.12 was Colab's runtime when it was chosen; the Phase 6 run found Colab on Python 3.13.15, which does not affect saved weights; venv is Python's node_modules |
| Model | DistilBERT via HuggingFace Transformers + PyTorch | Small enough to fine-tune on a free Colab GPU; fast inference on CPU |
| Training | Google Colab (free GPU) | No local GPU needed; torch and transformers pinned to the same versions as local |
| Claim extractor (Phase 7) | spaCy 3.8.16 with en_core_web_sm 3.8.0 (tokenizer and named-entity recogniser only) | Token patterns and organisation names for claims; the English model is not on PyPI, so requirements.txt pins it by URL and SHA-256 |
| Verifiers (Phase 8) | Python standard library, tldextract and RapidFuzz (already pinned); pandas only in build.py | Rule engines for claims against headers; no new dependency, no model, no regular expression over email text |
| Header parsing | email stdlib, mailbox, tldextract, rapidfuzz | Parsing, .mbox reading, domain splitting, lookalike and organisation-name matching |
| Data and metrics | pandas, pyarrow, scikit-learn | Tables in memory, Parquet files, metrics (scikit-learn is first used in Phase 5) |
| Downloads and progress (Phase 1) | requests, tqdm | Fetching the Apache list archives; progress bars for long runs |
| Cleaning (Phase 2) | beautifulsoup4 4.15.0, tldextract 5.4.0 | HTML to text; public suffix list for domain redaction (built-in copy, no downloads) |
| Header evidence (Phase 3) | RapidFuzz 3.14.6 | Lookalike domain similarity (string ratio after look-alike character mapping) |
| Keyword baseline (Phase 4) | Python standard library only | Phrase matching on normalised words; no new dependency |
| Labels and agreement (Phase 5) | scikit-learn 1.9.1 | cohen_kappa_score, used to cross-check the hand-written kappa; the other Phase 5 scripts use the standard library and pandas |
| Tactic classifier (Phase 6) | torch 2.14.1 on the Mac, transformers 5.19.0 on the Mac and on Colab (Colab keeps its own preinstalled torch) | Fine-tuning and CPU inference; weights as safetensors; precision, recall and F1 hand-written in src/eval/metrics.py (scikit-learn only inside its self-test) |
| Testing | pytest | One environment check only (tests/test_environment.py); no unit tests per phase |
| Explainability | LIME for text, written by hand (no new library; SHAP only if time) | Word-level highlights as character offsets; attention-as-explanation is academically contested; the lime package would add matplotlib and scikit-image, which only its image explainer uses |
| Router, ledger and score (Phase 10) | Python standard library; numpy for the LIME fit (already installed with pandas); pandas only in build.py | The score is a pure function of the ledger; no new dependency, nothing learned at run time beyond the Phase 6 classifier |
| Backend | FastAPI 0.141.1 (Starlette 1.7.0), Pydantic 2.13.5, slowapi 0.1.10, uvicorn 0.53.0 | The model lives in Python; schema validation; per-address rate limiting; httpx 0.28.1 only for FastAPI's TestClient in the self-test; versions pinned one release behind the newest and pip-audit clean |
| Frontend | React 19.3.0, Vite 6.4.4, Tailwind 4.3.3, Recharts 3.10.1 (plain JavaScript, Node v22.14.0); playwright-core 1.63.0 for the browser check only | Reuses existing React knowledge; no router, state library, UI kit, CDN or web font, so every line can be explained and the page loads only from its own server; exact versions, committed lock file, npm audit clean (Section 8.20) |
| Database | None, deliberately | Privacy by design: submitted email content is never stored |
| Repo | GitHub, public: Nagasai-Datta/PretextGuard | Commit history evidences original work; kept public by Nagasai's choice |
| Security tooling | pip-audit, .env for secrets | Dependency and secret hygiene |
| Annotation (offline only) | Free API tier: gemini-3.1-flash-lite, gemini-3.5-flash-lite, tie-break gemini-flash-lite-latest (chat windows as a fallback) | Keeps the project free; no paid APIs; never used at runtime |

**Rejected:** the MERN stack (Express would only proxy to FastAPI; MongoDB would store the email content the design promises not to keep). **No LLM at runtime** (cost, latency, no on-premise deployment for a mail gateway, non-determinism, no inspectable explanation); an LLM can appear only as an optional comparison baseline.

# 10. Security design

Security Features is worth 15 marks and is treated as a first-class module.

| **Control** | **Implementation** | **OWASP mapping** |
|---|---|---|
| No persistence | Email content lives in memory for the request only; never logged, never written to disk | A02 / privacy by design |
| Input validation | At most 4,000,000 bytes per request, counted as the bytes arrive (Content-Length can lie or be missing), 300,000 bytes per email, 50 messages and 1,500,000 bytes per thread, at most 10 top-level fields; application/json only (a cross-site form post cannot reach the routes); Pydantic schemas that refuse unknown fields and wrong types, and a domain-shape check without a regular expression; no .eml upload (the browser reads the file and sends the text in JSON, so there is no multipart parser); the key is checked before the body is read | A03 Injection; A04 Insecure Design |
| Safe parsing | Attachments are never opened or executed; nested MIME is limited to 20 levels (Phase 11 found that 3,000 nested parts raised RecursionError in Python's parser; deeper mail is now read as plain text with a coverage note) and a thread to 50 messages | A04 Insecure Design |
| Safe data handling (build time) | Downloaded archives unpacked with path-traversal checks (tarfile data filter, zip names checked) and a 5 GB limit; file types checked by their first bytes; raw data made read-only; attachments never decoded; Kaggle values squashed onto one line before they become header lines (header injection) | A08 Software and Data Integrity Failures |
| ReDoS-safe text processing | The cleaning and redaction functions will run on attacker-written email in the API, so every pattern has bounded repeats and no look-ahead over long text, and bodies are capped at 200,000 characters. Testing on 31 crafted inputs found two real bugs (a footer pattern that ran for hours on 200,000 dashes; 10 seconds on 20,000 nested HTML tags); after the fixes the slowest input takes under two seconds | A04 Insecure Design (denial of service) |
| Untrusted header parsing | Headers are written by the sender: the header block is cut at 64 KB and each field at 2,000 characters; at most 50 Received lines, 10 Authentication-Results headers and 100 reference IDs are kept; every field is parsed on its own, so one broken header cannot lose the rest; bounded patterns. Crafted inputs (60,000-character fields, thousands of Received lines, nested comments) each finish in under 0.2 seconds | A04 Insecure Design (denial of service) |
| Trusted authentication results | Only Authentication-Results headers added by the receiving organisation are read: the topmost one, plus the headers directly below it from the same organisation, stopping at the first header from anyone else (RFC 8601, Section 5). A fake dmarc=pass written by the sender is ignored; an address hidden in an encoded word is never taken as the sender | A08 Software and Data Integrity Failures |
| Phrase matching without regular expressions | The keyword baseline matches whole words from a lookup table keyed by each phrase's first word, so cost grows in proportion to the text length; text is capped at 200,000 characters, and zero-width characters are removed so a phrase cannot be hidden by splitting it. Eight crafted 200,000-character inputs each finish in under one second | A04 Insecure Design (denial of service) |
| Redaction before data leaves the machine | Annotation batches sent to outside web chats (Phase 5) use body_redacted only: no real addresses, no live links. tldextract never downloads its suffix list | A02 / privacy by design |
| Annotation prompt hardening (build time) | Each email is wrapped as data in an <email> block with its angle brackets replaced, so it cannot close the block; the prompt says never to follow text inside and repeats it after the emails; a reply must be a JSON array of exactly the batch's ids with a fixed shape, and anything else is rejected and re-asked; quoted spans must appear in the email; a reply that gives every email the same answer is rejected as a likely hijack; batches (full email text) are never committed; API keys live only in .env (ignored by Git), travel only in the Authorization header over HTTPS, and are removed from every error message | LLM01 Prompt injection; A03 Injection |
| Model files and offline inference (Phase 6) | Weights are stored and loaded as safetensors (plain numbers; the older pickle format can run code when loaded); loading is offline (local_files_only), trust_remote_code is never set, and the model's output order is checked against the tactic order; input is cut at 2,000 characters and 512 tokens; the Colab upload file holds train and validation rows only, so test emails and labels never reach training; the check suite fails if a pickle-style file sits in the model folder | A08 Software and Data Integrity Failures; A06 Vulnerable Components |
| Claim extraction (Phase 7) | Input is cut before matching (2,000 characters of body, 1,000 of signature); phrase patterns match spaCy tokens, so cost grows with the number of tokens and cannot backtrack, and the only regular expressions are two short bounded ones (a phone number and the [EMAIL] placeholder); eight crafted 200,000-character inputs each finish in 0.54 s; the signature column is redacted before it is read; the spaCy model is loaded from disk, never downloaded at run time, and pinned by URL and SHA-256; every claim's text is checked to be exactly the slice of its span, so a highlight cannot point at the wrong words; results files hold counts only | A04 Insecure Design (denial of service); A08 Software and Data Integrity Failures; A06 Vulnerable Components |
| Verifiers (Phase 8) | Headers and signatures are attacker-written, so the verifiers read only values the Phase 3 code has capped and parsed per field; a signature is cut at 1,000 characters and scanned for addresses with fixed limits (40 '@' signs, 64 characters left, 255 right); bank details are found by word lookup on the first 5,000 characters with no regular expression; crafted inputs (60,000-character display names and Reply-To values, floods of '@', IBAN-shaped words, markup in a claimed organisation) each finish in 0.01 s at most; every string from an email goes through clean_text or clean_domain before it reaches a reason, and check_row rejects a reason with markup; account numbers and IBANs are shown masked (country and last four characters) and the self-test checks that a full IBAN never appears in a row; authentication is read only from the trusted headers of Phase 3 and domains are compared through the offline tldextract; results files hold counts only | A04 Insecure Design (denial of service); A03 Injection (XSS); A09 Logging Failures (PII) |
| Thread verifier (Phase 9) | A thread is attacker-written input: at most 50 messages are examined, each text is cut at 60,000 characters and 5,000 words, at most 100 Message-IDs are read per message, a Subject is cut at 300 characters before its prefixes are removed, raw files are read up to 300,000 bytes; no regular expression runs over email text (words are found in one pass over the characters and a quotation is compared as a set of 5-word runs); IDs are only looked up in a set and never followed, so a cyclic In-Reply-To chain cannot loop; reasons are built from fixed templates, domains through clean_domain and masked bank details, and check_row rejects markup; crafted inputs (50 messages of 200,000 characters, 100 References, 10,000 lines of '>', 100,000 'Re:' prefixes, a cyclic chain, floods of '@', a 200-message thread) each finish in under two seconds; benchmark prompts hold redacted excerpts inside <email> blocks with angle brackets replaced, the prompt says they are data, a reply must be a JSON array whose quoted cues appear in the text, and the prompt files are never committed | A04 Insecure Design (denial of service); A03 Injection; LLM01 Prompt injection |
| Router, ledger, score and pipeline (Phase 10) | A message is cut at 300,000 bytes, a thread at its last 50 messages, and the body and signature read at 2,000 and 1,000 characters; every string that comes from an email is made display-safe before it enters a report (< and > shown as the look-alike characters U+2039 and U+203A, backticks as apostrophes, control and invisible characters as spaces, one for one so offsets still fit), other strings go through clean_text or clean_domain, reasons are built from validated values and action texts are fixed; check_report runs on every report, recomputes the score and the coverage from the ledger and rejects markup, and a mismatch raises ReportError (a server error, never a result); a request id is 1 to 64 letters, digits, - or _; header-less input is not an error and not a free pass (the coverage says what could not be checked); crafted inputs (3,000 extra header lines, 60,000 '@' signs, a 60-message thread, bytes that are not valid text, wrong types, markup in names and bodies, and since Phase 11 3,000 nested MIME levels) are in the self-test (108 checks); nothing is stored or logged here | A03 Injection (XSS); A04 Insecure Design (denial of service); A09 Logging Failures (PII) |
| LIME (Phase 10) | Cost is bounded whatever the email: 2,000 characters, at most 1,000 word positions, 400 distinct words and 50 to 2,000 copies; the result holds numbers and character offsets, and a highlighted word holds only letters, digits and apostrophes, so it cannot carry markup; the seed is fixed; crafted inputs (one 5,000-character word, 2,000 one-letter words, 3,000 distinct words, zero-width and control characters, markup) finish in a fraction of a second with the stand-in classifier; an explanation costs the classifier work of about 300 emails, so the API makes it optional and rate-limits it | A04 Insecure Design (denial of service); A03 Injection (XSS) |
| Output encoding (XSS) (Phase 12) | Email bodies are attacker-controlled. Every string of a report (text read, claims, reasons, highlights, table cells) is drawn as a React text node: no dangerouslySetInnerHTML, innerHTML, markdown, link or eval anywhere in src/ (a scan in `npm run check`); the API has already replaced < > and backticks; highlights are cut by code points and a span that does not fit is skipped, never drawn wrongly; an email carrying script payloads in every part (the display name, the Subject, the greeting, the signature) is driven through the built app and no element, alert or script appears (browser check) | A03 Injection (XSS) |
| Interface hardening (Phase 12) | The built app is served with Content-Security-Policy default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none', plus nosniff, no-referrer, X-Frame-Options DENY and Cross-Origin-Resource-Policy same-origin; the API key is added by the interface server and is not in the bundle (searched for by `npm run check`); the page loads nothing from another host (no CDN, no fonts), stores nothing in the browser and logs nothing to the console; files are read as text after a size check and never uploaded as files; packages are pinned exactly with a committed lock file and `npm audit` is clean; the checks themselves are tested by breaking things on purpose (`npm run mutation-check`) | A05 Misconfiguration; A06 Vulnerable Components; A03 Injection (XSS) |
| PII redaction | Email addresses, phone numbers and account numbers are redacted before any text reaches a model; the audit log cannot hold content at all (a fixed list of fields, every value reduced to safe characters) | A09 Logging Failures |
| Rate limiting | slowapi per client address (the socket's peer, never X-Forwarded-For), moving window: 120 requests a minute for all routes together, counted before anything is read, and 30 for /analyze and /analyze/thread together and 6 for /explain, counted before the key is checked so wrong keys use up the allowance; a stray RATELIMIT_ENABLED in the environment cannot switch it off | A04 Insecure Design |
| Authentication | X-API-Key header, one value, compared as SHA-256 digests with hmac.compare_digest (constant time), never read from the URL; the server refuses to start with a missing key, the placeholder, fewer than 24 characters or fewer than 8 different characters; every kind of failure gets the same fixed 401 | A01 / A07 |
| Audit logging | One JSON line per event from a fixed list of fields (request id, time, mode, score, verdict, tactics that fired, contradictions, duration, sizes; for refusals the status, the reason and the client address), every value reduced to safe characters; errors log the class and the place in the code, never the message; a canary string sent in every part of a request appears in no log line | A09 Logging Failures |
| Dependency hygiene | Pinned requirements, pip-audit in the build (clean at Phase 0) | A06 Vulnerable Components |
| Secrets management | .env never committed; .env.example lists variable names only (PRETEXTGUARD_API_KEY and the optional PRETEXTGUARD_* settings); the environment check confirms .env is ignored; the key is masked in every summary and appears in no error or log line; `python -m src.api.settings --new-key` makes a random one | A05 Misconfiguration |
| API response hardening (Phase 11) | Cache-Control: no-store, X-Content-Type-Options: nosniff, Content-Security-Policy: default-src 'none'; frame-ancestors 'none', X-Frame-Options: DENY, Referrer-Policy: no-referrer and X-Request-ID on every answer including errors and 500s; no CORS headers in the design (a marked temporary switch, CORS_ALLOW_ANY_ORIGIN in src/api/main.py, opens CORS to every origin for testing and must be False before any deployment); a Host header allow-list (DNS rebinding); /docs, /redoc and /openapi.json off; fixed error sentences with a request id; the report is typed (Pydantic) and checked by check_report | A05 Misconfiguration; A03 Injection (XSS) |
| Concurrency and exposure (Phase 11) | One analysis at a time behind a lock (/analyze waits 2 s and then answers 503, /explain never waits), run in a worker thread so the event loop stays free; uvicorn on 127.0.0.1 with one worker, at most 20 connections, no server header and no trust in proxy headers; /results serves a fixed dictionary of table names read at start-up, so no request value becomes a path | A04 Insecure Design; A01 Broken Access Control |
| Prompt-injection note | No LLM at runtime. During offline annotation in web chats, email text is wrapped as data, the instructions say never to follow it, and replies are validated against a fixed schema. | LLM01 |

# 11. Evaluation plan

| **Experiment** | **Question** | **Metric** | **Supports** |
|---|---|---|---|
| Tactic classifier | How well are tactics detected? | Per-tactic precision, recall, F1; macro-F1 | Base |
| Keyword baseline vs DistilBERT | Does the model beat rules? | Macro-F1 on the labelled validation and test items (all random draws, none picked by keyword); per-tactic thresholds tuned on validation for both; tactics with too few positives reported as counts | Base |
| Claim extraction | How accurately are claims found? | Precision, recall and F1 per claim type against the LLM claim labels, for the five types with enough real positives (affiliation_internal, affiliation_external, authority, signature_contact, credential_request) and counts for the other six; real and synthetic emails apart; at two confidence levels (all claims, strong claims only); validation in Phase 7, the test split once in Phase 13 | All verifiers |
| Verifier contradiction rates | Do contradictions appear more in attacks than in ordinary mail, and where can claims be checked at all? | Contradicted share of the checkable claims per category and per source; claims that could not be checked reported apart, never as 'no contradiction'; train and validation; no precision or recall (nobody labelled contradictions), the effect on detection is the N3 ablation | N3 |
| N1 ablation | How much of a phishing detector's accuracy is link-reading? | Attack-class F1 and false-positive rate for models A and B on raw, redacted and naturally link-free test views | N1 |
| N2 ablation | Does thread verification catch hijacks N3 misses? | Detection rate with vs without the thread verifier; hijack-index accuracy; content signals on Enron threads, header signals on Apache threads | N2 |
| Thread verifier rates (Phase 9) | How noisy is N2 on real threads, and what does it find that the Phase 8 verifiers miss? | False alarms on real unmodified threads per source; detection of five-case hijack benchmark per variant and source for N2, the header and request verifiers and both; which signal caught each case; whether the scan flips at the injected message; bootstrap intervals over threads; counts only below 10 cases; train, and validation once in Phase 9 | N2 |
| Risk score calibration (Phase 10) | How often do legitimate mail and real threads reach Suspicious or High risk, and how do the attack corpora and the hijack benchmark score under the frozen numbers? | Share of checked legitimate emails (ham) and of real thread messages reaching Suspicious or above and High risk per source, with Wilson 95% intervals, against a budget declared before validation was read; bands per category and source with both denominators; the hijack benchmark per variant with and without the thread verifier; no precision or recall (no contradiction labels); validation, once for score version 0.2 | N2, N3, Architecture |
| LIME faithfulness (Phase 10) | Do the highlighted words matter to the classifier? | Deletion test on real validation emails: drop of the tactic probability after removing the LIME words against frequency-matched random words, share of explanations where LIME's drop is larger, how often the tactic stops firing, stability of the top words under another seed, overlap with the lime package | Plain |
| API security tests (Phase 11) | Does each control of the API hold under crafted requests, and does the test suite notice when a control is removed? | PASS/FAIL checks per group (settings, routes, key, validation, size limits, rate limits, concurrency, errors, headers, markup, audit log) with a stand-in classifier; mutation check: controls broken one at a time, share caught; a real session with the trained model (timings, oversize bodies, the canary in the server log, corpus emails with script payloads); no precision or recall | Security |
| Interface checks (Phase 12) | Does the interface keep the key and untrusted text out of harm's way, draw what the API answered, and show every error state, and do its checks notice when something breaks? | Static checks (source scan, pins, bundle scan, offset and size logic on hand-made cases) with PASS/FAIL per group; mutation check: things broken on purpose, share noticed; the built app driven in a real browser: what is drawn against what the API answered (score, band, finding, claim and tactic counts, the text character for character), error states, size limits, dashboard tables against the API's tables, phone width, dark mode, no Content-Security-Policy violation, script error or alert box; no accuracy metric | Security |
| N3 ablation | Does conditioning beat the alternatives? | F1 and false-positive rate: full vs text-only vs headers-only vs parallel fusion; real affiliation positives and synthetic BEC reported separately | N3 |
| Architecture ablation | Does routing beat a flat classifier on the same signals? | F1, false-positive rate, share of findings with a traceable reason | Architecture |
| SemEval pretraining (optional) | Does pretraining help with little data? | Macro-F1 across training sizes | Plain |
| Adversarial paraphrase | Does it survive rewording? | Detection before vs after paraphrase | Robustness |
| Style-confound test | Is the model reading writing style? | Source-classifier AUC | Validity |
| Header coverage | Which sources carry which headers? | Per-source coverage table | Validity |
| Annotator agreement | How reliable are the labels? | Cohen's kappa per tactic and per claim type between the two LLM annotators | Validity |
| Co-occurrence and confusion analysis | Which tactics stack; where it fails | Heatmap, confusion pairs | Analysis |

**Metrics in plain words:** precision is the share of flagged emails that really were attacks; recall is the share of real attacks that got flagged; F1 balances the two in one number; macro-F1 averages F1 equally over the seven tactics; the false-positive rate is how often legitimate emails get flagged, which matters because a tool that cries wolf gets switched off. **Ablation:** remove one component and measure again; the drop is what that component contributed. Each novelty claim has one.

> **Rule:** every number in the report or slides must come from a script in src/eval, with its output saved in results/ in the repo. Fake or manipulated results cost 20 marks.

# 12. Build plan

## 12.1 How the build runs

For each phase, the assistant explains the background, then provides every file with a function-by-function explanation and the exact commands to run, delivered as downloadable files plus one block of mv commands, or as paste blocks that create each file in place when the interface cannot hand over files. Files that themselves contain Markdown code fences (most READMEs) are always delivered as downloadable files, because a paste block breaks at the first inner fence. Nagasai runs everything in VS Code (training on Colab), reports the output or error, commits after each working step and pushes. The assistant never runs Git itself. A new chat has no memory of earlier chats, so every session starts from docs/PretextGuard_Context.md and this document. At the end of a phase the assistant lists exactly what changed in this document.

## 12.2 Phases and status

| **Phase** | **Deliverable** | **Module** | **Status** |
|---|---|---|---|
| 0 | Environment: Python 3.12, venv, VS Code, Git, GitHub CLI, folder structure, requirements, .gitignore, .env.example, pytest smoke test, pip-audit | repo root | Done (Sep 2026) |
| 1 | Data acquisition (paths, unpack, Apache fetch, loaders, stage, coverage and split scripts): Kaggle merge, raw SpamAssassin, raw Nazario, phishing_pot, raw Enron, Apache list archives; staged.parquet; header coverage table; Enron thread-header check; 70/15/15 split; root README and one README per major folder | src/data | Done (6 Oct 2026) |
| 2 | Preprocessing and payload-free redaction (N1) | src/preprocess | Done (6 Oct 2026) |
| 3 | Parser and header evidence extractor; fills the header columns; organisation domain handling | src/headers | Done (7 Oct 2026) |
| 4 | Keyword baseline: lexicon of strong and weak phrases, normaliser, scorer; train-split hit rates, phrase table and sanity checks | src/baseline | Done (7 Oct 2026) |
| 5 | Tactic and claim labels: batch prompt builder, annotation through a free API (two annotator models and a tie-breaker), schema validation, Cohen's kappa, SemEval 23-to-7 mapping; synthetic emails via a free API into data/synthetic/ | src/data | Done (8 Oct 2026) |
| 6 | DistilBERT tactic classifier on Colab (SemEval pretraining skipped), validation scores and checks | src/models, src/eval | Done (8 Oct 2026) |
| 7 | Claim extractor and claim schema (spaCy, token patterns, organisation and signature rules; train-only development, frozen version scored once on validation) | src/claims | Done (8 Oct 2026) |
| 8 | Header verifier (N3: internal and external affiliation, authority, reply, signature) and request verifier; rules written from definitions and train results, frozen at version 0.3, validation read once | src/verifiers | Done (9 October 2026) |
| 9 | Thread builder (Enron and Apache), thread-hijack benchmark, thread verifier (N2, including request drift); rules frozen at version 0.2, validation threads scored once | src/thread, src/verifiers, src/data | Done (9 October 2026) |
| 10 | Claim router, verdict ledger, risk score, LIME highlights; score version 0.2 frozen after calibration on validation (false-alarm budget; the one miss is a finding) | src/router, src/explain | Done (9 October 2026) |
| 11 | FastAPI backend with all security controls | src/api | Done (10 October 2026) |
| 12 | React frontend: analyzer (single email and thread) and evaluation dashboard; frontend README | frontend | Done (10 October 2026) |
| 13 | Evaluation: all experiments, claim-extraction accuracy, charts; outputs saved to results/ | src/eval, results | Not started |
| 14 | Report, viva preparation, Review deck update | docs | Not started |

## 12.3 Folder structure

```
pretextguard/             (~/Desktop/pretextguard)
  README.md             end-to-end overview and setup (Phase 1)
  venv/                 never commit
  .vscode/              settings.json: VS Code uses venv/bin/python
  data/                 README.md: every dataset and every stage
    raw/                downloads, read-only forever (ignored)
    processed/          staged tables in Parquet (ignored)
    labelled/           annotation batches and raw replies
    synthetic/          synthetic emails from web chats
    threads/            rebuilt threads + hijack benchmark
  artifacts/            trained model weights (ignored; README kept)
  results/              eval outputs and charts (committed)
  src/                  README.md; every folder has __init__.py
    data/               loading, staging, schema, coverage, benchmark
    preprocess/         cleaning + redaction (N1)
    headers/            parser + header evidence
    thread/             thread builder + thread signals
    models/             DistilBERT training + inference
    claims/             claim extractor
    verifiers/          header (N3), thread (N2), request
    router/             router, ledger, risk score
    explain/            LIME
    baseline/           keyword baseline
    eval/               metrics, ablations, charts
    api/                FastAPI app
  frontend/             React + Vite + Tailwind (Phase 12)
  notebooks/            Colab training notebooks
  tests/                test_environment.py (setup check)
  docs/                 this document, context file, report, slides
  .env  .env.example  .gitignore  pytest.ini
  requirements.txt
```

## 12.4 If time runs short

Drop in this order: (1) SemEval pretraining, (2) the style-drift signal, (3) the evaluation dashboard page (keep charts as images in the report), (4) the adversarial paraphrase test, (5) SHAP. Never drop N1, N2, N3, the router and ledger, or the security controls.

## 12.5 Environment notes

- Activate the venv in every new terminal; the prompt must show (venv). A missing (venv) is the most common reason a package seems to disappear.

- data/raw is read-only. Scripts read from raw and write to processed, so any mistake can be fixed by deleting processed and rerunning.

- Train on Colab, save the model to artifacts/, run inference locally on CPU. transformers is pinned to the same version in Colab and in requirements.txt. torch is pinned in requirements.txt for the Mac; Colab keeps its own preinstalled torch, and its Python version can differ from the venv's (the Phase 6 run: torch 2.11.0+cu130 and Python 3.13.15 on Colab, torch 2.14.1 and Python 3.12 on the Mac). The saved weights are plain numbers, and the Phase 6 check that the Mac reproduces Colab's predictions to within 0.001 passed (largest difference 0.000001).

- .gitignore includes: venv/, \_\_pycache\_\_/, \*.pyc, .env, data/raw/, data/processed/, artifacts/\* with !artifacts/README.md (so the folder README is committed), \*.pt, \*.bin, \*.safetensors, node_modules/, frontend/dist/, .ipynb_checkpoints/, .pytest_cache/, .DS_Store.

- The project lives at ~/Desktop/pretextguard. iCloud Desktop sync is off, so the venv and data stay on local disk only.

- Python is 3.12.14 from Homebrew (python@3.12). The Mac also has Homebrew 3.14 (the default python3), python.org 3.11 and Apple's 3.9; the project uses only the venv's 3.12.

- Always work from ~/Desktop/pretextguard, never from src/: source venv/bin/activate is a relative path. The shell aliases python to python3, which is harmless inside the venv.

## 12.6 Planned file map

Planned file names; each phase may adjust them. The root and major-folder READMEs are written in Phase 1, and each src package gets its README in the phase that builds it.

| Folder | Planned files | What they do | Phase |
|---|---|---|---|
| src/data | paths.py, unpack.py, fetch_apache.py, loaders.py, stage.py, coverage.py, split.py | Folder paths; check and safely unpack the downloads; fetch the Apache list archives; one reader per source format; dedupe and write staged.parquet; header coverage table; grouped train/validation/test split | 1 (done) |
| src/data | label_schema.py, prompts.py, clipboard.py, llm_api.py, batches.py, annotate.py, validate_labels.py, agreement.py, labels.py, synthetic.py, semeval_map.py | Label vocabulary; the annotation prompt; clipboard copy and paste; one chat-API call for Gemini and Mistral; the sample and its batches; the annotation loop (automatic or by hand); reply validation and re-asks; Cohen's kappa and tie-break batches; merge into final labels; synthetic pair prompts, checks and loading; SemEval 23-to-7 mapping | 5 (done) |
| src/preprocess | clean.py, redact.py, build.py | HTML to text, list footer and quote removal, signature; N1 redaction (\[URL\] \[EMAIL\] \[FILE\] \[DOMAIN\], including spaced forms); build writes cleaned.parquet and the checks | 2 (done) |
| src/headers | parser.py, domains.py, evidence.py, build.py | Raw email to header block, body and header fields; registered domains, freemail and open-platform lists, lookalike score; evidence dict with trusted authentication verdicts; build writes headers.parquet and the checks. The brand-domain list for external affiliation moves to Phase 8 | 3 (done) |
| src/baseline | lexicon.py, keywords.py, build.py | Word lists per tactic (data only); text normaliser, scorer and lexicon check; train-split hit rates, phrase table and sanity checks | 4 (done) |
| src/models | dataset.py, train.py, predict.py, validate.py | Training table (train and validation rows only) and its checks; fine-tuning on Colab; loading weights and predicting 7 tactic probabilities; validation scores and PASS/FAIL checks on the Mac | 6 (done) |
| src/claims | schema.py, patterns.py, extractor.py, build.py | Claim object and limits; phrase patterns and word lists (data only); spaCy and token patterns to typed claims; train hit rates, scores against the labels and checks | 7 (done) |
| src/verifiers | rows.py, facts.py, brands.py, bank.py, header_verifier.py, request_verifier.py, verify.py, selftest.py, build.py | Ledger row and its checks; cleaned facts, domain similarity and signature addresses; brand domains (data only); IBAN and bank-detail finder; N3 checks; who is asking for money or credentials; routing of claims to verifiers; self-test; contradiction rates and checks | 8 (done) |
| src/thread, src/verifiers, src/data | signals.py, builder.py, features.py, build.py, selftest.py, evaluate.py, thread_verifier.py, hijack_benchmark.py | The four N2 measurements; Enron and Apache thread rebuilding; cached tactic probabilities and claims of thread messages; thread build, false-alarm rates and checks; self-test; benchmark scoring; N2 rules, rows and flip point; the hijack benchmark (plan, prompts, API replies, cases) | 9 (done) |
| src/router, src/explain | router.py, ledger.py, score.py, reliability.json, pipeline.py, selftest.py, build.py, build_selftest.py, lime_explain.py, check.py | Routing; ledger rows and coverage; 0-100 score and bands; reliability factors (data); analyze() end to end; self-tests; calibration and results; LIME highlights; LIME faithfulness check | 10 (done) |
| src/api | settings.py, schemas.py, security.py, results.py, main.py, selftest.py, mutation_check.py, smoke.py | Settings and fixed size caps; Pydantic request and response shapes; the layers (request id and headers, body guard), rate limits, key check and audit log; the results allow-list; the app, routes, error handlers and server options; the self-test, the mutation check and the real-server smoke test | 11 (done) |
| frontend | package.json, package-lock.json, vite.config.js, index.html, README.md; src/main.jsx, App.jsx, api.js, index.css; src/pages/AnalyzerPage.jsx, DashboardPage.jsx; src/components/EmailInput, ErrorBanner, Results, RiskBadge, CoverageNote, FindingsTable, ThreadTimeline, HighlightedBody, TacticList, ScoreBreakdown, ClaimsTable, HeaderFindings, ResultTable and charts/ (parts, TacticF1Chart, BenchmarkChart, DistributionChart, BudgetChart); src/lib/segments.js, limits.js, format.js, useAnalysis.js, useResult.js, examples.js; scripts/check.mjs, mutation_check.mjs, browser_check.mjs, make_examples.py | Entry, layout and the API-not-ready banner; the proxy and the security headers; the only file that uses the network; the analyzer and dashboard pages; the form; one component per block of a result; four charts; offsets to pieces of text; the API's size limits; labels; the two-call flow; the generated examples; static checks, mutation check and browser check | 12 (done) |
| src/eval | metrics.py, ablation_n1.py, ablation_n2.py, ablation_n3.py, ablation_arch.py, claim_extraction.py, style_confound.py, paraphrase.py, charts.py | Metrics (metrics.py, written in Phase 6); one script per ablation; supporting experiments; charts | 6, 13 |

# 13. Viva preparation

> **Pitch (say it at the start and the end):** Pretexting emails have no link or attachment, so scanners miss them. PretextGuard reads what an email claims about itself and checks each claim against two independent references: its headers and its own conversation history. When the claim and the evidence disagree, that contradiction is the detection.

| **Question** | **Answer** |
|---|---|
| Hasn't this been done? There's a 2025 paper. | Yes, the MDPI Computers two-stage framework, which we cite. It scores payload-bearing phishing with LLM-generated, LLM-labelled data, body only. We isolate payload-free pretexting (N1), verify claims against headers (N3) and against thread history (N2). The ablations measure each difference. |
| The title says metadata. Where is it? | Half the system: the header evidence extractor and the thread builder are pure metadata, and both verifiers use it. |
| What if the attacker controls a real account and SPF passes? | That is exactly what N2 is for. The headers look clean, so we check the message against its own thread: new urgency, new bank details, a different sending path, or a fake reply chain. |
| Gmail passes SPF, DKIM and DMARC. How do you catch the fake David? | Authentication proves which domain sent the message, not who the person is. The body claims Acme Finance; the authenticated domain is gmail.com. That mismatch is the contradiction. A header-only check that treats pass as safe misses it. |
| How is this different from BEC-Guard? | BEC-Guard adds a header score and a body score in parallel. Addition cannot say "the body claims X and the headers disprove X". We route each claim to the evidence that can test it. |
| Mithun et al. already talk about claim mismatches. | They annotate the claims and explicitly leave verification to a future algorithm; they do not build a detector. We build that verifier, and add thread evidence they do not consider. |
| Ho et al. already detect phishing from compromised accounts. | Their detector is URL-based and needs organisation-wide mailbox data. Ours is payload-free and works from the message and its thread. |
| ConvoSentinel already does conversation-level detection. | For chat. It uses no email headers and no thread-integrity checks. |
| Aggarwal et al. (2014) already detected link-free phishing. | They score scam content that baits a reply: no recipient name, a money offer, a reply prompt. They never check who the sender claims to be against the headers or the thread, and they do not cover colleague impersonation or hijacked threads. |
| Plenty of student projects combine DistilBERT, metadata features and LIME. | Those fuse a text score and a metadata score, which is the parallel-fusion pattern. We route each claim to the evidence that can test it, and the ablation against parallel fusion measures the difference. |
| Isn't your data synthetic or circular? | Primary positives are real attack emails (Nazario, Nigerian Fraud, phishing_pot), and N3's affiliation checks are tested on their real claims. Synthetic data only fills modern gaps, mainly colleague impersonation, and always has matched benign twins. The thread benchmark uses real Enron and Apache threads with injected replies, and we say so. |
| How were tactic labels made? | Two LLM annotators (gemini-3.1-flash-lite and gemini-3.5-flash-lite) called through a free API at temperature 0, a third model (gemini-flash-lite-latest) breaking ties, a fixed JSON schema, and Cohen's kappa per label, following Pan et al. (2026); SemEval human labels for optional pretraining. All three models come from one family and one provider's free tier, so their agreement is agreement between models of one family, their errors are partly shared, and the labels are that family's judgement; kappa measures consistency between two models, not correctness. This is a limitation the report states. gemini-flash-lite-latest is a moving alias, not a pinned version: the provider's reply names the alias and not the model behind it, so the exact version is not recorded and it may be the same model as another annotator. Providers also update their models over time, so the labels are not exactly reproducible. |
| Why not just ask an LLM? | Cost and latency at gateway scale, no on-premise deployment, non-deterministic output, and no inspectable reasoning. An LLM can be an optional baseline. |
| Your F1 is below the published 99%. | Deliberately. Those numbers are on payload-bearing phishing where the link carries the signal. N1 removes that crutch and measures how far the number falls. |
| Why no database? | Privacy by design. The tool handles sensitive corporate email; storing it would create the breach risk the tool exists to reduce. |
| What is an ablation? | Remove one component, re-measure; the drop shows what that component contributed. We run one per claim. |
| What if Authentication-Results is missing? | Recorded as unknown, never as pass. The verifiers fall back to name-vs-address, Reply-To, lookalike and thread evidence. |
| How do you know an Authentication-Results header is real? | Anyone can write one into the email they send. We read only the headers the receiving organisation added: the topmost one, plus those directly below it from the same organisation, stopping at the first header from anyone else. RFC 8601 requires receivers to delete incoming headers that claim to come from inside their organisation. |
| Why not just use Python's address parser? | We do, first. It is strict and gave up on 28% of phishing_pot From headers, including the display-name spoof service@paypal.com \<x@evil.ru\>. The fallback takes the last \<...\> address, which is where replies go. |
| Is the keyword baseline a fair opponent for DistilBERT? | It is the simple-rules reference: phrase lists written from the tactic definitions, revised (if at all) by reading the train split only, and frozen before any label existed. Its thresholds are tuned on validation like DistilBERT's, and no labelled email was picked by its keyword hits, so it has no selection advantage. |
| How do you know your LLM-made labels are right? | Two annotators from different model families label every email from the same fixed prompt; Cohen's kappa per label measures agreement beyond chance (mean 0.501 over the tactics); a third annotator decides each disagreement; every raw reply and the model names are saved. There is no human validation sample, which is a stated limitation: the tactic scores are agreement with LLM annotators, not with people. |
| Aren't synthetic emails just one LLM's style? | Yes, so they are never mixed into real-email results. Every attack has a benign twin from the same template, the twin must not trip the keyword baseline, each attack's tactics are confirmed by a quoted cue, and the synthetic set exists only to give rare tactics enough positives. |
| Why DistilBERT, and can it run without a GPU? | DistilBERT is a smaller, faster BERT (6 layers, 66 million learned numbers). Fine-tuning needs a GPU, so it ran once on Colab; analysing one email afterwards takes a fraction of a second on a CPU, which is all the web app needs, and there is no LLM at run time. |
| How do you know the model is not just memorising 700 emails? | The training and validation loss are logged every epoch, training stops after three epochs without improvement on real validation emails and keeps the best epoch, three seeds are run and all reported, and the test split is touched once, in Phase 13. The validation scores are slightly optimistic because validation picked the epoch, the seed and the thresholds; the report says so. |
| Why are reciprocity, social proof and liking counts and not F1? | Each has fewer than 10 real positives in validation or test, so one email would move F1 by several points. They learn mostly from synthetic emails, whose results are reported apart because they carry one LLM's style. |
| Why tune thresholds, and why on validation? | A 0.5 cutoff assumes balanced classes; with rare tactics and a loss that up-weights positives the probabilities are shifted, so each of the four main tactics gets its own cutoff chosen on validation emails. The keyword baseline is tuned the same way, and the test split is used once with the cutoffs fixed. |
| How does the claim extractor work, and why not a neural model or an LLM? | spaCy cuts the text into tokens and marks names; 85 hand-written patterns over tokens, plus organisation and signature rules, turn it into typed claims. The claim types are a closed list of typical phrasings, so rules need no training data beyond a few hundred labels, every claim names the rule that produced it (an explanation by construction), cost grows only with text length, and there is no LLM at run time. The limit is that it does not understand paraphrase, and the scores say how large that limit is. |
| How do you know the claim patterns were not fitted to the validation or test data? | There are four versions (0.1 to 0.4) and each revision was made only after reading train results (the false positives printed from the train split); the development runs never load a validation email (--train-only); version 0.4 was committed (8633c4f) before the validation emails were scored once; nothing was changed after that, and the test split is untouched until Phase 13. The train scores are called development scores for that reason. |
| Your claim F1 is modest. Is that good? | Partly. On the validation emails the five types with enough positives score F1 0.17 to 0.78 (macro 0.56). On 3 of the 5 the extractor is within 0.1 of the F1 the two LLM annotators reach against each other, which is about the most that labels agreeing this loosely can support (mean kappa over claim types 0.458); on the others (affiliation_internal and signature_contact) it is clearly lower, and affiliation_internal (0.17) is the weak one because it cannot be decided from the body alone. Six of the eleven types have too few real positives to give an F1 and are reported as counts. The tables in Section 8.15 show each type. |
| What does a claim's confidence mean? | The strength of the rule that fired (0.9 for a phrase that is hard to say innocently, 0.6 for one that is common in ordinary mail). It is not a probability and nothing calibrates it. Results are reported at two operating points, every claim and strong claims only, and Phase 13 chooses between them per type on validation. |
| Can an attacker get past the extractor by rewording, or by writing in another language? | Yes, that is a stated limit: the patterns are English phrasings and do not read paraphrase. Two things limit the damage: the signature and organisation rules do not depend on the attacker's wording, and the header verifier checks the sender's evidence whatever words were used. The paraphrase test in Phase 13 measures the loss. |

## 13.1 Concepts already taught

- Email as plain text: headers, blank line, body; From, Reply-To, Return-Path, Received, Authentication-Results.

- Display name vs actual address; the letter-and-envelope model of SMTP.

- SPF, DKIM and DMARC as verdicts we read, not computations we run.

- Payload vs payload-free; why pretexting evades technical controls; what a .eml file is.

- Ablation studies; the seven-tactic taxonomy; why several datasets are merged.

- Homebrew, venv and activation, pip with pinned requirements, packages and \_\_init\_\_.py, running from the project root (Phase 0).

- .gitignore, .env and .env.example, pytest basics, pip-audit (Phase 0).

- .eml, mbox and maildir; MIME parts, transfer encodings and character sets; generators; pandas DataFrames and Parquet; hashing for deduplication and train-test leakage; stratified, grouped and hash-based splits; the header coverage table; magic bytes, path traversal, decompression bombs and header injection (Phase 1).

- Shortcut learning and why redaction matters; HTML parsing with BeautifulSoup; regular expressions, replacement order and ReDoS; the public suffix list; email quoting and signature conventions; pre-tokenised text (Phase 2).

- Header syntax (folding, encoded words) and address parsing with email.utils; the Received chain read bottom-up and public vs private IP addresses; the Authentication-Results format (standard and Microsoft) and which headers to trust; registered domains; freemail providers and open platforms; lookalike scoring with rapidfuzz, punycode and look-alike characters; time zones and send hour (Phase 3).

- Rule-based versus learned classifiers and why a baseline matters; text normalisation (case, punctuation, contractions, pre-tokenised text); whole-word phrase matching versus regular expressions; strong and weak phrases, scores and thresholds; multi-label output; precision versus recall for word lists; leakage from choosing words on test data; selection bias when keyword hits pick the labelled sample (Phase 4).

- Annotation as ground truth and why two annotators; Cohen's kappa (agreement beyond chance, one value per label); label noise; fixed-allocation stratified sampling; JSON schema validation; prompt injection into an LLM that reads attacker-written text; matched benign twins as a style-confound control; why a SemEval mapping must mask labels it cannot give (Phase 5).

- Tokenisers and word pieces; fine-tuning a pretrained model; tensors, autograd, the training loop and DataLoader in PyTorch (compared with Node and React); multi-label sigmoid outputs versus softmax; binary cross-entropy; class imbalance and pos_weight; why 0.5 is usually the wrong threshold and per-tactic thresholds tuned on validation; train, validation and test roles; overfitting and early stopping; seeds and GPU reproducibility; safetensors versus pickle (Phase 6).

- Tokens, named-entity recognition and what spaCy's small English model does and does not find; rules versus learned extraction; a token-pattern language compiled to spaCy's Matcher and why it avoids ReDoS; character spans and offsets; precision and recall per type at two operating points (all claims, strong claims only); development set versus frozen version, and why patterns are written from the train split only (Phase 7).

- Claim-conditioned rules versus learned features (a route guard that reads the request body, not a global middleware); the three domains (From, authenticated, claimed) and what each header proves; a three-valued result (contradiction, consistent, not checkable; true, false, null) and why 'not checkable' is never 'no contradiction'; severity as rule strength, not probability; display-name spoofing, Reply-To hijacking and look-alike domains as rules; brand domains and third-party mailers; the IBAN mod 97 checksum; testing a rule engine without labels (hand-made cases, rates by category and source, reading the false alarms, then a freeze) (Phase 8).

- Message-ID, In-Reply-To and References and how mail programs thread a conversation; rebuilding threads without them (normalised subjects, time runs, shared participants, duplicates across folders); union-find; quoted history and word-run shingles as a way to compare re-wrapped text; why a hijacked account still passes SPF, DKIM and DMARC; change-point detection in plain words (the flip point); request drift as a set difference; sending-path fingerprints (the first Received hop, the mail program without its version) and why one change alone is weak; building a benchmark by injection and why it can be circular (the benign twin as the style control, each signal in its own variant); grouped splits for threads; bootstrap intervals that resample threads rather than cases (Phase 9).

- Claim routing as a lookup table (an Express route table); the verdict ledger as a fact-checking record (claim, evidence, verdict, reason) and why the output is the explanation; turning categorical severities into a score (points per severity, the strongest row of each claim, a saturating half-weight sum, a multiplier, a cap); why a cap and why consistent rows never lower a score; calibration without labels (a declared false-alarm budget, a small fixed grid, a meaning that must hold, the nearest point to the initial numbers) and what a surrogate target can and cannot say; the corpus confound (attacks and legitimate mail come from different corpora, so report per source and with both denominators); Wilson intervals; reliability factors as data computed from train rates; a parity check between the batch code and the product code; a stand-in classifier for testing code that needs a model; LIME in plain words (hide random words, watch the probability, fit a small weighted line near the email), why it explains a classifier and not rules, and the deletion test with a frequency-matched random baseline (Phase 10).

- FastAPI against Express (a decorated function is a route; Depends is middleware that only some routes use; an ASGI middleware sees every request); Pydantic as a schema (Joi or Zod) and why the routes parse the body themselves (FastAPI parses before dependencies, which would put the key check after the parsing); the event loop and why CPU-bound work goes to a worker thread; a lock and a busy answer instead of an unbounded queue; uvicorn; API keys and constant-time comparison; rate limiting per client address, a moving window, and why X-Forwarded-For is not trusted; counting bytes as they arrive because Content-Length can lie; CORS as a browser rule, DNS rebinding and the Host header; response headers (no-store, nosniff, CSP); fixed error messages and request ids; logging by a fixed list of fields and a canary string; a stand-in classifier again; mutation testing (break a control and see whether a test notices) (Phase 11).

- React for this project (components and state with useState, effects and cleanup, a custom hook for the two-call flow, lazy loading of the dashboard); the Vite dev and preview server as a same-origin proxy that adds the key, `loadEnv` and why only VITE_ variables reach the browser; why rendering untrusted text as a text node defeats XSS and why dangerouslySetInnerHTML does not; turning character offsets into highlighted pieces (code points against UTF-16 units, overlapping spans); fetch with AbortController, a timeout and one error type; reading the API's Retry-After; Tailwind v4 and CSS variables for light and dark; Recharts and why every chart gets a table view; what a Content-Security-Policy blocks line by line; exact pins, a lock file and npm audit; driving a page with a real browser and comparing what is drawn with what the API answered; mutation testing of the checks themselves (Phase 12).

To be taught during the build: the ablations (remove one component and measure again), why the test split is used once, bootstrap intervals again, TF-IDF with logistic regression as a cheap second model, AUC for the style-confound test, paraphrase attacks, and drawing the charts of the report (Phase 13).

# 14. Decisions log

| **When** | **Decision** | **Reason** |
|---|---|---|
| July 2026 | Picked Problem Statement 37 | Best effort-to-marks ratio on the list; text in, labels out, no hardware |
| July 2026 | v1 scrapped; rebuilt as PretextGuard v2 | v1 duplicated the 2025 MDPI Computers paper |
| July 2026 | FastAPI + React, no database; MERN rejected | Model lives in Python; privacy by design |
| July 2026 | Real attack corpora as primary positives; synthetic only as gap-fill with matched benign twins | Avoid the style confound and circular data |
| July 2026 | LLM-assisted annotation; no hand-labelling or human validation sample | Nagasai's choice; Pan et al. (2026) precedent |
| July 2026 | Secrecy added as the seventh tactic; commitment dropped | BEC literature; sparse label |
| From 29 July 2026 | Review-I presented | Deck, prep notes and slide spec delivered |
| After Review-I | Faculty struck old N2 (SemEval transfer) and old N4 (severity model) | Faculty decision; one more core claim requested |
| 21 Sep 2026 | New N2: thread consistency verification | Covers N3's blind spot: authenticated, hijacked accounts |
| 21 Sep 2026 | Claim-routed verification pipeline adopted as the architecture contribution | Fact-checking style design; builds the verifier Mithun et al. (2024) left open |
| 21 Sep 2026 | SemEval pretraining and the 0-100 score kept as plain components | Useful, but not claimed as novelty |
| 21 Sep 2026 | Claude writes all code phase by phase; Nagasai runs it in VS Code | Nagasai's choice |
| 21 Sep 2026 | Missing authentication headers are treated as unknown, never pass | Evidence honesty |
| 22 Sep 2026 | Running example corrected: freemail and lookalike senders pass authentication; exact-domain spoofing is a separate case | Technical correctness; strengthens N3's conditioning argument |
| 22 Sep 2026 | Affiliation claims (internal and external) replace internal-only identity claims | Gives N3 real positives from Nazario and Nigerian Fraud |
| 22 Sep 2026 | N1 task fixed: binary attack detection, models A and B, three test views | The protocol was underspecified |
| 22 Sep 2026 | Raw header sources added (SpamAssassin, Nazario, phishing_pot) with a header coverage table | The Kaggle merge has no Reply-To, Received or Authentication-Results |
| 22 Sep 2026 | Apache mailing-list threads added for N2 header signals | Enron lacks reply-chain and routing headers |
| 22 Sep 2026 | Request drift owned by the thread verifier (N2); the request verifier checks the sender only | Diagram and text disagreed |
| 22 Sep 2026 | Optional organisation domain input, defaulting to the To domain | Internal-affiliation checks need it |
| 22 Sep 2026 | Claim types added to the annotation; claim extractor evaluated | Every verifier depends on claim extraction |
| 22 Sep 2026 | Annotation through free web chats (Gemini, DeepSeek; z.ai tie-break); no paid APIs | Nagasai's choice: keep the project free |
| 22 Sep 2026 | Python 3.12 instead of 3.11 | Matches the Colab runtime |
| 22 Sep 2026 | Commit after each working step | Stronger evidence of incremental work |
| 22 Sep 2026 | Deadline is not a planning constraint; scope not cut | Nagasai's decision |
| 22 Sep 2026 | Section 7 corrected: five tactics from Cialdini, urgency from Stajano and Wilson | Factual accuracy |
| 22 Sep 2026 | Figures redrawn (N1 marked novel, LIME fed by the classifier, organisation domain and security steps shown), text descriptions added, schema filled in stages | Diagram review before build |
| Sep 2026 | Phase 0 complete: Python 3.12.14 from Homebrew in a venv, repository pushed, environment check and pip-audit clean | Environment ready |
| Sep 2026 | No unit tests per phase; each phase is verified by running its scripts; one environment check kept | Nagasai's decision: focus on building |
| Sep 2026 | GitHub repo kept public (Nagasai-Datta/PretextGuard) | Nagasai's choice; raw data and .env are never committed |
| Sep 2026 | Phase 1 staging decisions: category column (spam is not an attack), cross-source deduplication, Kaggle header block, raw Enron kept out of the single-email table, Parquet, 70/15/15 stratified split | Honest labels and no train-test leakage |
| 2 Oct 2026 | READMEs: root (end-to-end idea) and each major folder in Phase 1; each src package in its own phase | Nagasai's request; documentation that matches the code |
| 2 Oct 2026 | Synthetic emails generated through free web chats into data/synthetic/ | No paid APIs; the method was missing |
| 2 Oct 2026 | Context file docs/PretextGuard_Context.md added; every new chat starts from it and this document; files arrive as downloads with mv commands or as paste blocks | Work continues in fresh chats with no memory, including Claude Code on the web |
| 2 Oct 2026 | Version 3.2: stale sections fixed; beginner walkthrough folded in (3.6, 6.10, 6.11, 8.8, 8.9, 12.6); Figure 5 added | Document review before Phase 1 |
| 6 Oct 2026 | Phase 1 downloads made by hand in the browser and moved into data/raw/; scripts only check, unpack and fetch the Apache archives (download.py replaced by unpack.py and fetch_apache.py) | Nagasai's suggestion; simpler code, and the assistant's sandbox could not reach the data hosts |
| 6 Oct 2026 | Apache lists: users@tomcat and users@kafka over 24 months (Oct 2024 to Sep 2026); Apache mail enters the single-email table as ham | spark and httpd too quiet; 12 months too few threads; the only modern benign source with authentication headers |
| 6 Oct 2026 | Kaggle phishing_email.csv not read; Kaggle Nazario.csv and SpamAssasin.csv left out | A merged duplicate; reprocessed copies of the raw corpora that the body fingerprint missed (98% and 96% matched by sender, date and subject) |
| 6 Oct 2026 | Deduplication by SHA-256 of a body's lowercase letters and digits; emails with no readable text dropped | Copies that differ only in spacing or punctuation match; nothing for a text model to read |
| 6 Oct 2026 | Split grouped by normalised subject, groups capped at 2% of a stratum (minimum 25), order from SHA-256 of seed 42 and the group key | Threads and spam campaigns never straddle train and test; identical on every machine and library version |
| 6 Oct 2026 | A Reply-To set by a mailing list is not counted as Reply-To divergence (Phase 3) | Every Apache message carries a list Reply-To and List-Id; avoids false N3 contradictions |
| 6 Oct 2026 | Phase 1 complete: 99,324 unique emails (20,313 attacks), header coverage table, split, READMEs; raw Enron confirmed to have no reply or routing headers | Phase 2 can start |
| 6 Oct 2026 | Files that contain code fences (READMEs) are delivered as downloadable files with mv commands, never as paste blocks; Claude Code on the web can attach files | A README paste block broke at its first inner fence |
| 6 Oct 2026 | Version 3.3: Phase 1 results folded into Sections 2, 4.3, 6.5, 8, 9, 10, 12, 13.1, 15, 16 and 17 | End of Phase 1 |
| 6 Oct 2026 | Every file arrives as a download with one mv block (no paste blocks when files can be attached); each phase is folded into two or three steps | Nagasai's request after Phase 1 |
| 6 Oct 2026 | body_clean keeps links (hidden HTML link targets written after the link text); quoted history and list footers removed; signature kept and copied to its own column; whitespace collapsed for every source | N1 model A needs the links; footers and spacing are source cues; claims live in signatures |
| 6 Oct 2026 | \[EMAIL\] added as a fourth placeholder; order \[URL\], \[EMAIL\], \[FILE\], \[DOMAIN\]; domains checked against tldextract's built-in public suffix list | An address hides a domain; .zip is a top-level domain; no network calls |
| 6 Oct 2026 | has_url from the raw body (text, HTML attributes, spaced forms) plus Kaggle's urls column for CEAS-08 and Nigerian Fraud | The link-free view must exclude emails whose links were lost in Kaggle's cleanup |
| 6 Oct 2026 | Each phase writes its own Parquet file (cleaned.parquet); earlier files are never modified | A mistake in one phase cannot damage an earlier one |
| 6 Oct 2026 | Kaggle Enron and Ling found pre-tokenised; spaced patterns added for all four placeholders and for quote markers | 13,107 Enron and 2,192 Ling redacted bodies still held spaced links or addresses |
| 6 Oct 2026 | ReDoS hardening of src/preprocess: bounded patterns, footer search rewritten, line breaks skipped for tag-heavy HTML | Two real backtracking bugs found in testing; the same code will clean attacker email in the API |
| 6 Oct 2026 | Phase 2 complete: no link or address pattern left after redaction (45 stray "www."), 4,580 naturally link-free attacks (696 in test) | Phase 3 can start |
| 6 Oct 2026 | Version 3.4: Phase 2 folded into Sections 2, 4.2, 6.2, 8.7, 8.9, 8.10 (new), 9, 10, 12, 13.1, 15 and 16 | End of Phase 2 |
| 7 Oct 2026 | Header evidence lives in its own file, data/processed/headers.parquet, joined on id | Each phase writes its own file |
| 7 Oct 2026 | Legacy email parser with each header field parsed on its own; a fallback for From values the strict address parser rejects | Malformed spam headers must not lose a whole row; the strict parser lost 28% of phishing_pot senders, display-name spoofs among them |
| 7 Oct 2026 | Authentication-Results read in both formats (standard, and Microsoft's without a server name) | Every phishing_pot mailbox is on Microsoft; the first run lost all their SPF verdicts |
| 7 Oct 2026 | Trusted Authentication-Results: the topmost header plus the headers directly below it from the same organisation; a higher header wins | Apache's topmost header records only an internal hand-over; fake headers written by the sender stay ignored (RFC 8601, Section 5) |
| 7 Oct 2026 | Freemail list hand-written (about 100 providers) plus open platforms (onmicrosoft.com, firebaseapp.com), with the tenant name compared for lookalikes | Additions read from the most common sender domains; lookalike Microsoft 365 tenants are a real attack pattern |
| 7 Oct 2026 | No organisation domain for collector mailboxes (monkey.org, ceas-challenge.cc, taint.org), placeholders (example.com, domain.com) or free mailboxes | They say nothing about the recipient's organisation; internal-affiliation checks there are recorded as not checkable |
| 7 Oct 2026 | Authentication evidence is never a learned feature; N3 uses it through claim-conditioned rules and Phase 13 reports it per source | No benign source carries SPF or DMARC verdicts, so a model would learn "has verdicts" means attack |
| 7 Oct 2026 | Brand-domain list for external affiliation moved to Phase 8 | It belongs with the verifier that uses it |
| 7 Oct 2026 | Phase 3 complete: header evidence for every email; src/headers README; stale phase status fixed in the root, src, data and results READMEs | Phase 4 can start |
| 7 Oct 2026 | Version 3.5: Phase 3 folded into Sections 2, 4.4, 6.2, 6.5, 8.1, 8.7, 8.9, 8.11 (new), 9, 10, 12, 13, 14, 15, 16 and 17 | End of Phase 3 |
| 7 Oct 2026 | Keyword baseline matches whole words from a normalised phrase lookup, not regular expressions | No ReDoS; "now" never matches inside "know"; one normaliser handles Kaggle's pre-tokenised text and ordinary text alike |
| 7 Oct 2026 | Tactic score = sum of the weights of the distinct matched phrases (strong 1.0, weak 0.5; the longer phrase wins on overlap); fires at 1.0 by default; per-tactic thresholds tuned on validation in Phase 13 | Repetition cannot inflate a score; weights encode precision; no labels exist yet |
| 7 Oct 2026 | Word lists written from the Section 7 definitions, revised only by reading the train split, frozen before Phase 5 labels come back; build.py loads train rows only | Leakage guard: validation and test never influence the words |
| 7 Oct 2026 | Authority list holds assertion phrases, not bare job titles | Titles appear in every signature and would fire on ordinary mail |
| 7 Oct 2026 | Phase 5 labelled sample drawn at random, stratified by source and category; any keyword-hit top-up is tagged sample_origin = keyword_topup and kept out of the headline baseline-versus-DistilBERT comparison | Picking emails by the baseline's own hits inflates its recall |
| 7 Oct 2026 | Phase 4 complete: lexicon, scorer and train-split checks; no new library | Phase 5 can start |
| 7 Oct 2026 | Version 3.6: Phase 4 folded into Sections 2, 6.11, 8.4, 8.7, 8.9, 8.12 (new), 9, 10, 11, 12, 13, 14, 15 and 16 | End of Phase 4 |
| 8 Oct 2026 | Real labelled sample: 700 emails by a fixed allocation per source and category (450 attacks, 150 ham, 100 spam), 60/20/20 across train, validation and test; ham and spam labelled too | The classifier and claim extractor need ordinary mail as negatives, and validation and test need labels for threshold tuning and the final run |
| 8 Oct 2026 | No keyword top-up for rare tactics; the sample_origin column is dropped (reverses the Phase 4 plan) | In the Phase 4 results reciprocity fires on 0.18% of phishing and social proof on 0.14%, and most firings are on ham or spam, so a top-up would have picked false positives; rare tactics come from synthetic emails |
| 8 Oct 2026 | Annotation runs through one command per annotator that calls the provider's free-tier API at temperature 0 (src/data/llm_api.py); the copy-and-paste chat loop stays as a fallback; raw replies are saved untouched, every reply is logged with the model name and time; an invalid item is re-asked once then dropped; disagreements go to a third model (Mistral Large) and the majority of three decides | About 120 manual pastes were too many to ask; an API fixes the temperature, which chat windows cannot, and the log is the audit trail; models still change over time, so the record is the mitigation |
| 8 Oct 2026 | Annotators see body_redacted only, cut at 2,000 characters; angle brackets are replaced; a reply must be a fixed JSON shape with spans quoted from the email; all-identical replies are rejected | Same text the classifier reads; prompt-injection hardening; hallucinated spans are caught |
| 8 Oct 2026 | data/labelled/batches/ is not committed; replies and labels are | Batches hold full email text and phishing_pot's licence forbids redistribution; replies hold only labels and short spans |
| 8 Oct 2026 | 240 synthetic attack-and-twin pairs over 12 situations; each attack's tactics fixed by the plan and confirmed by a quoted cue; the twin must not trip the keyword baseline; pairs split together; reported separately from real results | Gives rare tactics positives with known labels; style-confound control |
| 8 Oct 2026 | Annotators are three different models from one free API tier (gemini-3.1-flash-lite, gemini-3.5-flash-lite, tie-break gemini-flash-lite-latest) instead of Gemini, DeepSeek and z.ai | DeepSeek's, z.ai's and Mistral's APIs are not free, and Groq's free token limits are too small for 20-email batches; separate model families would be better, so the agreement is between models of one family, which the report states. annotate.py auto refuses to run two annotators on the same model, because a model agrees with itself |
| 8 Oct 2026 | SemEval techniques mapped as direct, partial or none; tactics SemEval cannot label are masked, never 0 | Calling an unannotated tactic 0 would teach the model that it is absent |
| 8 Oct 2026 | Phase 5 complete: 690 labelled emails, mean tactic kappa 0.501, 222 valid synthetic pairs | Phase 6 can start |
| 8 Oct 2026 | Version 3.7: Phase 5 folded into Sections 2, 8.4, 8.7, 8.9, 8.12, 8.13 (new), 9, 10, 11, 12, 13, 14, 15 and 16 | End of Phase 5 |
| 8 Oct 2026 | Training mix for the tactic classifier: the real and the synthetic train emails together, plus a real-only run with the same settings as a comparison | The three rare tactics have 2 to 11 real train positives and can only learn from synthetic text; the comparison measures whether the synthetic emails help |
| 8 Oct 2026 | Loss: binary cross-entropy with pos_weight per tactic (negatives divided by positives, at most 10), one sigmoid per tactic | Seven independent yes/no questions, so no softmax; a rare positive has to count like many negatives |
| 8 Oct 2026 | distilbert-base-uncased, 512 tokens with dynamic padding, batch 16, AdamW at 3e-5 with warm-up and linear decay, at most 8 epochs, stop after 3 without improvement, seeds 42, 43 and 44 all reported | Uncased because the Kaggle Enron and Ling text is lowercase; early stopping and three seeds guard against overfitting on about 700 emails and show how much luck matters |
| 8 Oct 2026 | Epoch, seed and thresholds chosen on real validation macro-F1 over authority, urgency, scarcity and secrecy; reciprocity, social proof and liking stay at 0.5 and are counts only | Tuning on fewer than 10 positives would only fit noise; validation scores are therefore slightly optimistic and the test split is used once, in Phase 13 |
| 8 Oct 2026 | The file uploaded to Colab holds train and validation rows only | Test emails and test labels cannot reach the training code |
| 8 Oct 2026 | Weights stored and loaded as safetensors, offline, with the output order checked against the tactic order | A pickle-format model can run code when loaded; a wrong output order would silently attach one tactic's probability to another |
| 8 Oct 2026 | Colab keeps its own preinstalled torch and Python (torch 2.11.0+cu130, Python 3.13.15 in the run); transformers is pinned to the same version as the Mac, and torch stays pinned for the Mac | Reinstalling torch on Colab is a multi-gigabyte download that can mismatch the GPU driver, and weights are plain numbers; the check that the Mac reproduces Colab's predictions (largest difference 0.000001, limit 0.001) shows the difference does not matter |
| 8 Oct 2026 | The keyword baseline is scored in Phase 6 too, with its default thresholds and with thresholds tuned on the same real validation emails; on synthetic emails it gets recall only | A fair comparison tunes both alike; twins that tripped the baseline were dropped, so its synthetic precision would be fake. The final comparison stays in Phase 13, on the test split |
| 8 Oct 2026 | SemEval pretraining skipped | The first item to drop (Section 12.4); the labelled and synthetic emails were enough to start |
| 8 Oct 2026 | Phase 6 complete: validation scores and checks in results/tactic_validation_scores.csv and tactic_checks.csv | Phase 7 can start |
| 8 Oct 2026 | Version 3.8: Phase 6 folded into Sections 2, 8.9, 8.14 (new), 9, 10, 12, 13, 14, 15 and 16 | End of Phase 6 |
| 8 Oct 2026 | Claims are found by spaCy name detection plus hand-written token patterns and organisation and signature rules; no model is trained for this step (revises the regular-expression plan of Section 6.2) | The claim types are a closed list of typical phrasings; token patterns cost time in proportion to the text and cannot backtrack (ReDoS-safe); each word is one whole token; the same patterns read Kaggle's pre-tokenised text; every claim names the rule behind it |
| 8 Oct 2026 | A claim's confidence is the strength of its rule (0.9 strong, 0.6 weak), not a probability; every result is reported for all claims and for strong claims only | Nothing calibrates the number, so it must not be read as a probability; two operating points show the precision and recall trade-off, and Phase 13 picks one per type on validation |
| 8 Oct 2026 | Patterns were written from the train split only, in four versions (0.1 to 0.4) with each revision read off train results; `--train-only` never loads validation; version 0.4 was committed (8633c4f) before the validation emails were scored once, and nothing changed afterwards | The same leakage discipline as the keyword baseline: a pattern revised after seeing validation would be tuning on validation. The real train scores are development scores |
| 8 Oct 2026 | The signature column is redacted at read time, and the extractor reads body_redacted cut at 2,000 characters (what the annotators labelled) plus 1,000 characters of signature | The Phase 2 signature column is cut from body_clean and still holds raw addresses; the labels' spans were quoted from the 2,000 characters |
| 8 Oct 2026 | Only five types (affiliation_internal, affiliation_external, authority, signature_contact, credential_request) have 10 or more real positives in validation and test and get an F1; the other six are counts; synthetic emails are scored apart and their precision is a lower bound | One email moves F1 by several points below 10 positives; the synthetic labels list only the claims the generator was required to include |
| 8 Oct 2026 | Phase 7 complete: hit rates, validation scores and checks in results/claim_*.csv | Phase 8 can start |
| 8 Oct 2026 | Version 3.9: Phase 7 folded into Sections 2, 6.2, 6.3, 6.11, 8.9, 8.10, 8.15 (new), 9, 10, 11, 12, 13, 14, 15 and 16 | End of Phase 7 |
| 9 Oct 2026 | Ledger rows have three values: contradiction (true), consistent (false) and not checkable (null); a rule that lacks its evidence returns not checkable, never 'no contradiction'; every row carries the rule and the claim type | Missing evidence must never read as safe, and a source without authentication verdicts must not look cleaner than one with them; a row traceable to its rule is an explanation by construction |
| 9 Oct 2026 | Authentication is read only through claim-conditioned rules; internal-affiliation checks need the organisation domain and are not checkable for mailing-list mail (the recipient domain is the list's host) | The same header values mean different things under different claims; no benign source has SPF or DMARC verdicts, so a learned feature would read 'has verdicts' as 'attack' |
| 9 Oct 2026 | Brand domains are a hand-written data file of certain domains only, with no free-mailbox domain and no third-party mailer; a missing domain gives a medium contradiction, never high; a brand's mail through a mailer counts as genuine only if the brand's own domain authenticated it | A gap in the list should cost a little precision and open no hole; 15 secondary domains are flagged for a hand check |
| 9 Oct 2026 | A look-alike is a name equal after look-alike character mapping, or a rapidfuzz ratio of 80 or more with both names at least 6 letters; the same name under another suffix is a weaker relation (medium) | Fixed from definitions, not tuned; short names such as visa and vista are alike by chance; regional domains of one brand are common |
| 9 Oct 2026 | Severity is the strength of the rule (high, medium, low), a weak claim lowers it one step, and the request verifier moves it for payment_change and gift_card (+1), data_request (-1) and valid bank details (+1) | Initial labels set from definitions; Phase 10 turns them into points and calibrates on validation, never on test |
| 9 Oct 2026 | The request verifier asks who is asking, not whether the request is true; a bank-detail change is always 'not checkable: needs the thread'; bank details are found without regular expressions (IBAN mod 97 and the country's length, labelled numbers) and shown masked | Headers can never confirm a change of bank details; no whole account number in a row or a log |
| 9 Oct 2026 | Signature addresses are read from the unredacted signature block (or the end of the cleaned body), not from the redacted text | The redacted text holds only the placeholder [EMAIL] |
| 9 Oct 2026 | The verifiers are checked by contradiction rates per category and per source, a self-test and a reading of the false alarms, not by precision or recall; the category contrasts are judged only with 20 or more checkable claims on both sides and are called partly corpus contrasts | Nobody labelled contradictions; attacks and ham come from different corpora with different header evidence |
| 9 Oct 2026 | Rules were revised only after reading train results, in versions up to 0.3; the validation emails were read once for the frozen version; the test split waits for Phase 13 | The same leakage discipline as Phases 4 and 7 |
| 9 Oct 2026 | An affiliation_external claim is checked only if the claim's own words name the organisation and say the sender is that organisation (a team, department, support, security, a footer, 'on behalf of'); a reference such as 'your Microsoft account' is not checkable, and the organisation is read from the claim text, not from the nearest organisation | The first train read contradicted 98 to 100 percent of the checkable external claims in every category, because brand mentions in ordinary mail were treated as claims of identity |
| 9 Oct 2026 | The attack-versus-ham check compares the share of emails with a contradicted claim, not the rate among checkable claims | The second is close to 100 percent in every category when 'checkable' mostly means 'contradicted'; changed after seeing the first train read and logged as that |
| 9 Oct 2026 | The signature text is cut at the first list-footer or quoted-header marker, the reader's own address is ignored when the recipient has no organisation, and a signature address on the same free mailbox provider as the sender is not checkable; an attack-versus-ham contrast that is above ham but below twice is a finding (info), and only a rate not above ham fails | The second train read showed the signature_contact alarms in ordinary mail were list footers, quoted headers and the collector mailbox of the corpus (ceas-challenge.cc, monkey.org); at version 0.2 signature_contact separated only 1.6 times, which is a finding for a low-severity rule, not a failure |
| 9 Oct 2026 | A display name with only a bare domain (Brand.com) is a low signal and only a shown e-mail address is medium; signature addresses are compared only for contact claims, not for postal addresses, disclaimers, copyright lines or sign-off names; an unrelated domain under an internal claim, and an unknown organisation from a free mailbox, are low | Read off the ham false alarms of the first train run: mailing-list recipient domains without a List-Id, name-recogniser mistakes such as 'Hi team', brand names written as Brand.com |
| 9 Oct 2026 | The extracted claims are cached per split in data/processed/claims_cache/ | The extractor takes about 20 minutes over the train split; the rules were revised several times and Phases 10 and 13 reuse the claims |
| 9 Oct 2026 | Synthetic header blocks are generated in Phase 13 for the N3 ablation only, reported apart from real results (not in Phase 8) | Tuning the rules on headers written by the same person would be circular |
| 9 Oct 2026 | A caveat is added to Section 8.15: the synthetic validation macro-F1 averages five types, one of which (credential_request) has a single positive there; no re-run, and the scorer of Phase 13 applies the 10-positive rule to macros too | The table showed the type as counts while the macro still included its F1 |
| 9 Oct 2026 | Phase 8 complete: contradiction rates, rule hits and checks in results/verifier_*.csv | Phase 9 can start |
| 9 Oct 2026 | Version 3.10: Phase 8 folded into Sections 2, 6.2, 6.3, 8.9, 8.15, 8.16 (new), 9, 10, 11, 12, 13, 14, 15 and 16 | End of Phase 8 |
| 9 Oct 2026 | The thread verifier is built from four measurements that return plain numbers and sets (src/thread/signals.py) and one file of rules that turns them into ledger rows (src/verifiers/thread_verifier.py); `verify_claims` gets an optional `thread` argument and its default behaviour is unchanged | A measurement can be tested with a hand-made thread and no model; the Phase 8 results stay reproducible (RULES_VERSION unchanged) |
| 9 Oct 2026 | Apache threads are rebuilt from Message-ID, In-Reply-To and References (union-find); Enron threads from the normalised subject, 14-day runs and shared participants, with copies removed by date, sender and subject (the copies carry different Message-IDs); a thread needs 3 to 50 messages and at least two senders | Raw Enron has no reply headers; a bigger group is an announcement list, not a conversation; one sender is a monologue |
| 9 Oct 2026 | The new text of a message is cut as in Phase 2; its quotation (lines marked >, or everything after an Outlook-style marker) and its whole text are kept too, and a quotation is compared with the WHOLE text of the earlier messages; forwards are not checked (version 0.2) | The first real train run showed inline replies: the sender's own answers between quoted paragraphs were counted as history, and the earlier inline answers a reply quotes back were missing from the comparison |
| 9 Oct 2026 | The quotation check compares 5-word shingles (a quotation of 20 words or more with under 30% matching shingles is high), not lines | Mail programs re-wrap and prefix quoted text; shingles survive that; fixed from the definition, not tuned |
| 9 Oct 2026 | Tactic onset uses only authority, urgency, scarcity and secrecy and the Phase 6 thresholds: it fires when a tactic reaches its threshold in a message and in no earlier one and is at least 0.40 above the average of the earlier messages (the 0.40 was added in version 0.2), with at least two earlier messages | The other three tactics have under 10 real positives; the first real train run showed urgency crossing its threshold of 0.45 by a hair in ordinary business mail, while an attack jumps |
| 9 Oct 2026 | Request drift is a set difference on bank_detail_keys plus the first request of each type in the thread; a different detail of the same kind is high, a first detail medium | A change of bank details in a running thread is the classic hijack; the sets come from the Phase 8 bank finder |
| 9 Oct 2026 | One change of server or mail program alone is low and both together medium; the server is compared by its network (the first three numbers of the IP address, version 0.2) and the mail program without its version; a look-alike domain under an earlier sender's name is high | Servers and programs change for harmless reasons (a new phone, a trip, an upgrade) and a provider rotates its addresses: a new exact address alone fired on 402 of 1,243 real Apache messages |
| 9 Oct 2026 | prior_relationship is judged by whether the sender took part earlier in the thread; the strongest answer is a low contradiction | A call outside the thread cannot be disproved |
| 9 Oct 2026 | The flip point is the first message with a medium or high contradiction, judged message by message against its own past | Change-point detection in its simplest form; the index is the explanation |
| 9 Oct 2026 | The benchmark has five cases per base thread (neg_real, neg_synth, A takeover, B look-alike swap on Apache, C forged) and the benign text is the body of B and C and of neg_synth | Each signal is tested in its own variant; the same words as a negative and as a positive remove the style confound |
| 9 Oct 2026 | Bank details in injected texts are inserted by code as a valid fictional IBAN (the model writes a token) | An invented IBAN almost never passes the check digits, so the signal could not fire |
| 9 Oct 2026 | The injected message ends the thread (the later real messages are dropped), and the scan must flip at the injected message | The later real messages quote the real reply, not the injected one |
| 9 Oct 2026 | Rates are bootstrapped over threads, not cases, and a cell under 10 cases is a count only | The cases of one thread share its history; one case moves a rate by many points below 10 |
| 9 Oct 2026 | Rules were written from definitions and revised only after reading train results; the validation threads were scored once for the frozen version; the test threads wait for Phase 13 | The same leakage discipline as Phases 4, 7 and 8 |
| 9 Oct 2026 | Threads with a message the tactic classifier trained on are kept out of validation and test | The classifier must not have seen the messages whose onset it is asked to find |
| 9 Oct 2026 | Phase 9 complete: thread counts, false-alarm rates, benchmark counts, detection scores and checks in results/thread_*.csv and hijack_*.csv | Phase 10 can start |
| 9 Oct 2026 | Version 3.11: Phase 9 folded into Sections 2, 4.3, 6.2, 8.7, 8.9, 8.17 (new), 10, 11, 12, 13, 14, 15 and 16 | End of Phase 9 |
| 9 Oct 2026 | LIME for text is written by hand (random word removal, kernel weights, weighted ridge fit, fixed seed) and cross-checked once against the lime package, instead of adding that package | `pip install lime` also installs matplotlib and scikit-image, which only its image explainer uses; no new dependency in a service graded on security; every line can be explained at the viva; exact character offsets for the highlights |
| 9 Oct 2026 | The risk score takes points from the severity of a ledger row, not from the type of its claim; the strongest row of each claim counts, each further claim counts half as much as the one before, consistent and not-checkable rows add nothing, and a reliability factor per rule (set from train false-alarm rates) lowers a noisy rule | The severities of Phases 8 and 9 already encode how strong each rule is, so per-claim-type weights would count the same thing twice; replaces the Section 6.6 wording that affiliation and payment contradictions weigh most |
| 9 Oct 2026 | The first verdict band is named Low risk, not Benign, and the report carries a coverage block (claims found, checked, contradicted, consistent, not checkable) | A consistent row means nothing contradicts the message, never that it is safe; a pasted body with no headers has little to check |
| 9 Oct 2026 | header_findings is the cleaned header evidence the header verifier read, not ledger rows, and the whole report shape is spelled out in Section 6.3; Section 6.11 no longer describes LIME as removing one word at a time | The shape was listed without saying what header_findings held; removing single words is occlusion, a different method |
| 9 Oct 2026 | Version 3.11.1: corrections before Phase 10 in Sections 6.2, 6.3, 6.6, 6.11, 9, 14, 15 and 17 | Writing the Phase 10 plan found a conflict and gaps between the context file and the master document |
| 9 Oct 2026 | Phase 10 complete: score version 0.2 frozen; the router, ledger, score and analyze() and the hand-written LIME are built; calibration, budget, distribution, benchmark check and LIME check in results/score_*.csv and lime_checks.csv | Phase 11 can start |
| 9 Oct 2026 | The risk score takes its numbers from a false-alarm budget on legitimate validation mail (High risk at most 1%, Suspicious or above at most 5% per source, judged from 20 checked messages), a fixed grid of 27 points and the rule "nearest to the initial numbers that keeps the meaning and meets the budget"; the attack corpora, the hijack benchmark and the labelled tactics are never fitted | Nobody labelled contradictions, so nothing can be fitted to detection; the benchmark is built to trigger the rules (circular) and attacks differ from legitimate mail by corpus |
| 9 Oct 2026 | Reliability factors: a rule that fires on more than 5% of the checked legitimate mail (ham) of a source or of real thread messages, with at least 20 hits, counts 0.5; above 10% it counts 0; stored in src/router/reliability.json (hv_sig_freemail_sender, hv_sig_other_domain, tv_path_origin count 0) | A rule that cries wolf on legitimate mail would breach the Suspicious budget on its own; a data file, like thresholds.json, so the numbers are visible and checked |
| 9 Oct 2026 | Legitimate mail means ham only: spam is listed, not budgeted, and does not count towards a rule's reliability (the constant ORDINARY in src/router/build.py). Made after the validation emails had been read, so the validation figures are a check, not an independent test | The first validation run counted spam as ordinary mail; spam asking for payments from free mailboxes put rv_freemail at half weight, a lone free-mailbox payment request scored 30 (Low risk) and two spam emails decided a budget verdict. Spam is not legitimate mail; the test split in Phase 13 is the clean measurement |
| 9 Oct 2026 | A group over the budget is a finding (OVER), not a failed run, and when no grid point meets the budget the initial numbers are kept; the Enron thread group is over (5.38% Suspicious or above in enron (real thread messages)) because of the quote check, which is also the only rule that finds the forged-thread variant on Enron | The budget is a policy choice; fitting a rule's weight to make a validation number pass would be fitting on validation; the trade-off is stated in Section 8.18 |
| 9 Oct 2026 | The LIME faithfulness check compares the LIME words with random words matched by how often they occur in the email; the first check (random words of any frequency) was unfair and its numbers are not used | The words LIME names are often frequent ones, so removing them removes more text than removing a rare random word |
| 9 Oct 2026 | Version 3.12: Phase 10 folded into Sections 2, 6.6, 8.18 (new), 9, 10, 11, 12, 13, 14, 15, 16 and 17 | End of Phase 10 |
| 10 Oct 2026 | The API has five routes: POST /analyze, POST /analyze/thread, POST /explain, GET /results and GET /health; LIME is its own route | slowapi limits are per route and a LIME run costs about 100 times a normal analysis (4.9 s against 0.05 s), so it needs a tighter limit; the interface shows the score first and asks for the highlights afterwards |
| 10 Oct 2026 | Requests are JSON only: no multipart upload, no python-multipart; a POST that is not application/json is 415 | The browser reads a .eml as text and sends it in a JSON field; a form post from another site cannot send that content type without a preflight, and the design has no CORS, so it is refused |
| 10 Oct 2026 | Size caps: 4,000,000 bytes per request counted as the bytes arrive, 300,000 bytes per email (the pipeline's own cap), 50 messages and 1,500,000 bytes per thread, refused and never cut silently | Section 10 had suggested 100 KB, but real .eml files with attachments are mostly base64 text; Content-Length can lie or be missing, so the count of arriving bytes is the limit; the caps are constants, not settings |
| 10 Oct 2026 | The API key is checked before the body is read: the routes read the body themselves and check it with Pydantic (parse_request) | FastAPI parses a declared body before it runs dependencies, which would put the key check after the parsing; an unauthenticated client now costs almost nothing |
| 10 Oct 2026 | The key is one X-API-Key header compared as SHA-256 digests with hmac.compare_digest, never read from the URL; the server refuses to start with a missing, placeholder, short (under 24) or low-variety key | A plain == leaks timing; URLs end up in logs and history; the placeholder in .env.example must never run |
| 10 Oct 2026 | Rate limits (slowapi, moving window, per socket peer address, never X-Forwarded-For): 120 a minute for all routes together counted before anything is read, 30 for /analyze and /analyze/thread together and 6 for /explain counted before the key check | A client can write X-Forwarded-For; counting before the key check means wrong keys use up the allowance and guessing is limited; slowapi also reads RATELIMIT_* from the environment, so the limiter is forced on |
| 10 Oct 2026 | One analysis at a time behind a lock, run in a worker thread: /analyze waits 2 s then answers 503 busy with Retry-After, /explain never waits | The classifier is CPU-bound and not built to run twice at once; an async handler doing CPU work would freeze the event loop; an unbounded queue is a denial-of-service lever |
| 10 Oct 2026 | No CORS in the design, a Host header allow-list (127.0.0.1, localhost), the server on the loopback address with one worker, 20 connections at most, no server header, proxy headers not trusted, /docs off | The interface uses a same-origin dev proxy so the key stays out of the browser; the Host check defends against DNS rebinding; uvicorn would trust X-Forwarded-For from 127.0.0.1 by default |
| 10 Oct 2026 | CORS_ALLOW_ANY_ORIGIN, a marked temporary switch at the top of src/api/main.py, opens CORS to every origin while testing (any origin, method and header, no credentials; X-Request-ID and Retry-After readable); it must be False before any deployment | Nagasai asked for CORS wide open while the API is only tested locally; the key is still required on the POST routes, no cookies are used and the Host check still applies; the self-test checks both settings, prints an info row for the shipped one, and a mutation of the switch is caught |
| 10 Oct 2026 | Every answer carries Cache-Control: no-store, nosniff, a CSP that allows nothing, no framing, no referrer and X-Request-ID; every error is a fixed sentence with a code and a request id; an exception's message is never returned or logged | A report is about one email and must not be cached; exception messages can quote the input; the id lets a user and the log meet |
| 10 Oct 2026 | The audit log writes one JSON line per event from a fixed list of fields and reduces every value to safe characters; the client address is logged only for refusals; a canary string sent everywhere must appear in no log line | Content cannot get into a log by construction, and the canary test proves it for every part of a request |
| 10 Oct 2026 | GET /results serves a fixed dictionary of table names (RESULT_FILES in results.py) read at start-up, 1 MB and 5,000 rows at most, numbers as numbers, cells display-safe; adding a result file means adding its name | No request value becomes a path, and a file dropped into results/ by accident is not published; the dashboard needs numbers, not CSV text |
| 10 Oct 2026 | Found while planning the API: parse_message raised RecursionError on 3,000 nested MIME levels; read_body now counts the depth without recursion and reads text over 20 levels as plain text with a coverage note | The Phase 10 docstring said it never raises and Section 10 promised a MIME depth limit; the Phase 10 crafted-input tests had missed nesting |
| 10 Oct 2026 | The libraries are pinned one release behind the newest (fastapi 0.141.1, pydantic 2.13.5, uvicorn 0.53.0); httpx 0.28.1 is used for the TestClient although Starlette prefers httpx2 | FastAPI 0.143.0 and Pydantic 2.14.0 were a day old; pip-audit found nothing in the pinned set; httpx is the established package and the notice is only a deprecation |
| 10 Oct 2026 | src/api/mutation_check.py breaks the controls one at a time in a scratch copy and the self-test must fail each time | A test that always passes proves nothing; the first run showed two checks that did not notice (a comparison test that read the docstring instead of the code, and a flood test with a timing limit that was too loose) and four that noticed only by crashing the self-test; all were fixed |
| 10 Oct 2026 | Phase 11 complete: 88 self-test checks, 37 of 37 broken controls caught, 19 real-session checks; results in results/api_checks.csv, api_mutations.csv and api_smoke.csv | Phase 12 can start |
| 10 Oct 2026 | Version 3.13: Phase 11 folded into Sections 2, 6.2, 6.10, 8.18, 8.19 (new), 9, 10, 11, 12, 13, 14, 15, 16 and 17 | End of Phase 11 |
| 10 Oct 2026 | The interface calls the API through its own server: vite.config.js forwards /api to 127.0.0.1:8000 and adds the X-API-Key header read from .env with loadEnv; the key is not a VITE_ variable | The browser never holds the key (the static check searches the bundle for it) and never makes a cross-origin request, so CORS is not needed; the server refuses to start with a short or placeholder key |
| 10 Oct 2026 | Every string from the API is drawn as a React text node: no dangerouslySetInnerHTML, innerHTML, markdown, links or eval, checked by a scan of src/ | Email text is attacker-written; the API already replaces < > and backticks, and drawing as text is the second line of defence; the browser check drives an email with script payloads in every part and no element or alert appears |
| 10 Oct 2026 | Highlights are cut from the text by code points (Array.from), not by JavaScript string offsets; a span that does not fit is skipped and counted | Python counts characters, JavaScript counts UTF-16 units: an emoji before a highlight would shift every later mark; the browser check compares the drawn text with text_read character for character |
| 10 Oct 2026 | The score is drawn first (POST /analyze) and the highlights second (POST /explain); a failed second call keeps the score and offers a retry; a new analysis cancels the old one | The score does not depend on LIME and LIME costs about 100 times a normal analysis; the API runs one analysis at a time and rate-limits /explain harder |
| 10 Oct 2026 | 'Low risk' is blue, never green, and a note appears when the band is Low risk but little or nothing could be checked | The band means no contradiction was found among the claims that could be checked; a pasted body without headers can only add tactic points (at most 12), and a green label would read as safe |
| 10 Oct 2026 | The demo runs `npm run preview`, which sends a strict Content-Security-Policy (own scripts and own connections only) and four more security headers; the development server cannot | Hot reload needs inline scripts; the browser check fails if the policy is missing and reports any violation, so the claim is tested and not assumed |
| 10 Oct 2026 | No router library, no state library, no UI kit, no CDN, no web fonts; Recharts for the four charts, loaded only when the dashboard is first opened | Fewer parts to explain and to audit; the page loads only from its own server (checked in the bundle); the chart library is the largest part of the bundle |
| 10 Oct 2026 | Each chart has a table view with exactly the numbers drawn and prints under it what it cannot show; counts-only tactics are listed apart; groups under 20 are flagged | A chart must never be the only way to read a result, and the dashboard must not say more than the validation numbers can (the labels come from one model family; the hijacks are synthetic) |
| 10 Oct 2026 | The page records that the second call finished (explainDone) instead of reading the report's `explained` flag | The API sets `explained` only when LIME ran, which needs a fired tactic; the first browser run on the real model found the page stuck on 'not asked for' after a successful call when no tactic fired, and a model-independent test now guards it |
| 10 Oct 2026 | The browser check compares what is drawn with what the API answered instead of asserting scores; the error states use made-up responses | The result then holds whichever model is loaded and tests the page; the API's own refusals are tested by src/api/selftest.py |
| 10 Oct 2026 | npm run mutation-check breaks the static checks' targets one at a time in a scratch copy and the check must fail each time | As in Phase 11: a check that never fails proves nothing; the mutations are hand-picked, so the result says the checks notice these changes |
| 10 Oct 2026 | The frontend result files frontend_checks, frontend_mutations and frontend_browser_checks are on the API's allow-list | The dashboard can show them; an unlisted file in results/ is not served |
| 10 Oct 2026 | Phase 12 complete: 96 static checks, 26 of 26 broken things caught, 93 browser checks; results in results/frontend_checks.csv, frontend_mutations.csv and frontend_browser_checks.csv | Phase 13 can start |
| 10 Oct 2026 | Version 3.14: Phase 12 folded into Sections 2, 6.2, 6.10, 8.20 (new), 9, 10, 11, 12, 13, 14, 15, 16 and 17 | End of Phase 12 |

# 15. Open items and next actions

1.  **Start Phase 13** (all experiments and charts: the ablations, the test split once, the report charts) in a new chat with docs/PretextGuard_Context.md and this document.

2.  **Replace the project-file copy** with v3.14 (remove older copies) and keep docs/ in the repo current.

3.  **Update the Review deck** when needed: novelty slide (N1, N2, N3 and the architecture contribution), the architecture diagram (Figure 2), the corrected running example (authentication passes for gmail.com), and the literature table (add Mithun et al. 2024, Ho et al. 2019, Valecha et al. 2022, ConvoSentinel, Aggarwal et al. 2014).

4.  **Phase 8 notes from Phase 3:** envelope mismatch is normal for mailing-list mail (lists send bounces to their own server), so count it only when list_mail is false; use authentication evidence only through claim-conditioned rules (no benign source has SPF or DMARC verdicts, and Apache has DKIM only); build the brand-domain list for external-affiliation claims and compare claimed domains with lookalike_score from src/headers/domains.py; send_hour comes from the sender's own Date header, so it is weak evidence alone; Kaggle rows carry only a rebuilt header block, so their header evidence is mostly unknown.

5.  **Training mix (decided and run in Phase 6):** the real and synthetic train emails together, with a real-only comparison run (Section 8.14); SemEval pretraining was skipped, so no label was masked (src/data/semeval_map.py stays available if time allows).

6.  **Re-verify statistics** before the report: IC3 2024 (and whether a 2025 report is out), DBIR 2026 wording, and the under-8% figure.

7.  **Calibrate** risk score weights and bands on the validation split (done in Phase 10: score version 0.2, Section 8.18).

8.  **Decide late** whether SemEval pretraining runs (only if time allows).

9.  **Later phases:** Kaggle Enron and Ling bodies are lowercase and tokenised; DistilBERT-uncased and TF-IDF see the same tokens either way, but a cased model would not (Phase 6). The naturally link-free attacks come mostly from Nigerian Fraud, Nazario and phishing_pot; report per-source shares with the N1 results (Phase 13). Models skip the 335 bodies that are empty after cleaning.

10. **Phase 13 notes from Phase 4:** tune one threshold per tactic on validation labels for the baseline and for DistilBERT alike (the default 1.0 until then); report baseline-versus-DistilBERT macro-F1 on the labelled validation and test items (all random draws, so no selection bias); report tactics with too few positives (see results/keyword_checks.csv) with counts instead of F1; state the lexicon version used (LEXICON_VERSION in src/baseline/lexicon.py).

11. **Phase 6 notes from Phase 5 (applied in Phase 6, repeat them in Phase 13):** report real-email and synthetic results separately; tactics with fewer than 10 positives in validation or test (see results/label_counts.csv) are reported as counts, not F1; tune per-tactic thresholds on the validation labels only and use the test labels once; the labels are LLM labels, so say so wherever an F1 appears; run semeval_map.py --check on the registered data before any SemEval pretraining.

12. **Phase 13 notes from Phase 6:** load the model with TacticClassifier (src/models/predict.py) and its thresholds from artifacts/tactic_model/thresholds.json; reuse src/eval/metrics.py for every system; use the test split once, with thresholds fixed on validation (tuned thresholds for the keyword baseline are in results/tactic_validation_scores.csv); report real and synthetic results apart; for synthetic emails with fewer than 10 attack positives in a split (test has fewer than 10 for urgency, liking, secrecy and reciprocity), pool validation and test and label it as pooled; keep tactics with fewer than 10 real positives as counts; quote the validation scores as slightly optimistic; report a bootstrap confidence interval for each F1 (with 12 to 44 positives per tactic, differences of a few points are noise); the baseline gets recall only on synthetic emails. LIME (Phase 10) needs a batch prediction function: use TacticClassifier.probabilities.

13. **Phase 8 notes from Phase 7:** extract_claims (src/claims/extractor.py) works on one email; the API reuses it. Route by type as in Section 6.4 and use attributes.organisation, attributes.department and attributes.person as the claimed identity. KNOWN_ORGS in src/claims/patterns.py (about 55 often-imitated organisations, data only) is the starting point for the brand-domain list: attach each name's real domains and compare the sender's registered domain with lookalike_score from src/headers/domains.py; an affiliation_external claim with no organisation in its attributes (a cue like "Security Team" alone) has nothing to check and is recorded as not checkable. affiliation_internal claims are phrases like "IT help desk" or "this is David from Finance" with at most a department; whether they are internal depends on the organisation domain (Section 4.4), so the verifier decides, and the extractor found only 13% of the labelled ones on validation, so a missing claim is never evidence of honesty. Spans point into the text the extractor read (body_redacted cut at 2,000 characters, or the redacted signature named by zone), so the API must keep that text for highlights. signature_contact finds contact blocks in redacted text, where every address is the placeholder [EMAIL]; to compare a signature address with the From address, the verifier must read the addresses from the unredacted signature (the signature column, or the parsed email at run time). confidence is rule strength, so a verifier may give strong claims more weight but must not treat it as a probability.

14. **Phase 13 notes from Phase 7:** the frozen patterns are in src/claims/patterns.py (PATTERN_VERSION is saved in results/claim_checks.csv); build.py never loads the test split, so Phase 13 adds src/eval/claim_extraction.py, which scores the frozen patterns on the test labels once. Choose the operating point (all claims or strong only) per type on validation and apply it once to test. Report the five types with enough positives as F1 with a bootstrap confidence interval and the other six as counts; real and synthetic apart; say that every score is agreement with LLM labels from one model family. Report affiliation_internal, signature_contact precision and reply_direction recall as the weak spots, with the annotator-agreement F1 beside them (results/label_agreement.csv). Include the claim extractor in the adversarial paraphrase test.

15. **Phase 9 notes from Phase 8 (applied in Phase 9, Section 8.17):** `verify_claims` (src/verifiers/verify.py) routes prior_relationship to the thread verifier and, until Phase 9 exists, returns the placeholder row `tv_needs_thread` (not checkable); the thread verifier returns rows of the same shape (verifier 'thread', rule ids starting tv_, built with `contradiction_row`, `consistent_row` and `unchecked_row` of src/verifiers/rows.py and checked with `check_row`) and replaces the placeholder. Request drift: `bank_detail_keys(text)` (src/verifiers/bank.py) returns the set of (kind, value) bank details of a message; compare the sets between messages; the request verifier already marks a bank-detail change 'not checkable: needs the thread' (rule rv_change_needs_thread). Sending-path drift reads origin_ip, received_hops, mailer and from_registered_domain from headers.parquet; on mailing-list mail the authenticated domain and the DKIM signature belong to the list, not the author (auth_state 'list_relayed'), and the Apache Reply-To is set by the list. The claims of every message in headers.parquet are already in data/processed/claims_cache/ (train and validation); raw Enron messages are not in cleaned.parquet, so their claims need `extract_many`. Tactic onset needs the tactic probabilities of every message from TacticClassifier (the weights exist only on the Mac). Use the 10-positive rule and bootstrap confidence intervals for the N2 results.

16. **Phase 13 notes from Phase 8:** the rules are frozen at version 0.3 (RULES_VERSION in src/verifiers/verify.py, saved in results/verifier_checks.csv); the test split is read once with them. The N3 ablation (full against text-only, headers-only and parallel fusion) needs per-source results because authentication evidence differs by source (Section 8.11) and real affiliation positives apart from synthetic BEC; the synthetic emails have no headers, so generate clearly synthetic header blocks (a BEC attack from a freemail sender with a matched benign twin from the organisation's own domain) for that ablation only and report them apart. Choose the claim operating point (all claims or strong claims only) per type on validation and apply it once to test; severities become points in Phase 10 and are calibrated on validation. Say wherever a number appears that the claims come from a rule-based extractor scored against LLM labels from one model family, and that the contradiction rates are not precision or recall. Use the cached claims (data/processed/claims_cache/) for the train and validation splits; the test split needs its own cache.

17. **Phase 10 notes from Phase 9 (applied in Phase 10, Section 8.18):** the thread verifier is `verify_thread_message(messages, index)` and `scan_thread(messages)` (src/verifiers/thread_verifier.py); `verify_claims(claims, facts, contact_text, body_text, thread=(messages, index))` routes prior_relationship to it and gives each request claim a second, thread row. The rows about the thread itself (tactic onset, bank details, sending path, integrity) have claim_id 'thread' and claim_type set to the signal name (tactic_onset, request_drift, sending_path, thread_integrity, single_email). A message dictionary is described in src/thread/signals.py and built by src/thread/builder.py (record_from_table, message_record); the new text and the quoted history come from split_message; tactics come from TacticClassifier.probabilities and claims from extract_many (src/thread/features.py shows both with a cache). Thresholds come from artifacts/tactic_model/thresholds.json (load_thresholds). Severities are initial labels (rule strength) and are calibrated in Phase 10 on validation only; the N2 results of Phase 9 (results/thread_scores.csv) are the validation evidence for the thread rules, and results/thread_signal_rates.csv shows which thread rules are noisy on real threads (give a noisy low rule little or no weight). The single-email rule tv_single_no_reply_ids is low severity because many real replies lack reply headers.

18. **Phase 13 notes from Phase 9:** the frozen thread rules are in src/verifiers/thread_verifier.py (THREAD_RULES_VERSION and the version log are saved in results/thread_checks.csv); the test threads are built (data/processed/threads.parquet has a `split` column) but were never scored, so Phase 13 adds src/eval/ablation_n2.py, which scores the test cases of data/threads/cases.csv once (features for the test messages need their own cache: attach_features(messages, 'test')). Report N2 with and without the thread verifier inside the full risk score, per variant and source, the 10-positive rule and bootstrap intervals over threads (as src/thread/evaluate.py does), content signals on Enron threads and all four signals on Apache threads, real and synthetic apart. State that the injected messages and headers are synthetic, that variant A copies the details on purpose, that Enron has no sending-path data, and that the base threads are real. Include the thread verifier's false-alarm rates on real test threads.

19. **Phase 11 notes from Phase 10 (applied in Phase 11, Section 8.19):** the API calls `Analyzer.analyze(raw, org_domain=None, explain=True, request_id=None)` in src/router/pipeline.py and nothing else; create the `Analyzer` once at startup (it loads DistilBERT, about 270 MB, and spaCy; the module function `analyze` keeps one shared instance). `raw` is text or bytes, or a list of them for a thread (the newest by Date is judged, at most 50 messages of 300,000 bytes). It raises TypeError for input that is not text, bytes or a list, ValueError for an empty thread or a request id that is not 1 to 64 letters, digits, - or _, and ReportError when the report fails its own checks (a bug: answer 500 with the request id and a fixed message, never the details). The report is JSON-ready and has the shape of Section 6.3; `text_read`, claim texts and highlight texts are display-safe (< and > shown as U+2039 and U+203A, backticks as apostrophes, control characters as spaces, same length so every offset fits), but the interface must still render them as text. LIME costs about 300 emails of classifier work: 10.6 seconds per explanation at 300 copies and 4.9 at 150, so make `explain` optional (default off, or a second call after the score is shown, or `Analyzer(explain_samples=150)`) and rate-limit it harder; the score does not depend on LIME. The classifier is CPU-bound and one forward pass is not designed to run in parallel with another: run the analysis in a thread pool behind a lock or a small semaphore and answer busy (429 or 503) rather than queue without limit. The API's own size cap (for example 100 KB per email) comes first; the pipeline's 300,000 bytes is a backstop. Log the request id, time, mode, score, verdict, tactics fired and duration, never content or addresses. GET /results must serve an allow-list of results/*.csv (no path parameter). The pipeline needs src/router/reliability.json and artifacts/tactic_model/ on the machine that runs the API (the weights exist only on the Mac).

20. **Phase 13 notes from Phase 10:** the score numbers are frozen at version 0.2 (SCORE_VERSION in src/router/score.py and results/score_config.csv); the test split is read once with them, never to change them. Report the risk score per source and with both denominators (all emails and emails with a checked claim), attacks against legitimate mail only as descriptive shares because the corpora differ in header evidence (Section 8.16), and state the Enron thread-quote miss (Section 8.18) and the ham-only correction made after validation was read. The N3 ablation (full against text-only, headers-only and parallel fusion) and the N2 ablation (with and without the thread verifier inside the risk score) can reuse `scored`, `email_units` and `thread_units` in src/router/build.py, which score emails and threads in batch with the same ledger code `analyze` uses (parity was checked on 100.0% of validation emails). The architecture ablation builds a flat classifier from `flat_features` (src/router/ledger.py, FEATURE_NAMES) on the same signals and compares it with the routed score on F1, false-positive rate and the share of findings with a traceable reason. Score the hijack benchmark's test cases once (data/threads/cases.csv; test features need their own cache). The LIME numbers are validation numbers on 20 emails: say that the exact words are not stable (top 3 overlap 0.42 under another seed) while the deletion test holds, and that LIME explains the classifier only. Include `analyze` in the adversarial paraphrase test.

21. **Phase 12 notes from Phase 11 (applied in Phase 12, Section 8.20):** the API is described in Section 8.19 and src/api/README.md. Call it through a same-origin proxy (the Vite dev server forwarding `/api` to http://127.0.0.1:8000 and adding the `X-API-Key` header from the environment in vite.config.js): the browser never holds the key, and CORS is not needed, so CORS_ALLOW_ANY_ORIGIN in src/api/main.py can be False (an `import.meta.env` variable is only exposed to the browser if it starts with VITE_, so read the key with `loadEnv` inside the config file, never as VITE_*). Flow: POST /analyze shows the score, verdict, action and `coverage.note` first; then POST /explain (same body) fills the highlights; send one request at a time, because the server runs one analysis at a time. Statuses to handle: 401 (key), 413 and 422 (show the field from `errors[].loc`), 429 and 503 busy (wait `Retry-After` seconds), 503 model_unavailable, 500 (show the `request_id`). Every error body is `{"detail", "code", "request_id", "errors"?}`. Everything in a report is display-safe text, but render every string as a text node: no dangerouslySetInnerHTML, no `innerHTML`, no markdown or link rendering; test with the XSS payloads of src/api/selftest.py (XSS_PAYLOADS) and with real corpus emails. Highlights are character offsets into `text_read` (and claims into `text_read` or `signature_read` by `attributes.zone`): cut the text at the offsets and merge overlapping spans from different tactics. 'Low risk' means that no contradiction was found among the claims that could be checked: show `coverage` beside the band, and explain that a pasted body with no headers can only add tactic points. Thread input: several emails in any order, 1 to 50, up to 1,500,000 bytes together; a .eml is read in the browser (FileReader) and sent as text. The dashboard reads GET /results (the list) and GET /results?name=... (a table: `columns`, `rows` as objects, numbers as numbers, empty cells null); add a file to `RESULT_FILES` in src/api/results.py before the dashboard can read it. Counts-only cells (fewer than 10 positives) are counts, not rates: show them as counts.

22. **Phase 13 notes from Phase 11:** the API is not part of the ablations. Report its tests as they are: results/api_checks.csv (the stand-in classifier), results/api_mutations.csv (controls broken on purpose, all caught) and results/api_smoke.csv (the real model, timings, the canary in the server log). Say that the self-test uses a stand-in classifier, that the mutations are hand-picked, and that the slow-client limit of Section 8.19 is open. The adversarial paraphrase test should call `analyze()` directly (src/router/pipeline.py), not the API.

23. **Before any deployment (CORS):** CORS_ALLOW_ANY_ORIGIN at the top of src/api/main.py was True when Phase 11 ended: CORS is wide open for local testing, marked TEMPORARY in the code, in src/api/README.md and by a warning that `python -m src.api.main` prints. Set it to False before the API is deployed or reachable from another machine; the interface of Phase 12 goes through a same-origin proxy and does not need CORS. The self-test (results/api_checks.csv) prints which way the shipped switch is set and checks both settings. Phase 12 changes nothing here: the interface talks to its own server only and works with the switch either way (frontend/README.md). The switch is still True when Phase 12 ends.

24. **Phase 13 notes from Phase 12 (the interface and the dashboard):** the dashboard draws only files on the allow-list RESULT_FILES (src/api/results.py) and groups them by the part of the file name before the first underscore (GROUPS in frontend/src/pages/DashboardPage.jsx; an unknown prefix lands under Other), so every Phase 13 result file needs its name in both places (restart the API after adding a name: the files are read at start-up). The four charts read validation tables: TacticF1Chart filters `data === 'real_validation'` in tactic_validation_scores, DistributionChart and BudgetChart read validation rows of score_distribution and score_budget, BenchmarkChart reads score_benchmark_check; a test-split chart needs a new table (the test numbers are produced once) and its own component next to them in frontend/src/components/charts. Keep the rules of the existing charts: one colour per entity, a legend, a table view, what the chart cannot show printed under it, counts only below 10 positives, groups under 20 flagged. Charts for the report are made by src/eval/charts.py (matplotlib would be a new pinned library); the dashboard's Recharts charts are separate and read the same CSV files. frontend/src/lib/limits.js copies the API's size limits (change both together); frontend/src/lib/examples.js is generated from src/router/selftest.py (`PYTHONPATH=. python frontend/scripts/make_examples.py`). After any change to the interface run `npm run build`, `npm run check`, `npm run mutation-check` and `npm run browser-check` (wait a minute between two browser runs: the API allows 6 explanations a minute).

25. **Phase 14 notes from Phase 12:** the report may quote results/frontend_checks.csv, frontend_mutations.csv and frontend_browser_checks.csv as they are. Say that the browser check compares what is drawn with what the API answered and does not assert scores, that the error states use made-up responses, that the mutations are hand-picked, that only a Chromium-based browser was driven and that no screen reader or accessibility audit was run. For the viva: be ready to explain `vite.config.js` (the proxy and why the key is not in the bundle), `src/api.js`, `src/lib/segments.js` (code points against UTF-16 units), `useAnalysis.js` (two calls and cancellation), why React text nodes defeat XSS, and the Content-Security-Policy line by line. Screenshots for the slides: run `npm run preview` and capture the David example (score, findings, highlights) and the takeover thread (the flip point).

# 16. Glossary

| **Term** | **Meaning** |
|---|---|
| Payload | The part of an email that does technical damage: a malicious link or attachment |
| Payload-free | No link and no attachment; nothing for a scanner to catch |
| Pretexting | An attack built on a made-up identity or story; the victim does the damage |
| BEC / VEC / ATO | Business Email Compromise / Vendor Email Compromise / Account Takeover |
| Thread hijacking | An attacker replies inside a real conversation, usually from a compromised account |
| .eml | A plain-text file holding one email: headers, a blank line, then the body |
| Display name | The free-text name in From, for example "David Chen"; anyone can type anything |
| SPF / DKIM / DMARC | Checks on whether a sender may use a domain, whether the message is signed, and the combined verdict |
| Reply-To / Return-Path / Received | Where replies go / where bounces go (envelope sender) / the servers the message passed through |
| Message-ID / In-Reply-To / References | A message's unique ID / the ID it replies to / the chain of earlier IDs in the thread |
| Thread | The messages of one conversation, in time order; rebuilt from Message-ID links (Apache) or from subject, time and participants (Enron) |
| Flip point | The first message of a thread that breaks the pattern of the messages before it: the index N2 reports |
| Request drift | A request or bank detail that appears in a message and in no earlier message of its thread (a set difference) |
| Sending-path drift | The same sender writing from a server or mail program it never used earlier in the thread, or an earlier sender's name appearing at a look-alike domain |
| Shingle | A run of five consecutive words; a quotation is compared with the earlier messages as a set of shingles |
| Change-point detection | Finding the position where a sequence stops behaving as it did before |
| Hijack benchmark | Real threads with an attacker's message injected in place of a real one, and real and synthetic negatives; labels: hijacked or not, and the position |
| Claim | Something the email asserts about itself (identity, authority, relationship, request) |
| Verifier | A function that checks one kind of claim against evidence |
| Verdict ledger | The list of findings: claim, evidence, contradiction or not, and the reason |
| Ablation | Remove one part, re-measure, and the drop shows what that part was worth |
| Multi-label | One email can carry several tactics at once |
| Macro-F1 | F1 averaged equally across all tactic labels |
| Cohen's kappa | Agreement between two annotators beyond what chance would give |
| LIME | An explanation method that shows which words pushed a prediction |
| DistilBERT | A smaller, faster version of BERT used for the tactic classifier |
| Style confound | A model learning who wrote the text instead of what the text does |
| Corpus | A dataset of text (plural: corpora) |
| Affiliation claim | A statement that the sender represents an organisation: internal (the recipient's company) or external (a bank, vendor or agency) |
| Exact-domain spoofing | Forging the real company's own domain in From; fails DMARC when the company publishes a DMARC policy |
| Organisation domain | The recipient organisation's own domain, used for internal-affiliation checks |
| Header coverage table | Per-source counts of which headers exist; decides where header signals can be scored |
| .mbox | One file holding many emails back to back; how Nazario and mailing-list archives are distributed |
| Build time / run time | Build time: data, labels, training and experiments, done once. Run time: the web app analysing one email at a time |
| Fine-tuning | Further training of a pretrained model on our own labelled examples |
| Weights | The learned numbers of a trained model, saved as files in artifacts/ |
| Parquet | A compressed, typed file format for tables; faster and smaller than CSV |
| Precision / recall | Share of flagged emails that were attacks / share of attacks that got flagged |
| False-positive rate | How often legitimate emails are wrongly flagged |
| Deduplication | Removing repeated emails so none appears in both training and test |
| Data leakage | Test information reaching training, which makes scores look better than they are |
| venv | A project's private Python interpreter and packages, like node_modules for Python |
| Paste block | A terminal command that creates a file in place: cat \> path \<\< 'PG_EOF' ... PG_EOF |
| Context file | docs/PretextGuard_Context.md: what a fresh chat needs to continue the build |
| Magic bytes | The fixed first bytes of a file format (zip files start with PK); a reliable type check, unlike the file name |
| Path traversal | An archive member named like ../../file that would be written outside its folder; refused when unpacking |
| Grouped split | A split that keeps related emails (a thread, a campaign) together on one side of the train/test line |
| Placeholder | A fixed token such as \[URL\] that replaces a link, address, file name or domain in body_redacted |
| Pre-tokenised text | Text stored with every punctuation mark set apart by spaces ("john @ enron . com"), as in the Kaggle Enron and Ling files |
| ReDoS | Regular-expression denial of service: crafted text that makes a pattern try millions of ways to match |
| Registered domain | The part of a domain someone actually registered: mail.paypal.co.uk gives paypal.co.uk; found with the public suffix list |
| Public suffix list | The list of endings under which people register names (.com, .co.uk and so on); tldextract ships a copy |
| Authenticated domain | The domain an SPF, DKIM or DMARC pass actually vouched for; gmail.com for the fake David |
| Open platform | A service where anyone can create a sub-domain for free, such as \<tenant\>.onmicrosoft.com; the tenant name is what the attacker chooses |
| Collector mailbox | The address a corpus was gathered at (Nazario's monkey.org); it says nothing about a recipient organisation |
| Punycode | The xn--... form of a domain with non-Latin letters; decoded before lookalike comparison |
| Trust boundary | The receiving organisation's own mail servers; only Authentication-Results headers added inside it are trusted |
| Keyword baseline | Fixed phrase lists per tactic and a scorer; the simple-rules reference DistilBERT must beat (src/baseline) |
| Lexicon | The word and phrase lists of the keyword baseline; a strong phrase fires a tactic alone, a weak phrase needs a second different one |
| Normalisation | Turning text into one standard form (lowercase, plain apostrophes, no punctuation) before comparing it with phrases |
| Selection bias | A sample that favours one model because of how its items were picked, for example emails chosen by the baseline's own keyword hits |
| Annotator | One of the free-tier models that labels emails: annotator 1 and annotator 2 label everything, a third model (the tie-breaker) decides their disagreements |
| Batch | 20 emails and the instructions, pasted into one fresh chat |
| Re-ask | Sending an item back to the same annotator once because its answer was invalid or missing |
| Span | The exact words of an email that carry a claim, copied by the annotator and checked against the email |
| Benign twin | A legitimate synthetic email written from the same template as an attack, with no manipulation |
| Prompt injection | Text inside the data that tries to give instructions to the model reading it |
| Masked label | A label left out of training because its source cannot say whether it is 0 or 1 |
| Tokeniser | Cuts text into word pieces and maps each to a number from a fixed dictionary; DistilBERT reads at most 512 of them |
| Logit / sigmoid | The raw number the model gives per tactic / the function that turns it into a probability between 0 and 1; one sigmoid per tactic, so the seven probabilities do not add up to 1 |
| Binary cross-entropy | The loss for a yes/no answer: the more confident the wrong answer, the larger the penalty |
| pos_weight | A per-tactic loss weight (negatives divided by positives, at most 10) so a rare positive counts like many negatives |
| Threshold | The probability at which a tactic counts as fired; tuned per tactic on validation emails |
| Epoch | One pass over all training emails |
| Early stopping | Stopping after several epochs without validation improvement and keeping the best epoch; a guard against overfitting |
| Overfitting | A model memorising its training emails: training loss keeps falling while validation loss rises |
| Seed | The number that fixes shuffling and starting values, so a run can be repeated (GPU arithmetic still makes it similar, not identical) |
| Safetensors | A model file format that holds only numbers; the older pickle format can run code when loaded |
| Claim extractor | The part that reads an email and returns the claims it makes about itself (src/claims); it finds claims, the verifiers check them |
| Token | One word-like piece of text as spaCy splits it ("verify", "David", ","); the patterns match tokens, not characters |
| Named-entity recognition | Finding the names of people and organisations in text; spaCy's small English model does it, with mistakes |
| Token pattern | A hand-written phrase such as `verif*\|confirm* ..2 your ..2 account*` that matches a run of tokens; cost grows with text length and cannot backtrack |
| Rule strength (confidence) | 0.9 for a phrase hard to say innocently, 0.6 for one common in ordinary mail; not a probability |
| Operating point | One way of using the same extractor: all claims (higher recall) or strong claims only (higher precision) |
| Development set | Data a system was built while reading (here the train emails and their labels); its scores are optimistic and are kept apart from the frozen version's validation scores |
| Frozen version | A pattern or model version that is committed and no longer changed before it is scored on validation or test |
| Ledger row | One verdict about one claim: the claim, the verifier, the rule, the evidence, contradiction (true, false or null), severity and a plain-English reason |
| Not checkable | A ledger row whose evidence is missing (no organisation domain, no authentication verdict, no thread); it is never counted as 'no contradiction' |
| Claim-conditioned rule | A check that runs only for one type of claim, so the same header values mean different things under different claims |
| Severity | The strength of the rule that fired (high, medium, low); not a probability; Phase 10 turns it into points |
| Look-alike domain | A registered name that differs from a real one only by look-alike characters or a letter or two (paypa1.com, acme-corp.co) |
| Brand domain | A domain an often-imitated organisation really sends mail from; the list is hand-written in src/verifiers/brands.py |
| IBAN checksum | Move the first four characters to the end, turn letters into numbers (A is 10), read the result as one number: it must leave remainder 1 when divided by 97 |
| Request drift | A request in a new message (new bank details, a new account) that differs from everything earlier in the thread; checked in Phase 9 |
| Claim router | A lookup table from claim type to the verifier that can check it (Section 6.4); a claim of an unknown type is reported, never dropped |
| Risk score | 0 to 100 from the ledger: points per severity, the strongest row of each claim, each further claim worth half the one before, urgency and secrecy multiplying, a cap at 100 |
| Verdict band | Low risk (0-34), Suspicious (35-69) or High risk (70-100); Low risk means no contradiction among the claims that could be checked, never that the email is safe |
| Coverage | How many claims were found, checked, contradicted, consistent and not checkable, and a plain sentence on what could not run and why |
| Reliability factor | 1, 0.5 or 0 per rule, from how often the rule fires on legitimate mail; a rule that cries wolf counts less (src/router/reliability.json) |
| False-alarm budget | The share of legitimate mail allowed to reach Suspicious (5%) or High risk (1%) per source; declared before validation is read; a policy choice |
| Saturating sum | A sum where each further item counts half as much as the one before, so a second finding is strong evidence and a tenth adds almost nothing |
| Wilson interval | A 95% confidence interval for a share that stays sensible for small counts and for shares near 0 |
| Deletion test | Remove the words an explanation names and see whether the classifier's probability drops; the baseline removes random words that occur as often |
| Stand-in classifier | A small fake with the classifier's interface and known behaviour, used to test code that needs a model |
| API key | A long random secret sent in the X-API-Key header; the server compares it in constant time and refuses to start with a weak one |
| Constant-time comparison | Comparing secrets so that the time taken does not depend on how many leading characters match (hmac.compare_digest); a plain == stops at the first difference |
| Rate limiting | Counting requests per client in a time window and answering 429 beyond the limit; the key function says who counts as one client (here the socket peer address) |
| ASGI middleware | A layer that sees every HTTP request before the routes do and every response after them (Express: app.use) |
| Dependency (FastAPI) | A function a route lists with Depends(); it runs before the route and can refuse the request by raising an error (Express: middleware for some routes only) |
| Pydantic | A library that checks the shape, types and limits of data against a class; Joi or Zod in JavaScript |
| CORS | A browser rule that decides whether a page on one origin may read answers from another; it protects the user, not the server; the design keeps it closed, and a marked switch opens it for testing |
| DNS rebinding | An attack in which a web page makes its own name point at 127.0.0.1 to reach a local server; the Host header allow-list stops it |
| Canary string | A made-up string sent in every part of a request to prove that it appears in no log line or error message |
| Mutation testing | Changing the code on purpose (breaking a control) and checking that a test fails; a test that never fails proves nothing |
| Same-origin proxy | The interface's own server forwards /api to the API and adds the key, so the browser talks to one origin and never holds the key |
| Content-Security-Policy | A response header that lists where a page may load scripts, styles and connections from; anything else is blocked even if an attacker managed to inject it |
| Text node | A piece of text in the page that the browser never parses as HTML; React draws every string this way unless told otherwise, which is why untrusted text cannot become markup |
| Code point | One Unicode character as Python counts it; JavaScript counts UTF-16 units, so an emoji is one code point but two units |
| AbortController | A browser object that cancels a running fetch; a new analysis cancels the previous request with it |
| Lock file (package-lock.json) | The exact version and checksum of every package npm installed, so every machine installs the same thing |

# 17. References

1.  Karki, B., Abri, F., Siami Namin, A., Jones, K. S. (2022). Using Transformers for Identification of Persuasion Principles in Phishing Emails. IEEE International Conference on Big Data, pp. 2841-2848.

2.  A Two-Stage Deep Learning Framework for AI-Driven Phishing Email Detection Based on Persuasion Principles (2025). MDPI Computers, 14(12):523.

3.  Pan, T., Yang, Q., Cole, A. J., Wilson, R., Woodard, D. (2026). Psychology of Phishing Emails: Quantifying Persuasion Principles and Simulating Detection with Large Language Models. Expert Systems with Applications.

4.  Valecha, R., Mandaokar, P., Rao, H. R. (2022). Phishing Email Detection Using Persuasion Cues. IEEE Transactions on Dependable and Secure Computing, 19(2):747-756.

5.  Aggarwal, S., Kumar, V., Sudarsan, S. D. (2014). Identification and Detection of Phishing Emails Using Natural Language Processing Techniques. Proceedings of the 7th International Conference on Security of Information and Networks (SIN '14), ACM, pp. 217-222.

6.  Mithun, P., Bartlett, G., Mirkovic, J., Freedman, M. (2024). Phishing Email Detection Using Inputs From Artificial Intelligence. arXiv:2405.12494.

7.  Cidon, A., Gavish, L., Bleier, I., Korshun, N., Schweighauser, M., Tsitkin, A. (2019). High Precision Detection of Business Email Compromise. USENIX Security Symposium.

8.  Ho, G., Cidon, A., Gavish, L., Schweighauser, M., Paxson, V., Savage, S., Voelker, G. M., Wagner, D. (2019). Detecting and Characterizing Lateral Phishing at Scale. USENIX Security Symposium.

9.  Ai, L. et al. (2024). Defending Against Social Engineering Attacks in the Age of LLMs (ConvoSentinel). arXiv:2406.12263.

10. Piskorski, J. et al. (2023). SemEval-2023 Task 3: Detecting the Category, the Framing, and the Persuasion Techniques in Online News in a Multi-lingual Setup. ACL.

11. Al-Subaiey, A., Al-Thani, M., Alam, N. A., Antora, K. F., Khandakar, A., Zaman, S. A. (2024). Novel Interpretable and Robust Web-based AI Platform for Phishing Email Detection. Computers and Electrical Engineering, 120:109625.

12. Cialdini, R. B. Influence: The Psychology of Persuasion.

13. Stajano, F., Wilson, P. (2011). Understanding Scam Victims: Seven Principles for Systems Security. Communications of the ACM, 54(3):70-75.

14. FBI Internet Crime Complaint Center (IC3). Internet Crime Reports 2023 and 2024.

15. Verizon. Data Breach Investigations Report (recent editions, including 2026).

16. Klimt, B., Yang, Y. (2004). The Enron Corpus: A New Dataset for Email Classification Research. ECML 2004.

17. Nazario, J. Phishing corpus (raw mbox files by year), monkey.org.

18. Apache SpamAssassin project. SpamAssassin public mail corpus.

19. rf-peixoto. phishing_pot: real phishing samples collected via honeypots. GitHub dataset repository, licence CC BY-NC 4.0; last public commit May 2026 (data used, no code).

20. Apache Software Foundation. Public mailing-list archives (lists.apache.org): users@tomcat.apache.org and users@kafka.apache.org.

21. Alam, N. A. Phishing Email Dataset ("Phish No More"). Kaggle.

22. Kucherawy, M. (2019). Message Header Field for Indicating Message Authentication Status. RFC 8601, IETF.

23. Ribeiro, M. T., Singh, S., Guestrin, C. (2016). "Why Should I Trust You?": Explaining the Predictions of Any Classifier. Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, pp. 1135-1144.

24. Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association, 22(158):209-212.

25. OWASP Foundation (2021). OWASP Top 10:2021. https://owasp.org/Top10/

26. OWASP Foundation (2023). OWASP API Security Top 10. https://owasp.org/API-Security/

27. Fielding, R., Nottingham, M., Reschke, J. (2022). HTTP Semantics. RFC 9110, IETF.

28. OWASP Foundation. Cross Site Scripting Prevention Cheat Sheet. OWASP Cheat Sheet Series. https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html

29. West, M. et al. Content Security Policy Level 3. W3C Working Draft. https://www.w3.org/TR/CSP3/
