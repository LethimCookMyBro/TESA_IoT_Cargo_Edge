"""One command that runs the whole multi-robot Fleet Guardian scenario and records the evidence.

    .\\.venv\\Scripts\\python.exe scripts/fleet_scenario.py

Needs an MQTT broker on 127.0.0.1:1883 (Bitstream Studio's embedded Aedes broker serves it) and,
for the persistence half, `docker compose up -d` plus `python -m cargo.db`. Without a reachable
database the run still completes and reports the historian as unavailable -- that is the point.

Three robots publish concurrently over the *production* topics. Nothing here bypasses the contracts
the real hardware would use, and every record is labelled SIMULATED.
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

from cargo import contracts, db
from cargo.fleet import FleetGuardian
from cargo.fleet_service import FleetMqttService
from cargo.historian import Historian, NullHistorian
from cargo.simulator import FLEET, ScenarioSource, samples

# Kept small so the evidence file stays readable; the database holds the full history.
EVIDENCE_EXAMPLES = 3


def _client(client_id: str, host: str, port: int) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    return client


class Publisher(threading.Thread):
    """One robot, one MQTT connection, publishing its own telemetry topic. Never shares state."""

    def __init__(self, robot, source, *, host, port, seed, count, zones, interval_s):
        super().__init__(daemon=True, name=f"sim-{robot.robot_id}")
        self.robot, self.host, self.port = robot, host, port
        self.interval_s = interval_s
        self.published = 0
        self.error: str | None = None
        # Generated up front, on the calling thread. Running the classifier inside the publish loop
        # made each "50 ms" sample take far longer than 50 ms in wall-clock time, so every robot
        # looked stale to the freshness check and latched a Safe Stop. A real robot does not run a
        # RandomForest between two sensor reads either. Timestamps here are relative to zero and
        # are re-anchored to the wall clock at publish time.
        self.payloads = list(samples(robot, source, seed=seed, count=count, zones=zones,
                                     start_ms=0, interval_ms=int(interval_s * 1000)))

    def run(self) -> None:
        topic = contracts.topics(self.robot.robot_id)["telemetry"]
        client = _client(f"sim-{self.robot.robot_id}", self.host, self.port)
        # A fixed anchor plus the nominal interval drifts away from the wall clock, because a 50 ms
        # sleep on this platform is reliably longer than 50 ms. Stamping from the real clock keeps
        # a healthy robot honestly fresh, while the *relative* shortfall of a deliberately
        # regressed sample is preserved, so that fault stays exactly as old as it was designed to be.
        newest_relative_ms = 0
        try:
            for payload in self.payloads:
                relative_ms = payload["observed_ms"]
                newest_relative_ms = max(newest_relative_ms, relative_ms)
                now_ms = int(time.time() * 1000)
                payload["observed_ms"] = now_ms - (newest_relative_ms - relative_ms)
                payload["received_ms"] = now_ms
                # allow_nan keeps the deliberately malformed channel on the wire as the JSON
                # literal NaN, so the guardian's validation is exercised by real traffic.
                client.publish(topic, json.dumps(payload, allow_nan=True))
                self.published += 1
                time.sleep(self.interval_s)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            client.loop_stop(); client.disconnect()


def _wait(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def main() -> None:
    parser = argparse.ArgumentParser(description="CargoShield multi-robot fleet scenario")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--samples", type=int, default=24, help="telemetry samples per robot")
    parser.add_argument("--interval", type=float, default=0.05, help="seconds between samples")
    parser.add_argument("--no-database", action="store_true", help="run with persistence disabled")
    parser.add_argument("--out", default="reports/fleet_scenario_evidence.json")
    args = parser.parse_args()

    evidence: dict = {
        "broker": f"{args.host}:{args.port}", "seed": args.seed,
        "samples_per_robot": args.samples, "interval_s": args.interval,
        "provenance": "SIMULATED — synthesised catalog-unit channels; predictions are real model "
                      "output over real stored CareerCon windows. No physical robot, no real "
                      "localization, no real distance sensor.",
        "robots": {robot.robot_id: robot.description for robot in FLEET},
    }

    reachable, reason = (False, "disabled by --no-database") if args.no_database else db.available()
    evidence["database"] = {"reachable": reachable, "reason": reason,
                            "identity": db.settings_from_env().redacted() if not args.no_database else None}
    historian = Historian() if reachable else NullHistorian(reason)
    historian.start()

    guardian = FleetGuardian(sink=historian.submit, expected_interval_ms=int(args.interval * 1000))
    service = FleetMqttService(guardian, historian)
    engine = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="cargoshield-fleet-scenario")
    service.attach(engine)
    engine.connect(args.host, args.port, keepalive=30)
    engine.loop_start()

    source = ScenarioSource(ROOT)
    try:
        # --- 1. Plan a first mission for every robot, from a clean risk map.
        first_routes = {}
        for robot in FLEET:
            route = guardian.start_mission(robot.robot_id, pickup=robot.pickup,
                                           destination=robot.destination, cargo_type=robot.cargo_type,
                                           mission_id=f"m1-{robot.robot_id}")
            first_routes[robot.robot_id] = list(route.nodes) if route else None
        evidence["first_routes"] = first_routes

        # --- 2. All three robots publish concurrently over the production topics.
        publishers = [Publisher(robot, source, host=args.host, port=args.port, seed=args.seed,
                                count=args.samples, zones=tuple(first_routes[robot.robot_id] or ()),
                                interval_s=args.interval)
                      for robot in FLEET]
        started = time.monotonic()
        for publisher in publishers:
            publisher.start()

        # --- 3. Mid-run, take the historian's database away. The Safety Core must not notice.
        outage_started = None
        time.sleep(max(0.4, args.samples * args.interval * 0.3))
        if reachable:
            outage_started = time.monotonic()
            decisions_before = sum(record.samples for record in guardian.robots.values())
            historian.flush(timeout=3.0)
            evidence["historian_before_outage"] = historian.health()
            historian.stop(timeout=2.0)
            # A closed port is a real connection failure: connect() fails, the writer backs off,
            # the bounded queue fills and then drops, and every drop is counted.
            broken = db.Settings(host="127.0.0.1", port=1, database="cargoshield",
                                 user="cargoshield", password="unused")
            outage_historian = Historian(broken, max_queue=50)
            outage_historian.start()
            guardian.sink = outage_historian.submit
            time.sleep(max(0.5, args.samples * args.interval * 0.4))
            decisions_during = sum(record.samples for record in guardian.robots.values())
            outage_historian.stop(timeout=1.0)
            evidence["database_outage"] = {
                "held_for_s": round(time.monotonic() - outage_started, 2),
                "samples_decided_before": decisions_before,
                "samples_decided_during_outage": decisions_during - decisions_before,
                "safety_core_kept_deciding": decisions_during > decisions_before,
                "historian_during_outage": outage_historian.health(),
                "note": "the writer could not reach any database; decisions continued unchanged",
            }
            historian = Historian()
            historian.start()
            guardian.sink = historian.submit
            service.historian = historian

        for publisher in publishers:
            publisher.join(timeout=args.samples * args.interval + 30)
        _wait(lambda: sum(record.samples + record.rejected for record in guardian.robots.values())
              >= sum(publisher.published for publisher in publishers), timeout=10)
        evidence["elapsed_s"] = round(time.monotonic() - started, 2)
        evidence["published"] = {publisher.robot.robot_id: publisher.published for publisher in publishers}
        evidence["publisher_errors"] = {p.robot.robot_id: p.error for p in publishers if p.error}

        # --- 4. What each robot ended up in, and why.
        per_robot = {}
        for robot in FLEET:
            record = guardian.robots.get(robot.robot_id)
            if record is None:
                per_robot[robot.robot_id] = {"seen": False}
                continue
            per_robot[robot.robot_id] = {
                "seen": True, "profile": robot.profile, "status": record.status,
                "health_state": record.last_health.get("state"),
                "health_reasons": record.last_health.get("reasons", [])[:EVIDENCE_EXAMPLES],
                "quarantined_channels": record.last_health.get("quarantined", []),
                "latched_stop": record.latched_stop, "latch_reason": record.latch_reason,
                "accepted_samples": record.samples, "rejected_samples": record.rejected,
                "duplicates": record.last_health.get("duplicates"),
                "out_of_order": record.last_health.get("out_of_order"),
                "decision": record.last_decision.__dict__ if record.last_decision else None,
            }
        evidence["per_robot"] = per_robot

        # --- 5. Isolation: the faulty robot must not have moved the healthy one.
        alpha, charlie = per_robot["robot-alpha"], per_robot["robot-charlie"]
        evidence["isolation"] = {
            "healthy_robot_state": alpha["health_state"], "healthy_robot_latched": alpha["latched_stop"],
            "faulty_robot_state": charlie["health_state"], "faulty_robot_latched": charlie["latched_stop"],
            "faulty_robot_rejected_samples": charlie["rejected_samples"],
            "healthy_unaffected_by_faulty": alpha["health_state"] == "HEALTHY" and not alpha["latched_stop"],
        }

        # --- 6. Accumulated route risk changes the NEXT mission, never the running one.
        bravo = guardian.robots["robot-bravo"]
        route_before = list(bravo.route.nodes) if bravo.route else None
        replanned = guardian.start_mission("robot-bravo", pickup="A1", destination="C2",
                                           cargo_type="fragile", mission_id="m2-robot-bravo")
        evidence["next_mission_route"] = {
            "robot_id": "robot-bravo",
            "route_during_first_mission": first_routes["robot-bravo"],
            "route_still_unchanged_at_end_of_first_mission": route_before == first_routes["robot-bravo"],
            "zone_risk_after_first_mission": bravo.risks.as_dict(),
            "route_planned_for_next_mission": list(replanned.nodes) if replanned else None,
            "next_route_differs": bool(replanned) and list(replanned.nodes) != first_routes["robot-bravo"],
        }

        # --- 7. Persistence and latency.
        historian.flush(timeout=10)
        # Three writer instances span this run (before, during and after the outage), so the
        # per-instance counters below are phases, not a fleet total. `database_rows` is the total.
        evidence["historian"] = historian.health()
        evidence["latency"] = guardian.latency_summary()
        evidence["fleet_status_counts"] = guardian.fleet_status()["counts"]

        if reachable:
            with db.connect() as connection:
                evidence["database_rows"] = {
                    table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    for table in ("robots", "missions", "telemetry_samples", "model_predictions",
                                  "derived_features", "fleet_events", "maintenance_findings")
                }
                evidence["database_rows_by_robot"] = dict(connection.execute(
                    "SELECT robot_id, count(*) FROM telemetry_samples GROUP BY robot_id ORDER BY robot_id"
                ).fetchall())
    finally:
        engine.loop_stop(); engine.disconnect()
        historian.stop(timeout=5.0)

    checks = {
        "three_robots_ingested": len(guardian.robots) >= 3,
        "healthy_robot_stayed_healthy": evidence["isolation"]["healthy_unaffected_by_faulty"],
        "faulty_robot_left_healthy_state": evidence["per_robot"]["robot-charlie"]["health_state"] != "HEALTHY",
        "faulty_robot_rejected_bad_samples": evidence["per_robot"]["robot-charlie"]["rejected_samples"] > 0,
        "impact_latched_a_safe_stop": evidence["per_robot"]["robot-bravo"]["latched_stop"],
        "running_route_never_changed": evidence["next_mission_route"]["route_still_unchanged_at_end_of_first_mission"],
        "next_mission_route_differs": evidence["next_mission_route"]["next_route_differs"],
        "no_publisher_errors": not evidence["publisher_errors"],
    }
    if reachable:
        checks["history_written_for_every_robot"] = len(evidence.get("database_rows_by_robot", {})) >= 3
        checks["safety_core_survived_database_outage"] = evidence["database_outage"]["safety_core_kept_deciding"]
        checks["outage_was_counted_not_silent"] = (
            evidence["database_outage"]["historian_during_outage"]["dropped"] > 0
            or evidence["database_outage"]["historian_during_outage"]["last_error"] is not None)
    evidence["checks"] = checks
    evidence["passed"] = all(checks.values())

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "checks": checks,
                      "latency": evidence["latency"], "historian": evidence["historian"]}, indent=2))
    if not evidence["passed"]:
        raise SystemExit(f"fleet scenario failed; see {args.out}")


if __name__ == "__main__":
    main()
