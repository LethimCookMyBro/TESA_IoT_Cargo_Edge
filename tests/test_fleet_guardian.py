"""Fleet contracts, health rules and the multi-robot Safety Core. No database needed."""

from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path

from cargo import contracts
from cargo.decision_engine import SELECTED_MINIMUM_CONFIDENCE, CargoPolicy, decide, load_policy
from cargo.fleet import FleetGuardian, sample
from cargo.fleet_service import FleetMqttService
from cargo.health import DEGRADED, HEALTHY, OFFLINE, UNSAFE, HealthMonitor
from cargo.historian import Historian, NullHistorian

ROOT = Path(__file__).resolve().parents[1]
GOOD = {"bmi270.accelX": 0.1, "bmi270.accelY": 0.0, "bmi270.accelZ": 9.81}
CONFIDENT = {"confidence": 0.95, "vibration_risk": "low"}


class ContractTests(unittest.TestCase):
    def test_robot_id_is_validated_at_the_trust_boundary(self):
        for good in ("robot-01", "a1", "robot-alpha", "x" * 32):
            self.assertEqual(contracts.validate_robot_id(good), good)
        for bad in ("", "A1", "robot_01", "-lead", "x" * 33, "a", 7, None, "../etc"):
            with self.subTest(bad=bad), self.assertRaises(contracts.ContractError):
                contracts.validate_robot_id(bad)

    def test_topics_are_robot_scoped_and_command_is_separate(self):
        topics = contracts.topics("robot-01")
        self.assertEqual(topics["state"], "cargoshield/robot-01/state")
        self.assertEqual(topics["telemetry"], "cargoshield/robot-01/telemetry")
        self.assertEqual(topics["events"], "cargoshield/robot-01/events")
        self.assertEqual(topics["command"], "cargoshield/robot-01/command")
        # Command must not be reachable by a read-only subscriber's wildcard on state/telemetry.
        self.assertNotIn(topics["command"], {topics["state"], topics["telemetry"], topics["events"]})

    def test_only_last_known_state_is_retained(self):
        self.assertIn(contracts.SCHEMA_STATE, contracts.RETAINED_SCHEMAS)
        self.assertIn(contracts.SCHEMA_FLEET_STATUS, contracts.RETAINED_SCHEMAS)
        for transient in (contracts.SCHEMA_TELEMETRY, contracts.SCHEMA_EVENT, contracts.SCHEMA_COMMAND):
            self.assertNotIn(transient, contracts.RETAINED_SCHEMAS)

    def test_envelope_refuses_an_unlabelled_record(self):
        with self.assertRaises(contracts.ContractError):
            contracts.envelope(contracts.SCHEMA_TELEMETRY, "raw_telemetry", "robot-01",
                               provenance="MADE_UP", source_mode="x", observed_ms=1)
        with self.assertRaises(contracts.ContractError):
            contracts.envelope(contracts.SCHEMA_TELEMETRY, "not_a_kind", "robot-01",
                               provenance="SIMULATED", source_mode="x", observed_ms=1)
        with self.assertRaises(contracts.ContractError):
            contracts.envelope(contracts.SCHEMA_TELEMETRY, "raw_telemetry", "robot-01",
                               provenance="SIMULATED", source_mode="x", observed_ms=-1)

    def test_every_envelope_field_is_required(self):
        head = contracts.envelope(contracts.SCHEMA_TELEMETRY, "raw_telemetry", "robot-01",
                                  provenance="SIMULATED", source_mode="sim", observed_ms=1, seq=1)
        self.assertEqual(contracts.validate_envelope(head)["robot_id"], "robot-01")
        for field in contracts.ENVELOPE_FIELDS:
            with self.subTest(field=field), self.assertRaises(contracts.ContractError):
                contracts.validate_envelope({k: v for k, v in head.items() if k != field})

    def test_duplicate_and_out_of_order_are_named_not_merged(self):
        gate = contracts.SequenceGate(history=4)
        self.assertEqual(gate.classify("r", seq=1, observed_ms=100, event_id="a"), "accept")
        self.assertEqual(gate.classify("r", seq=1, observed_ms=100, event_id="a"), "duplicate")
        self.assertEqual(gate.classify("r", seq=5, observed_ms=500, event_id="b"), "accept")
        self.assertEqual(gate.classify("r", seq=2, observed_ms=200, event_id="c"), "out_of_order")
        # One robot's disordered stream must not affect another's gate.
        self.assertEqual(gate.classify("other", seq=2, observed_ms=200, event_id="d"), "accept")

    def test_gate_memory_is_bounded(self):
        gate = contracts.SequenceGate(history=8)
        for seq in range(200):
            gate.classify("r", seq=seq, observed_ms=seq, event_id=f"e{seq}")
        self.assertLessEqual(len(gate._seen["r"]), 8)
        gate.forget("r")
        self.assertNotIn("r", gate._seen)

    def test_topic_parser_rejects_foreign_and_malformed_topics(self):
        self.assertEqual(contracts.robot_id_from_topic("cargoshield/robot-01/state"), "robot-01")
        for bad in ("device/dk1/devkit-twin/telemetry", "cargoshield/BAD/state",
                    "cargoshield/robot-01", "cargoshield//state", "nonsense"):
            self.assertIsNone(contracts.robot_id_from_topic(bad))


