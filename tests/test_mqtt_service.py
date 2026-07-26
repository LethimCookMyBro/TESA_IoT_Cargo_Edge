import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


from cargo.mqtt_service import DEMO_SEQUENCE, REPLAY_INTERVAL_S, CargoMqttService
from cargo.routing import DEMO_GRAPH, choose_route


class _EmptySource:
    """Mirrors DatasetReplaySource's real surface: a length, and windows by index."""

    def __len__(self):
        return 0

    def window(self, index):
        raise IndexError(index)


class FakeClient:
    def __init__(self):
        self.published = []
        self.subscriptions = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload), qos, retain))

    def subscribe(self, topic):
        self.subscriptions.append(topic)


class CargoMqttServiceTests(unittest.TestCase):
    def test_operator_command_updates_engine_and_publishes_state(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service.handle_command({"action": "set_cargo", "cargo_type": "fragile"})
        self.assertEqual(service.controller.cargo_type, "fragile")
        self.assertEqual(client.published[-1][0], service.state_topic)

    def test_unknown_command_surfaces_an_error_state(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service.handle_command({"action": "unsupported"})
        self.assertIn("error", client.published[-1][1])

    def test_rejected_cargo_type_leaves_the_service_usable(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service.handle_command({"action": "set_cargo", "cargo_type": "banana"})
        self.assertIn("error", client.published[-1][1])
        self.assertEqual(service.controller.cargo_type, "standard")
        service.handle_command({"action": "set_mission", "pickup": "A1", "destination": "C2"})
        self.assertNotIn("error", client.published[-1][1])
        service.handle_command({"action": "set_cargo", "cargo_type": "fragile"})
        self.assertEqual(service.controller.cargo_type, "fragile")
        self.assertNotIn("error", client.published[-1][1])

    def test_rejected_destination_leaves_the_route_intact(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service.handle_command({"action": "set_mission", "pickup": "A1", "destination": "C2"})
        route = service.controller.route
        service.handle_command({"action": "set_mission", "pickup": "A1", "destination": "Z9"})
        self.assertIn("error", client.published[-1][1])
        self.assertEqual(service.controller.destination, "C2")
        self.assertEqual(service.controller.route, route)

    def test_devkit_telemetry_diagnostics_are_throttled(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        message = SimpleNamespace(topic="device/dk1/devkit-twin/telemetry", payload=b'{"sensor":"bmi270"}')
        for _ in range(50):
            service._on_message(None, None, message)
        self.assertEqual(sum("source_diagnostic" in payload for _, payload, _, _ in client.published), 1)
        service.handle_command({"action": "set_cargo", "cargo_type": "fragile"})
        self.assertEqual(client.published[-1][1]["cargo_type"], "fragile")

    def test_malformed_devkit_telemetry_is_throttled_too(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        message = SimpleNamespace(topic="device/dk1/devkit-twin/telemetry", payload=b"{bad")
        for _ in range(50):
            service._on_message(None, None, message)
        self.assertEqual(len(client.published), 1)

    def test_malformed_command_is_never_throttled(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        message = SimpleNamespace(topic=service.command_topic, payload=b"{bad")
        for _ in range(5):
            service._on_message(None, None, message)
        self.assertEqual(sum(payload.get("error") == "ignored invalid JSON message" for _, payload, _, _ in client.published), 5)

    def test_normal_state_is_retained_for_late_subscribers(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service.handle_command({"action": "set_cargo", "cargo_type": "fragile"})
        topic, payload, _, retain = client.published[-1]
        self.assertEqual(topic, service.state_topic)
        self.assertTrue(retain)
        self.assertNotIn("error", payload)

    def test_error_and_diagnostic_states_are_not_retained(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service.handle_command({"action": "unsupported"})
        self.assertIn("error", client.published[-1][1])
        self.assertFalse(client.published[-1][3])
        service._on_message(None, None, SimpleNamespace(topic="device/dk1/devkit-twin/telemetry", payload=b'{"sensor":"bmi270"}'))
        self.assertIn("source_diagnostic", client.published[-1][1])
        self.assertFalse(client.published[-1][3])

    def test_empty_replay_sets_error(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client)
        service._replay_dataset(_EmptySource())
        self.assertEqual(service.controller.status, "ERROR")
        self.assertEqual(client.published[-1][1]["error"], "dataset replay has no windows")
        self.assertNotIn("COMPLETED", [payload["status"] for _, payload, _, _ in client.published])

    def test_start_replays_real_dataset_through_existing_engine(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client, interval_s=0)
        service.handle_command({"action": "start"})
        assert service._replay is not None
        service._replay.join(timeout=30)
        self.assertEqual(service.controller.status, "COMPLETED")


class DemoReplaySequenceTests(unittest.TestCase):
    """The curated demonstration sequence must keep showing the behaviour the demo claims."""

    def _run(self, cargo_type="standard"):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client, interval_s=0)
        service.handle_command({"action": "set_cargo", "cargo_type": cargo_type})
        service.handle_command({"action": "start"})
        service._replay.join(timeout=30)
        # Full state payloads, so a test can compare last.zone against the route published beside it.
        steps = [payload for _, payload, _, _ in client.published if isinstance(payload.get("last"), dict) and "progress" in payload["last"]]
        return service, steps

    @staticmethod
    def _await_first_window(service, timeout=30):
        """The first window pays for loading the model; never time a replay against a fixed sleep."""
        deadline = time.monotonic() + timeout
        while service.controller.last.get("progress") is None and time.monotonic() < deadline:
            time.sleep(0.02)
        return service.controller.last.get("progress")

    def test_demo_duration_stays_watchable(self):
        seconds = len(DEMO_SEQUENCE) * REPLAY_INTERVAL_S
        self.assertGreaterEqual(seconds, 8)
        self.assertLessEqual(seconds, 12)

    def test_replay_interval_is_configurable_independently_of_window_count(self):
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=FakeClient(), interval_s=0.25)
        self.assertEqual(service.interval_s, 0.25)
        self.assertEqual(CargoMqttService(root, client=FakeClient()).interval_s, REPLAY_INTERVAL_S)

    def test_sequence_shows_move_hold_and_every_risk_band(self):
        _, steps = self._run()
        self.assertEqual(len(steps), len(DEMO_SEQUENCE) + 1)  # one per window plus the completion publish
        actions = {step["last"]["decision"]["action"] for step in steps}
        self.assertIn("MOVE", actions)
        self.assertIn("HOLD_UNCERTAIN", actions)
        self.assertEqual({step["last"]["risk"] for step in steps}, {"low", "medium", "high"})

    def test_progress_runs_zero_to_one_without_gaps(self):
        _, steps = self._run()
        progress = [step["last"]["progress"] for step in steps[:len(DEMO_SEQUENCE)]]
        self.assertEqual(progress, [(i + 1) / len(DEMO_SEQUENCE) for i in range(len(DEMO_SEQUENCE))])
        self.assertEqual(progress[-1], 1.0)

    def test_route_is_immutable_for_the_whole_replay(self):
        for cargo_type in ("standard", "fragile"):
            with self.subTest(cargo_type=cargo_type):
                _, steps = self._run(cargo_type)
                routes = {tuple(step["route"]["nodes"]) for step in steps}
                self.assertEqual(len(routes), 1, f"route changed mid-replay: {routes}")

    def test_every_reported_zone_belongs_to_the_route_published_with_it(self):
        for cargo_type in ("standard", "fragile"):
            with self.subTest(cargo_type=cargo_type):
                _, steps = self._run(cargo_type)
                mismatched = [(step["last"]["zone"], step["route"]["nodes"]) for step in steps if step["last"]["zone"] not in step["route"]["nodes"]]
                self.assertEqual(mismatched, [], f"zones outside the published route: {mismatched}")

    def test_fragile_replay_never_walks_zones_off_a_stability_first_route(self):
        _, steps = self._run("fragile")
        route = steps[0]["route"]["nodes"]
        walked = [step["last"]["zone"] for step in steps]
        off_route = sorted({zone for zone in walked if zone not in route})
        self.assertEqual(off_route, [], f"route {route} but walked {walked}")
        if route == ["A1", "B1", "C1", "C2"]:
            self.assertNotIn("A2", walked)
            self.assertNotIn("B2", walked)

    def test_zone_walk_advances_along_the_route_without_backtracking(self):
        service, steps = self._run()
        planned = list(service.controller.route.nodes)
        walked = [step["last"]["zone"] for step in steps[:len(DEMO_SEQUENCE)]]
        # No filtering: every walked zone must be on the planned route, in order.
        self.assertTrue(set(walked) <= set(planned), f"walked {walked} off route {planned}")
        positions = [planned.index(zone) for zone in walked]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(walked[0], "A1")
        self.assertEqual(walked[-1], "C2")

    def test_a_new_replay_replans_from_the_learned_risk_map(self):
        service, steps = self._run("fragile")
        first_route = steps[0]["route"]["nodes"]
        controller = service.controller
        # Make the first route's middle expensive, exactly the way replay observations do.
        for zone in first_route[1:-1]:
            for _ in range(10):
                controller.risks.observe(zone, 1.0, "rough")
        # The new run must plan from the risk map as it stands now, then keep that route for the whole run.
        expected = choose_route(DEMO_GRAPH, controller.risks, controller.pickup, controller.destination, controller.cargo_type)
        service.interval_s = 0
        service.handle_command({"action": "start"})
        service._replay.join(timeout=30)
        self.assertNotEqual(controller.route.nodes, tuple(first_route))
        self.assertEqual(controller.route, expected)

    def test_cargo_policy_changes_the_speed_ratio_for_the_same_windows(self):
        _, standard = self._run("standard")
        _, fragile = self._run("fragile")
        moving = [(s["last"]["decision"]["speed_ratio"], f["last"]["decision"]["speed_ratio"]) for s, f in zip(standard, fragile) if s["last"]["decision"]["action"] == "MOVE"]
        self.assertTrue(moving)
        self.assertTrue(all(fragile_speed < standard_speed for standard_speed, fragile_speed in moving))

    def test_pause_holds_the_replay_and_manual_resume_finishes_it(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client, interval_s=0.05)
        service.handle_command({"action": "start"})
        self.assertIsNotNone(self._await_first_window(service))
        service.handle_command({"action": "pause"})
        time.sleep(0.3)
        paused_progress = service.controller.last.get("progress")
        time.sleep(0.4)
        self.assertEqual(service.controller.last.get("progress"), paused_progress)
        self.assertEqual(service.controller.status, "PAUSED")
        service.handle_command({"action": "manual_resume"})
        service._replay.join(timeout=30)
        self.assertEqual(service.controller.status, "COMPLETED")
        self.assertEqual(service.controller.last["progress"], 1.0)

    def test_safe_stop_during_replay_halts_it_until_manual_resume(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client, interval_s=0.05)
        service.handle_command({"action": "start"})
        self._await_first_window(service)
        service.handle_command({"action": "set_obstacle", "distance": 20})
        service._replay.join(timeout=30)
        self.assertEqual(service.controller.status, "SAFE_STOPPED")
        self.assertTrue(service.controller.latched_stop)
        self.assertLess(service.controller.last["progress"], 1.0)
        service.handle_command({"action": "clear_obstacle"})
        self.assertTrue(service.controller.latched_stop)
        service.handle_command({"action": "manual_resume"})
        self.assertFalse(service.controller.latched_stop)

    def test_safe_stop_raised_inside_the_replay_ends_that_run_for_good(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client, interval_s=0.4)
        service.handle_command({"action": "set_obstacle", "distance": 20})
        self.assertEqual(service.controller.status, "IDLE")
        service.handle_command({"action": "start"})
        deadline = time.monotonic() + 30
        while service.controller.status != "SAFE_STOPPED" and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(service.controller.status, "SAFE_STOPPED")
        stopped_at = service.controller.last["progress"]
        service.handle_command({"action": "manual_resume"})
        service.handle_command({"action": "clear_obstacle"})
        service._replay.join(timeout=10)
        self.assertFalse(service._replay.is_alive())
        time.sleep(1.0)
        self.assertEqual(service.controller.last["progress"], stopped_at)
        self.assertLess(stopped_at, 1.0)
        self.assertNotEqual(service.controller.status, "COMPLETED")
        # The replay is dead, so the dashboard must not be told the robot is moving.
        self.assertNotEqual(service.controller.status, "MOVING")
        self.assertFalse(service.controller.mission_running)
        # Only a fresh Start runs the demo again.
        service.interval_s = 0
        service.handle_command({"action": "start"})
        service._replay.join(timeout=30)
        self.assertEqual(service.controller.status, "COMPLETED")
        self.assertEqual(service.controller.last["progress"], 1.0)

    def test_manual_resume_after_a_safe_stop_does_not_silently_restart_the_replay(self):
        client = FakeClient()
        root = Path(__file__).resolve().parents[1]
        service = CargoMqttService(root, client=client, interval_s=0.4)
        service.handle_command({"action": "start"})
        self._await_first_window(service)
        service.handle_command({"action": "set_obstacle", "distance": 20})
        service.handle_command({"action": "manual_resume"})
        service._replay.join(timeout=10)
        self.assertFalse(service._replay.is_alive())
        stalled = service.controller.last.get("progress")
        time.sleep(1.0)
        self.assertEqual(service.controller.last.get("progress"), stalled)
        self.assertLess(stalled, 1.0)
        # Restarting with the obstacle still in place must latch again, not drive through it.
        service.handle_command({"action": "start"})
        service._replay.join(timeout=30)
        self.assertEqual(service.controller.status, "SAFE_STOPPED")
        service.handle_command({"action": "clear_obstacle"})
        service.handle_command({"action": "manual_resume"})
        service.interval_s = 0
        service.handle_command({"action": "start"})
        service._replay.join(timeout=30)
        self.assertEqual(service.controller.status, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
