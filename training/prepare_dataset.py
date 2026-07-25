"""Load the local data and create one deterministic, group-disjoint 3-way split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
LABELS = {
    0: "hard_tiles_large_space", 1: "soft_pvc", 2: "soft_tiles", 3: "fine_concrete",
    4: "concrete", 5: "hard_tiles", 6: "carpet", 7: "tiled", 8: "wood",
}


def load_dataset(dataset_dir: Path = DATASET) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    paths = {name: dataset_dir / name for name in ("X_data.npy", "label.npy", "groups.npy")}
    if any(not path.is_file() for path in paths.values()):
        missing = ", ".join(name for name, path in paths.items() if not path.is_file())
        raise FileNotFoundError(f"missing dataset files: {missing}")
    x, labels, groups = (np.load(paths[name]) for name in ("X_data.npy", "label.npy", "groups.npy"))
    if x.shape != (len(labels), 128, 10) or labels.shape != groups.shape or not np.isfinite(x).all():
        raise ValueError(f"invalid dataset shapes or values: X={x.shape}, labels={labels.shape}, groups={groups.shape}")
    return x, labels.astype(int), groups


def split_indices(labels: np.ndarray, groups: np.ndarray, seed: int = 42) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    split_groups = {name: [] for name in ("train", "validation", "test")}
    for label in sorted(set(labels)):
        label_groups = np.unique(groups[labels == label])
        if len(label_groups) < 3:
            raise ValueError(f"label {label} has fewer than three groups; cannot make a 3-way group-safe split")
        rng.shuffle(label_groups)
        train_end = min(max(1, round(len(label_groups) * .6)), len(label_groups) - 2)
        validation_end = train_end + min(max(1, round(len(label_groups) * .2)), len(label_groups) - train_end - 1)
        split_groups["train"].extend(label_groups[:train_end])
        split_groups["validation"].extend(label_groups[train_end:validation_end])
        split_groups["test"].extend(label_groups[validation_end:])
    result = {name: np.flatnonzero(np.isin(groups, selected)) for name, selected in split_groups.items()}
    group_sets = {name: set(groups[index]) for name, index in result.items()}
    if group_sets["train"] & group_sets["validation"] or group_sets["train"] & group_sets["test"] or group_sets["validation"] & group_sets["test"]:
        raise AssertionError("group leakage detected")
    return result


def prepare(output_dir: Path = ROOT / "models", reports_dir: Path = ROOT / "reports") -> dict:
    x, labels, groups = load_dataset()
    indices = split_indices(labels, groups)
    output_dir.mkdir(parents=True, exist_ok=True); reports_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_dir / "split_indices.npz", **indices)
    metadata = {"seed": 42, "splits": {name: {"samples": int(len(index)), "groups": int(len(set(groups[index]))), "labels": sorted(set(map(int, labels[index])))} for name, index in indices.items()}}
    (reports_dir / "split_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
