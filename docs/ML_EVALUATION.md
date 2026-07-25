# ML evaluation

The checked-in generated report uses a deterministic group-disjoint split (seed 42), 48 window statistics, and a `RandomForestClassifier`.

- Held-out Macro F1: 0.5155913157
- Held-out weighted F1: 0.5448699269
- Held-out test set: 1,454 windows from 15 groups
- Model file: 53,058,065 bytes
- Measured local batch prediction: 0.074880 ms/window

These are local dataset results only. Regenerate with `python -m training.evaluate_baseline`; `reports/metrics.json` stays the source of truth.
