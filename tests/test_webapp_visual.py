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

EXTRACT = """
import { OBSTACLE_POLICY, ZONE_POSITIONS, DEMO_EDGES, SURFACE_TINTS, obstacleTone, motion, routePosition } from './controls.js';
const statuses = %s;
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
}));
""" % json.dumps(STATUSES)


def _extract() -> dict:
    script = WEBAPP / "_extract_visual.mjs"
    script.write_text(EXTRACT, encoding="utf-8")
    try:
        result = subprocess.run([shutil.which("node"), str(script)], capture_output=True, text=True, timeout=60, cwd=str(WEBAPP))
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


if __name__ == "__main__":
    unittest.main()
