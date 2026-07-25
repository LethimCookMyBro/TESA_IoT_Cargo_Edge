"""Deterministic demo policy. It is deliberately separate from ML inference."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CargoPolicy:
    # Demo values only; calibrate against a real obstacle sensor before deployment.
    stop_distance: float = 30.0
    warning_distance: float = 80.0
    minimum_confidence: float = 0.45


@dataclass(frozen=True)
class Decision:
    action: str
    speed_ratio: float
    reason: str
    manual_resume_required: bool


def decide(policy: CargoPolicy, *, cargo_type: str, vibration_risk: str, telemetry_valid: bool, confidence: float, obstacle_distance: float | None, latched_stop: bool) -> Decision:
    if latched_stop:
        return Decision("SAFE_STOP", 0.0, "manual resume required after a safe stop", True)
    if obstacle_distance is not None and obstacle_distance <= policy.stop_distance:
        return Decision("SAFE_STOP", 0.0, "simulated obstacle is in the demo stop region", True)
    if not telemetry_valid or confidence < policy.minimum_confidence:
        return Decision("HOLD_UNCERTAIN", 0.0, "telemetry or model confidence is insufficient", False)
    if vibration_risk not in {"low", "medium", "high"}:
        raise ValueError("vibration_risk must be low, medium, or high")
    caps = {"standard": {"low": 1.0, "medium": 0.75, "high": 0.5}, "fragile": {"low": 0.8, "medium": 0.45, "high": 0.25}}
    if cargo_type not in caps:
        raise ValueError("cargo_type must be standard or fragile")
    speed = caps[cargo_type][vibration_risk]
    if obstacle_distance is not None and obstacle_distance <= policy.warning_distance:
        return Decision("SLOW_DOWN", min(speed, 0.5), "simulated obstacle is in the demo warning region", False)
    return Decision("MOVE", speed, f"{cargo_type} cargo with {vibration_risk} vibration risk", False)
