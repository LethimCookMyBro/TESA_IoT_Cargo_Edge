"""The 3D console must not drift away from the engine it is drawing.

Everything asserted here is read out of `webapp/controls.js` with node, so the scene's floor plan,
its obstacle colour bands and its "may the robot be animated?" rule stay pinned to the Python
policy, the demo map and the trained model's label set. Skipped when node is unavailable.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from cargo.controller import STATUS_BY_ACTION
from cargo.decision_engine import CargoPolicy
from cargo.routing import DEMO_GRAPH

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"

# Statuses the engine can put on the wire, plus the two terminal ones it sets directly.
STATUSES = sorted(set(STATUS_BY_ACTION.values()) | {"IDLE", "READY", "COMPLETED", "PAUSED", "ERROR"})

# Every action `cargo.decision_engine.decide` can return.
ACTIONS = sorted(STATUS_BY_ACTION)

EXTRACT = """
import { OBSTACLE_POLICY, ZONE_POSITIONS, DEMO_EDGES, SURFACE_TINTS, obstacleTone, motion,
  routePosition, PROTECTION_STATES, protectionState, actionTone, explain, CAMERA_MODES,
  ROUTE_WIDTHS } from './controls.js';
const statuses = %s;
const actions = %s;
const window = (extra) => ({
  status: 'MOVING', cargo_type: 'fragile', obstacle_distance: null,
  last: { label: 'carpet', risk: 'high', confidence: 0.62,
          decision: { action: 'SLOW_DOWN', speed_ratio: 0.45, reason: 'engine reason' } },
  ...extra,
});
console.log(JSON.stringify({
  policy: OBSTACLE_POLICY,
  zones: Object.keys(ZONE_POSITIONS),
  positions: ZONE_POSITIONS,
  edges: DEMO_EDGES,
  surfaces: Object.keys(SURFACE_TINTS),
  tones: [null, 0, 30, 30.1, 80, 80.1, 200].map((d) => [d, obstacleTone(d)]),
  motion: statuses.map((status) => [status, motion({ status, last: { decision: { speed_ratio: 0.45 } } })]),
  moving_without_decision: motion({ status: 'MOVING' }),
  route: [
    ['A1', 0.0], ['A1', 0.1], ['A2', 0.4], ['A2', 0.95], ['B2', 0.5], ['C2', 0.9], ['C2', 1.0], ['ZZ', 0.3],
  ].map(([zone, progress]) => [zone, progress, routePosition(['A1', 'A2', 'B2', 'C2'], zone, progress)]),
  no_route: routePosition([], 'A1', 0.5),
  no_progress: routePosition(['A1', 'A2', 'B2', 'C2'], 'B2', null),
  protection_keys: Object.keys(PROTECTION_STATES),
  protection: statuses.map((status) => [status, protectionState({ status })]),
  protection_unknown: protectionState({ status: 'NOT_A_STATUS' }),
  protection_absent: protectionState({}),
  action_tones: actions.map((action) => [action, actionTone(action)]),
  action_tone_unknown: actionTone(undefined),
  explain_slow: explain(window({})),
  explain_stop: explain(window({
    obstacle_distance: 20,
    last: { label: 'concrete', risk: 'low', confidence: 0.9,
            decision: { action: 'SAFE_STOP', speed_ratio: 0, reason: 'obstacle' } },
  })),
  explain_hold: explain(window({
    last: { label: 'wood', risk: 'medium', confidence: 0.31,
            decision: { action: 'HOLD_UNCERTAIN', speed_ratio: 0, reason: 'low confidence' } },
  })),
  explain_empty: explain({ status: 'IDLE' }),
  camera_modes: CAMERA_MODES,
  route_widths: ROUTE_WIDTHS,
}));
""" % (json.dumps(STATUSES), json.dumps(ACTIONS))


def _extract() -> dict:
    script = WEBAPP / "_extract_visual.mjs"
    script.write_text(EXTRACT, encoding="utf-8")
    try:
        # UTF-8 explicitly: the operator labels are Thai, and `text=True` would otherwise decode
        # node's stdout with the system ANSI codepage (cp874 here) and fail on the first Thai byte.
        result = subprocess.run([shutil.which("node"), str(script)], capture_output=True, text=True,
                                encoding="utf-8", timeout=60, cwd=str(WEBAPP))
    finally:
        script.unlink(missing_ok=True)
    if result.returncode != 0:
        raise AssertionError(f"node failed reading webapp/controls.js: {result.stderr.strip()}")
    return json.loads(result.stdout)


@unittest.skipIf(shutil.which("node") is None, "node is required to read webapp/controls.js")
class WebappVisualContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = _extract()

    def test_obstacle_bands_match_the_engine_policy(self):
        policy = CargoPolicy()
        self.assertEqual(self.contract["policy"]["stop_distance"], policy.stop_distance)
        self.assertEqual(self.contract["policy"]["warning_distance"], policy.warning_distance)

    def test_obstacle_tone_switches_on_the_engine_thresholds(self):
        self.assertEqual(
            [tone for _distance, tone in self.contract["tones"]],
            ["none", "stop", "stop", "warn", "warn", "clear", "clear"],
        )

    def test_floor_plan_covers_the_demo_map_exactly(self):
        self.assertEqual(sorted(self.contract["zones"]), sorted(DEMO_GRAPH))
        expected = {frozenset((node, neighbor)) for node, edges in DEMO_GRAPH.items() for neighbor, _cost in edges}
        self.assertEqual({frozenset(edge) for edge in self.contract["edges"]}, expected)
        self.assertEqual(len(self.contract["edges"]), len(expected), "an aisle is drawn twice")

    def test_every_zone_has_a_distinct_position(self):
        points = [tuple(point) for point in self.contract["positions"].values()]
        self.assertEqual(len(set(points)), len(points))

    def test_surface_tints_cover_the_trained_label_set(self):
        labels = set(json.loads((ROOT / "models" / "label_mapping.json").read_text(encoding="utf-8")).values())
        self.assertEqual(set(self.contract["surfaces"]), labels)

    def test_only_moving_and_slowing_may_be_animated(self):
        animated = {status for status, result in self.contract["motion"] if result["animate"]}
        self.assertEqual(animated, {"MOVING", "SLOWING"})

    def test_animation_speed_follows_the_engine_speed_ratio(self):
        by_status = dict(self.contract["motion"])
        self.assertEqual(by_status["MOVING"]["speed"], 0.45)
        self.assertEqual(by_status["SAFE_STOPPED"], {"animate": False, "speed": 0, "halted": True})
        self.assertEqual(by_status["ERROR"]["halted"], True)
        for status in ("PAUSED", "HOLDING"):
            self.assertEqual(by_status[status]["speed"], 0, f"{status} must freeze the robot")
        # A status with no decision yet still animates, just without a ratio to slow it down.
        self.assertEqual(self.contract["moving_without_decision"], {"animate": True, "speed": 1, "halted": False})

    def test_route_position_never_runs_ahead_of_the_reported_zone(self):
        results = {(zone, progress): value for zone, progress, value in self.contract["route"]}
        self.assertEqual(results[("A1", 0.0)], 0.0)
        # Progress refines the position inside the current hop...
        self.assertAlmostEqual(results[("A1", 0.1)], 0.1)
        self.assertAlmostEqual(results[("A2", 0.4)], 0.4)
        # ...but never runs past the next node, nor back behind the node the engine reported.
        self.assertAlmostEqual(results[("A2", 0.95)], 2 / 3)
        self.assertAlmostEqual(results[("B2", 0.5)], 2 / 3)
        self.assertAlmostEqual(results[("C2", 0.9)], 1.0)
        self.assertEqual(results[("C2", 1.0)], 1.0)
        # An unknown zone falls back to the start of the route rather than guessing.
        self.assertEqual(results[("ZZ", 0.3)], 0.3)
        self.assertIsNone(self.contract["no_route"])
        self.assertAlmostEqual(self.contract["no_progress"], 2 / 3)

    def test_every_engine_status_has_a_cargo_protection_state(self):
        """The headline renames what Python decided; a status with no entry would render blank."""
        self.assertEqual(sorted(self.contract["protection_keys"]), STATUSES)
        for status, state in self.contract["protection"]:
            with self.subTest(status=status):
                self.assertTrue(state["label"], f"{status} has no Thai label")
                self.assertTrue(state["english"], f"{status} has no English label")
                # Colour is never the only signal: every state also carries a shape.
                self.assertTrue(state["glyph"], f"{status} has no glyph")

    def test_the_headline_states_the_engine_halted_or_slowed(self):
        by_status = dict(self.contract["protection"])
        self.assertEqual(by_status["SAFE_STOPPED"]["tone"], "stop")
        self.assertEqual(by_status["HOLDING"]["tone"], "uncertain")
        self.assertEqual(by_status["SLOWING"]["tone"], "hold")
        self.assertEqual(by_status["MOVING"]["tone"], "go")

    def test_an_unknown_or_absent_status_stays_honestly_unknown(self):
        for case in ("protection_unknown", "protection_absent"):
            with self.subTest(case=case):
                self.assertEqual(self.contract[case]["key"], "UNKNOWN")

    def test_every_engine_action_has_its_own_stage_tone(self):
        tones = dict(self.contract["action_tones"])
        self.assertEqual(sorted(tones), ACTIONS)
        # HOLD_UNCERTAIN must not share amber with a deliberate slow-down.
        self.assertEqual(len(set(tones.values())), len(ACTIONS))
        self.assertEqual(tones["HOLD_UNCERTAIN"], "uncertain")
        self.assertEqual(self.contract["action_tone_unknown"], "idle")

    def test_the_explanation_only_repeats_what_the_engine_published(self):
        slow = self.contract["explain_slow"]
        self.assertTrue(any("carpet" in line for line in slow), slow)
        self.assertTrue(any("45%" in line for line in slow), "the engine's own speed ratio is missing")
        # The raw Safety Core reason is always the last line, so an answer can be traced back.
        self.assertIn("engine reason", slow[-1])

        stop = self.contract["explain_stop"]
        self.assertTrue(any("20" in line for line in stop), "the simulated obstacle distance is missing")
        self.assertTrue(any("Safe Stop" in line for line in stop), stop)

        hold = self.contract["explain_hold"]
        self.assertTrue(any("0.31" in line for line in hold), "the confidence that caused the hold is missing")

        # With no inference published there is nothing to explain, and nothing is invented.
        self.assertEqual(self.contract["explain_empty"], [])

    def test_camera_modes_are_ui_only_and_route_phases_have_distinct_widths(self):
        self.assertEqual(self.contract["camera_modes"], ["overview", "follow", "robot-pov"])
        widths = self.contract["route_widths"]
        self.assertGreater(widths["current"], widths["remaining"])
        self.assertGreater(widths["remaining"], widths["travelled"])
        self.assertGreater(widths["travelled"], widths["lane"])

        index = (WEBAPP / "index.html").read_text(encoding="utf-8")
        scene = (WEBAPP / "scene.js").read_text(encoding="utf-8")
        for mode in self.contract["camera_modes"]:
            self.assertIn(f'data-camera-mode="{mode}"', index)
        self.assertNotIn('data-cmd="overview"', index)
        self.assertIn("setCameraMode", scene)
        self.assertIn("reducedMotion ? 1", scene)


if __name__ == "__main__":
    unittest.main()
