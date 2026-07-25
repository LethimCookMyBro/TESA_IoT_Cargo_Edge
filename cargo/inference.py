"""Local model loading and prediction; no BLE protocol or UI dependency."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np

from training.features import extract_features


def _features(window: np.ndarray) -> np.ndarray:
    """One window through the exact training-time extractor; never re-implement it here."""
    return extract_features(np.asarray(window)[None])


class SurfaceClassifier:
    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self.model = joblib.load(models_dir / "surface_baseline.joblib")
        self.labels = {int(key): value for key, value in json.loads((models_dir / "label_mapping.json").read_text(encoding="utf-8")).items()}
        self.config = json.loads((models_dir / "feature_config.json").read_text(encoding="utf-8"))

    def predict(self, window: np.ndarray) -> dict:
        features = _features(window); started = perf_counter()
        probabilities = self.model.predict_proba(features)[0]; label = int(self.model.classes_[int(np.argmax(probabilities))])
        accel_spread = float(np.linalg.norm(window[:, 3:6].std(axis=0)))
        q = self.config["risk_quantiles"]
        risk = "low" if accel_spread < q["low_to_medium"] else "medium" if accel_spread < q["medium_to_high"] else "high"
        return {"label": self.labels[label], "confidence": float(probabilities.max()), "vibration_score": accel_spread, "vibration_risk": risk, "inference_ms": (perf_counter() - started) * 1000}
