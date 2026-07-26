"""Deterministic demo policy. It is deliberately separate from ML inference."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from .health import DEGRADED, HEALTHY, OFFLINE, UNSAFE

# Mirrors models/confidence_policy.json, which training/select_confidence.py writes from the
# validation split. Kept as a literal so the Safety Core needs no file to start, and pinned by a
# test so the two can never drift apart.
SELECTED_MINIMUM_CONFIDENCE = 0.55


@dataclass(frozen=True)
class CargoPolicy:
    # Demo values only; calibrate against a real obstacle sensor before deployment.
    stop_distance: float = 30.0
    warning_distance: float = 80.0
    # Chosen on the group-disjoint validation split, never on the held-out test split.
    # See training/select_confidence.py and models/confidence_policy.json.
    minimum_confidence: float = SELECTED_MINIMUM_CONFIDENCE
    # A robot whose sensors are degraded may still finish its run, slowly and visibly.
    degraded_speed_cap: float = 0.4


def load_policy(models_dir: Path, base: CargoPolicy | None = None) -> CargoPolicy:
    """Policy with the confidence threshold as recorded by the validation-split selection.

    Falls back to the compiled-in default when the file is absent, so a fresh checkout that has
    not run training still makes safe decisions.
    """
    policy = base or CargoPolicy()
    path = Path(models_dir) / "confidence_policy.json"
    try:
        selected = json.loads(path.read_text(encoding="utf-8"))["minimum_confidence"]
    except (OSError, KeyError, ValueError):
        return policy
    return replace(policy, minimum_confidence=float(selected))


@dataclass(frozen=True)
class Decision:
    action: str
    speed_ratio: float
    reason: str
    manual_resume_required: bool


def decide(policy: CargoPolicy, *, cargo_type: str, vibration_risk: str, telemetry_valid: bool, confidence: float, obstacle_distance: float | None, latched_stop: bool, health_state: str = HEALTHY, health_reason: str = "") -> Decision:
    """The one authority for Stop/Slow/Hold/Move. No model and no language model reaches this.

    ``health_state`` is the deterministic verdict from ``cargo.health.HealthMonitor``. Callers with
    no live channel stream -- the stored-dataset replay path -- pass ``HEALTHY`` because no channel
    fault has been observed; the fleet ingest path always passes the monitor's real answer.
    """
    if latched_stop:
        return Decision("SAFE_STOP", 0.0, "manual resume required after a safe stop", True)
    if obstacle_distance is not None and obstacle_distance <= policy.stop_distance:
        return Decision("SAFE_STOP", 0.0, "simulated obstacle is in the demo stop region", True)
    # An unsafe sensor state latches exactly like an obstacle stop: the operator must look at the
    # robot before it moves again. The reason travels with the decision so the console can show it.
    if health_state == UNSAFE:
        return Decision("SAFE_STOP", 0.0, f"sensor health is UNSAFE: {health_reason or 'no reason recorded'}", True)
    if health_state == OFFLINE:
        return Decision("HOLD_UNCERTAIN", 0.0, f"telemetry is OFFLINE: {health_reason or 'no reason recorded'}", False)
    if not telemetry_valid or confidence < policy.minimum_confidence:
        return Decision("HOLD_UNCERTAIN", 0.0, "telemetry or model confidence is insufficient", False)
    if vibration_risk not in {"low", "medium", "high"}:
        raise ValueError("vibration_risk must be low, medium, or high")
    caps = {"standard": {"low": 1.0, "medium": 0.75, "high": 0.5}, "fragile": {"low": 0.8, "medium": 0.45, "high": 0.25}}
    if cargo_type not in caps:
        raise ValueError("cargo_type must be standard or fragile")
    speed = caps[cargo_type][vibration_risk]
    if health_state == DEGRADED:
        speed = min(speed, policy.degraded_speed_cap)
    if obstacle_distance is not None and obstacle_distance <= policy.warning_distance:
        return Decision("SLOW_DOWN", min(speed, 0.5), "simulated obstacle is in the demo warning region", False)
    if health_state == DEGRADED:
        return Decision("SLOW_DOWN", speed, f"sensor health is DEGRADED: {health_reason or 'no reason recorded'}", False)
    return Decision("MOVE", speed, f"{cargo_type} cargo with {vibration_risk} vibration risk", False)
