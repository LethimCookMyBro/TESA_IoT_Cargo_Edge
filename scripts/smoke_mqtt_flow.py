"""Verify the local CargoShield MQTT command/state path against a running broker."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cargo.mqtt_service import CargoMqttService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="cargo-smoke")
    parser.add_argument("--dataset-demo", action="store_true", help="also run the curated demo replay through the real broker")
    args = parser.parse_args()

    received, completed, engine_ready, observer_ready, state = threading.Event(), threading.Event(), threading.Event(), threading.Event(), {}
    service = CargoMqttService(Path(__file__).resolve().parents[1], device_id=args.device_id)
    engine = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"cargoshield-engine-{args.device_id}")
    observer = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"cargoshield-observer-{args.device_id}")

    def on_observer_connect(client, _userdata, _flags, _reason_code, _properties=None):
        client.subscribe(service.state_topic)
        observer_ready.set()

    def on_message(_client, _userdata, message):
        payload = json.loads(message.payload.decode("utf-8"))
        if payload.get("cargo_type") == "fragile":
            state.update(payload)
            received.set()
            if payload.get("status") == "COMPLETED":
                completed.set()

    observer.on_connect, observer.on_message = on_observer_connect, on_message
    service.attach(engine)
    service_on_connect = engine.on_connect

    def on_engine_connect(client, userdata, flags, reason_code, properties=None):
        service_on_connect(client, userdata, flags, reason_code, properties)
        engine_ready.set()

    engine.on_connect = on_engine_connect
    engine.connect(args.host, args.port, keepalive=10)
    observer.connect(args.host, args.port, keepalive=10)
    engine.loop_start(); observer.loop_start()
    try:
        if not (engine_ready.wait(10) and observer_ready.wait(10)):
            raise SystemExit("MQTT clients did not connect")
        engine.publish(service.command_topic, '{"action":"set_cargo","cargo_type":"fragile"}')
        if not received.wait(10):
            raise SystemExit("no fragile state message received")
        if args.dataset_demo:
            engine.publish(service.command_topic, '{"action":"start"}')
            if not completed.wait(30):
                raise SystemExit("dataset demo did not complete")
            assert state["last"]["risk"] in {"low", "medium", "high"}
        assert state["schema"] == "cargoshield.state.v1"
        assert state["device_id"] == args.device_id
        print(json.dumps({"topic": service.state_topic, "cargo_type": state["cargo_type"], "status": state["status"], "risk": state.get("last", {}).get("risk"), "schema": state["schema"]}))
    finally:
        engine.loop_stop(); observer.loop_stop()
        engine.disconnect(); observer.disconnect()


if __name__ == "__main__":
    main()
