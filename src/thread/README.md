# src/thread/

Phase 9: **thread consistency verification (N2)**. This folder rebuilds real conversations and measures a message against the messages before it; `src/verifiers/thread_verifier.py` turns the measurements into ledger rows; `src/data/hijack_benchmark.py` makes the hijacked threads that test it.

Why it exists: a hijacked account sends through the real provider with the real credentials, so SPF, DKIM and DMARC pass for the real domain and every Phase 8 rule says "consistent". What gives the attacker away is not the message but the **change**: the thread was about a project and now asks for a new bank account; the same address suddenly writes from another server; the "earlier conversation" it quotes never happened. N3 catches the impersonator; N2 catches the attacker who is already inside the account.

```bash
python -m src.thread.selftest                     # hand-made threads and crafted input, no data and no model needed (87 PASS lines)
python -m src.thread.build --count                # find the threads (Apache from Message-IDs, Enron from subjects) and print what was found
python -m src.thread.build --train-only            # also compute tactic probabilities and claims and score the TRAIN threads: false alarms on real threads
python -m src.thread.build --train-only --show-rules tv_quote_mismatch,tv_who_other_domain
                                                  # also print up to 25 examples of each named rule (never saved)
python -m src.thread.build --train-only --reuse   # score again after a rule change without rebuilding the threads (reads data/processed/threads.parquet)
python -m src.thread.build                        # the final run of a frozen version: also scores the validation threads, once
python -m src.data.hijack_benchmark build         # plan the base threads and write the prompts
python -m src.data.hijack_benchmark auto annotator_1   # send the prompts to the free Gemini API (resumes where it stopped)
python -m src.data.hijack_benchmark collect       # check the replies, write the benchmark
python -m src.thread.evaluate --train-only        # development scores on the train threads
python -m src.thread.evaluate                     # the final run: also scores validation, once
```

```python
from src.verifiers.thread_verifier import scan_thread, verify_thread_message

# messages: a list of dictionaries in time order (the fields are listed in signals.py)
rows = verify_thread_message(messages, 3)         # the ledger rows for the 4th message, judged against the first three
result = scan_thread(messages)                    # {"flip_index": 3, "messages": [{"index", "worst", "rules", "rows"}, ...]}
```

## Files

| File | Job |
|---|---|
| `signals.py` | The four measurements as plain functions (no model, no I/O): `tactic_onset`, `bank_drift` and `request_novelty`, `sender_identity` and `path_drift`, `id_integrity` and `quote_integrity`; word and shingle helpers. Every fixed number is a constant at the top |
| `builder.py` | Rebuilds threads: `apache_threads` (Message-ID, In-Reply-To, References), `enron_candidates` and `enron_threads` (normalised subject, time runs, shared participants), `split_message` (new text, quotation and whole text), `split_of_thread` |
| `features.py` | Computes and caches the tactic probabilities (Phase 6 classifier) and claims (Phase 7 extractor) of every thread message |
| `build.py` | Finds the threads, writes `data/processed/threads.parquet`, scores real threads for false alarms, writes `results/thread_*.csv` |
| `selftest.py` | 87 checks: hand-made threads and the rules they must give, scan, builder and API checks (some guard mistakes the real runs showed), 9 crafted hostile inputs |
| `evaluate.py` | Scores N2 and the Phase 8 verifiers on the benchmark; bootstrap intervals over threads; `results/thread_scores.csv`, `results/hijack_checks.csv` |

## The four signals (master document Section 4.3)

| Signal | What is compared | Rules (severity) |
|---|---|---|
| **Tactic onset** | the message's tactic probabilities against every earlier message, for authority, urgency, scarcity and secrecy (the only tactics with enough real positives in Phase 6); needs two earlier messages | a tactic reaches its Phase 6 threshold here, in no earlier message, and is at least 0.40 above the average of the earlier messages (version 0.2): `tv_onset_one` (medium); two or more at once: `tv_onset_many` (high) |
| **Request drift** | the bank details of the message against all earlier text of the thread (a set difference), and request types against earlier requests | `tv_bank_changed` (high: a different detail of the same kind), `tv_bank_new` (medium), `tv_req_credential_new`, `tv_req_gift_card_new`, `tv_req_change_new` (medium), `tv_req_payment_new`, `tv_req_data_new` (low) |
| **Sending-path drift** | the sender against the earlier senders: same address, or the name of an earlier sender at another domain; and for the same address, the network of the first public IP of the Received chain (the first three numbers; version 0.2) and the mail program (version dropped) | `tv_who_lookalike` (high), `tv_who_suffix` (medium), `tv_who_other_domain` (low); `tv_path_origin_mailer` (medium), `tv_path_origin`, `tv_path_mailer` (low) |
| **Thread integrity** | In-Reply-To and References against the Message-IDs of the thread; the quotation (lines marked `>`, or everything after an Outlook-style marker) against the WHOLE text of the earlier messages (5-word shingles); forwards are not checked | `tv_int_ids_unknown` (medium), `tv_int_parent_missing` (low); `tv_quote_mismatch` (high: a quotation of 20 words or more where under 30% of its shingles occur in the earlier messages); `tv_quote_forward` (not checkable) |
| *Style drift* | optional in the master document, dropped first (Section 12.4): not built | |

