"""MQTT adapter for Sensor Studio; CargoShield Python remains authoritative."""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Any

from .controller import MissionController
from .sources import DatasetReplaySource

DIAGNOSTIC_MIN_INTERVAL_S = 1.0

# Seconds between replayed windows. Independent of how many windows the sequence holds,
# so demo pacing can be retuned without changing which data is shown.
REPLAY_INTERVAL_S = 1.0

# Curated dataset demonstration sequence, not an evaluation result: fixed indices into the
# local CareerCon windows, chosen so one run exercises every low/medium/high vibration band
# and both the confident and the below-threshold model responses. Predictions, confidences and
# risk bands stay exactly what the trained model returns for these real stored windows;
# held-out metrics come from reports/metrics.json alone.
DEMO_SEQUENCE = (278, 279, 25, 26, 3, 1, 13, 42, 23, 280)


class CargoMqttService:
    """Expose only explicit project-owned MQTT commands and state topics."""

    def __init__(self, project_root: Path, *, device_id: str = "cargo-robot-01", client=None, interval_s: float = REPLAY_INTERVAL_S) -> None:
        self.controller = MissionController(project_root)
        self.device_id, self.client, self.interval_s = device_id, client, interval_s
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._replay: threading.Thread | None = None
        self._last_diagnostic_s = -DIAGNOSTIC_MIN_INTERVAL_S

    @property
    def command_topic(self) -> str:
        return f"cargoshield/{self.device_id}/command"

    @property
    def state_topic(self) -> str:
        return f"cargoshield/{self.device_id}/state"

    @property
    def devkit_telemetry_topic(self) -> str:
        return "device/+/devkit-twin/telemetry"

    def attach(self, client) -> None:
        self.client = client
        client.on_connect = self._on_connect
        client.on_message = self._on_message

    def _on_connect(self, client, _userdata, _flags, _reason_code, _properties=None) -> None:
        client.subscribe(self.command_topic)
        client.subscribe(self.devkit_telemetry_topic)
        self.publish_state()

    def _diagnostic_due(self) -> bool:
        """One shared 1 Hz publish budget for DevKit telemetry, valid or malformed."""
        now = time.monotonic()
        if now - self._last_diagnostic_s < DIAGNOSTIC_MIN_INTERVAL_S:
            return False
        self._last_diagnostic_s = now
        return True

    def _on_message(self, _client, _userdata, message) -> None:
        # Route by topic before parsing; a malformed telemetry burst must not bypass the throttle,
        # and an operator command must always get its error back immediately.
        is_command = message.topic == self.command_topic
        if not is_command and not self._diagnostic_due():
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.publish_state(error="ignored invalid JSON message")
            return
        if is_command:
            self.handle_command(payload)
        else:
            # Existing DevKit examples only document environmental channel names;
            # do not invent a BMI270 conversion from an unknown MQTT payload.
            self.publish_state(source_diagnostic="DevKit telemetry received; BMI270 schema must be mapped explicitly before inference")

    def publish_state(self, *, error: str | None = None, source_diagnostic: str | None = None) -> None:
        if self.client is None:
            return
        payload: dict[str, Any] = {"schema": "cargoshield.state.v1", "device_id": self.device_id, **self.controller.snapshot()}
        if error:
            payload["error"] = error
        if source_diagnostic:
            payload["source_diagnostic"] = source_diagnostic
        # Retain the mission state so a Sensor Studio flow subscribing later renders immediately;
        # one-off errors and DevKit diagnostics must not stick around as the retained state.
        retain = not (error or source_diagnostic)
        self.client.publish(self.state_topic, json.dumps(payload, separators=(",", ":")), qos=0, retain=retain)

    def handle_command(self, command: dict[str, Any]) -> None:
        action = command.get("action")
        try:
            if action == "set_cargo":
                self.controller.select(cargo_type=str(command["cargo_type"]))
            elif action == "set_mission":
                self.controller.select(pickup=str(command["pickup"]), destination=str(command["destination"]))
            elif action == "set_obstacle":
                self.controller.set_obstacle(float(command["distance"]))
            elif action == "clear_obstacle":
                self.controller.set_obstacle(None)
            elif action == "manual_resume":
                self._paused.clear(); self.controller.manual_resume()
            elif action == "pause":
                self._paused.set(); self.controller.pause()
            elif action == "reset":
                self._stop.set(); self.controller.reset()
            elif action == "start":
                self.start_dataset_demo()
            else:
                raise ValueError(f"unsupported command action: {action!r}")
            # A latched safe stop ends the run for good. Without this, clearing the latch inside the
            # replay's sleep window silently resumes a half-finished run: the operator must press Start.
            if self.controller.latched_stop:
                self._stop.set()
            self.publish_state()
        except (KeyError, TypeError, ValueError) as exc:
            self.publish_state(error=str(exc))

    def start_dataset_demo(self) -> None:
        if self._replay is not None and self._replay.is_alive():
            raise ValueError("dataset replay is already running")
        self._stop.clear(); self._paused.clear()
        self.controller.select(source="dataset")
        self.controller.start()
        if self.controller.status == "ERROR":
            return
        labels = {int(key): value for key, value in json.loads((self.controller.root / "models" / "label_mapping.json").read_text(encoding="utf-8")).items()}
        source = DatasetReplaySource(self.controller.root / "dataset", labels)
        self._replay = threading.Thread(target=self._replay_dataset, args=(source,), daemon=True, name="cargoshield-dataset-replay")
        self._replay.start()

    def _replay_dataset(self, source: DatasetReplaySource) -> None:
        self.controller.mission_running = True
        try:
            available = len(source.indices())
            indices = [index for index in DEMO_SEQUENCE if index < available]
            total = len(indices)
            if total == 0:
                self.controller.status = "ERROR"; self.publish_state(error="dataset replay has no windows"); return
            route = self.controller.route
            if route is None:
                self.controller.status = "ERROR"; self.publish_state(error="route unavailable"); return
            # Spread the sequence across the mission route, which stays fixed for the whole run, so every
            # reported zone is a node of the route the dashboard is showing.
            zones = [route.nodes[min(step * len(route.nodes) // total, len(route.nodes) - 1)] for step in range(total)]
            for step, index in enumerate(indices):
                while self._paused.is_set() and not self._stop.is_set():
                    time.sleep(0.05)
                if self._stop.is_set() or self.controller.latched_stop:
                    return
                window, point = source.window(int(index))
                self.controller.process_dataset_window(window, point.ground_truth or "unknown", zones[step])
                self.controller.last["progress"] = (step + 1) / total
                self.publish_state()
                if self.controller.latched_stop:
                    # End the run at the instant this window latched, before a manual_resume can clear
                    # the latch and let the sleeping thread read it as "carry on". Start begins a new run.
                    self._stop.set()
                    return
                # Wait, but wake immediately on stop so a safe stop or reset ends the run without a lag.
                self._stop.wait(self.interval_s)
            if not self.controller.latched_stop and not self._stop.is_set():
                self.controller.complete(); self.publish_state()
        except Exception as exc:
            self.controller.status = "ERROR"; self.publish_state(error=f"dataset replay failed: {exc!r}")
        finally:
            self.controller.mission_running = False


def main() -> None:
    parser = argparse.ArgumentParser(description="CargoShield MQTT bridge for Bitstream Studio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="cargo-robot-01")
    parser.add_argument("--interval", type=float, default=REPLAY_INTERVAL_S, help="seconds between replayed demo windows")
    args = parser.parse_args()
    import paho.mqtt.client as mqtt
    service = CargoMqttService(Path(__file__).resolve().parents[1], device_id=args.device_id, interval_s=args.interval)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"cargoshield-{args.device_id}")
    service.attach(client)
    client.connect(args.host, args.port, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
