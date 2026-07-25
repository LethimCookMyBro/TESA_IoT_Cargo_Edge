"""Drive the whole demo over a real broker and record reproducible evidence in reports/.

Run the Bitstream Studio broker on 127.0.0.1:1883, then:
    .\\.venv\\Scripts\\python.exe scripts/demo_e2e_check.py
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cargo.mqtt_service import DEMO_SEQUENCE, REPLAY_INTERVAL_S, CargoMqttService

STATE_PATHS = ("status", "cargo_type", "route", "obstacle_distance", "last.label", "last.confidence",
               "last.risk", "last.decision.speed_ratio", "last.decision.action", "last.zone", "risk_map")
CONTROL_COMMANDS = ({"action": "set_cargo", "cargo_type": "fragile"}, {"action": "set_cargo", "cargo_type": "standard"},
                    {"action": "set_mission", "pickup": "A1", "destination": "C2"}, {"action": "set_obstacle", "distance": 50},
                    {"action": "clear_obstacle"}, {"action": "pause"}, {"action": "manual_resume"}, {"action": "reset"})


_MISSING = object()


def _dig(payload: dict, path: str, default=None):
    value = payload
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _has(payload: dict, path: str) -> bool:
    """A dashboard path exists even when its value is legitimately null (no obstacle set)."""
    return _dig(payload, path, _MISSING) is not _MISSING


class Observer:
    """Live subscriber that records every state message the engine publishes."""

    def __init__(self, host: str, port: int, topic: str, client_id: str) -> None:
        self.messages: list[dict] = []
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = lambda c, *_args, **_kw: (c.subscribe(topic), self.ready.set())
        self.client.on_message = lambda _c, _u, message: self.messages.append({**json.loads(message.payload), "_retain_flag": message.retain})
        self.client.connect(host, port, keepalive=15)
        self.client.loop_start()
        if not self.ready.wait(10):
            raise SystemExit("observer did not connect")

    def wait_for(self, predicate, timeout: float = 20.0) -> dict | None:
        """Match only messages that arrive from this call onward; an earlier step's state is not an answer."""
        deadline, cursor = time.monotonic() + timeout, len(self.messages)
        while time.monotonic() < deadline:
            while cursor < len(self.messages):
                message = self.messages[cursor]
                cursor += 1
                if predicate(message):
                    return message
            time.sleep(0.05)
        return None

    def close(self) -> None:
        self.client.loop_stop(); self.client.disconnect()


def retained_snapshot(host: str, port: int, topic: str, client_id: str) -> dict | None:
    """Connect fresh and report only what the broker replays from its retained store."""
    observer = Observer(host, port, topic, client_id)
    try:
        return observer.wait_for(lambda message: message["_retain_flag"], timeout=5)
    finally:
        observer.close()


