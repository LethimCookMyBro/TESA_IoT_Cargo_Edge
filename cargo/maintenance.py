"""Provider-neutral, read-only maintenance context.

This is the boundary any Maintenance Copilot (Hermes or otherwise) is allowed to see. It answers
from curated data and nothing else. Three things enforce that, in order of strength:

1. **PostgreSQL.** It connects as ``cargoshield_readonly``, a role with SELECT and nothing else
   (``cargo/db.py::ensure_readonly_role``). An INSERT from here is refused by the database.
2. **No transport.** There is no MQTT client, no publisher, and no command builder in this module,
   so it cannot reach ``cargoshield/{robot_id}/command`` even by mistake.
3. **No mutators.** Every public method returns data. None writes, and a test asserts that.

A copilot may explain, summarise, compare history and draft a checklist. It may never clear a Safe
Stop, change a threshold, acknowledge a finding, or write to an operational table. Acknowledgement
stays an operator action on the command topic.

Latency here is not part of the real-time safety budget: alerts and recovery are already
deterministic and have happened by the time anything reads this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import time
from typing import Any

from . import db

SHIFT_MS = 8 * 60 * 60 * 1000

# What a copilot is allowed to do with this context, shipped alongside the data so a prompt cannot
# quietly widen it.
BOUNDARY = {
    "may": ["explain why a robot stopped or degraded", "summarise a shift",
            "compare historical vibration exposure across routes and zones",
            "list robots needing inspection", "draft a maintenance checklist",
            "suggest data ranges suitable for export"],
    "may_not": ["publish any MQTT command", "clear or override a Safe Stop",
                "change a safety threshold or model", "acknowledge a maintenance finding",
                "write to any operational table", "run shell commands or write files"],
    "enforced_by": ["SELECT-only PostgreSQL role", "no transport client in this module",
                    "no mutating method on this class"],
    "real_time_role": "none; the deterministic Safety Core has already acted",
}


@dataclass(frozen=True)
class Answer:
    """One curated answer plus the evidence it rests on, so a copilot can cite rather than invent."""

    question: str
    summary: str
    evidence: list[dict[str, Any]]
    generated_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {"question": self.question, "summary": self.summary, "evidence": self.evidence,
                "generated_ms": self.generated_ms, "boundary": BOUNDARY}


class MaintenanceContext:
    """Read-only curated views. Construct with the SELECT-only role; that is the whole point."""

    def __init__(self, settings: db.Settings | None = None) -> None:
        self.settings = settings or db.readonly_settings_from_env()

    def _query(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with db.connect(self.settings, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _answer(self, question: str, summary: str, evidence: list[dict[str, Any]]) -> Answer:
        return Answer(question, summary, evidence, int(time() * 1000))

    # ---------- the seven curated questions ----------

    def why_did_robot_stop(self, robot_id: str) -> Answer:
        rows = self._query(
            "SELECT observed_ms, severity, kind, action, health_state, reason, zone, mission_id"
            " FROM fleet_events WHERE robot_id = %s AND severity IN ('warning', 'critical')"
            " ORDER BY observed_ms DESC LIMIT 10", (robot_id,))
        if not rows:
            return self._answer(f"why did {robot_id} stop or degrade?",
                                f"No warning or critical event is recorded for {robot_id}.", [])
        newest = rows[0]
        return self._answer(
            f"why did {robot_id} stop or degrade?",
            f"Most recent {newest['severity']} event: {newest['action'] or newest['kind']} "
            f"with health {newest['health_state']} — {newest['reason']}.",
            rows)

    def evidence_for_conclusion(self, robot_id: str, *, around_ms: int, window_ms: int = 5000) -> Answer:
        rows = self._query(
            "SELECT observed_ms, zone, provenance, source_mode, channels FROM telemetry_samples"
            " WHERE robot_id = %s AND observed_ms BETWEEN %s AND %s"
            " ORDER BY observed_ms DESC LIMIT 50",
            (robot_id, around_ms - window_ms, around_ms + window_ms))
        return self._answer(
            f"which sensor readings support the conclusion about {robot_id}?",
            f"{len(rows)} samples within {window_ms} ms of the event. Channel values are the "
            f"evidence; the health rules that read them are deterministic and live in cargo/health.py.",
            rows)

    def highest_vibration_exposure(self, limit: int = 10) -> Answer:
        rows = self._query(
            "SELECT t.zone, count(*) AS samples, avg(p.vibration_score) AS mean_vibration,"
            " max(p.vibration_score) AS peak_vibration"
            " FROM telemetry_samples t JOIN model_predictions p"
            "  ON p.robot_id = t.robot_id AND p.observed_ms = t.observed_ms"
            " WHERE t.zone IS NOT NULL GROUP BY t.zone"
            " ORDER BY mean_vibration DESC NULLS LAST LIMIT %s", (limit,))
        worst = rows[0]["zone"] if rows else None
        return self._answer(
            "which routes or zones carry the highest accumulated vibration exposure?",
            f"Highest mean vibration is zone {worst}." if worst else "No zone exposure recorded yet.",
            rows)

    def robots_needing_inspection(self) -> Answer:
        rows = self._query(
            "SELECT r.robot_id, r.health_state, r.status, r.last_seen_ms,"
            " count(m.finding_id) FILTER (WHERE m.acknowledged_ms IS NULL) AS unresolved,"
            " max(m.opened_ms) FILTER (WHERE m.acknowledged_ms IS NULL) AS newest_unresolved_ms"
            " FROM robots r LEFT JOIN maintenance_findings m ON m.robot_id = r.robot_id"
            " GROUP BY r.robot_id, r.health_state, r.status, r.last_seen_ms"
            " HAVING count(m.finding_id) FILTER (WHERE m.acknowledged_ms IS NULL) > 0"
            "     OR r.health_state <> 'HEALTHY'"
            " ORDER BY unresolved DESC, r.robot_id")
        return self._answer(
            "which robots need inspection?",
            f"{len(rows)} robot(s) have an unresolved finding or a non-healthy state.", rows)

    def maintenance_checklist(self, robot_id: str) -> Answer:
        """A draft for a human. Nothing here is executed and nothing is acknowledged."""
        faults = self._query(
            "SELECT DISTINCT health_state, reason FROM fleet_events"
            " WHERE robot_id = %s AND severity IN ('warning', 'critical') AND reason IS NOT NULL"
            " ORDER BY reason LIMIT 20", (robot_id,))
        steps = [
            "Confirm the robot is powered down and physically safe to approach.",
            "Record the current Safe Stop reason from Live Operations before clearing anything.",
        ]
        for fault in faults:
            reason = str(fault["reason"])
            if "stuck channel" in reason or "flatline" in reason:
                steps.append(f"Inspect the sensor behind a flatlined channel: {reason}")
            elif "jumped" in reason or "impact" in reason:
                steps.append(f"Inspect the chassis and payload mounting after an impact: {reason}")
            elif "outside" in reason or "not finite" in reason:
                steps.append(f"Check wiring and the sensor's calibration: {reason}")
            elif "disagree" in reason:
                steps.append(f"Compare temperature sensors against a reference: {reason}")
            elif "old" in reason or "OFFLINE" in reason:
                steps.append(f"Check the telemetry link and antenna: {reason}")
        steps.append("An operator must acknowledge the finding; no copilot may acknowledge it.")
        return self._answer(f"draft a maintenance checklist for {robot_id}",
                            f"{len(steps)} draft steps from {len(faults)} distinct recorded faults.",
                            [{"step": index + 1, "action": step} for index, step in enumerate(steps)])

    def shift_summary(self, *, since_ms: int | None = None) -> Answer:
        since = since_ms if since_ms is not None else int(time() * 1000) - SHIFT_MS
        rows = self._query(
            "SELECT robot_id, severity, count(*) AS events FROM fleet_events"
            " WHERE observed_ms >= %s GROUP BY robot_id, severity ORDER BY robot_id, severity", (since,))
        missions = self._query(
            "SELECT count(*) AS missions FROM missions WHERE started_ms >= %s", (since,))
        total = sum(int(row["events"]) for row in rows)
        return self._answer(
            "summarise the shift",
            f"{total} events across {len({row['robot_id'] for row in rows})} robot(s) and "
            f"{missions[0]['missions'] if missions else 0} mission(s) since {since}.",
            rows + missions)

    def exportable_ranges(self) -> Answer:
        rows = self._query(
            "SELECT robot_id, provenance, count(*) AS samples, min(observed_ms) AS from_ms,"
            " max(observed_ms) AS to_ms FROM telemetry_samples"
            " GROUP BY robot_id, provenance ORDER BY robot_id, provenance")
        return self._answer(
            "which data ranges are suitable for export?",
            "Ranges are grouped by robot and provenance. SIMULATED and DATASET rows must never be "
            "reported as real-world performance, and no HARDWARE rows exist in this prototype.",
            rows)

    # ---------- graceful degradation ----------

    def available(self) -> tuple[bool, str]:
        return db.available(self.settings)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="CargoShield read-only maintenance context")
    parser.add_argument("--robot", default=None, help="robot id for the per-robot questions")
    args = parser.parse_args()

    context = MaintenanceContext()
    ok, reason = context.available()
    if not ok:
        # Graceful fallback: the copilot boundary being unavailable is never a safety event.
        print(json.dumps({"available": False, "reason": reason, "boundary": BOUNDARY,
                          "note": "robot safety is unaffected; the Safety Core does not read this"},
                         indent=2))
        raise SystemExit(1)

    answers = [context.robots_needing_inspection(), context.highest_vibration_exposure(),
               context.shift_summary(), context.exportable_ranges()]
    if args.robot:
        answers = [context.why_did_robot_stop(args.robot), context.maintenance_checklist(args.robot)] + answers
    print(json.dumps({"available": True, "answers": [answer.as_dict() for answer in answers]},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
