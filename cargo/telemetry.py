"""Validated IMU records shared by BLE and dataset replay."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import time
from typing import Mapping


@dataclass(frozen=True)
class Telemetry:
    source: str
    timestamp_ms: int
    accel: tuple[float, float, float]
    gyro: tuple[float, float, float]
    ground_truth: str | None = None


def normalize_bmi270(sample: Mapping) -> Telemetry | None:
    """Map an already-decoded BS2 BMI270 sample; never decode BLE here."""
    if sample.get("sensor") != "bmi270":
        return None
    fields = sample.get("fields")
    if not isinstance(fields, Mapping):
        return None
    keys = ("accelX", "accelY", "accelZ", "gyroX", "gyroY", "gyroZ")
    try:
        values = tuple(float(fields[key]) for key in keys)
    except (KeyError, TypeError, ValueError):
        return None
    if not all(isfinite(value) for value in values):
        return None
    timestamp = sample.get("device_ms")
    if not isinstance(timestamp, int) or timestamp < 0:
        timestamp = int(time() * 1000)
    return Telemetry("ble", timestamp, values[:3], values[3:])


def dataset_telemetry(timestamp_ms: int, accel: tuple[float, float, float], gyro: tuple[float, float, float], ground_truth: str | None) -> Telemetry:
    values = (*accel, *gyro)
    if timestamp_ms < 0 or not all(isfinite(float(value)) for value in values):
        raise ValueError("dataset telemetry must contain finite accel and gyro values")
    return Telemetry("dataset", timestamp_ms, tuple(map(float, accel)), tuple(map(float, gyro)), ground_truth)
