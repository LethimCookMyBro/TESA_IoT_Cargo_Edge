"""Replay of the real stored CareerCon windows. This is the only dataset reader in production."""

from __future__ import annotations

from pathlib import Path

import numpy as np


class DatasetReplaySource:
    def __init__(self, dataset_dir: Path, labels: dict[int, str]) -> None:
        self.x = np.load(dataset_dir / "X_data.npy", mmap_mode="r")
        self.labels = np.load(dataset_dir / "label.npy").astype(int)
        self.names = labels
        if self.x.ndim != 3 or self.x.shape[1:] != (128, 10):
            raise ValueError(f"unsupported dataset shape: {self.x.shape}")

    def __len__(self) -> int:
        return len(self.x)

    def window(self, index: int) -> tuple[np.ndarray, str]:
        """One window's IMU channels and its ground-truth surface label."""
        raw = np.asarray(self.x[index])
        # Verified CareerCon mapping: channels 4:7 gyro, 7:10 linear acceleration.
        imu = raw[:, 4:10]
        if not np.isfinite(imu).all():
            raise ValueError(f"dataset window {index} contains non-finite IMU values")
        return imu, self.names[int(self.labels[index])]
