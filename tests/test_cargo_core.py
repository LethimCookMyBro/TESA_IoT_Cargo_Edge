import unittest
from pathlib import Path

from cargo.controller import MissionController
from cargo.decision_engine import CargoPolicy, decide
from cargo.risk_map import ZoneRiskMap
from cargo.routing import DEMO_GRAPH, choose_route


class CargoCoreTests(unittest.TestCase):
    def test_fragile_prefers_stable_route_after_risk_observation(self):
        risks = ZoneRiskMap()
        for _ in range(4):
            risks.observe("A2", 1.0, "rough")
        standard = choose_route(DEMO_GRAPH, risks, "A1", "C2", "standard")
        fragile = choose_route(DEMO_GRAPH, risks, "A1", "C2", "fragile")
        self.assertEqual(standard.nodes, ("A1", "A2", "B2", "C2"))
        self.assertEqual(fragile.nodes, ("A1", "B1", "C1", "C2"))

    def test_safe_stop_latches_until_manual_resume(self):
        stopped = decide(CargoPolicy(), cargo_type="fragile", vibration_risk="low", telemetry_valid=True, confidence=1.0, obstacle_distance=20, latched_stop=False)
        held = decide(CargoPolicy(), cargo_type="fragile", vibration_risk="low", telemetry_valid=True, confidence=1.0, obstacle_distance=200, latched_stop=True)
        self.assertEqual(stopped.action, "SAFE_STOP")
        self.assertEqual(held.action, "SAFE_STOP")

    def test_blocked_destination_has_no_demo_route(self):
        self.assertIsNone(choose_route(DEMO_GRAPH, ZoneRiskMap(), "A1", "C2", "standard", {"C2"}))

    def test_low_confidence_holds_mission(self):
        decision = decide(CargoPolicy(), cargo_type="standard", vibration_risk="low", telemetry_valid=True, confidence=0.1, obstacle_distance=None, latched_stop=False)
        self.assertEqual(decision.action, "HOLD_UNCERTAIN")

    def test_low_confidence_window_is_holding_not_error(self):
        controller = MissionController(Path("."))
        controller._classifier = _LowConfidenceModel()
        result = controller.process_dataset_window(None, "unknown", "A1")
        self.assertEqual(controller.status, "HOLDING")
        self.assertEqual(result["decision"]["action"], "HOLD_UNCERTAIN")
        self.assertEqual(result["decision"]["speed_ratio"], 0.0)
        self.assertEqual(result["risk"], "low")
        self.assertFalse(controller.latched_stop)

    def test_inference_exception_is_error_not_holding(self):
        controller = MissionController(Path("."))
        controller._classifier = _FailingModel()
        result = controller.process_dataset_window(None, "unknown", "A1")
        self.assertEqual(controller.status, "ERROR")
        self.assertIn("dataset inference failed", result["reason"])


