# data/threads/

Phase 9: the **thread-hijack benchmark** that tests the thread verifier (N2). Real conversations (raw Enron and the Apache mailing lists) are cut before one message and an attacker's message is put in its place. Nobody has labelled real hijacks, so they are made; the base threads are real and the injected messages are synthetic, and the report says so.

The rebuilt threads themselves (full email text) are `data/processed/threads.parquet` and are never committed. This folder holds only what is safe and small: the plan, the synthetic texts, the raw replies and the manifest.

```bash
python -m src.thread.build --count                          # first: find the threads
python -m src.data.hijack_benchmark build                   # plan ~300 Enron and ~200 Apache base threads, write the prompts (about 125 of them, 4 threads each)
python -m src.data.hijack_benchmark auto annotator_1        # free Gemini API, as in Phase 5; stop with Ctrl+C and run again to continue
python -m src.data.hijack_benchmark collect                 # check the replies, write re-ask prompts for failures, write injections.csv and cases.csv
python -m src.data.hijack_benchmark auto annotator_1        # answers the re-ask prompts (once), then collect again
```

## Files

| File | Committed | What it is |
|---|---|---|
| `plan.csv` | yes | One row per base thread: id, source, split, injection position, goal, two tactics (no email text) |
| `injections.csv` | yes | The synthetic texts per thread: the attack reply, the benign reply, the fabricated quotation, the model that wrote them |
| `cases.csv` | yes | The benchmark manifest: one row per case (thread, split, variant, label, position) |
| `replies/` | yes | The raw replies of the API, untouched; `replies_log.csv` and `generator.csv` say which model wrote them and when |
| `prompts/` | **no** | The prompts hold redacted excerpts of real emails (the last three messages before the injection point); rebuilt by `build` |

## The five variants of a case

For each base thread, the real messages before message *k* are the history, and the candidate at *k* is:

| Variant | Candidate | Label | What it isolates |
|---|---|---|---|
| `neg_real` | the **real** next reply | 0 | false alarms on real mail |
| `neg_synth` | the benign text, the sender's real details, genuine IDs and quotation | 0 | the style control |
| `A` takeover | the attack text from the real sender with the same server, mail program and IDs | 1 | **content signals only** (tactic onset, request drift): the attacker is inside the account, so the headers are the real ones and N3 sees nothing new |
| `B` swap (Apache only) | the **benign** text from a look-alike of the sender's domain, a new server and mail program | 1 | **sending-path signals only** |
| `C` forged | the **benign** text with a fabricated quotation and, on Apache, Message-IDs that do not exist | 1 | **thread-integrity signals only** |

`B` and `C` use the benign text on purpose: the same words appear as a negative (`neg_synth`) and as a positive, so a detector cannot win by recognising the generator's style (master document Section 8.5). Each signal is tested in its own variant; an attacker who changes everything at once is easier to catch than any single one, and the report says so.

## How the injected texts are made

One API call per four threads (Gemini free tier, temperature 0.8, `src/data/llm_api.py`). For each thread the model writes an attack reply (it continues the topic, then drifts into a request: new bank details, a login, gift cards or an urgent payment, with two of authority/urgency/scarcity/secrecy, each quoted from the text), a benign reply, and a few sentences that read like an earlier message of the thread but are not one. The code checks every reply: word counts, no links, every quoted cue and the request cue must appear in the text, the benign text and the quotation must trip nothing in the frozen keyword baseline, the quotation must not copy the real history. A failing thread is re-asked once, then dropped (`results/hijack_generation.csv`).

The model never writes bank details: it puts the token `{{BANK}}` in the text and `hijack_benchmark.py` inserts a valid fictional IBAN (check digits computed), because an invented IBAN almost never passes the check and the bank-detail signal could not fire.

## Splits

By thread (70/15/15 from the SHA-256 of seed 42 and the thread id), so one thread never stands in two splits. A thread with a message the tactic classifier trained on is kept out of validation and test (Apache messages carry their ids; raw Enron cannot be matched to the Kaggle copy, and only 80 of the 29,119 Kaggle Enron emails were labelled, about 60% of them in the training split).

## Limits the report states

- The injected texts and headers are synthetic and written from the same fields the signals read, so header variants test that the rules work as defined, not how real attackers behave. The false alarms come from the real threads and `neg_real`.
- The later real messages of a thread are dropped after the candidate: they quote the real message, not the injected one.
- The prompts leave the machine as redacted excerpts of public corpora (Enron and the Apache lists); a free API tier may keep them (`src/data/llm_api.py`).
- Only one model family writes the injected texts.
- `neg_synth` messages quote the previous message by construction, so they cannot show quote false alarms; `neg_real` does.
