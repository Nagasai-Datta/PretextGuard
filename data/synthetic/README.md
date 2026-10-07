# data/synthetic/

Phase 5: 240 synthetic pretexting emails with 240 matched benign twins (480 emails), written by a free-tier model (through its API, or a chat window) from fixed prompt templates. The code is `src/data/synthetic.py`.

## Why it exists

The real corpora have almost no modern, link-free pretexting, and almost no reciprocity or social proof: on the Phase 4 train split the keyword baseline fires on 0.18% of phishing for reciprocity and 0.14% for social proof, and most of those hits are on ordinary mail. Synthetic emails fill that gap with labels known by construction. They are always reported separately from real-email results, because an LLM-written attack beside a human-written legitimate email lets a model learn "LLM or not" instead of manipulation.

## The style-confound control

Every attack has a **benign twin** from the same template: same kind of sender, same situation, same claim types, no manipulation tactic. The twin is checked: it must not make the frozen Phase 4 keyword baseline fire on any tactic, and its body must differ from the attack's. Attack and twin always sit in the same split (the split is by pair), so a pair never straddles the train/test line.

## What is in here

| Path | What it is |
|---|---|
| `plan.csv` | What each of the 240 pairs was told to be: scenario, industry, tone, length, the attack's tactics and claims, the twin's claims, the split |
| `prompts/synth_NNN.txt` | The 30 prompts, 8 pairs each (and `synth_reask_NNN.txt` for pairs that failed a check) |
| `replies/synth_NNN.txt` | The raw replies, exactly as the chat gave them |
| `generator.csv` | Which chat service and model wrote them: fill in both columns before the first prompt |
| `replies_log.csv` | One row per saved reply: time, model, prompt, pairs asked, pairs valid |
| `synthetic.csv` | The loaded emails, with `body_redacted`, seven `tactic_*` label columns and `claims` as JSON, `label_source = synthetic` |

Everything here is committed: it is synthetic text, so there is nothing to protect.

## The plan

- **240 pairs over 12 situations**, for example an executive asking for a wire transfer, a gift-card request, a payroll bank-detail change, a supplier's new bank account, an IT help desk asking for a password, a reply inside a real project thread that suddenly changes the payment account.
- **Each tactic is the primary tactic of a seventh of the attacks**, and each attack uses two or three tactics, so every tactic has plenty of positives. Real BEC mostly uses authority, urgency and secrecy; the synthetic set deliberately over-represents the rare tactics, and the report says so.
- The attack is told to use exactly its tactics and none of the other seven; the twin none.

## Running it

From the project root with the venv active:

```bash
python -m src.data.synthetic build
```

**Automatic (recommended).** With the key and model ids in `.env` (see `data/labelled/README.md`), one command sends all 30 prompts to the model's API and saves the replies. It writes the service and model into `generator.csv` for you. Any of the three roles can write them; `annotator_1` is the example. Try two first:

```bash
python -m src.data.synthetic auto annotator_1 --limit 2
python -m src.data.synthetic auto annotator_1
```

The temperature is 0.8, a little variety between emails. Stop and start again whenever you like.

**By hand.** Fill in `chat_service` and `model_name` in `generator.csv`. Then, for each of the 30 prompts:

```bash
python -m src.data.synthetic next
```

Open a fresh chat, paste, send, copy the whole reply, then:

```bash
python -m src.data.synthetic save
```

**Either way**, when all prompts are answered:

```bash
python -m src.data.synthetic collect
```

`collect` writes `synth_reask_NNN` prompts for pairs that failed a check (answer them with `auto` or with `next` and `save`, then run `collect` again) and `synthetic.csv` plus `results/synthetic_counts.csv`. A pair that fails again after its re-ask is dropped and counted.

## How a reply is checked

"Labels known from the prompt" is only true if the chat did what it was told, so for every pair:

- the attack must give, word for word, the phrase that carries each required tactic (`tactic_cues`), and each phrase must appear in the body;
- every required claim must be listed with a span that appears in the body (the same rule as for annotators);
- no email may contain a link (`http`, `www.`, `://`);
- bodies are 20 to 260 words;
- the twin must not trip the keyword baseline and must not equal the attack.

## Limits to state in the report

Labels come from the prompt and are confirmed by quoted cues, not by an independent annotator. The emails are the writing style of one or two LLMs. They carry no real headers: synthetic headers, where Phase 8 and 9 need them, are generated separately and disclosed.
