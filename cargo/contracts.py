"""Versioned fleet contracts: the only place a wire payload is built or validated.

Every topic, schema string, provenance value and envelope field the fleet uses lives here so a
rename cannot silently desync the engine, the simulator, the historian and the browser.
"""

from __future__ import annotations

import re
from collections import deque
from math import isfinite
from time import time
from typing import Any, Mapping
from uuid import uuid4

# A robot id ends up in an MQTT topic, a database key and a URL query string. Keep it to the
# characters all three treat literally, and bound it so a malicious id cannot blow up a topic.
ROBOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")

# Where a value came from. There is no fourth option: an unlabelled sample is rejected.
PROVENANCE = frozenset({"SIMULATED", "DATASET", "HARDWARE"})

# What a payload *is*. Raw sensing, a feature derived from it, a model's opinion, the deterministic
# safety verdict, and the health/mission/maintenance records are deliberately distinct kinds so a
# prediction can never be read back as a measurement.
KINDS = frozenset({
    "raw_telemetry", "derived_feature", "model_prediction",
    "safety_decision", "health_event", "mission_event", "maintenance_finding",
})

SCHEMA_STATE = "cargoshield.state.v2"
SCHEMA_TELEMETRY = "cargoshield.telemetry.v1"
SCHEMA_EVENT = "cargoshield.event.v1"
SCHEMA_COMMAND = "cargoshield.command.v1"
SCHEMA_FLEET_STATUS = "cargoshield.fleet_status.v1"

FLEET_STATUS_TOPIC = "cargoshield/fleet/status"

# Only last-known state may be retained. Transient errors, raw telemetry and one-off diagnostics
# must not be replayed to a subscriber that connects an hour later as if they were current.
RETAINED_SCHEMAS = frozenset({SCHEMA_STATE, SCHEMA_FLEET_STATUS})


class ContractError(ValueError):
    """A payload or identifier that must be rejected at the trust boundary."""


def validate_robot_id(robot_id: Any) -> str:
    if not isinstance(robot_id, str) or not ROBOT_ID_PATTERN.match(robot_id):
        raise ContractError(f"invalid robot_id: {robot_id!r}")
    return robot_id


def topics(robot_id: str) -> dict[str, str]:
    """The five robot-scoped topics. Command is deliberately separate from every read-only topic."""
    robot_id = validate_robot_id(robot_id)
    return {
        "state": f"cargoshield/{robot_id}/state",
        "telemetry": f"cargoshield/{robot_id}/telemetry",
        "events": f"cargoshield/{robot_id}/events",
        "command": f"cargoshield/{robot_id}/command",
    }


def robot_id_from_topic(topic: str) -> str | None:
    """Recover and validate the robot id a message claims. None means 'not one of ours'."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "cargoshield":
        return None
    try:
        return validate_robot_id(parts[1])
    except ContractError:
        return None


def envelope(
    schema: str,
    kind: str,
    robot_id: str,
    *,
    provenance: str,
    source_mode: str,
    observed_ms: int,
    seq: int | None = None,
    event_id: str | None = None,
    received_ms: int | None = None,
) -> dict[str, Any]:
    """The header every fleet payload carries. Raises rather than emit an unlabelled record."""
    validate_robot_id(robot_id)
    if kind not in KINDS:
        raise ContractError(f"unknown kind: {kind!r}")
    if provenance not in PROVENANCE:
        raise ContractError(f"provenance must be one of {sorted(PROVENANCE)}, got {provenance!r}")
    if not isinstance(observed_ms, int) or observed_ms < 0:
        raise ContractError(f"observed_ms must be a non-negative int, got {observed_ms!r}")
    if seq is not None and (not isinstance(seq, int) or seq < 0):
        raise ContractError(f"seq must be a non-negative int, got {seq!r}")
    return {
        "schema": schema,
        "kind": kind,
        "robot_id": robot_id,
        "event_id": event_id or uuid4().hex,
        "seq": seq,
        "observed_ms": observed_ms,
        "received_ms": received_ms if received_ms is not None else int(time() * 1000),
        "provenance": provenance,
        "source_mode": source_mode,
    }


ENVELOPE_FIELDS = ("schema", "kind", "robot_id", "event_id", "observed_ms", "received_ms", "provenance", "source_mode")


def validate_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check an inbound payload at the trust boundary. Raises ContractError with a precise reason."""
    if not isinstance(payload, Mapping):
        raise ContractError("payload must be a JSON object")
    missing = [field for field in ENVELOPE_FIELDS if field not in payload]
    if missing:
        raise ContractError(f"missing envelope fields: {', '.join(missing)}")
    validate_robot_id(payload["robot_id"])
    if payload["kind"] not in KINDS:
        raise ContractError(f"unknown kind: {payload['kind']!r}")
    if payload["provenance"] not in PROVENANCE:
        raise ContractError(f"unknown provenance: {payload['provenance']!r}")
    for field in ("observed_ms", "received_ms"):
        if not isinstance(payload[field], int) or isinstance(payload[field], bool) or payload[field] < 0:
            raise ContractError(f"{field} must be a non-negative int, got {payload[field]!r}")
    seq = payload.get("seq")
    if seq is not None and (not isinstance(seq, int) or isinstance(seq, bool) or seq < 0):
        raise ContractError(f"seq must be a non-negative int or null, got {seq!r}")
    prediction = payload.get("prediction")
    if prediction is not None:
        if not isinstance(prediction, Mapping):
            raise ContractError("prediction must be a JSON object")
        for field in ("confidence", "vibration_score"):
            if field not in prediction:
                continue
            value = prediction[field]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not isfinite(float(value))):
                raise ContractError(f"prediction.{field} must be a finite number")
        confidence = prediction.get("confidence")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise ContractError("prediction.confidence must be between 0 and 1")
        vibration_risk = prediction.get("vibration_risk")
        if vibration_risk is not None and vibration_risk not in {"low", "medium", "high"}:
            raise ContractError("prediction.vibration_risk must be low, medium, or high")
    return dict(payload)


