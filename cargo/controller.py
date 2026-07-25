"""Mission state joins source, inference, deterministic policy, routing, and bounded events."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
from pathlib import Path
from time import time

from .decision_engine import CargoPolicy, decide
from .inference import SurfaceClassifier
from .risk_map import ZoneRiskMap
from .routing import DEMO_GRAPH, choose_route
from .telemetry import normalize_bmi270

# A mission that is under way still owes the operator a live answer to an obstacle input.
ACTIVE_STATUSES = frozenset({"READY", "MOVING", "SLOWING", "HOLDING", "PAUSED", "SAFE_STOPPED"})
STATUS_BY_ACTION = {"SAFE_STOP": "SAFE_STOPPED", "HOLD_UNCERTAIN": "HOLDING", "SLOW_DOWN": "SLOWING", "MOVE": "MOVING"}


class MissionController:
    def __init__(self, project_root: Path, on_change=None) -> None:
        self.root, self.on_change = project_root, on_change
        self.risks, self.events = ZoneRiskMap(), deque(maxlen=200)
        self.cargo_type, self.source, self.pickup, self.destination = "standard", "dataset", "A1", "C2"
        self.status, self.obstacle_distance, self.latched_stop = "IDLE", None, False
        self.mission_running = False  # True only while something is actually stepping windows
        self.last, self.route, self._classifier = {}, None, None
        self._log("app initialized")

    def _log(self, text: str) -> None:
        self.events.append({"timestamp_ms": int(time() * 1000), "message": text})
        if self.on_change: self.on_change(self.snapshot())

    def _model(self) -> SurfaceClassifier:
        if self._classifier is None: self._classifier = SurfaceClassifier(self.root / "models")
        return self._classifier

    def select(self, *, cargo_type: str | None = None, source: str | None = None, pickup: str | None = None, destination: str | None = None) -> None:
        # Route the candidate first; a rejected command must leave the mission usable.
        cargo_type, pickup, destination = cargo_type or self.cargo_type, pickup or self.pickup, destination or self.destination
        route = choose_route(DEMO_GRAPH, self.risks, pickup, destination, cargo_type)
        if route is None:
            raise ValueError(f"no demo route from {pickup!r} to {destination!r}")
        self.cargo_type, self.pickup, self.destination, self.route = cargo_type, pickup, destination, route
        if source: self.source = source
        self._log("mission settings changed; route recalculated")

    def _apply_decision(self, decision) -> None:
        self.latched_stop |= decision.manual_resume_required
        self.status = STATUS_BY_ACTION.get(decision.action, "ERROR")

    def _last_inference(self) -> dict | None:
        """The most recent real model output, or None; never decide from a placeholder record."""
        valid = self.last.get("source") == "dataset" and {"confidence", "vibration_risk"} <= self.last.keys()
        return self.last if valid else None

    def set_obstacle(self, distance: float | None) -> None:
        self.obstacle_distance = distance
        inference = self._last_inference()
        # IDLE / COMPLETED / ERROR record the input only: no movement may be invented from a finished run.
        if self.status in ACTIVE_STATUSES and inference is not None:
            decision = decide(CargoPolicy(), cargo_type=self.cargo_type, vibration_risk=inference["vibration_risk"], telemetry_valid=True, confidence=inference["confidence"], obstacle_distance=distance, latched_stop=self.latched_stop)
            was_paused = self.status == "PAUSED"
            self._apply_decision(decision)
            # A safe stop overrides a pause; anything milder must not silently un-pause the mission.
            if was_paused and decision.action != "SAFE_STOP":
                self.status = "PAUSED"
            # An obstacle input may only restrict motion. With no run stepping windows there is nothing
            # to move, so clearing an obstacle must not promote a finished run back to MOVING.
            elif decision.action == "MOVE" and not self.mission_running:
                self.status = "READY"
            self.last["decision"] = asdict(decision)
        self._log("simulated obstacle input changed")

    def start(self) -> None:
        self.route = choose_route(DEMO_GRAPH, self.risks, self.pickup, self.destination, self.cargo_type)
        self.status = "READY" if self.route else "ERROR"
        self._log("mission started" if self.route else "destination is unreachable")

    def pause(self) -> None:
        self.status = "PAUSED"; self._log("mission paused")

    def complete(self) -> None:
        self.status = "COMPLETED"; self._log("mission completed")

    def reset(self) -> None:
        self.status, self.obstacle_distance, self.latched_stop, self.last = "IDLE", None, False, {}
        self.mission_running = False
        self._log("mission reset")

    def manual_resume(self) -> None:
        self.latched_stop = False; self.status = "READY"; self._log("manual resume")

    def process_dataset_window(self, window, ground_truth: str, zone: str) -> dict:
        try:
            model = self._model()
            result = model.predict(window)
            self.risks.observe(zone, min(1.0, result["vibration_score"] / max(1e-9, model.config["risk_quantiles"]["medium_to_high"])), result["label"])
            decision = decide(CargoPolicy(), cargo_type=self.cargo_type, vibration_risk=result["vibration_risk"], telemetry_valid=True, confidence=result["confidence"], obstacle_distance=self.obstacle_distance, latched_stop=self.latched_stop)
        except Exception as exc:
            self.status = "ERROR"
            self.last = {"source": "dataset", "reason": f"dataset inference failed: {exc!r}"}
            self._log(self.last["reason"])
            return self.last
        self._apply_decision(decision)
        self.last = {**result, "risk": result["vibration_risk"], "ground_truth": ground_truth, "decision": asdict(decision), "zone": zone, "source": "dataset"}
        # The route of a mission under way is fixed: re-planning here would report a path the robot is
        # not walking. The observation above still feeds risk_map, so the next start() picks a new route.
        self._log(f"prediction {result['label']} ({result['confidence']:.2f}); {decision.action}")
        return self.last

    def accept_ble_sample(self, sample: dict) -> None:
        # Current BLE units/windows are not calibrated to CareerCon; do not run an invalid inference.
        telemetry = normalize_bmi270(sample)
        self.last = {"source": "ble", "data_valid": False, "telemetry_received": telemetry is not None, "reason": "BLE calibration and 128-sample compatibility are required before inference"}
        self._log("BLE BMI270 telemetry received; inference withheld pending calibration")

    def snapshot(self) -> dict:
        return {"status": self.status, "cargo_type": self.cargo_type, "source": self.source, "route": asdict(self.route) if self.route else None, "obstacle_distance": self.obstacle_distance, "last": self.last, "events": list(self.events), "risk_map": self.risks.as_dict()}