class HealthRuleTests(unittest.TestCase):
    def monitor(self, **kwargs) -> HealthMonitor:
        return HealthMonitor("robot-01", expected_interval_ms=100, **kwargs)

    def test_healthy_sample_is_healthy(self):
        self.assertEqual(self.monitor().observe(GOOD, observed_ms=1000, now_ms=1000).state, HEALTHY)

    def test_non_finite_and_out_of_range_are_unsafe(self):
        for channels in ({"bmi270.accelX": float("nan")}, {"bmi270.accelX": float("inf")},
                         {"bmi270.accelX": 25.0}, {"dps368.pressureHpa": 5.0},
                         {"sht40.humidityPct": 140.0}, {"bmi270.gyroX": 100.0}):
            with self.subTest(channels=channels):
                self.assertEqual(self.monitor().observe(channels, observed_ms=1, now_ms=1).state, UNSAFE)

    def test_catalog_units_are_enforced_not_datasheet_units(self):
        # 12 would be inside a +/-16 g band but is well inside -20..20 m/s^2; 100 rad/s is not a
        # plausible reading even though 100 deg/s would be. The catalog is the authority.
        self.assertEqual(self.monitor().observe({"bmi270.accelX": 12.0}, observed_ms=1, now_ms=1).state, HEALTHY)
        self.assertEqual(self.monitor().observe({"bmi270.gyroX": 100.0}, observed_ms=1, now_ms=1).state, UNSAFE)

    def test_staleness_scales_with_the_configured_rate(self):
        self.assertEqual(self.monitor().observe(GOOD, observed_ms=0, now_ms=50).state, HEALTHY)
        self.assertEqual(self.monitor().observe(GOOD, observed_ms=0, now_ms=400).state, DEGRADED)
        self.assertEqual(self.monitor().observe(GOOD, observed_ms=0, now_ms=9000).state, UNSAFE)
        # A slower robot is not failing merely for being slower.
        slow = HealthMonitor("r", expected_interval_ms=1000)
        self.assertEqual(slow.observe(GOOD, observed_ms=0, now_ms=400).state, HEALTHY)

    def test_timestamp_regression_is_reported_without_rewinding_state(self):
        monitor = self.monitor()
        monitor.observe(GOOD, observed_ms=5000, now_ms=5000)
        report = monitor.observe(GOOD, observed_ms=4950, now_ms=5000)
        self.assertEqual(report.state, DEGRADED)
        self.assertTrue(any("regression" in reason for reason in report.reasons))
        self.assertEqual(monitor.last_observed_ms, 5000)

    def test_flatline_needs_a_full_window(self):
        monitor = self.monitor(window=4)
        states = [monitor.observe({"bmi270.accelX": 1.0}, observed_ms=i, now_ms=i).state for i in range(6)]
        self.assertEqual(states[0], HEALTHY)
        self.assertIn(DEGRADED, states)

    def test_spike_quarantines_only_the_offending_channel(self):
        monitor = self.monitor()
        monitor.observe({"bmi270.accelX": 0.0, "sht40.humidityPct": 40.0}, observed_ms=0, now_ms=0)
        for step in range(1, 5):
            report = monitor.observe({"bmi270.accelX": 18.0 if step % 2 else -18.0,
                                      "sht40.humidityPct": 40.0}, observed_ms=step, now_ms=step)
        self.assertIn("bmi270.accelX", report.quarantined)
        self.assertIn("sht40.humidityPct", report.channels_checked)
        monitor.release_channel("bmi270.accelX")
        self.assertNotIn("bmi270.accelX", monitor.quarantined)

    def test_cross_sensor_temperature_disagreement(self):
        report = self.monitor().observe({"sht40.temperatureC": 20.0, "bmi270.temperatureC": 60.0},
                                        observed_ms=1, now_ms=1)
        self.assertEqual(report.state, DEGRADED)
        self.assertTrue(any("disagree" in reason for reason in report.reasons))

    def test_quaternion_and_magnetic_sanity(self):
        bad_quat = dict(zip(("bmi270.quatW", "bmi270.quatX", "bmi270.quatY", "bmi270.quatZ"), (0.5, 0, 0, 0)))
        good_quat = dict(zip(("bmi270.quatW", "bmi270.quatX", "bmi270.quatY", "bmi270.quatZ"), (1.0, 0, 0, 0)))
        self.assertEqual(self.monitor().observe(bad_quat, observed_ms=1, now_ms=1).state, UNSAFE)
        self.assertEqual(self.monitor().observe(good_quat, observed_ms=1, now_ms=1).state, HEALTHY)
        strong = dict(zip(("bmm350.magX", "bmm350.magY", "bmm350.magZ"), (900.0, 0.0, 0.0)))
        earth = dict(zip(("bmm350.magX", "bmm350.magY", "bmm350.magZ"), (20.0, 30.0, 25.0)))
        self.assertEqual(self.monitor().observe(strong, observed_ms=1, now_ms=1).state, DEGRADED)
        self.assertEqual(self.monitor().observe(earth, observed_ms=1, now_ms=1).state, HEALTHY)

    def test_disconnect_clears_windows_and_reconnect_restores(self):
        monitor = self.monitor()
        monitor.observe(GOOD, observed_ms=1, now_ms=1)
        monitor.note_disconnect()
        self.assertEqual(monitor.observe(GOOD, observed_ms=2, now_ms=2).state, OFFLINE)
        monitor.note_reconnect()
        self.assertEqual(monitor.observe(GOOD, observed_ms=3, now_ms=3).state, HEALTHY)