class SequenceGate:
    """Per-robot duplicate and out-of-order decision, with a bounded memory.

    Verdicts: ``accept``, ``duplicate`` (this exact event/seq was already seen) and ``out_of_order``
    (it is older than what has already been accepted). Only ``accept`` may update rolling state;
    the other two are recorded so the operator can see the transport is misbehaving.
    """

    def __init__(self, history: int = 512) -> None:
        self._history = history
        self._seen: dict[str, deque[str]] = {}
        self._seen_set: dict[str, set[str]] = {}
        self._high_water: dict[str, tuple[int, int]] = {}  # robot_id -> (seq, observed_ms)

    def classify(self, robot_id: str, *, seq: int | None, observed_ms: int, event_id: str) -> str:
        seen, order = self._seen.setdefault(robot_id, deque()), self._seen_set.setdefault(robot_id, set())
        key = event_id if seq is None else f"{seq}"
        if key in order:
            return "duplicate"
        high = self._high_water.get(robot_id)
        # An older sample is out of order whether the transport reordered it or a clock stepped back.
        # Either way it must not overwrite fresher rolling state, so it is classified before it is
        # remembered — a reordered burst reports every one of its members, not just the first.
        if high is not None:
            high_seq, high_ms = high
            if (seq is not None and seq < high_seq) or (seq is None and observed_ms < high_ms):
                return "out_of_order"
        seen.append(key)
        order.add(key)
        while len(seen) > self._history:
            order.discard(seen.popleft())
        if high is None or (seq or 0) >= high[0]:
            self._high_water[robot_id] = (seq or 0, observed_ms)
        return "accept"

    def forget(self, robot_id: str) -> None:
        """Drop a robot's memory when it disconnects, so the gate cannot grow with the fleet's history."""
        self._seen.pop(robot_id, None)
        self._seen_set.pop(robot_id, None)
        self._high_water.pop(robot_id, None)


def demo() -> None:
    """Self-check: run with `python -m cargo.contracts`."""
    assert topics("robot-01")["command"] == "cargoshield/robot-01/command"
    assert robot_id_from_topic("cargoshield/robot-01/state") == "robot-01"
    assert robot_id_from_topic("cargoshield/BAD_ID/state") is None
    assert robot_id_from_topic("device/dk1/devkit-twin/telemetry") is None
    for bad in ("", "Robot-01", "a" * 33, "-lead", 7, None):
        try:
            validate_robot_id(bad)
        except ContractError:
            pass
        else:
            raise AssertionError(f"accepted invalid robot_id {bad!r}")

    head = envelope(SCHEMA_TELEMETRY, "raw_telemetry", "robot-01", provenance="SIMULATED",
                    source_mode="simulator", observed_ms=1000, seq=1)
    assert validate_envelope(head)["robot_id"] == "robot-01"
    for field in ENVELOPE_FIELDS:
        broken = {key: value for key, value in head.items() if key != field}
        try:
            validate_envelope(broken)
        except ContractError:
            pass
        else:
            raise AssertionError(f"accepted a payload missing {field}")

    gate = SequenceGate(history=4)
    assert gate.classify("robot-01", seq=1, observed_ms=100, event_id="a") == "accept"
    assert gate.classify("robot-01", seq=1, observed_ms=100, event_id="a") == "duplicate"
    assert gate.classify("robot-01", seq=2, observed_ms=200, event_id="b") == "accept"
    assert gate.classify("robot-01", seq=0, observed_ms=50, event_id="c") == "out_of_order"
    # A second robot's sequence is independent; one robot's transport fault cannot reject another's.
    assert gate.classify("robot-02", seq=1, observed_ms=1, event_id="d") == "accept"
    print("cargo.contracts self-check passed")


if __name__ == "__main__":
    demo()
