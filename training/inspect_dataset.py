"""Print a factual local dataset summary without modifying it."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .features import CHANNELS
from .prepare_dataset import DATASET, LABELS, load_dataset


def inspect() -> dict:
    x, labels, groups = load_dataset()
    selected = x[:, :, 4:10]
    return {
        "paths": {name: str((DATASET / name).resolve()) for name in ("X_data.npy", "label.npy", "groups.npy", "details.csv")},
        "shape": list(x.shape), "dtype": str(x.dtype), "time_axis": 1,
        "verified_channel_mapping": {"0-3": "orientation quaternion XYZW", "4-6": "angular velocity XYZ", "7-9": "linear acceleration XYZ"},
        "baseline_channels": list(CHANNELS), "nan": int(np.isnan(x).sum()), "inf": int(np.isinf(x).sum()),
        "groups": int(len(set(groups))), "class_counts": {LABELS[label]: int((labels == label).sum()) for label in sorted(LABELS)},
        "baseline_stats": {channel: {key: float(value) for key, value in zip(("min", "max", "mean", "std"), (selected[:, :, i].min(), selected[:, :, i].max(), selected[:, :, i].mean(), selected[:, :, i].std()))} for i, channel in enumerate(CHANNELS)},
    }


if __name__ == "__main__":
    summary = inspect()
    reports = DATASET.parent / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "dataset_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