def websocket_state_probe(host: str, ws_port: int, topic: str, path: str) -> dict:
    """Sensor Studio nodes may only speak MQTT over WebSocket; prove that transport reaches the same state."""
    received, box = threading.Event(), {}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"cargoshield-ws-probe{path.replace('/', '-')}", transport="websockets")
    client.ws_set_options(path=path)
    client.on_connect = lambda c, *_args, **_kw: c.subscribe(topic)
    client.on_message = lambda _c, _u, message: (box.update({"status": json.loads(message.payload)["status"], "retain": message.retain}), received.set())
    try:
        client.connect(host, ws_port, keepalive=10)
        client.loop_start()
        return {"path": path, "connected": True, "retained_state_received": received.wait(8), **box}
    except Exception as exc:
        return {"path": path, "connected": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            client.loop_stop(); client.disconnect()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end CargoShield demo verification")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="cargo-e2e")
    parser.add_argument("--ws-port", type=int, default=8883, help="broker's MQTT-over-WebSocket port, used by Sensor Studio nodes")
    args = parser.parse_args()

    service = CargoMqttService(ROOT, device_id=args.device_id)
    engine = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"cargoshield-e2e-{args.device_id}")
    service.attach(engine)
    engine_ready = threading.Event()
    engine_on_connect = engine.on_connect
    engine.on_connect = lambda c, u, f, rc, p=None: (engine_on_connect(c, u, f, rc, p), engine_ready.set())
    engine.connect(args.host, args.port, keepalive=15)
    engine.loop_start()
    if not engine_ready.wait(10):
        raise SystemExit("engine did not connect")
    observer = Observer(args.host, args.port, service.state_topic, f"observer-{args.device_id}")
    evidence: dict = {"broker": f"{args.host}:{args.port}", "device_id": args.device_id, "state_topic": service.state_topic,
                      "command_topic": service.command_topic, "replay_interval_s": REPLAY_INTERVAL_S,
                      "demo_sequence_length": len(DEMO_SEQUENCE)}

    def command(payload: dict) -> None:
        engine.publish(service.command_topic, json.dumps(payload))

    try:
        # 1. A dashboard that subscribes after the engine started must still render immediately.
        late = retained_snapshot(args.host, args.port, service.state_topic, f"late-{args.device_id}")
        evidence["late_subscriber_retained_state"] = {"received": late is not None, "status": late and late["status"], "retain_flag": late and late["_retain_flag"]}

        # 2. Every operator control accepted over the real broker.
        control_results = []
        for payload in CONTROL_COMMANDS:
            command(payload)
            reply = observer.wait_for(lambda _message: True, timeout=10)
            control_results.append({"command": payload, "accepted": bool(reply) and "error" not in reply, "status": reply and reply["status"]})
        evidence["controls"] = control_results

        # 3. Full curated demo, then the live obstacle contract on top of it.
        started, run_start = time.monotonic(), len(observer.messages)
        command({"action": "start"})
        moving = observer.wait_for(lambda message: _dig(message, "last.decision.action") == "MOVE")
        holding = observer.wait_for(lambda message: _dig(message, "last.decision.action") == "HOLD_UNCERTAIN")
        completed = observer.wait_for(lambda message: message["status"] == "COMPLETED", timeout=30)
        evidence["demo_run"] = {"observed_move": bool(moving), "observed_hold_uncertain": bool(holding),
                                "completed": bool(completed), "elapsed_s": round(time.monotonic() - started, 2),
                                "final_progress": completed and _dig(completed, "last.progress"),
                                "risk_bands_seen": sorted({_dig(m, "last.risk") for m in observer.messages if _dig(m, "last.risk")})}
        evidence["state_paths"] = {path: _has(completed or {}, path) for path in STATE_PATHS}

        # The route of a mission under way must not change, and every reported zone must be a node of it.
        # The completion publish repeats the final window's `last`, so count dataset windows only.
        run = [message for message in observer.messages[run_start:]
               if _dig(message, "last.progress") is not None and message["status"] != "COMPLETED"]
        routes = {tuple(_dig(message, "route.nodes") or ()) for message in run}
        off_route = [{"zone": _dig(message, "last.zone"), "route": _dig(message, "route.nodes")}
                     for message in run if _dig(message, "last.zone") not in (_dig(message, "route.nodes") or [])]
        zones_walked = [_dig(message, "last.zone") for message in run]
        evidence["route_consistency"] = {"windows_observed": len(run),
                                         "expected_windows": len(DEMO_SEQUENCE),
                                         "counted_one_state_per_window": len(run) == len(DEMO_SEQUENCE) == len(zones_walked),
                                         "completion_publishes_counted": sum(message["status"] == "COMPLETED" for message in run),
                                         "distinct_routes_during_replay": len(routes),
                                         "route": sorted(routes)[0] if routes else None,
                                         "zones_walked": zones_walked,
                                         "zones_off_published_route": off_route,
                                         "route_immutable": len(routes) == 1,
                                         "every_zone_on_route": not off_route}

        # 4. Obstacle contract over MQTT: stop latches, clearing does not release it, manual resume does.
        command({"action": "start"})
        observer.wait_for(lambda message: _dig(message, "last.progress") not in (None, 1.0), timeout=15)
        command({"action": "set_obstacle", "distance": 20})
        stopped = observer.wait_for(lambda message: message["status"] == "SAFE_STOPPED")
        command({"action": "clear_obstacle"})
        still_stopped = observer.wait_for(lambda message: message["status"] == "SAFE_STOPPED" and message["obstacle_distance"] is None)
        command({"action": "manual_resume"})
        released = observer.wait_for(lambda message: message["status"] == "READY")
        evidence["obstacle_contract"] = {"safe_stop_latched": bool(stopped), "clear_obstacle_keeps_latch": bool(still_stopped),
                                         "manual_resume_releases": bool(released),
                                         "stopped_action": stopped and _dig(stopped, "last.decision.action"),
                                         "stopped_speed_ratio": stopped and _dig(stopped, "last.decision.speed_ratio")}

        # 5. A safe stop raised inside the replay ends that run for good, and clearing the obstacle
        #    afterwards must not resume it or claim the robot is moving. Only Start runs it again.
        command({"action": "reset"})
        command({"action": "set_obstacle", "distance": 20})
        command({"action": "start"})
        latched = observer.wait_for(lambda message: message["status"] == "SAFE_STOPPED", timeout=30)
        stopped_progress = latched and _dig(latched, "last.progress")
        command({"action": "manual_resume"})
        command({"action": "clear_obstacle"})
        time.sleep(REPLAY_INTERVAL_S * (len(DEMO_SEQUENCE) + 2))
        after = observer.messages[-1]
        evidence["safe_stop_inside_replay"] = {
            "latched_at_progress": stopped_progress,
            "final_status": after["status"], "final_progress": _dig(after, "last.progress"),
            "progress_did_not_advance": _dig(after, "last.progress") == stopped_progress,
            "did_not_complete_itself": after["status"] != "COMPLETED",
            "did_not_claim_movement": after["status"] != "MOVING"}
        command({"action": "clear_obstacle"})
        command({"action": "start"})
        restarted = observer.wait_for(lambda message: message["status"] == "COMPLETED", timeout=30)
        evidence["safe_stop_inside_replay"]["fresh_start_completes"] = bool(restarted)

        # 6. Malformed input: telemetry throttled, commands answered every time, neither retained.
        # Each burst is measured on its own, separated by more than the throttle window, because the
        # throttle is checked before parsing and one burst would otherwise consume the other's budget.
        def telemetry_burst(payload: bytes) -> dict:
            before, started = len(observer.messages), time.monotonic()
            for _ in range(50):
                engine.publish("device/dk1/devkit-twin/telemetry", payload)
            time.sleep(1.5)
            published, elapsed = len(observer.messages) - before, time.monotonic() - started
            # The contract is a rate ceiling, not a fixed count: a burst spanning N seconds may emit ~N states.
            return {"sent": 50, "published": published, "window_s": round(elapsed, 2),
                    "publishes_per_second": round(published / elapsed, 2), "within_rate_limit": published <= elapsed + 1}

        malformed_burst = telemetry_burst(b"{bad")
        time.sleep(1.5)
        valid_burst = telemetry_burst(b'{"sensor":"bmi270"}')
        diagnostics = sum("source_diagnostic" in message for message in observer.messages)
        before_errors = sum("error" in message for message in observer.messages)
        for _ in range(5):
            command({"action": "unsupported"})
        time.sleep(1.0)
        errors = sum("error" in message for message in observer.messages) - before_errors
        retained_after = retained_snapshot(args.host, args.port, service.state_topic, f"retain-{args.device_id}")
        evidence["malformed_inputs"] = {"malformed_telemetry_burst": malformed_burst, "valid_telemetry_burst": valid_burst,
                                        "diagnostic_states_published": diagnostics,
                                        "both_bursts_within_rate_limit": malformed_burst["within_rate_limit"] and valid_burst["within_rate_limit"],
                                        "malformed_commands_sent": 5, "error_states_published": errors,
                                        "every_malformed_command_answered": errors == 5,
                                        "retained_state_is_not_an_error": retained_after is not None and "error" not in retained_after and "source_diagnostic" not in retained_after}

        # 7. The transport a Sensor Studio node will actually use.
        evidence["websocket_transport"] = [websocket_state_probe(args.host, args.ws_port, service.state_topic, path) for path in ("/mqtt", "/")]

        checks = {"late_subscriber_retained_state": evidence["late_subscriber_retained_state"]["received"],
                  "websocket_transport_reaches_state": any(probe.get("retained_state_received") for probe in evidence["websocket_transport"]),
                  "all_controls_accepted": all(result["accepted"] for result in control_results),
                  "demo_shows_move_and_hold": evidence["demo_run"]["observed_move"] and evidence["demo_run"]["observed_hold_uncertain"],
                  "demo_completed": evidence["demo_run"]["completed"],
                  "all_state_paths_present": all(evidence["state_paths"].values()),
                  "route_immutable_during_replay": evidence["route_consistency"]["route_immutable"],
                  "every_zone_on_published_route": evidence["route_consistency"]["every_zone_on_route"],
                  "one_state_counted_per_dataset_window": evidence["route_consistency"]["counted_one_state_per_window"] and evidence["route_consistency"]["completion_publishes_counted"] == 0,
                  "obstacle_contract_holds": all(evidence["obstacle_contract"][key] for key in ("safe_stop_latched", "clear_obstacle_keeps_latch", "manual_resume_releases")),
                  "safe_stop_inside_replay_ends_the_run": all(evidence["safe_stop_inside_replay"][key] for key in ("progress_did_not_advance", "did_not_complete_itself", "did_not_claim_movement", "fresh_start_completes")),
                  "malformed_telemetry_throttled": evidence["malformed_inputs"]["both_bursts_within_rate_limit"],
                  "malformed_commands_answered": evidence["malformed_inputs"]["every_malformed_command_answered"],
                  "errors_and_diagnostics_not_retained": evidence["malformed_inputs"]["retained_state_is_not_an_error"]}
        evidence["checks"] = checks
        evidence["passed"] = all(checks.values())
    finally:
        observer.close()
        engine.loop_stop(); engine.disconnect()

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "demo_e2e_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "checks": evidence["checks"]}, indent=2))
    if not evidence["passed"]:
        raise SystemExit("end-to-end verification failed; see reports/demo_e2e_evidence.json")


if __name__ == "__main__":
    main()