class HealthToActionTests(unittest.TestCase):
    """The deterministic mapping. An LLM never participates in any of these transitions."""

    def decide(self, health_state, **kwargs):
        params = dict(cargo_type="standard", vibration_risk="low", telemetry_valid=True,
                      confidence=0.95, obstacle_distance=None, latched_stop=False,
                      health_state=health_state, health_reason="because")
        params.update(kwargs)
        return decide(CargoPolicy(), **params)

    def test_every_health_state_maps_to_one_deterministic_action(self):
        for state, action, latched in ((HEALTHY, "MOVE", False), (DEGRADED, "SLOW_DOWN", False),
                                       (OFFLINE, "HOLD_UNCERTAIN", False), (UNSAFE, "SAFE_STOP", True)):
            with self.subTest(state=state):
                decision = self.decide(state)
                self.assertEqual(decision.action, action)
                self.assertEqual(decision.manual_resume_required, latched)

    def test_transitions_are_pure_and_repeatable(self):
        for state in (HEALTHY, DEGRADED, OFFLINE, UNSAFE):
            first, second = self.decide(state), self.decide(state)
            self.assertEqual(first, second)

    def test_degraded_caps_speed_and_states_the_reason(self):
        decision = self.decide(DEGRADED, vibration_risk="low", cargo_type="standard")
        self.assertLessEqual(decision.speed_ratio, CargoPolicy().degraded_speed_cap)
        self.assertIn("DEGRADED", decision.reason)

    def test_unsafe_health_outranks_a_confident_model(self):
        self.assertEqual(self.decide(UNSAFE, confidence=1.0).action, "SAFE_STOP")

    def test_confidence_threshold_matches_the_validation_selection(self):
        """The compiled-in default and the validation-selected file must never drift apart."""
        path = ROOT / "models" / "confidence_policy.json"
        self.assertTrue(path.is_file(), "run `python -m training.select_confidence`")
        recorded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(recorded["minimum_confidence"], SELECTED_MINIMUM_CONFIDENCE)
        self.assertEqual(CargoPolicy().minimum_confidence, SELECTED_MINIMUM_CONFIDENCE)
        self.assertEqual(load_policy(ROOT / "models").minimum_confidence, SELECTED_MINIMUM_CONFIDENCE)
        self.assertEqual(recorded["selected_on"], "validation")

    def test_load_policy_falls_back_without_the_file(self):
        self.assertEqual(load_policy(ROOT / "does-not-exist").minimum_confidence,
                         SELECTED_MINIMUM_CONFIDENCE)


