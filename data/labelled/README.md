# data/labelled/

Phase 5: tactic and claim labels for 700 real emails, made by two different LLMs (annotator_1 and annotator_2) with a third model (the tie-breaker) deciding their disagreements. All three call Google's Gemini API through the one free key, each with its own model id; pasting batches into chat windows by hand is the fallback. The code is in `src/data/` (see `src/data/README.md`).

## What is in here

| Path | In Git? | What it is |
|---|---|---|
| `sample.csv` | Yes | The 700 emails drawn: `id`, `source`, `category`, `split`, `batch` and the short `local_id` the chat copies. Ids only, never email text |
| `annotators.csv` | Yes | One row per annotator with the model name (filled in by `auto`, or by you when working by hand). The scripts refuse to run by hand until it is filled in |
| `replies_log.csv` | Yes | One row per saved reply: time, annotator, model name, batch, items valid and invalid |
| `annotator_1/`, `annotator_2/`, `tiebreaker/` | Yes | The raw replies, exactly as the model gave them (`batch_007.txt`, `reask_annotator_1_001.txt`, `tiebreak_003.txt`) |
| `labels.csv` | Yes | The final labels: one row per labelled email, seven `tactic_*` columns, `claims` as JSON, which annotators decided it |
| `batches/` | **No** | The prompts, with full email text. Rebuilt from the fixed seed by `python -m src.data.batches` |

`batches/` is ignored because it holds full email text and phishing_pot's licence (CC BY-NC 4.0) means it is never redistributed. The replies hold only labels and short quoted spans.

## The protocol

- **700 emails** by a fixed allocation per source and category, not proportional: 450 attacks (150 each from phishing_pot, Nazario and Nigerian Fraud), 150 ham and 100 spam. They come from all three splits in 60/20/20 shares, so validation and test have labels too. Emails under 8 words are not sampled. The pick is the order of SHA-256(seed 42, id), so it is identical on every machine.
- **No keyword hit picks any email.** The Phase 4 baseline fires on almost no real reciprocity or social-proof attacks, so choosing by it would select false positives. Rare tactics come from the synthetic emails (`data/synthetic/`).
- **35 batches of 20 emails.** Each email is shown as `body_redacted` (the text the models read), cut at 2,000 characters, inside an `<email id="...">` block. Angle brackets in the text are replaced so it cannot close the block.
- **Every annotator sees the same instructions.** Read them once (`python -m src.data.prompts` prints a preview, and `batches.py` prints the full text) before the first batch.
- **A fresh request per batch, one model per annotator for the whole run.** Do not edit a reply and do not answer a batch yourself. By API the temperature is fixed at 0; in a chat window it cannot be set. Either way the providers update their models over time, so labels are not exactly reproducible: the model name and time of every reply are logged, and every raw reply is kept.

## Running it

There are two ways to get replies, with identical files and checks. Automatic is recommended: it is one command per annotator instead of about 35 pastes.

### Setup (once)

```bash
python -m src.data.batches
```

It prints what was drawn and the instructions. For automatic mode you need one free key: Google AI Studio (aistudio.google.com), "Get API key". Put it in `.env`, which Git ignores:

```
GEMINI_API_KEY=your-key
```

Each of the three roles needs its own model id, and they must be different. List the ids your key can use:

```bash
python -m src.data.annotate check annotator_1
```

The free key gives access to the fast "Flash" class models, so pick three different ids with `flash` in the name (a different generation or size counts as different) and add them to `.env`, using the ids exactly as printed:

```
ANNOTATOR_1_MODEL=first-id
ANNOTATOR_2_MODEL=second-id
TIEBREAKER_MODEL=third-id
```

Then check each role:

```bash
python -m src.data.annotate check annotator_1
python -m src.data.annotate check annotator_2
python -m src.data.annotate check tiebreaker
```

Each is one tiny real request and says OK, or what is wrong (a missing key, a wrong model id). `auto` refuses to run two annotators on the same model: their agreement would measure nothing.