class ObstacleContractTests(unittest.TestCase):
    """set_obstacle must answer live from the last real inference, and only while the mission is active."""

    def _active_controller(self, cargo_type="standard"):
        controller = MissionController(Path("."))
        controller._classifier = _HighConfidenceModel()
        controller.select(cargo_type=cargo_type)
        controller.process_dataset_window(None, "unknown", "A1")
        return controller

    def test_stop_distance_safe_stops_and_latches(self):
        controller = self._active_controller()
        controller.set_obstacle(20)
        self.assertEqual(controller.status, "SAFE_STOPPED")
        self.assertEqual(controller.last["decision"]["action"], "SAFE_STOP")
        self.assertEqual(controller.last["decision"]["speed_ratio"], 0.0)
        self.assertTrue(controller.latched_stop)

    def test_warning_distance_slows_down_without_latching(self):
        controller = self._active_controller()
        controller.set_obstacle(50)
        self.assertEqual(controller.status, "SLOWING")
        self.assertEqual(controller.last["decision"]["action"], "SLOW_DOWN")
        self.assertFalse(controller.latched_stop)

    def test_clearing_the_obstacle_does_not_release_the_latch(self):
        controller = self._active_controller()
        controller.set_obstacle(20)
        controller.set_obstacle(None)
        self.assertEqual(controller.status, "SAFE_STOPPED")
        self.assertTrue(controller.latched_stop)
        self.assertIsNone(controller.obstacle_distance)

    def test_manual_resume_is_the_only_way_out_of_a_latched_stop(self):
        controller = self._active_controller()
        controller.set_obstacle(20)
        controller.set_obstacle(None)
        controller.manual_resume()
        self.assertFalse(controller.latched_stop)
        self.assertEqual(controller.status, "READY")
        controller.set_obstacle(200)
        # The policy answer is MOVE, but nothing is stepping windows, so the mission stays READY.
        self.assertEqual(controller.last["decision"]["action"], "MOVE")
        self.assertEqual(controller.status, "READY")

    def test_clearing_an_obstacle_never_claims_movement_without_a_running_mission(self):
        controller = self._active_controller()
        controller.set_obstacle(20)
        controller.manual_resume()
        controller.set_obstacle(None)
        self.assertEqual(controller.status, "READY")
        controller.mission_running = True
        controller.set_obstacle(None)
        self.assertEqual(controller.status, "MOVING")

    def test_cargo_policy_still_shapes_the_live_speed_ratio(self):
        standard = self._active_controller("standard")
        fragile = self._active_controller("fragile")
        standard.set_obstacle(None)
        fragile.set_obstacle(None)
        self.assertEqual(standard.last["decision"]["speed_ratio"], 1.0)
        self.assertEqual(fragile.last["decision"]["speed_ratio"], 0.8)

    def test_idle_mission_records_distance_without_inventing_movement(self):
        controller = MissionController(Path("."))
        controller.set_obstacle(20)
        self.assertEqual(controller.status, "IDLE")
        self.assertEqual(controller.obstacle_distance, 20)
        self.assertEqual(controller.last, {})
        self.assertFalse(controller.latched_stop)

    def test_completed_mission_records_distance_without_reacting(self):
        controller = self._active_controller()
        controller.complete()
        controller.set_obstacle(20)
        self.assertEqual(controller.status, "COMPLETED")
        self.assertEqual(controller.obstacle_distance, 20)
        self.assertEqual(controller.last["decision"]["action"], "MOVE")
        self.assertFalse(controller.latched_stop)

    def test_active_mission_without_a_real_inference_only_records_distance(self):
        # A started mission that has not yet produced a model output must not invent a decision
        # from an obstacle input alone.
        controller = MissionController(Path("."))
        controller.start()
        controller.set_obstacle(20)
        self.assertEqual(controller.status, "READY")
        self.assertEqual(controller.obstacle_distance, 20)
        self.assertNotIn("decision", controller.last)
        self.assertFalse(controller.latched_stop)

    def test_pause_survives_a_mild_obstacle_but_yields_to_a_safe_stop(self):
        controller = self._active_controller()
        controller.pause()
        controller.set_obstacle(50)
        self.assertEqual(controller.status, "PAUSED")
        self.assertEqual(controller.last["decision"]["action"], "SLOW_DOWN")
        controller.set_obstacle(20)
        self.assertEqual(controller.status, "SAFE_STOPPED")
        self.assertTrue(controller.latched_stop)


class _HighConfidenceModel:
    config = {"risk_quantiles": {"medium_to_high": 1.0}}

    @staticmethod
    def predict(_window):
        return {"label": "concrete", "confidence": 0.9, "vibration_score": 0.2, "vibration_risk": "low", "inference_ms": 1.0}


class _LowConfidenceModel:
    config = {"risk_quantiles": {"medium_to_high": 1.0}}

    @staticmethod
    def predict(_window):
        return {"label": "soft_pvc", "confidence": 0.1, "vibration_score": 0.2, "vibration_risk": "low", "inference_ms": 1.0}


class _FailingModel:
    def predict(self, _window):
        raise RuntimeError("model unavailable")


if __name__ == "__main__":
    unittest.main()