class FleetIngestTests(unittest.TestCase):
    def guardian(self, **kwargs) -> FleetGuardian:
        return FleetGuardian(expected_interval_ms=100, **kwargs)

    def test_three_robots_run_concurrently_and_stay_separate(self):
        fleet = self.guardian()
        ids = ("robot-alpha", "robot-bravo", "robot-charlie")
        for step in range(1, 6):
            for robot_id in ids:
                result = fleet.ingest(sample(robot_id, seq=step, observed_ms=step * 100,
                                             channels=GOOD, prediction=CONFIDENT), now_ms=step * 100)
                self.assertTrue(result["accepted"])
        self.assertEqual(len(fleet.robots), 3)
        for robot_id in ids:
            self.assertEqual(fleet.robots[robot_id].status, "MOVING")
        # Health monitors and risk maps are distinct objects, not a shared structure.
        monitors = {id(fleet.robots[robot_id].monitor) for robot_id in ids}
        risks = {id(fleet.robots[robot_id].risks) for robot_id in ids}
        self.assertEqual(len(monitors), 3)
        self.assertEqual(len(risks), 3)

    def test_one_robots_failure_does_not_corrupt_another(self):
        fleet = self.guardian()
        fleet.ingest(sample("robot-alpha", seq=1, observed_ms=100, channels=GOOD,
                            prediction=CONFIDENT), now_ms=100)
        for step in range(1, 6):
            fleet.ingest(sample("robot-charlie", seq=step, observed_ms=step * 100,
                                channels={"bmi270.accelX": float("nan")}), now_ms=step * 100)
        self.assertEqual(fleet.robots["robot-charlie"].status, "SAFE_STOPPED")
        self.assertTrue(fleet.robots["robot-charlie"].latched_stop)
        self.assertEqual(fleet.robots["robot-alpha"].status, "MOVING")
        self.assertFalse(fleet.robots["robot-alpha"].latched_stop)
        self.assertEqual(fleet.robots["robot-alpha"].last_health["state"], HEALTHY)

    def test_true_concurrent_ingest_keeps_per_robot_counts_exact(self):
        fleet = self.guardian()
        errors: list[Exception] = []

        def run(robot_id: str) -> None:
            try:
                for step in range(1, 41):
                    fleet.ingest(sample(robot_id, seq=step, observed_ms=step * 100, channels=GOOD,
                                        prediction=CONFIDENT), now_ms=step * 100)
            except Exception as exc:  # pragma: no cover - surfaced by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(f"robot-{name}",))
                   for name in ("alpha", "bravo", "charlie")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(errors, [])
        for name in ("alpha", "bravo", "charlie"):
            self.assertEqual(fleet.robots[f"robot-{name}"].samples, 40)

    def test_malformed_payloads_are_refused_without_raising(self):
        fleet = self.guardian()
        for payload in ({}, {"schema": "x"}, {"robot_id": "robot-01"}, [], "text", 7):
            with self.subTest(payload=payload):
                self.assertFalse(fleet.ingest(payload, now_ms=1)["accepted"])
        self.assertEqual(fleet.robots, {})
        broken = {**sample("robot-01", seq=1, observed_ms=1, channels={}), "channels": "not-a-map"}
        self.assertFalse(fleet.ingest(broken, now_ms=1)["accepted"])

    def test_duplicate_and_out_of_order_samples_do_not_move_a_decision(self):
        fleet = self.guardian()
        first = sample("robot-01", seq=2, observed_ms=200, channels=GOOD, prediction=CONFIDENT)
        self.assertTrue(fleet.ingest(first, now_ms=200)["accepted"])
        self.assertEqual(fleet.ingest(first, now_ms=200)["reason"], "duplicate")
        older = sample("robot-01", seq=1, observed_ms=100, channels={"bmi270.accelX": float("nan")})
        self.assertEqual(fleet.ingest(older, now_ms=200)["reason"], "out_of_order")
        # The rejected unsafe sample must not have latched anything.
        self.assertEqual(fleet.robots["robot-01"].status, "MOVING")
        self.assertFalse(fleet.robots["robot-01"].latched_stop)
        self.assertEqual(fleet.robots["robot-01"].rejected, 2)

    def test_latched_stop_survives_good_data_until_acknowledged(self):
        fleet = self.guardian()
        fleet.ingest(sample("robot-01", seq=1, observed_ms=100,
                            channels={"bmi270.accelX": float("nan")}), now_ms=100)
        self.assertTrue(fleet.robots["robot-01"].latched_stop)
        for step in range(2, 6):
            result = fleet.ingest(sample("robot-01", seq=step, observed_ms=step * 100,
                                         channels=GOOD, prediction=CONFIDENT), now_ms=step * 100)
            self.assertEqual(result["status"], "SAFE_STOPPED")
        self.assertTrue(fleet.acknowledge("robot-01"))
        self.assertFalse(fleet.acknowledge("robot-01"), "a second acknowledge is not a second release")
        after = fleet.ingest(sample("robot-01", seq=9, observed_ms=900, channels=GOOD,
                                    prediction=CONFIDENT), now_ms=900)
        self.assertEqual(after["status"], "MOVING")

    def test_accumulated_risk_changes_the_next_route_not_the_running_one(self):
        fleet = self.guardian()
        first = fleet.start_mission("robot-01", pickup="A1", destination="C2",
                                    cargo_type="fragile", mission_id="m1")
        for step in range(1, 12):
            fleet.ingest(sample("robot-01", seq=step, observed_ms=step * 100, channels=GOOD, zone="B2",
                                prediction={**CONFIDENT, "vibration_risk": "high",
                                            "vibration_score": 1.0, "label": "concrete"}),
                         now_ms=step * 100)
            self.assertEqual(fleet.robots["robot-01"].route, first)
        second = fleet.start_mission("robot-01", pickup="A1", destination="C2",
                                     cargo_type="fragile", mission_id="m2")
        self.assertIsNotNone(second)
        self.assertNotEqual(second.nodes, first.nodes)

    def test_fleet_size_is_capped(self):
        fleet = FleetGuardian(max_robots=2, expected_interval_ms=100)
        for name in ("aa", "bb"):
            self.assertTrue(fleet.ingest(sample(f"robot-{name}", seq=1, observed_ms=1,
                                                channels=GOOD), now_ms=1)["accepted"])
        self.assertFalse(fleet.ingest(sample("robot-cc", seq=1, observed_ms=1,
                                             channels=GOOD), now_ms=1)["accepted"])
        self.assertEqual(len(fleet.robots), 2)

    def test_persistence_failure_never_blocks_or_breaks_a_decision(self):
        def angry(_event):
            raise RuntimeError("database is down")

        fleet = FleetGuardian(sink=angry, expected_interval_ms=100)
        result = fleet.ingest(sample("robot-01", seq=1, observed_ms=100, channels=GOOD,
                                     prediction=CONFIDENT), now_ms=100)
        self.assertEqual(result["status"], "MOVING")
        self.assertGreater(fleet.sink_failures, 0)

    def test_a_slow_sink_does_not_slow_the_decision_materially(self):
        """Persistence is asynchronous: submit must return without waiting on a writer."""
        fast = FleetGuardian(expected_interval_ms=100)
        historian = Historian(max_queue=10_000)  # never started: submit only enqueues
        buffered = FleetGuardian(sink=historian.submit, expected_interval_ms=100)
        for guardian, robot in ((fast, "robot-aa"), (buffered, "robot-bb")):
            for step in range(1, 201):
                guardian.ingest(sample(robot, seq=step, observed_ms=step * 100, channels=GOOD,
                                       prediction=CONFIDENT), now_ms=step * 100)
        self.assertLess(buffered.latency_summary()["p95_ms"], 5.0)

    def test_latency_summary_is_labelled_as_a_simulator_measurement(self):
        fleet = self.guardian()
        fleet.ingest(sample("robot-01", seq=1, observed_ms=1, channels=GOOD), now_ms=1)
        summary = fleet.latency_summary()
        self.assertIn("not board performance", summary["measurement"])
        self.assertGreater(summary["samples"], 0)

    def test_fleet_status_counts_every_robot_exactly_once(self):
        fleet = self.guardian()
        fleet.ingest(sample("robot-aa", seq=1, observed_ms=100, channels=GOOD,
                            prediction=CONFIDENT), now_ms=100)
        fleet.ingest(sample("robot-bb", seq=1, observed_ms=100,
                            channels={"bmi270.accelX": float("nan")}), now_ms=100)
        status = fleet.fleet_status()
        self.assertEqual(status["robot_count"], 2)
        self.assertEqual(sum(status["counts"].values()), 2)
        self.assertEqual(status["schema"], contracts.SCHEMA_FLEET_STATUS)


