"""Choose the confidence-rejection threshold on the validation split.
`CargoPolicy.minimum_confidence` decides whether a prediction is acted on or routed to
HOLD_UNCERTAIN. It used to be a hand-picked constant while 1 824 validation windows -- 24 % of the
dataset -- sat unread. This module makes that split earn its keep.
Method: sweep candidate thresholds, and for each one measure *coverage* (the share of windows the
policy would act on) and *selective accuracy* (accuracy over only those accepted windows). Pick the
lowest threshold that reaches the target selective accuracy while still covering enough of the
data to be useful. Rejecting a low-confidence prediction into a safe non-action follows Renault et
al. (arXiv:2506.05435), who reassign below-threshold accelerometer events to an inert class rather
than acting on them.
The held-out **test** split is never loaded here. It is opened once, by evaluate_baseline, after
this threshold is already fixed.
"""
from __future__ import annotations
import json
import joblib
import numpy as np
from .features import extract_features
from .prepare_dataset import ROOT, load_dataset
# Sweep resolution. Finer than this is meaningless for a 1 824-window validation split.
THRESHOLDS = tuple(round(value, 2) for value in np.arange(0.20, 0.96, 0.05))
# Act on a prediction only if predictions at this confidence are right at least this often...
TARGET_SELECTIVE_ACCURACY = 0.75
# ...but never buy accuracy by refusing to answer: keep at least this share of windows.
MIN_COVERAGE = 0.35
def sweep(probabilities: np.ndarray, truth: np.ndarray, classes: np.ndarray) -> list[dict]:
    """Coverage and selective accuracy at every candidate threshold."""
    confidence = probabilities.max(axis=1)
    predicted = classes[probabilities.argmax(axis=1)]
    correct = predicted == truth
    rows = []
    for threshold in THRESHOLDS:
        accepted = confidence >= threshold
        count = int(accepted.sum())
        rows.append({
            "threshold": float(threshold),
            "coverage": float(count / len(truth)),
            "accepted": count,
            "rejected": int(len(truth) - count),
            "selective_accuracy": float(correct[accepted].mean()) if count else None,
            # What acting on this threshold would cost: accepted-but-wrong windows.
            "accepted_errors": int((~correct[accepted]).sum()) if count else 0,
        })
    return rows
def choose(rows: list[dict]) -> dict:
    """Lowest threshold meeting the accuracy target at acceptable coverage; else best-effort."""
    eligible = [row for row in rows
                if row["selective_accuracy"] is not None
                and row["selective_accuracy"] >= TARGET_SELECTIVE_ACCURACY
                and row["coverage"] >= MIN_COVERAGE]
    if eligible:
        return {**min(eligible, key=lambda row: row["threshold"]), "rule": "lowest threshold meeting both targets"}
    # Nothing meets both. Say so plainly and fall back to the best selective accuracy that still
    # covers enough data, rather than quietly pretending the target was met.
    covered = [row for row in rows if row["coverage"] >= MIN_COVERAGE and row["selective_accuracy"] is not None]
    best = max(covered, key=lambda row: row["selective_accuracy"])
    return {**best, "rule": f"target selective accuracy {TARGET_SELECTIVE_ACCURACY} unreachable at "
                            f"coverage >= {MIN_COVERAGE}; best available chosen"}
def select() -> dict:
    models, reports = ROOT / "models", ROOT / "reports"
    indices = np.load(models / "split_indices.npz")
    if "validation" not in indices:
        raise SystemExit("split_indices.npz has no validation split; run training.prepare_dataset")
    validation_idx = indices["validation"]
    x, labels, groups = load_dataset()
    # Guard, not decoration: if these ever intersect, the threshold would be tuned on data the
    # model trained on and every number below would be optimistic.
    for other in ("train", "test"):
        shared = set(groups[validation_idx]) & set(groups[indices[other]])
        if shared:
            raise SystemExit(f"group leakage between validation and {other}: {sorted(shared)[:5]}")
    model = joblib.load(models / "surface_baseline.joblib")
    features = extract_features(x[:, :, 4:10])
    probabilities = model.predict_proba(features[validation_idx])
    rows = sweep(probabilities, labels[validation_idx], model.classes_)
    chosen = choose(rows)
    policy = {
        "minimum_confidence": chosen["threshold"],
        "selected_on": "validation",
        "selection_rule": chosen["rule"],
        "target_selective_accuracy": TARGET_SELECTIVE_ACCURACY,
        "min_coverage": MIN_COVERAGE,
        "validation_samples": int(len(validation_idx)),
        "validation_groups": int(len(set(groups[validation_idx]))),
        "coverage_at_threshold": chosen["coverage"],
        "selective_accuracy_at_threshold": chosen["selective_accuracy"],
        "sweep": rows,
        "provenance": "DATASET — real stored CareerCon windows, group-disjoint validation split. "
                      "No simulator-generated label was used to choose this threshold, and the "
                      "held-out test split was not read.",
    }
    models.mkdir(exist_ok=True)
    (models / "confidence_policy.json").write_text(json.dumps(policy, indent=2), encoding="utf-8")
    reports.mkdir(exist_ok=True)
    (reports / "confidence_selection.json").write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return policy
def main() -> None:
    policy = select()
    print(json.dumps({key: value for key, value in policy.items() if key != "sweep"}, indent=2))
if __name__ == "__main__":
    main()
