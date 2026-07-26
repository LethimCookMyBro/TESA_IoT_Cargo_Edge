"""Evaluate only the held-out group split and write factual reports."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from .features import extract_features
from .prepare_dataset import LABELS, ROOT, load_dataset
from .train_baseline import train


def _png(matrix: np.ndarray, path: Path) -> None:
    cell, size = 24, matrix.shape[0] * 24
    max_value = max(1, int(matrix.max()))
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            value = matrix[y // cell, x // cell] / max_value
            row.extend((int(255 * (1 - value)), int(210 * (1 - value)), 255))
        rows.append(bytes(row))
    def chunk(kind: bytes, data: bytes) -> bytes: return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def _selective(model, features, truth, models_dir: Path) -> dict:
    """Coverage versus rejection on the held-out split, at the threshold validation already chose.

    The threshold is read, never re-tuned here: choosing it on the test split is exactly the leak
    the group-disjoint split exists to prevent.
    """
    policy_path = models_dir / "confidence_policy.json"
    if not policy_path.is_file():
        return {"available": False, "reason": "run training.select_confidence first"}
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    threshold = float(policy["minimum_confidence"])
    probabilities = model.predict_proba(features)
    confidence = probabilities.max(axis=1)
    predicted = model.classes_[probabilities.argmax(axis=1)]
    accepted = confidence >= threshold
    count = int(accepted.sum())
    return {
        "available": True,
        "threshold": threshold,
        "threshold_selected_on": policy.get("selected_on"),
        "coverage": float(count / len(truth)),
        "accepted": count,
        "rejected_to_hold_uncertain": int(len(truth) - count),
        "selective_accuracy": float((predicted[accepted] == truth[accepted]).mean()) if count else None,
        "accuracy_if_nothing_rejected": float((predicted == truth).mean()),
        "note": "rejected windows become HOLD_UNCERTAIN, which stops the robot rather than acting "
                "on a low-confidence prediction",
    }


def evaluate() -> dict:
    models, reports = ROOT / "models", ROOT / "reports"
    if not (models / "surface_baseline.joblib").is_file(): train()
    x, labels, groups = load_dataset(); test_idx = np.load(models / "split_indices.npz")["test"]
    features = extract_features(x[:, :, 4:10]); model = joblib.load(models / "surface_baseline.joblib")
    started = perf_counter(); predictions = model.predict(features[test_idx]); batch_s = perf_counter() - started
    matrix = confusion_matrix(labels[test_idx], predictions, labels=sorted(LABELS))
    selective = _selective(model, features[test_idx], labels[test_idx], models)
    report = classification_report(labels[test_idx], predictions, labels=sorted(LABELS), target_names=[LABELS[x] for x in sorted(LABELS)], output_dict=True, zero_division=0)
    metrics = {"macro_f1": f1_score(labels[test_idx], predictions, average="macro", zero_division=0), "weighted_f1": f1_score(labels[test_idx], predictions, average="weighted", zero_division=0), "test_samples": int(len(test_idx)), "test_groups": int(len(set(groups[test_idx]))), "batch_seconds": batch_s, "single_window_ms": batch_s * 1000 / len(test_idx), "model_bytes": (models / "surface_baseline.joblib").stat().st_size,
               "selective": selective,
               # The three classes the model fails hardest on, reported rather than averaged away.
               "worst_classes_by_f1": sorted(
                   ({"label": name, "f1": report[name]["f1-score"], "support": report[name]["support"]}
                    for name in LABELS.values() if name in report),
                   key=lambda row: row["f1"])[:3],
               "provenance": "DATASET — real stored CareerCon windows, group-disjoint held-out test split. "
                             "No simulator-generated label is included. Timings are host batch prediction, "
                             "not board inference."}
    reports.mkdir(exist_ok=True)
    (reports / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (reports / "classification_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _png(matrix, reports / "confusion_matrix.png")
    (reports / "model_summary.md").write_text("# Surface baseline\n\nGenerated locally from the held-out group split. See `metrics.json`; no hardware-performance claim is implied.\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
