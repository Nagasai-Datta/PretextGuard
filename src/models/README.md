# src/models/

Phase 6: the DistilBERT tactic classifier. It reads an email body (`body_redacted`) and gives seven independent probabilities, one per manipulation tactic: authority, urgency, scarcity, reciprocity, social proof, liking and secrecy. It is trained on Colab's free GPU and used on the Mac's CPU. It is what the keyword baseline (Phase 4) has to be beaten by.

```bash
python -m src.models.dataset     # Mac, before training: build the one file that goes to Colab (train and validation rows only)
                                 # ... run notebooks/phase6_tactic_classifier.ipynb on Colab (see notebooks/README.md) ...
python -m src.models.validate    # Mac, after training: score the model on validation, run the PASS/FAIL checks
python -m src.models.predict "This is the CFO. Wire it today and tell no one."    # try the model on one text
```

## Files

| File | Runs on | Job |
|---|---|---|
| `dataset.py` | Mac | Builds `data/processed/tactic_data.parquet` (train and validation rows, text and seven labels), checks it, and holds the helpers the other files share (`model_text`, `training_rows`, `validation_rows`, `labels_of`, `check_table`) |
| `train.py` | Colab | The training loop: two conditions, three seeds each, early stopping, thresholds, saving the model and its record |
| `predict.py` | Mac, Colab | `TacticClassifier` (load once, `predict(body)`), `predict_probs` (batches), `load_tactic_model`; offline and safetensors only |
| `validate.py` | Mac | Loads the trained model on the CPU, scores it and the baselines on validation, writes the scores and the checks |

`src/eval/metrics.py` (precision, recall, F1, threshold tuning, written by hand and cross-checked against scikit-learn) is shared with Phase 13. `dataset.py` never imports PyTorch, so the table can be built before PyTorch is installed.

## The data

`python -m src.models.dataset` joins three things into one table with the columns `id, origin, group, split, text` and the seven `tactic_*` labels:

| Part | Where from | Rows used |
|---|---|---|
| Real emails | `data/labelled/labels.csv` for the labels, `data/processed/cleaned.parquet` for the text | 413 train, 137 validation |
| Synthetic emails | `data/synthetic/synthetic.csv` (attack and benign-twin pairs) | 306 train, 76 validation |

- **No test rows.** The file holds the train and validation splits only. The test emails and their labels never reach the training code; the test labels are used once, in Phase 13. `train.py` refuses a table that holds a test row.
- **The text is what the annotators saw:** `body_redacted` cut at 2,000 characters (`prepare_text` in `src/data/label_schema.py`), links, addresses and domains already replaced by placeholders (N1). The `[TRUNCATED]` note is removed: it only marks long emails and would be a shortcut the model could learn instead of the tactic. DistilBERT reads at most 512 word pieces, which 2,000 characters of English almost always fit in.
- **Uncased model.** The Kaggle Enron and Ling emails are stored lowercase and pre-tokenised, so the model is `distilbert-base-uncased` (a cased model would see two different alphabets).
- **Checks** (printed, and saved in `tactic_checks.csv` later): no test rows, ids unique, no empty text, labels 0 or 1, the real positives per split and tactic equal the Phase 5 counts in `results/label_counts.csv`, the synthetic ones equal `results/synthetic_counts.csv`, every benign twin has no tactic, every synthetic attack has at least one. A failed check stops the build.
- `results/tactic_data_counts.csv` holds the counts per origin, split and tactic (never email text). The upload file holds full email text: it is in `data/processed/` (ignored by Git) and must never be committed.

## Two conditions, three seeds

| Condition | Trains on | Why |
|---|---|---|
| `mix` | the 413 real and the 306 synthetic train emails | The main model. Reciprocity, social proof and liking have 5, 2 and 11 real train positives, so they learn mostly from synthetic text |
| `real_only` | the 413 real train emails | A comparison, to measure whether the synthetic emails help. Its weights are not kept, only its validation probabilities and thresholds |

Each condition is trained with seeds 42, 43 and 44 and all three are reported. A seed fixes the order of the batches and the starting values of the new layer, so three seeds show how much the result depends on luck. GPU arithmetic is not bit-exact between runs, so "the same seed" gives similar results, not identical ones.

## How one training run works

1. **Tokenise.** Each email becomes up to 512 word-piece numbers. A batch is padded only to its longest email (dynamic padding), and a mask tells the model which positions are padding.
2. **Forward pass.** DistilBERT (6 layers, 66 million learned numbers, already trained to guess hidden words on a huge amount of English) turns the tokens into one vector; a small new layer turns that into seven numbers (logits), one per tactic.
3. **Loss.** Binary cross-entropy on each tactic separately (the model answers seven yes/no questions, not one multiple-choice question, so the outputs are seven independent sigmoids, not a softmax). `pos_weight` makes one positive example count like many negatives: per tactic, negatives divided by positives, at most 10 (for example, authority 4.75, urgency 3.02, reciprocity 10).
4. **Backward pass and step.** Autograd works out how each weight should change; AdamW changes every weight a little. Settings: learning rate 3e-5 with a 10% warm-up then a straight-line decay, weight decay 0.01, batch size 16, gradient clipping at 1.0.
5. **After every epoch** (one pass over the training emails) the model predicts all validation emails. The epoch is scored by macro-F1 over authority, urgency, scarcity and secrecy on the **real** validation emails at threshold 0.5; ties go to the lower validation loss. **Early stopping:** training stops after 3 epochs without improvement (at most 8 epochs), and the best epoch's weights are kept. This is the guard against overfitting: with about 700 emails the model could memorise them, and then the training loss keeps falling while the validation loss rises. Both are logged every epoch.
6. **Choose the seed.** The seed with the best score becomes the model.
7. **Thresholds.** A tactic is "fired" when its probability reaches its threshold. 0.5 is only right for balanced data, so the four main tactics get a threshold tuned on the real validation emails (grid 0.05 to 0.95 in steps of 0.05, ties go to the one nearest 0.5). The three rare tactics (reciprocity, social proof, liking) stay at 0.5, because tuning on fewer than 10 positives would only fit noise.

