"""Replaceable sources. Dataset replay is real local data; BLE remains decoded upstream."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .telemetry import Telemetry, dataset_telemetry


class DatasetReplaySource:
    def __init__(self, dataset_dir: Path, labels: dict[int, str]) -> None:
        self.x = np.load(dataset_dir / "X_data.npy", mmap_mode="r")
        self.labels = np.load(dataset_dir / "label.npy").astype(int)
        self.names = labels
        if self.x.ndim != 3 or self.x.shape[1:] != (128, 10):
            raise ValueError(f"unsupported dataset shape: {self.x.shape}")

    def indices(self, label: str | None = None) -> np.ndarray:
        if label is None: return np.arange(len(self.x))
        selected = [key for key, value in self.names.items() if value == label]
        return np.flatnonzero(self.labels == selected[0]) if selected else np.array([], dtype=int)

    def window(self, index: int) -> tuple[np.ndarray, Telemetry]:
        raw = np.asarray(self.x[index])
        # Verified CareerCon mapping: channels 4:7 gyro, 7:10 linear acceleration.
        imu = raw[:, 4:10]
        point = dataset_telemetry(index * 6400, tuple(raw[-1, 7:10]), tuple(raw[-1, 4:7]), self.names[int(self.labels[index])])
        return imu, point
