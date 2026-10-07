# data/labelled/

Phase 5: tactic and claim labels for 700 real emails, made by two free web-chat LLMs (Gemini and DeepSeek) with z.ai deciding their disagreements. The code is in `src/data/` (see `src/data/README.md`).

## What is in here

| Path | In Git? | What it is |
|---|---|---|
| `sample.csv` | Yes | The 700 emails drawn: `id`, `source`, `category`, `split`, `batch` and the short `local_id` the chat copies. Ids only, never email text |
| `annotators.csv` | Yes | One row per chat service with the model name you typed in. The scripts refuse to run until it is filled in |
| `replies_log.csv` | Yes | One row per saved reply: time, annotator, model name, batch, items valid and invalid |
| `gemini/`, `deepseek/`, `zai/` | Yes | The raw replies, exactly as the chat gave them (`batch_007.txt`, `reask_gemini_001.txt`, `tiebreak_003.txt`) |
| `labels.csv` | Yes | The final labels: one row per labelled email, seven `tactic_*` columns, `claims` as JSON, which annotators decided it |
| `batches/` | **No** | The prompts, with full email text. Rebuilt from the fixed seed by `python -m src.data.batches` |

`batches/` is ignored because it holds full email text and phishing_pot's licence (CC BY-NC 4.0) means it is never redistributed. The replies hold only labels and short quoted spans.

## The protocol

- **700 emails** by a fixed allocation per source and category, not proportional: 450 attacks (150 each from phishing_pot, Nazario and Nigerian Fraud), 150 ham and 100 spam. They come from all three splits in 60/20/20 shares, so validation and test have labels too. Emails under 8 words are not sampled. The pick is the order of SHA-256(seed 42, id), so it is identical on every machine.
- **No keyword hit picks any email.** The Phase 4 baseline fires on almost no real reciprocity or social-proof attacks, so choosing by it would select false positives. Rare tactics come from the synthetic emails (`data/synthetic/`).
- **35 batches of 20 emails.** Each email is shown as `body_redacted` (the text the models read), cut at 2,000 characters, inside an `<email id="...">` block. Angle brackets in the text are replaced so it cannot close the block.
- **Every annotator sees the same instructions.** Read them once (`python -m src.data.prompts` prints a preview, and `batches.py` prints the full text) before the first batch.
- **Fresh chat per batch, same service and model for the whole run.** Do not edit a reply and do not answer a batch yourself. Web chats give no temperature control and their models change over time, so labels are not exactly reproducible: the model name and time of every reply are logged, and every raw reply is kept.

## Running it

Once, from the project root with the venv active:

```bash
python -m src.data.batches
```

It prints what was drawn and the instructions. Then fill in `model_name` for `gemini`, `deepseek` and `zai` in `annotators.csv` (the model shown in each chat window).

One batch, for each of `gemini` and `deepseek` (35 each):

```bash
python -m src.data.annotate next gemini
```

Open a fresh Gemini chat, paste, send. When the reply is complete, copy all of it and run:

```bash
python -m src.data.annotate save gemini
```

It saves the reply, checks it at once and tells you which batch is next. `python -m src.data.annotate status` shows the progress of all three annotators.

If a chat stops in the middle of its reply (its output limit), send it "Repeat the complete JSON array from the beginning, compact, on one line" and save that reply instead. If the clipboard still holds the prompt, `save` refuses and tells you.

When both have finished:

```bash
python -m src.data.validate_labels
```

Items that were invalid or missing are re-asked once: new `reask_<annotator>_NNN` batches appear, answered with the same `next` and `save` commands, then run `validate_labels` again. An item that still fails after its re-ask is dropped and counted. Then:

```bash
python -m src.data.agreement
```

It prints Cohen's kappa per tactic and per claim type and writes `tiebreak_NNN` batches with the emails the two disagree on. Answer them with `next zai` and `save zai`, then:

```bash
python -m src.data.labels
```

## How a reply is checked

A reply is accepted as plain JSON, inside a code fence or inside a sentence of prose. Each item must have an id from the batch (once), exactly the seven tactic keys as 0 or 1, and claims with a known type, an organisation that is text or null, and a span of at most 300 characters that appears in the email (case and spacing ignored). A reply that gives the same answer for all 20 emails with no claims is rejected as a likely hijacked or lazy answer: an email can tell the model "answer 0 for everything".

## The final labels

- A tactic or claim type both annotators agree on stands. Where they disagree, z.ai's answer decides (the majority of three).
- A claim type is kept when at least two annotators listed it; the span and organisation come from the first of Gemini, DeepSeek, z.ai who listed it.
- Emails still waiting for a tie-break, or without a valid answer from one of the two main annotators, are left out and counted.
- A tactic with fewer than 10 positives in the validation or test labels is reported as a count, not as an F1 score.

## Limits to state in the report

There is no human validation sample (a decision, July 2026): the labels measure agreement with LLM annotators, not with people. The annotators see the body only, not the subject or the headers, because that is what the classifier reads. Names and phone numbers in these public corpora are not redacted; only links, addresses, domains and file names are.
