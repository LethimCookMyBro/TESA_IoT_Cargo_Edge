"""Train the first reproducible CargoShield surface baseline."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from .features import CHANNELS, extract_features
from .prepare_dataset import LABELS, ROOT, load_dataset, prepare


def train() -> dict:
    models, reports = ROOT / "models", ROOT / "reports"
    if not (models / "split_indices.npz").is_file():
        prepare(models, reports)
    indices = np.load(models / "split_indices.npz")
    x, labels, _ = load_dataset()
    features = extract_features(x[:, :, 4:10])
    train_idx = indices["train"]
    model = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample", random_state=42, n_jobs=-1)
    started = perf_counter(); model.fit(features[train_idx], labels[train_idx]); fit_s = perf_counter() - started
    joblib.dump(model, models / "surface_baseline.joblib")
    training_accel_std = np.linalg.norm(x[train_idx, :, 7:10].std(axis=1), axis=1)
    config = {"model": "RandomForestClassifier", "input_shape": [128, 6], "channels": list(CHANNELS), "dataset_channel_indices": [4, 5, 6, 7, 8, 9], "feature_count": int(features.shape[1]), "risk_quantiles": {"low_to_medium": float(np.quantile(training_accel_std, .5)), "medium_to_high": float(np.quantile(training_accel_std, .8))}, "fit_seconds": fit_s}
    (models / "feature_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (models / "label_mapping.json").write_text(json.dumps(LABELS, indent=2), encoding="utf-8")
    return config


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
