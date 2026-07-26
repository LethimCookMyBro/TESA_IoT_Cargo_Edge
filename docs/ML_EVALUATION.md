# ML evaluation

The checked-in generated report uses a deterministic group-disjoint split (seed 42), 48 window statistics, and a `RandomForestClassifier`.

- Held-out Macro F1: 0.5155913157
- Held-out weighted F1: 0.5448699269
- Held-out test set: 1,454 windows from 15 groups
- Model file: 53,058,065 bytes
- Measured local single-window-equivalent batch prediction: 0.039917 ms/window
- Confidence threshold: 0.55, selected on 1,824 validation windows from 17 groups
- Validation selective accuracy at 0.55: 0.5030 at 36.1% coverage

The target selective accuracy of 0.75 at coverage ≥ 0.35 was not reached; 0.55 is the best
available threshold under that constraint, not proof that the classifier is production-ready. On
the untouched test split, the validation-selected threshold yields 0.7210 selective accuracy at
52.8% coverage, compared with 0.5743 accuracy when no window is rejected. Rejected windows become
`HOLD_UNCERTAIN`.

Runtime Dataset Replay uses curated validation windows and never reads train or held-out test
windows. It demonstrates control behaviour; it is not part of the metric calculation.

These are local dataset results only. Regenerate metrics with
`python -m training.evaluate_baseline` and threshold selection with
`python -m training.select_confidence`. `reports/metrics.json` and
`reports/confidence_selection.json` remain the sources of truth.
