# src/eval/

Metrics, ablations and charts (Phase 13 builds the experiments). One file exists so far, written in Phase 6 because the tactic classifier needs it.

```bash
python -m src.eval.metrics    # self-test: every function against scikit-learn on random data, plus hand-worked cases
```

## Files

| File | Job |
|---|---|
| `metrics.py` | Precision, recall, F1, macro-F1 and per-tactic threshold tuning, written by hand |

## What `metrics.py` holds

| Function | What it does |
|---|---|
| `confusion(y_true, y_pred)` | Counts true positives, false positives, false negatives and true negatives for one yes/no question |
| `precision_recall_f1(tp, fp, fn)` | The three scores from the counts; an empty denominator gives 0.0 (scikit-learn's `zero_division=0`) |
| `f1_at(scores, y_true, threshold)` | F1 when every item scoring at least the threshold is called positive |
| `tune_threshold(scores, y_true, grid, default)` | The grid threshold with the best F1; ties go to the one nearest `default`, then the lower. Only ever called on validation data |
| `tactic_rows(y_true, y_pred, tactics)` | One table row per tactic (items, positives, predicted, tp, fp, fn, precision, recall, F1); precision, recall and F1 are left empty when the tactic has fewer than `MIN_POSITIVES` (10) positives |
| `macro_f1(y_true, y_pred, tactics, use)` | Mean F1 over the tactics named in `use` |

## Rules built in

- **Counts, not F1, below 10 positives.** The same rule as `src/data/labels.py` (`MIN_POSITIVES`). With so few positives one email moves F1 by several points, and the number would only look precise.
- **One function set for every system.** The keyword baseline and DistilBERT are scored by the same code, so the comparison is fair.
- **Thresholds are tuned on validation only.** The test split is used once, with the thresholds already fixed (Phase 13).
- **scikit-learn is only imported in the self-test,** so Colab and the API never need it. The self-test checks 200 random trials against scikit-learn's precision, recall and F1 (the largest difference is about 1e-16).

## Still to come (Phase 13)

`ablation_n1.py`, `ablation_n2.py`, `ablation_n3.py`, `ablation_arch.py`, `claim_extraction.py`, `style_confound.py`, `paraphrase.py`, `charts.py`: one script per experiment of master document Section 11, each writing its numbers to `results/`.
