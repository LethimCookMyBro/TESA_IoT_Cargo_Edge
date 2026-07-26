"""Multi-robot ingest and deterministic safety, entirely in memory.

Sensor input -> validation and timestamp checks -> rolling health -> deterministic policy ->
state/command result -> non-blocking hand-off to persistence. Nothing on this path touches a
database, a browser or a language model, and no step may block on one.

Each robot owns a private ``HealthMonitor`` and ``ZoneRiskMap``. Isolation is structural: there is
no shared mutable rolling state, so one robot's malformed stream cannot move another robot's
decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import perf_counter, time
from typing import Any, Callable, Mapping

from . import contracts
from .decision_engine import CargoPolicy, Decision, decide
from .health import HEALTHY, OFFLINE, UNSAFE, HealthMonitor
from .risk_map import ZoneRiskMap
from .routing import DEMO_GRAPH, Route, choose_route

# A fleet this size is already far beyond the demo; the cap exists so a malformed or hostile robot
# id stream cannot grow the guardian's memory without limit.
MAX_ROBOTS = 64

STATUS_BY_ACTION = {"SAFE_STOP": "SAFE_STOPPED", "HOLD_UNCERTAIN": "HOLDING", "SLOW_DOWN": "SLOWING", "MOVE": "MOVING"}


@dataclass
class RobotRecord:
    """Everything the guardian knows about one robot. Never shared with another robot."""

    robot_id: str
    provenance: str
    monitor: HealthMonitor
    risks: ZoneRiskMap = field(default_factory=ZoneRiskMap)
    status: str = "IDLE"
    latched_stop: bool = False
    latch_reason: str = ""
    route: Route | None = None
    cargo_type: str = "standard"
    mission_id: str | None = None
    last_decision: Decision | None = None
    last_health: dict[str, Any] = field(default_factory=dict)
    last_seen_ms: int = 0
    samples: int = 0
    rejected: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "robot_id": self.robot_id, "provenance": self.provenance, "status": self.status,
            "latched_stop": self.latched_stop, "latch_reason": self.latch_reason,
            "cargo_type": self.cargo_type, "mission_id": self.mission_id,
            "route": asdict(self.route) if self.route else None,
            "decision": asdict(self.last_decision) if self.last_decision else None,
            "health": dict(self.last_health), "last_seen_ms": self.last_seen_ms,
            "samples": self.samples, "rejected": self.rejected,
            "risk_map": self.risks.as_dict(),
        }


class FleetGuardian:
    """Owns every robot's real-time state. Construct one per process."""

    def __init__(self, *, policy: CargoPolicy | None = None,
                 sink: Callable[[dict[str, Any]], None] | None = None,
                 max_robots: int = MAX_ROBOTS, expected_interval_ms: int = 100) -> None:
        self.policy = policy or CargoPolicy()
        # `sink` receives every persistable event. It must never raise and never block: the
        # historian's bounded queue drops rather than wait, which is why the Safety Core survives a
        # database outage. A sink that raises is reported once and then ignored for that event.
        self.sink = sink
        self.max_robots = max_robots
        self.expected_interval_ms = expected_interval_ms
        self.robots: dict[str, RobotRecord] = {}
        self.gate = contracts.SequenceGate()
        self.rejected_unknown = 0
        self.sink_failures = 0
        # Ingest-to-decision durations in milliseconds, for the simulator-only latency budget.
        self.latencies_ms: list[float] = []

    # ---------- lifecycle ----------

    def _record(self, robot_id: str, provenance: str) -> RobotRecord:
        record = self.robots.get(robot_id)
        if record is None:
            if len(self.robots) >= self.max_robots:
                raise contracts.ContractError(f"fleet is full at {self.max_robots} robots; refusing {robot_id!r}")
            record = RobotRecord(robot_id, provenance,
                                 HealthMonitor(robot_id, expected_interval_ms=self.expected_interval_ms))
            self.robots[robot_id] = record
        return record

    def _emit(self, event: dict[str, Any]) -> None:
        if self.sink is None:
            return
        try:
            self.sink(event)
        except Exception:
            # Persistence must never be able to stop a safety decision. Count it and carry on.
            self.sink_failures += 1

    # ---------- the real-time path ----------

    def ingest(self, payload: Mapping[str, Any], *, now_ms: int | None = None) -> dict[str, Any]:
        """Validate, score and decide for one telemetry sample. Never raises for bad input."""
        started = perf_counter()
        now_ms = int(time() * 1000) if now_ms is None else now_ms
        try:
            envelope = contracts.validate_envelope(payload)
        except contracts.ContractError as exc:
            self.rejected_unknown += 1
            self._emit(self._fault_event(None, "rejected_payload", str(exc), now_ms))
            return {"accepted": False, "reason": str(exc)}

        robot_id = envelope["robot_id"]
        try:
            record = self._record(robot_id, envelope["provenance"])
        except contracts.ContractError as exc:
            self.rejected_unknown += 1
            self._emit(self._fault_event(None, "fleet_full", str(exc), now_ms))
            return {"accepted": False, "reason": str(exc)}

        channels = payload.get("channels")
        if not isinstance(channels, Mapping):
            record.rejected += 1
            self._emit(self._fault_event(robot_id, "rejected_payload", "channels must be an object", now_ms))
            return {"accepted": False, "reason": "channels must be an object", "robot_id": robot_id}

        verdict = self.gate.classify(robot_id, seq=envelope.get("seq"),
                                     observed_ms=envelope["observed_ms"], event_id=envelope["event_id"])
        if verdict != "accept":
            record.rejected += 1
            record.monitor.note_duplicate() if verdict == "duplicate" else record.monitor.note_out_of_order()
            self._emit(self._fault_event(robot_id, verdict, f"{verdict} sample seq={envelope.get('seq')}", now_ms))
            # A rejected sample must not extend a rolling window or move a decision.
            return {"accepted": False, "reason": verdict, "robot_id": robot_id}

        record.samples += 1
        record.last_seen_ms = envelope["received_ms"]
        report = record.monitor.observe(channels, observed_ms=envelope["observed_ms"], now_ms=now_ms)
        record.last_health = report.as_dict()

        result = self._decide(record, payload, report.state, "; ".join(report.reasons))
        # Persist the raw sample and any model output *after* deciding, so the queue hand-off can
        # never sit between a sensor reading and the action it implies.
        self._emit({**payload, "mission_id": record.mission_id, "status": record.status,
                    "health_state": report.state})
        self._emit_model_records(record, payload)
        self.latencies_ms.append((perf_counter() - started) * 1000.0)
        return result

    def _decide(self, record: RobotRecord, payload: Mapping[str, Any], health_state: str, health_reason: str) -> dict[str, Any]:
        inference = payload.get("prediction") if isinstance(payload.get("prediction"), Mapping) else {}
        vibration_risk = inference.get("vibration_risk", "low")
        confidence = float(inference.get("confidence", 1.0))
        zone = payload.get("zone")

        if zone and isinstance(inference.get("vibration_score"), (int, float)):
            # Accumulated exposure feeds the *next* mission's route only. The running route is fixed.
            record.risks.observe(str(zone), min(1.0, max(0.0, float(inference["vibration_score"]))),
                                 inference.get("label"))

        decision = decide(self.policy, cargo_type=record.cargo_type, vibration_risk=vibration_risk,
                          telemetry_valid=health_state != OFFLINE, confidence=confidence,
                          obstacle_distance=None, latched_stop=record.latched_stop,
                          health_state=health_state, health_reason=health_reason)
        if decision.manual_resume_required and not record.latched_stop:
            record.latched_stop, record.latch_reason = True, decision.reason
        record.last_decision = decision
        record.status = STATUS_BY_ACTION.get(decision.action, "ERROR")

        self._emit({
            **contracts.envelope(contracts.SCHEMA_EVENT, "safety_decision", record.robot_id,
                                 provenance=record.provenance, source_mode=payload.get("source_mode", "unknown"),
                                 observed_ms=payload["observed_ms"], seq=payload.get("seq")),
            "mission_id": record.mission_id, "zone": zone, "status": record.status,
            "health_state": health_state, "health_reason": health_reason,
            "action": decision.action, "speed_ratio": decision.speed_ratio, "reason": decision.reason,
            "severity": "critical" if decision.action == "SAFE_STOP" else "warning" if health_state != HEALTHY else "info",
        })
        return {"accepted": True, "robot_id": record.robot_id, "status": record.status,
                "health_state": health_state, "decision": asdict(decision)}

    def _emit_model_records(self, record: RobotRecord, payload: Mapping[str, Any]) -> None:
        """A prediction and the feature it was computed from are separate kinds, never merged.

        Keeping them apart is what stops a model's opinion being read back later as a measurement.
        """
        prediction = payload.get("prediction")
        if not isinstance(prediction, Mapping):
            return
        common = dict(provenance=record.provenance, source_mode=payload.get("source_mode", "unknown"),
                      observed_ms=payload["observed_ms"])
        confidence = prediction.get("confidence")
        self._emit({
            **contracts.envelope(contracts.SCHEMA_EVENT, "model_prediction", record.robot_id, **common),
            "mission_id": record.mission_id, "label": prediction.get("label"),
            "confidence": confidence, "vibration_score": prediction.get("vibration_score"),
            "vibration_risk": prediction.get("vibration_risk"),
            "accepted": None if confidence is None else float(confidence) >= self.policy.minimum_confidence,
        })
        features = prediction.get("features")
        if isinstance(features, Mapping) and features:
            self._emit({
                **contracts.envelope(contracts.SCHEMA_EVENT, "derived_feature", record.robot_id, **common),
                "mission_id": record.mission_id, "features": dict(features),
            })

    def _fault_event(self, robot_id: str | None, code: str, reason: str, now_ms: int) -> dict[str, Any]:
        # A fault from an unidentifiable payload still needs a home; it is attributed to the fleet.
        target = robot_id or "fleet-unknown"
        return {
            **contracts.envelope(contracts.SCHEMA_EVENT, "health_event", target,
                                 provenance="SIMULATED" if robot_id is None else self.robots[robot_id].provenance,
                                 source_mode="ingest", observed_ms=now_ms),
            "code": code, "reason": reason, "severity": "warning", "mission_id": None,
        }

    # ---------- mission control (not on the sample path) ----------

    def start_mission(self, robot_id: str, *, pickup: str, destination: str, cargo_type: str,
                      mission_id: str, provenance: str = "SIMULATED") -> Route | None:
        """Plan from accumulated risk. Called between missions, never mid-run."""
        record = self._record(contracts.validate_robot_id(robot_id), provenance)
        record.cargo_type = cargo_type
        route = choose_route(DEMO_GRAPH, record.risks, pickup, destination, cargo_type)
        record.route, record.mission_id = route, mission_id
        record.status = "READY" if route else "ERROR"
        self._emit({
            **contracts.envelope(contracts.SCHEMA_EVENT, "mission_event", record.robot_id,
                                 provenance=record.provenance, source_mode="operator",
                                 observed_ms=int(time() * 1000)),
            "mission_id": mission_id, "code": "mission_started" if route else "route_unavailable",
            "route": list(route.nodes) if route else None, "route_cost": route.cost if route else None,
            "route_reason": route.reason if route else "destination is unreachable",
            "cargo_type": cargo_type, "severity": "info" if route else "warning",
        })
        return route

    def acknowledge(self, robot_id: str, *, note: str = "") -> bool:
        """Operator clears a safety latch. This is the only way out of a latched stop."""
        record = self.robots.get(robot_id)
        if record is None or not record.latched_stop:
            return False
        record.latched_stop, record.status = False, "READY"
        for channel in tuple(record.monitor.quarantined):
            record.monitor.release_channel(channel)
        self._emit({
            **contracts.envelope(contracts.SCHEMA_EVENT, "maintenance_finding", robot_id,
                                 provenance=record.provenance, source_mode="operator",
                                 observed_ms=int(time() * 1000)),
            "mission_id": record.mission_id, "code": "acknowledged",
            "reason": note or record.latch_reason, "severity": "info",
        })
        record.latch_reason = ""
        return True

    def mark_offline(self, robot_id: str) -> None:
        record = self.robots.get(robot_id)
        if record is None:
            return
        record.monitor.note_disconnect()
        record.status = "OFFLINE"

    # ---------- read-only views ----------

    def snapshot(self, robot_id: str) -> dict[str, Any] | None:
        record = self.robots.get(robot_id)
        return record.as_dict() if record else None

    def fleet_status(self) -> dict[str, Any]:
        counts = {"online": 0, "degraded": 0, "offline": 0, "stopped": 0}
        for record in self.robots.values():
            state = record.last_health.get("state", HEALTHY)
            if record.latched_stop:
                counts["stopped"] += 1
            elif state == OFFLINE or record.status == "OFFLINE":
                counts["offline"] += 1
            elif state != HEALTHY:
                counts["degraded"] += 1
            else:
                counts["online"] += 1
        return {
            "schema": contracts.SCHEMA_FLEET_STATUS,
            "generated_ms": int(time() * 1000),
            "robot_count": len(self.robots),
            "counts": counts,
            "rejected_unknown": self.rejected_unknown,
            "sink_failures": self.sink_failures,
            "robots": {robot_id: record.as_dict() for robot_id, record in sorted(self.robots.items())},
        }

    def latency_summary(self) -> dict[str, Any]:
        """Local simulator measurement of ingest-to-decision. Not a board performance figure."""
        if not self.latencies_ms:
            return {"samples": 0, "measurement": "local simulator ingest-to-decision, not board performance"}
        ordered = sorted(self.latencies_ms)
        def percentile(fraction: float) -> float:
            return round(ordered[min(len(ordered) - 1, int(fraction * len(ordered)))], 4)
        return {
            "samples": len(ordered), "p50_ms": percentile(0.50), "p95_ms": percentile(0.95),
            "max_ms": round(ordered[-1], 4), "mean_ms": round(sum(ordered) / len(ordered), 4),
            "measurement": "local simulator ingest-to-decision, not board performance",
        }


