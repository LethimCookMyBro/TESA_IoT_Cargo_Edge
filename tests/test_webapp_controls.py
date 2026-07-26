"""Every control the operator page can emit must be a command the engine accepts.

The payloads are read out of `webapp/controls.js` itself via node, so the page and the engine cannot
drift apart silently. Skipped when node is unavailable.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from cargo.mqtt_service import CargoMqttService

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"

# Exercises every exported builder, including both cargo types and a stop-region distance.
EXTRACT = """
import { COMMANDS, CARGO_TYPES, ZONES, DISPLAY_PATHS } from './controls.js';
const payloads = [
  COMMANDS.start(), COMMANDS.pause(), COMMANDS.manual_resume(), COMMANDS.reset(),
  ...CARGO_TYPES.map((type) => COMMANDS.set_cargo(type)),
  COMMANDS.set_mission(ZONES[0], ZONES.at(-1)),
  COMMANDS.set_obstacle('20'), COMMANDS.set_obstacle(50), COMMANDS.clear_obstacle(),
];
console.log(JSON.stringify({ payloads, zones: ZONES, display_paths: DISPLAY_PATHS }));
"""


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append(json.loads(payload))

    def subscribe(self, topic):
        pass


def _extract() -> dict:
    script = WEBAPP / "_extract_controls.mjs"
    script.write_text(EXTRACT, encoding="utf-8")
    try:
        result = subprocess.run([shutil.which("node"), str(script)], capture_output=True, text=True, timeout=60, cwd=str(WEBAPP))
    finally:
        script.unlink(missing_ok=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed reading webapp/controls.js: {result.stderr.strip()}")
    return json.loads(result.stdout)


@unittest.skipIf(shutil.which("node") is None, "node is required to read webapp/controls.js")
class WebappControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = _extract()

    def test_every_page_control_is_accepted_by_the_engine(self):
        for payload in self.contract["payloads"]:
            with self.subTest(payload=payload):
                client = FakeClient()
                service = CargoMqttService(ROOT, client=client, interval_s=0)
                service.handle_command(payload)
                self.assertNotIn("error", client.published[-1], f"engine rejected {payload}")

    def test_page_zone_options_exist_in_the_demo_map(self):
        from cargo.routing import DEMO_GRAPH

        self.assertEqual(sorted(self.contract["zones"]), sorted(DEMO_GRAPH))

    def test_operator_commands_wait_for_broker_ack(self):
        source = (WEBAPP / "app.js").read_text(encoding="utf-8")
        self.assertIn("client.publish(topic.command, payload, { qos: 1 })", source)

    def test_operator_ui_labels_recorded_input_as_dataset_replay(self):
        index = (WEBAPP / "index.html").read_text(encoding="utf-8")
        fleet = (WEBAPP / "fleet.html").read_text(encoding="utf-8")
        app = (WEBAPP / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("ปฏิบัติการสด", index + fleet)
        self.assertIn("เริ่ม Dataset Replay", index)
        self.assertIn('id="progress-label"', index)
        self.assertIn("ไม่ใช่การวัดสด", app)
        self.assertIn("ความคืบหน้าการ Replay", app)

    def test_every_display_path_exists_in_a_real_state_payload(self):
        client = FakeClient()
        service = CargoMqttService(ROOT, client=client, interval_s=0)
        service.handle_command({"action": "start"})
        service._replay.join(timeout=30)
        state = client.published[-1]
        for name, path in self.contract["display_paths"].items():
            with self.subTest(path=path):
                value = state
                for key in path.split("."):
                    self.assertIsInstance(value, dict, f"{name}: {path} stops at {key}")
                    self.assertIn(key, value, f"{name}: {path} missing {key}")
                    value = value[key]


if __name__ == "__main__":
    unittest.main()