class _RecordingClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append({"topic": topic, "payload": json.loads(payload),
                               "qos": qos, "retain": retain})

    def subscribe(self, topic):
        pass


class FleetServiceTests(unittest.TestCase):
    def service(self, **kwargs):
        guardian = FleetGuardian(expected_interval_ms=100)
        client = _RecordingClient()
        service = FleetMqttService(guardian, NullHistorian(), client=client, **kwargs)
        return service, guardian, client

    def test_state_is_retained_but_events_are_not(self):
        service, _guardian, client = self.service()
        service.handle_telemetry("robot-01", sample("robot-01", seq=1, observed_ms=100,
                                                    channels=GOOD, prediction=CONFIDENT))
        states = [message for message in client.published if message["topic"].endswith("/state")]
        self.assertTrue(states)
        self.assertTrue(all(message["retain"] for message in states))
        service.publish_event("robot-01", {"kind": "health_event"})
        events = [message for message in client.published if message["topic"].endswith("/events")]
        self.assertTrue(events)
        self.assertFalse(any(message["retain"] for message in events))

    def test_fleet_status_is_retained_on_the_fleet_topic(self):
        service, _guardian, client = self.service()
        service.publish_fleet_status(force=True)
        published = [m for m in client.published if m["topic"] == contracts.FLEET_STATUS_TOPIC]
        self.assertTrue(published)
        self.assertTrue(published[-1]["retain"])

    def test_a_payload_that_disagrees_with_its_topic_is_refused(self):
        service, guardian, _client = self.service()
        payload = sample("robot-02", seq=1, observed_ms=100, channels=GOOD)
        result = service.handle_telemetry("robot-01", payload)
        self.assertFalse(result["accepted"])
        self.assertEqual(guardian.robots, {})

    def test_commands_require_a_token_when_one_is_configured(self):
        service, guardian, _client = self.service(command_token="secret")
        guardian.ingest(sample("robot-01", seq=1, observed_ms=100,
                               channels={"bmi270.accelX": float("nan")}), now_ms=100)
        self.assertTrue(guardian.robots["robot-01"].latched_stop)
        refused = service.handle_command("robot-01", {"action": "acknowledge"})
        self.assertFalse(refused["accepted"])
        self.assertTrue(guardian.robots["robot-01"].latched_stop, "an unauthorised command changed state")
        allowed = service.handle_command("robot-01", {"action": "acknowledge", "token": "secret"})
        self.assertTrue(allowed["accepted"])
        self.assertFalse(guardian.robots["robot-01"].latched_stop)

    def test_unknown_commands_are_refused_without_raising(self):
        service, _guardian, _client = self.service()
        for command in ({"action": "shutdown"}, {"action": "start_mission"}, {}, {"action": None}):
            with self.subTest(command=command):
                self.assertFalse(service.handle_command("robot-01", command)["accepted"])