Plus `tv_prior_*` for `prior_relationship` claims ("as we discussed on the call": did this sender take part earlier in the thread? the strongest answer is a low contradiction, because a call outside the thread cannot be disproved) and `tv_single_*` for single-email mode (a "Re:" with quoted history but no reply headers: low, and `build.py` prints how often real replies lack them).

Three values, as in Phase 8: contradiction (high, medium or low), consistent, or not checkable. Missing evidence is never "no contradiction": raw Enron has no Message-IDs in replies, so the ID rule says `tv_int_no_ids` (not checkable) there, and the quote rule still runs.

**The flip point.** `scan_thread` judges message 1, 2, 3 ... each against its own past; the thread flipped at the first message with a medium or high contradiction. That is change-point detection in its simplest form. Message 0 has no past.

## How a thread is found

- **Apache** keeps the headers mail programs use: two messages join a group when one names the other's Message-ID in In-Reply-To or References (Phase 3 stores References as one space-separated string, which `decode_references` reads) (union-find, so cycles and missing parents are harmless). Messages are ordered by date.
- **Raw Enron** has no In-Reply-To, References, Received or X-Mailer (0%, `results/header_coverage.csv`), so threads are guessed the way old mail clients did: the subject without "Re:"/"Fw:" prefixes, split into runs (a gap of more than 14 days starts a new run), messages in a run join when they share a participant. The same message sits in several folders (inbox, sent, all_documents) and the copies carry different Message-IDs in this dump, so a copy is recognised by the same date, sender and subject and removed. Candidates are read in hash order, 1,000 at a time, until the wanted number of threads (default 1,200) pass the rules.
- A thread needs 3 to 50 messages and at least two senders (Enron: at least two "Re:" subjects too). `results/thread_counts.csv` says how many groups were dropped and why.
- The thread split is by thread (70/15/15 from the SHA-256 of seed 42 and the thread id), so no thread stands in two splits.

## What the results can and cannot say

- The real threads are unmodified, so every medium or high contradiction on them is a **false alarm** (`results/thread_signal_rates.csv`). The benchmark (`data/threads/README.md`) says how many hijacks the same rules catch.
- Injected messages and their headers are **synthetic** and written from the same fields the signals read. The detection rates say the rules do what they are defined to do against this construction, not how real attackers behave. The same benign text appears as a negative and as a positive, so a detector cannot win by recognising the generator's style.
- A hijacker with mailbox access can copy real Message-IDs, sending details and wording. Then only the content signals can catch the message (variant A), and if the attacker also keeps the content calm, nothing here can. "Consistent" means "nothing in the thread contradicts this message", never "safe".
- Enron has no sending-path data and no reply IDs, so Enron threads test the content signals and the quote check; Apache threads test all four. The report states the split.
- Rules were written from the definitions and revised only after reading TRAIN results (`THREAD_VERSION_LOG` in `thread_verifier.py`: version 0.2 changed the quotation, the tactic jump and the IP network after the first real train run); the validation threads are scored once for the frozen version; the test threads are built but never scored before Phase 13.
- The tactic probabilities come from a model trained on LLM labels from one model family, and the claims from a rule-based extractor (recall 0.13 on `affiliation_internal`): a missing claim is never evidence of honesty.

## Security

Thread input is attacker-written. At most 50 messages are examined; each text is cut at 60,000 characters and 5,000 words; at most 100 Message-IDs are read per message; a Subject is cut at 300 characters before its prefixes are removed; files are read up to 300,000 bytes; no regular expression runs over email text (words are found in one pass over the characters, quotations are compared as sets of word runs); IDs are only looked up in a set, never followed, so a cyclic In-Reply-To chain cannot loop. Reasons are built from fixed templates and validated values only (`clean_domain`, masked bank details); `check_row` rejects markup. `selftest.py` feeds 50 messages of 200,000 characters, 100 References, 10,000 lines of `>`, 100,000 "Re:" prefixes, a cyclic chain, floods of `@` and a 200-message thread; each finishes in under two seconds.
