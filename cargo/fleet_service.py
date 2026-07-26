"""MQTT front door for the fleet: robot-scoped topics in, retained state and fleet status out.

Read and write paths are separated by topic and by transport. Telemetry and state are read-only
traffic; the only way to change anything is a payload on ``cargoshield/{robot_id}/command``, which
can additionally require a shared token. The read-only history API cannot reach this module at all.
"""

from __future__ import annotations

import json
import threading
from time import time
from typing import Any

from . import contracts
from .fleet import FleetGuardian
from .historian import NullHistorian

# Fleet status is a summary, not a stream: publish it at most this often however busy the fleet is.
FLEET_STATUS_MIN_INTERVAL_S = 1.0


class FleetMqttService:
    """Bridges a paho client to one ``FleetGuardian``. Owns no policy of its own."""

    def __init__(self, guardian: FleetGuardian, historian=None, *, client=None,
                 command_token: str | None = None) -> None:
        self.guardian = guardian
        self.historian = historian or NullHistorian("no historian attached")
        self.client = client
        # When set, a command payload must carry a matching `token`. State and history never do.
        self.command_token = command_token
        self._lock = threading.Lock()
        self._last_fleet_publish = 0.0
        self.commands_rejected = 0

    # ---------- wiring ----------

    def attach(self, client) -> None:
        self.client = client
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, _userdata, _flags, _reason_code, _properties=None) -> None:
        client.subscribe("cargoshield/+/telemetry")
        client.subscribe("cargoshield/+/command")
        self.publish_fleet_status(force=True)

    def _on_disconnect(self, _client, _userdata, *_args) -> None:
        # Every robot's stream is gone, not just one; each monitor clears its own rolling windows.
        for robot_id in list(self.guardian.robots):
            self.guardian.mark_offline(robot_id)

    # ---------- inbound ----------

    def _on_message(self, _client, _userdata, message) -> None:
        robot_id = contracts.robot_id_from_topic(message.topic)
        if robot_id is None:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.guardian.rejected_unknown += 1
            return
        if message.topic.endswith("/command"):
            self.handle_command(robot_id, payload)
        else:
            self.handle_telemetry(robot_id, payload)

    def handle_telemetry(self, robot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # The topic is a claim; the payload's own robot_id is the one that is validated. A payload
        # that disagrees with its topic is refused rather than silently re-attributed.
        if payload.get("robot_id") != robot_id:
            self.guardian.rejected_unknown += 1
            return {"accepted": False, "reason": "robot_id does not match its topic"}
        result = self.guardian.ingest(payload)
        if result.get("accepted"):
            self.publish_robot_state(robot_id)
        self.publish_fleet_status()
        return result

    def handle_command(self, robot_id: str, command: dict[str, Any]) -> dict[str, Any]:
        if self.command_token is not None and command.get("token") != self.command_token:
            self.commands_rejected += 1
            return {"accepted": False, "reason": "command rejected: missing or wrong token"}
        action = command.get("action")
        try:
            if action == "acknowledge":
                released = self.guardian.acknowledge(robot_id, note=str(command.get("note", "")))
                result = {"accepted": True, "released": released}
            elif action == "start_mission":
                route = self.guardian.start_mission(
                    robot_id, pickup=str(command["pickup"]), destination=str(command["destination"]),
                    cargo_type=str(command.get("cargo_type", "standard")),
                    mission_id=str(command["mission_id"]),
                    provenance=str(command.get("provenance", "SIMULATED")))
                result = {"accepted": True, "route": list(route.nodes) if route else None}
            else:
                raise ValueError(f"unsupported command action: {action!r}")
        except (KeyError, TypeError, ValueError, contracts.ContractError) as exc:
            self.commands_rejected += 1
            return {"accepted": False, "reason": str(exc)}
        self.publish_robot_state(robot_id)
        self.publish_fleet_status(force=True)
        return result

    # ---------- outbound ----------

    def _publish(self, topic: str, payload: dict[str, Any], *, retain: bool) -> None:
        if self.client is None:
            return
        self.client.publish(topic, json.dumps(payload, separators=(",", ":"), default=str),
                            qos=0, retain=retain)

    def publish_robot_state(self, robot_id: str) -> None:
        snapshot = self.guardian.snapshot(robot_id)
        if snapshot is None:
            return
        # Last-known state is the one thing worth retaining: a console opening later renders at once.
        self._publish(contracts.topics(robot_id)["state"],
                      {"schema": contracts.SCHEMA_STATE, "generated_ms": int(time() * 1000), **snapshot},
                      retain=True)

    def publish_event(self, robot_id: str, event: dict[str, Any]) -> None:
        """Transient by definition: an event is never retained, so it cannot be replayed as current."""
        self._publish(contracts.topics(robot_id)["events"], event, retain=False)

    def publish_fleet_status(self, *, force: bool = False) -> None:
        with self._lock:
            now = time()
            if not force and now - self._last_fleet_publish < FLEET_STATUS_MIN_INTERVAL_S:
                return
            self._last_fleet_publish = now
        status = {**self.guardian.fleet_status(),
                  "historian": self.historian.health(),
                  "latency": self.guardian.latency_summary()}
        self._publish(contracts.FLEET_STATUS_TOPIC, status, retain=True)


def main() -> None:
    import argparse

    from .db import settings_from_env
    from .historian import Historian

    parser = argparse.ArgumentParser(description="CargoShield fleet guardian MQTT service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--command-token", default=None, help="require this token on command payloads")
    parser.add_argument("--no-historian", action="store_true", help="run with persistence disabled")
    args = parser.parse_args()

    import paho.mqtt.client as mqtt

    historian = NullHistorian("disabled by --no-historian") if args.no_historian else Historian(settings_from_env())
    historian.start()
    guardian = FleetGuardian(sink=historian.submit)
    service = FleetMqttService(guardian, historian, command_token=args.command_token)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="cargoshield-fleet-guardian")
    service.attach(client)
    client.connect(args.host, args.port, keepalive=30)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        historian.stop()


if __name__ == "__main__":
    main()