def sample(robot_id: str, *, seq: int, observed_ms: int, channels: Mapping[str, Any],
           provenance: str = "SIMULATED", source_mode: str = "simulator",
           zone: str | None = None, prediction: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a valid telemetry payload. The simulator and the tests use the production builder."""
    payload = {
        **contracts.envelope(contracts.SCHEMA_TELEMETRY, "raw_telemetry", robot_id,
                             provenance=provenance, source_mode=source_mode,
                             observed_ms=observed_ms, seq=seq),
        "channels": dict(channels),
    }
    if zone is not None:
        payload["zone"] = zone
    if prediction is not None:
        payload["prediction"] = dict(prediction)
    return payload


def demo() -> None:
    """Self-check: run with `python -m cargo.fleet`."""
    healthy = {"bmi270.accelX": 0.1, "bmi270.accelY": 0.0, "bmi270.accelZ": 9.81}
    events: list[dict] = []
    fleet = FleetGuardian(sink=events.append, expected_interval_ms=100)

    ok = fleet.ingest(sample("robot-01", seq=1, observed_ms=1000, channels=healthy,
                             prediction={"confidence": 0.9, "vibration_risk": "low"}), now_ms=1000)
    assert ok["accepted"] and ok["status"] == "MOVING", ok

    # A duplicate and an out-of-order sample are both refused, and neither moves the decision.
    duplicate = fleet.ingest(sample("robot-01", seq=1, observed_ms=1000, channels=healthy), now_ms=1000)
    assert duplicate == {"accepted": False, "reason": "duplicate", "robot_id": "robot-01"}, duplicate
    stale = fleet.ingest(sample("robot-01", seq=0, observed_ms=500, channels=healthy), now_ms=1000)
    assert stale["reason"] == "out_of_order", stale
    assert fleet.robots["robot-01"].status == "MOVING"

    # A malformed payload is rejected without raising and without creating a robot.
    assert not fleet.ingest({"schema": "nope"}, now_ms=1000)["accepted"]
    no_channels = {**sample("robot-01", seq=9, observed_ms=1100, channels={}), "channels": "not-a-map"}
    assert not fleet.ingest(no_channels, now_ms=1100)["accepted"]

    # Robot isolation: a second robot's unsafe stream must not touch the first robot's state.
    bad = fleet.ingest(sample("robot-02", seq=1, observed_ms=1000,
                              channels={"bmi270.accelX": float("inf")}), now_ms=1000)
    assert bad["status"] == "SAFE_STOPPED" and bad["health_state"] == UNSAFE, bad
    assert fleet.robots["robot-01"].status == "MOVING", "robot-02 changed robot-01's state"
    assert fleet.robots["robot-01"].latched_stop is False

    # The latch holds until an operator acknowledges it, and only then.
    again = fleet.ingest(sample("robot-02", seq=2, observed_ms=1100, channels=healthy,
                                prediction={"confidence": 0.99, "vibration_risk": "low"}), now_ms=1100)
    assert again["status"] == "SAFE_STOPPED", "a latched stop must survive good data"
    assert fleet.acknowledge("robot-02") is True
    assert fleet.acknowledge("robot-02") is False, "acknowledging twice must not be a second release"
    after = fleet.ingest(sample("robot-02", seq=3, observed_ms=1200, channels=healthy,
                                prediction={"confidence": 0.99, "vibration_risk": "low"}), now_ms=1200)
    assert after["status"] == "MOVING", after

    # Accumulated risk changes the *next* route, never the running one.
    quiet = FleetGuardian(expected_interval_ms=100)
    first = quiet.start_mission("robot-03", pickup="A1", destination="C2", cargo_type="fragile", mission_id="m1")
    for step in range(1, 12):
        quiet.ingest(sample("robot-03", seq=step, observed_ms=step * 100, channels=healthy, zone="B2",
                            prediction={"confidence": 0.9, "vibration_risk": "high", "vibration_score": 1.0,
                                        "label": "concrete"}), now_ms=step * 100)
    assert quiet.robots["robot-03"].route == first, "the running route must not be re-planned mid-mission"
    second = quiet.start_mission("robot-03", pickup="A1", destination="C2", cargo_type="fragile", mission_id="m2")
    assert second is not None and second.nodes != first.nodes, (first, second)

    # A sink that throws cannot stop a decision.
    def angry(_event): raise RuntimeError("database is down")
    resilient = FleetGuardian(sink=angry, expected_interval_ms=100)
    assert resilient.ingest(sample("robot-04", seq=1, observed_ms=1, channels=healthy,
                                   prediction={"confidence": 0.9, "vibration_risk": "low"}), now_ms=1)["status"] == "MOVING"
    assert resilient.sink_failures > 0

    # The fleet cap is enforced rather than growing without limit.
    small = FleetGuardian(max_robots=1, expected_interval_ms=100)
    assert small.ingest(sample("robot-aa", seq=1, observed_ms=1, channels=healthy), now_ms=1)["accepted"]
    assert not small.ingest(sample("robot-bb", seq=1, observed_ms=1, channels=healthy), now_ms=1)["accepted"]

    status = fleet.fleet_status()
    assert status["robot_count"] == 2 and status["counts"]["online"] >= 1, status
    assert fleet.latency_summary()["samples"] > 0
    assert any(event["kind"] == "safety_decision" for event in events)
    print(f"cargo.fleet self-check passed ({len(events)} events, {fleet.latency_summary()})")


if __name__ == "__main__":
    demo()