class HistorianQueueTests(unittest.TestCase):
    def test_queue_is_bounded_and_drops_are_counted_not_silent(self):
        historian = Historian(max_queue=10)  # never started, so nothing drains it
        accepted = sum(historian.submit({"kind": "health_event", "n": index}) for index in range(50))
        self.assertEqual(accepted, 10)
        self.assertEqual(historian.dropped, 40)
        health = historian.health()
        self.assertEqual(health["queue_depth"], 10)
        self.assertEqual(health["queue_capacity"], 10)
        self.assertEqual(health["dropped"], 40)

    def test_submit_never_raises_and_never_blocks(self):
        historian = Historian(max_queue=1)
        started = time.perf_counter()
        for index in range(2000):
            self.assertIsInstance(historian.submit({"kind": "health_event", "n": index}), bool)
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_null_historian_matches_the_surface_and_keeps_nothing(self):
        historian = NullHistorian("no database in this profile")
        self.assertFalse(historian.submit({"kind": "health_event"}))
        historian.start(); historian.stop(); self.assertTrue(historian.flush())
        self.assertEqual(historian.health()["written"], 0)
        self.assertEqual(historian.health()["last_error"], "no database in this profile")

    def test_non_finite_channels_are_made_storable_without_losing_the_fact(self):
        stored = json.loads(Historian._storable_channels(
            {"bmi270.accelX": float("nan"), "bmi270.accelZ": 9.81}))
        self.assertIsNone(stored["bmi270.accelX"])
        self.assertEqual(stored["bmi270.accelZ"], 9.81)
        self.assertEqual(stored["_nonfinite"], ["bmi270.accelX"])


if __name__ == "__main__":
    unittest.main()
