"""Interpretable features for verified CareerCon gyro + linear-acceleration axes."""

from __future__ import annotations

import numpy as np


CHANNELS = ("gyro_x", "gyro_y", "gyro_z", "linear_accel_x", "linear_accel_y", "linear_accel_z")


def extract_features(windows: np.ndarray) -> np.ndarray:
    if windows.ndim != 3 or windows.shape[1:] != (128, 6):
        raise ValueError(f"expected (samples, 128, 6) verified IMU windows; received {windows.shape}")
    if not np.isfinite(windows).all():
        raise ValueError("features require finite values")
    delta = np.diff(windows, axis=1)
    stats = (
        windows.mean(axis=1), windows.std(axis=1), np.median(windows, axis=1),
        windows.min(axis=1), windows.max(axis=1), np.ptp(windows, axis=1),
        np.sqrt(np.mean(np.square(windows), axis=1)), np.mean(np.abs(delta), axis=1),
    )
    return np.concatenate(stats, axis=1)