**An honest limit.** The ideal is annotators from different companies, so their mistakes are independent. DeepSeek, z.ai and Mistral do not offer a free API, and Groq's free token limits are too small for 20-email batches, so all three roles are Gemini-family models. Their agreement is therefore agreement between models of one family, and the labels are one family's judgement. The report says this. If you later get a key for another service, set `ANNOTATOR_2_API_KEY`, `ANNOTATOR_2_BASE_URL` and `ANNOTATOR_2_MODEL` (the same for the others) and rerun from the start.

The emails are public-corpus text with links, addresses and domains already replaced. A free tier may let Google use the inputs to improve its products, so read the terms; the report states it.

### Automatic (recommended)

First two batches only, to see it work:

```bash
python -m src.data.annotate auto annotator_1 --limit 2
```

If both say "20 of 20 items valid" or close, run it for all, then for the second annotator:

```bash
python -m src.data.annotate auto annotator_1
python -m src.data.annotate auto annotator_2
```

It runs every pending batch at temperature 0 (the model's most likely answer, which chat windows cannot give), saves each reply exactly as received, checks it, logs it, and writes the model id plus "(API, temperature 0)" into `annotators.csv`. The free tier has rate limits: the script waits and retries on its own, and stops with a clear message if a daily limit is reached; run the same command the next day and it continues from the next unanswered batch. Stop with Ctrl+C and start again whenever you like. One annotator must be one model: if replies from another model exist (for example from a chat window), `auto` refuses and tells you which file to delete.

### By hand (the chat window)

```bash
python -m src.data.annotate next annotator_1
```

Fill in `model_name` in `annotators.csv` first (the model shown in the chat window). Open a fresh chat, paste, send. When the reply is complete, copy all of it and run:

```bash
python -m src.data.annotate save annotator_1
```

It saves the reply, checks it at once and tells you which batch is next. Always run `next` again before the next `save`: `save` files whatever is on the clipboard under the next unanswered batch, and it refuses a reply that answers a different batch or repeats one already saved. If a chat stops in the middle of its reply (its output limit), send it "Repeat the complete JSON array from the beginning, compact, on one line" and save that reply instead.

`python -m src.data.annotate status` shows the progress of all three annotators in either mode.

### After the main batches (both modes)

```bash
python -m src.data.validate_labels
```

Items that were invalid or missing are re-asked once: new `reask_<annotator>_NNN` batches appear, answered with the same `auto` (or `next` and `save`) command, then run `validate_labels` again. An item that still fails after its re-ask is dropped and counted. Then:

```bash
python -m src.data.agreement
```

It prints Cohen's kappa per tactic and per claim type and writes `tiebreak_NNN` batches with the emails the two disagree on. Answer them with `auto tiebreaker`, then run `validate_labels` and `agreement` once more and finish with:

```bash
python -m src.data.labels
```

## How a reply is checked

A reply is accepted as plain JSON, inside a code fence or inside a sentence of prose. Each item must have an id from the batch (once), exactly the seven tactic keys as 0 or 1, and claims with a known type, an organisation that is text or null, and a span of at most 300 characters whose words appear in a row in the email (case, spacing and punctuation are ignored, so "don't" matches the tokenised "don ' t"). A reply that gives the same answer for all 20 emails with no claims is rejected as a likely hijacked or lazy answer: an email can tell the model "answer 0 for everything".

## The final labels

- A tactic or claim type both annotators agree on stands. Where they disagree, the tie-breaker's answer decides (the majority of three).
- A claim type is kept when at least two annotators listed it; the span and organisation come from the first of annotator 1, annotator 2, the tie-breaker who listed it.
- Emails still waiting for a tie-break, or without a valid answer from one of the two main annotators, are left out and counted.
- A tactic with fewer than 10 positives in the validation or test labels is reported as a count, not as an F1 score.

## Limits to state in the report

There is no human validation sample (a decision, July 2026): the labels measure agreement with LLM annotators, not with people. The annotators see the body only, not the subject or the headers, because that is what the classifier reads. Names and phone numbers in these public corpora are not redacted; only links, addresses, domains and file names are.