**Why only four tactics choose the epoch, seed and thresholds:** a tactic with fewer than 10 positives in the real validation or test emails is reported as counts, never as an F1 (`results/label_counts.csv`, the same rule as `src/data/labels.py`). Authority (21 validation positives), urgency (39), scarcity (27) and secrecy (12) are the four that can get an F1.

**Optimism.** Validation picked the epoch, the seed and the thresholds, so the validation scores are a little better than the model deserves. The honest number is the test split, used once, in Phase 13.

## What Colab produces and where it goes

`train.py` writes into one output folder (the notebook zips it):

| Output | Goes to | Content |
|---|---|---|
| `tactic_model/` | `artifacts/tactic_model/` (ignored by Git) | `model.safetensors` (the weights), `config.json` (names the seven outputs in order), tokenizer files, `thresholds.json` |
| `tactic_training_log.csv` | `results/` | Per condition, seed and epoch: training loss, validation loss, validation macro-F1, whether it was the chosen epoch |
| `tactic_seed_summary.csv` | `results/` | Per condition and seed: best epoch, epochs run, score, whether the seed was chosen |
| `tactic_val_probs.csv` | `results/` | The chosen model's probability for every tactic on every validation email (ids and numbers only) |
| `tactic_run_info.json` | `results/` | Settings, `pos_weight`, thresholds, library versions, GPU name, data checksum, code commit, base-model revision |

## The Mac validation (`validate.py`)

It loads `artifacts/tactic_model/` on the CPU with no network, predicts every validation email, and writes:

- `results/tactic_validation_scores.csv`: per validation set (real, synthetic), system and tactic: items, positives, predicted, tp, fp, fn, precision, recall, F1 and the threshold used. Systems: `distilbert`, `distilbert_real_only`, `keyword_default` (every tactic fires at score 1.0) and `keyword_tuned` (one threshold per main tactic tuned on the same real validation emails, so the comparison with the tuned DistilBERT is fair). The final baseline comparison is Phase 13, on the test split.
- `results/tactic_checks.csv`: PASS/FAIL checks: the data checks above; the upload table is the very file Colab trained on (SHA-256); only `model.safetensors`, no pickle-style files; thresholds valid and the rare three at 0.5; probabilities finite and between 0 and 1; **the Mac's CPU reproduces Colab's probabilities to within 0.001**; the same `transformers` version on both sides; each main tactic flags some but not all emails; the training loss fell in every run. A few rows are "info" only: the torch versions, and the training and validation loss of each chosen epoch (to watch for overfitting).

How to read the scores:

- **Real and synthetic are always apart.** Synthetic emails are one LLM's writing and carry its style, so their scores say little about real mail.
- **Counts, not F1,** for any tactic with fewer than 10 positives in that set: you see tp, fp and fn.
- **The baseline's synthetic precision is meaningless:** a twin that made the keyword baseline fire was dropped when the synthetic emails were made, so its false-positive rate there is zero by construction. The baseline therefore gets recall only on synthetic emails.
- **Every F1 is agreement with LLM labels from one model family** (Phase 5), not with people.

## Using the model from code (Phases 10 and 11)

```python
from src.models.predict import TacticClassifier

classifier = TacticClassifier()                   # load once, at start-up (about 260 MB, CPU)
classifier.predict(body_redacted)                 # {"urgency": {"probability": 0.91, "threshold": 0.4, "fired": True}, ...}
classifier.probabilities([body1, body2])          # a 2 x 7 array, columns in the order of src.data.label_schema.TACTICS
```

The input is the same `body_redacted` text the rest of the pipeline uses; `TacticClassifier` applies the 2,000-character cut itself.

## Security

- **Safetensors only.** The weights are plain numbers in a `.safetensors` file. The older `.bin` format is a pickle, which can run code when loaded. `use_safetensors=True` refuses it, and `validate.py` fails if a pickle-style file sits in the model folder.
- **No network at run time.** `local_files_only=True`; nothing is downloaded when the model loads. `trust_remote_code` is never set, so no code from a model folder is run.
- **Output order checked.** `load_tactic_model` compares the model's saved output names with the project's tactic order, so a mismatched model cannot attach urgency's probability to authority.
- **Bounded input.** Text is cut at 2,000 characters, then at 512 tokens, so a huge email cannot slow the model down.
- **Data stays private.** The upload file holds full email text (phishing_pot's licence forbids redistribution): ignored by Git, uploaded only to your own Drive. The results files hold ids, counts and probabilities, never text.
- **Supply chain.** `torch` and `transformers` are pinned in `requirements.txt` and audited with `pip-audit`. The base model's revision (commit) is recorded in `tactic_run_info.json`.

## Known limits

- The labels are LLM labels from one model family and no human validated them; the model learns that family's judgement.
- The three rare tactics have almost no real positives. On real emails they are counts only; the synthetic emails give them something to learn from, but they are one LLM's style.
- Validation scores are optimistic (see above). Seeds, GPU arithmetic and Colab library versions make a rerun similar, not identical.
- The model reads the body only; headers and thread history are the verifiers' job (Phases 8 and 9).
