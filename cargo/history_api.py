"""Narrow read-only HTTP API over the fleet historian.

The browser never connects to PostgreSQL. It reads history through this process, which:
  * serves GET only -- every other method is 405, so nothing here can mutate operational data;
  * runs a fixed set of parameterised queries, never SQL supplied by a caller;
  * binds to the loopback interface by default;
  * returns no credentials, only the redacted database identity.

Built on the standard library's ThreadingHTTPServer. A local read-only demo API does not justify a
web framework dependency.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urlparse

from . import contracts, db, maintenance
from .export import csv_bytes

DEFAULT_LIMIT, MAX_LIMIT = 200, 5000
PAGE_SIZE, MAX_PAGE_SIZE = 20, 20
CSV_MAX_ROWS = 5000
MAX_REJECTED_BODY_BYTES = 64 * 1024
EVENT_CSV_COLUMNS = (
    "event_id", "robot_id", "mission_id", "severity", "code", "kind", "observed_at",
    "received_at", "provenance", "zone", "status", "health_state", "action", "speed_ratio",
    "reason",
)
MISSION_CSV_COLUMNS = (
    "mission_id", "robot_id", "cargo_type", "route", "route_cost", "route_reason",
    "started_at", "ended_at", "provenance",
)


class _CsvDownload(NamedTuple):
    body: bytes
    filename: str
    row_count: int

# The curated questions a Maintenance Copilot may ask, mapped to the read-only methods that answer
# them. This dict is the whole allowlist: a question that is not a key here has no endpoint, and
# nothing on the wire can name a method that is not listed. `needs_robot` marks the per-robot ones.
COPILOT_QUESTIONS: dict[str, dict[str, Any]] = {
    "why-stop": {"method": "why_did_robot_stop", "needs_robot": True,
                 "th": "ทำไมหุ่นยนต์ตัวนี้ Safe Stop หรือเสื่อมสภาพ?"},
    "inspection": {"method": "robots_needing_inspection", "needs_robot": False,
                   "th": "หุ่นยนต์ตัวไหนควรตรวจสภาพ?"},
    "vibration-exposure": {"method": "highest_vibration_exposure", "needs_robot": False,
                           "th": "โซนไหนมีแรงสั่นสะสมสูงที่สุด?"},
    "shift-summary": {"method": "shift_summary", "needs_robot": False,
                      "th": "สรุปเหตุการณ์ของกะนี้"},
    "checklist": {"method": "maintenance_checklist", "needs_robot": True,
                  "th": "สร้าง maintenance checklist (ฉบับร่างให้มนุษย์ตรวจ)"},
    "evidence": {"method": "evidence_for_conclusion", "needs_robot": True,
                 "th": "แสดงหลักฐานเซ็นเซอร์รอบเหตุการณ์"},
    "export-ranges": {"method": "exportable_ranges", "needs_robot": False,
                      "th": "ช่วงข้อมูลใดเหมาะกับการ export ไปตรวจหรือ train รอบใหม่?"},
}


def _limit(params: dict[str, list[str]]) -> int:
    try:
        return max(1, min(MAX_LIMIT, int(params.get("limit", [DEFAULT_LIMIT])[0])))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def _pagination(params: dict[str, list[str]]) -> tuple[int, int, int]:
    """Strict page contract for operator tables; malformed input is never silently rewritten."""
    def read(name: str, default: int, maximum: int | None = None) -> int:
        values = params.get(name)
        if values is None:
            return default
        if len(values) != 1 or not values[0].isascii() or not values[0].isdecimal():
            raise contracts.ContractError(f"{name} must be one positive integer")
        value = int(values[0])
        if value < 1 or (maximum is not None and value > maximum):
            ceiling = f" no greater than {maximum}" if maximum is not None else ""
            raise contracts.ContractError(f"{name} must be a positive integer{ceiling}")
        return value

    page = read("page", 1)
    page_size = read("limit", PAGE_SIZE, MAX_PAGE_SIZE)
    return page, page_size, (page - 1) * page_size


def _page_result(name: str, rows: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    shown = rows[:page_size]
    start = (page - 1) * page_size + 1 if shown else 0
    return {
        name: shown,
        "page": page,
        "page_size": page_size,
        "has_previous": page > 1,
        "has_more": len(rows) > page_size,
        "range_start": start,
        "range_end": start + len(shown) - 1 if shown else 0,
    }


def _severity(params: dict[str, list[str]]) -> str | None:
    severity = params.get("severity", [None])[0]
    if severity not in (None, "info", "warning", "critical"):
        raise contracts.ContractError(f"unknown severity: {severity!r}")
    return severity


def _iso_ms(value: int | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def _download(kind: str, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> _CsvDownload:
    if len(rows) > CSV_MAX_ROWS:
        raise contracts.ContractError(
            f"CSV export exceeds {CSV_MAX_ROWS} rows; narrow the active filters")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _CsvDownload(csv_bytes(rows, columns), f"cargoshield_{kind}_{stamp}.csv", len(rows))


def _window(params: dict[str, list[str]]) -> tuple[int, int]:
    def read(name: str, fallback: int) -> int:
        try:
            return int(params.get(name, [fallback])[0])
        except (TypeError, ValueError):
            return fallback
    return read("from_ms", 0), read("to_ms", 2 ** 62)


def _rows(cursor) -> list[dict[str, Any]]:
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


class HistoryQueries:
    """Every query the API can run. Adding one here is the only way to widen the surface."""

    def __init__(self, settings: db.Settings | None = None) -> None:
        self.settings = settings or db.settings_from_env()

    def _query(self, sql: str, args: tuple) -> list[dict[str, Any]]:
        with db.connect(self.settings, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                return _rows(cursor)

    def health(self) -> dict[str, Any]:
        ok, reason = db.available(self.settings)
        return {"database": self.settings.redacted(), "reachable": ok, "reason": reason,
                "note": "read-only history API; the Safety Core does not depend on it"}

    def fleet(self) -> list[dict[str, Any]]:
        return self._query(
            "SELECT r.robot_id, r.provenance, r.status, r.health_state, r.first_seen_ms, r.last_seen_ms,"
            " (SELECT count(*) FROM maintenance_findings m"
            "   WHERE m.robot_id = r.robot_id AND m.acknowledged_ms IS NULL) AS unresolved_findings"
            " FROM robots r ORDER BY r.robot_id", ())

    def events(self, robot_id: str | None, from_ms: int, to_ms: int, severity: str | None,
               limit: int, offset: int = 0):
        return self._query(
            "SELECT event_id, robot_id, mission_id, kind, code, severity, observed_ms, received_ms,"
            " provenance, zone, status, health_state, action, speed_ratio, reason"
            " FROM fleet_events"
            " WHERE (%s::text IS NULL OR robot_id = %s)"
            "   AND (%s::text IS NULL OR severity = %s)"
            "   AND observed_ms BETWEEN %s AND %s"
            " ORDER BY observed_ms DESC, event_id DESC LIMIT %s OFFSET %s",
            (robot_id, robot_id, severity, severity, from_ms, to_ms, limit, offset))

    def telemetry(self, robot_id: str, from_ms: int, to_ms: int, limit: int):
        return self._query(
            "SELECT event_id, robot_id, mission_id, seq, observed_ms, received_ms, provenance,"
            " source_mode, zone, channels FROM telemetry_samples"
            " WHERE robot_id = %s AND observed_ms BETWEEN %s AND %s"
            " ORDER BY observed_ms DESC LIMIT %s", (robot_id, from_ms, to_ms, limit))

    def predictions(self, robot_id: str | None, from_ms: int, to_ms: int, limit: int):
        return self._query(
            "SELECT event_id, robot_id, mission_id, observed_ms, provenance, label, confidence,"
            " vibration_score, vibration_risk, accepted FROM model_predictions"
            " WHERE (%s::text IS NULL OR robot_id = %s) AND observed_ms BETWEEN %s AND %s"
            " ORDER BY observed_ms DESC LIMIT %s", (robot_id, robot_id, from_ms, to_ms, limit))

    def missions(self, robot_id: str | None, limit: int, offset: int = 0):
        return self._query(
            "SELECT m.mission_id, m.robot_id, m.cargo_type, m.route, m.route_cost, m.route_reason,"
            " m.started_ms, m.ended_ms, r.provenance"
            " FROM missions m JOIN robots r ON r.robot_id = m.robot_id"
            " WHERE (%s::text IS NULL OR m.robot_id = %s)"
            " ORDER BY m.started_ms DESC, m.mission_id DESC LIMIT %s OFFSET %s",
            (robot_id, robot_id, limit, offset))

    def maintenance(self, unresolved_only: bool, limit: int):
        return self._query(
            "SELECT finding_id, robot_id, mission_id, opened_ms, severity, reason,"
            " acknowledged_ms, acknowledged_by, note FROM maintenance_findings"
            " WHERE (NOT %s OR acknowledged_ms IS NULL)"
            " ORDER BY (acknowledged_ms IS NULL) DESC, opened_ms DESC LIMIT %s", (unresolved_only, limit))

    def zone_risk(self):
        """Accumulated vibration exposure per zone, across the whole fleet's history."""
        return self._query(
            "SELECT t.zone,"
            " count(*) AS samples,"
            " avg(p.vibration_score) AS mean_vibration,"
            " max(p.vibration_score) AS peak_vibration,"
            " count(*) FILTER (WHERE p.vibration_risk = 'high') AS high_risk_samples"
            " FROM telemetry_samples t JOIN model_predictions p ON p.observed_ms = t.observed_ms"
            "  AND p.robot_id = t.robot_id"
            " WHERE t.zone IS NOT NULL GROUP BY t.zone ORDER BY mean_vibration DESC NULLS LAST", ())

    def data_quality(self):
        """Provenance and acceptance breakdown, so the dashboard can show what the data really is."""
        return self._query(
            "SELECT provenance, count(*) AS samples FROM telemetry_samples GROUP BY provenance"
            " ORDER BY provenance", ())

    def manifests(self, limit: int):
        return self._query(
            "SELECT export_id, created_ms, schema_version, format, row_count, from_ms, to_ms,"
            " robot_ids, labels, provenance, filters, path FROM export_manifests"
            " ORDER BY created_ms DESC LIMIT %s", (limit,))


class Handler(BaseHTTPRequestHandler):
    queries: HistoryQueries
    copilot: maintenance.MaintenanceContext
    server_version = "CargoShieldHistoryAPI/1"

    def log_message(self, fmt: str, *args) -> None:  # keep the demo console readable
        return

    def _send(self, status: int, body: Any) -> None:
        raw = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        # The dashboard is served from a different local port. This API is GET-only and bound to
        # loopback, so a permissive read-only CORS header cannot be used to change anything.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_csv(self, download: _CsvDownload) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{download.filename}"')
        self.send_header("Content-Length", str(len(download.body)))
        self.send_header("X-Row-Count", str(download.row_count))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, X-Row-Count")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(download.body)

    def _reject_write(self) -> None:
        # Closing a Windows TCP socket with unread request bytes can reset the connection before
        # the client receives this 405. Drain ordinary local requests; cap it so a false
        # Content-Length cannot block a server thread indefinitely.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = 0
        if 0 < length <= MAX_REJECTED_BODY_BYTES:
            self.rfile.read(length)
        self.send_response(405)
        self.send_header("Allow", "GET, OPTIONS")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    # Every mutating verb is refused by the transport itself, not by a check inside a handler.
    do_POST = do_PUT = do_PATCH = do_DELETE = _reject_write

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        try:
            result = self._route(parts, params)
            self._send_csv(result) if isinstance(result, _CsvDownload) else self._send(200, result)
        except contracts.ContractError as exc:
            self._send(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            self._send(404, {"error": str(exc)})
        except Exception as exc:
            # A database outage must read as "history unavailable", never as a crashed dashboard.
            self._send(503, {"error": f"{type(exc).__name__}: {exc}",
                             "note": "history is unavailable; robot safety is unaffected"})

    def _route(self, parts: list[str], params: dict[str, list[str]]) -> Any:
        queries, limit = self.queries, _limit(params)
        from_ms, to_ms = _window(params)
        robot = params.get("robot_id", [None])[0]
        if robot is not None:
            contracts.validate_robot_id(robot)

        if parts in ([], ["api"]):
            return {"endpoints": ["/api/health", "/api/fleet", "/api/events", "/api/telemetry",
                                  "/api/events.csv", "/api/predictions", "/api/missions",
                                  "/api/missions.csv", "/api/maintenance",
                                  "/api/zones", "/api/data-quality", "/api/exports",
                                  "/api/copilot", "/api/copilot/{question}"],
                    "methods": ["GET"], "writes": "none"}
        if parts == ["api", "copilot"]:
            return self._copilot_index()
        if len(parts) == 3 and parts[:2] == ["api", "copilot"]:
            return self._copilot_answer(parts[2], params, robot)
        if parts == ["api", "health"]:
            return queries.health()
        if parts == ["api", "fleet"]:
            return {"robots": queries.fleet()}
        if parts == ["api", "events"]:
            severity = _severity(params)
            page, page_size, offset = _pagination(params)
            rows = queries.events(robot, from_ms, to_ms, severity, page_size + 1, offset)
            return _page_result("events", rows, page, page_size)
        if parts == ["api", "events.csv"]:
            rows = queries.events(robot, from_ms, to_ms, _severity(params), CSV_MAX_ROWS + 1, 0)
            exported = [
                {**row, "observed_at": _iso_ms(row.get("observed_ms")),
                 "received_at": _iso_ms(row.get("received_ms"))}
                for row in rows
            ]
            return _download("safety_events", exported, EVENT_CSV_COLUMNS)
        if parts == ["api", "telemetry"]:
            if robot is None:
                raise contracts.ContractError("telemetry requires a robot_id")
            return {"samples": queries.telemetry(robot, from_ms, to_ms, limit)}
        if parts == ["api", "predictions"]:
            return {"predictions": queries.predictions(robot, from_ms, to_ms, limit)}
        if parts == ["api", "missions"]:
            page, page_size, offset = _pagination(params)
            rows = queries.missions(robot, page_size + 1, offset)
            return _page_result("missions", rows, page, page_size)
        if parts == ["api", "missions.csv"]:
            rows = queries.missions(robot, CSV_MAX_ROWS + 1, 0)
            exported = [
                {**row, "route": " \u2192 ".join(row.get("route") or ()),
                 "started_at": _iso_ms(row.get("started_ms")),
                 "ended_at": _iso_ms(row.get("ended_ms"))}
                for row in rows
            ]
            return _download("mission_history", exported, MISSION_CSV_COLUMNS)
        if parts == ["api", "maintenance"]:
            return {"findings": queries.maintenance(params.get("unresolved", ["1"])[0] != "0", limit)}
        if parts == ["api", "zones"]:
            return {"zones": queries.zone_risk()}
        if parts == ["api", "data-quality"]:
            return {"provenance": queries.data_quality()}
        if parts == ["api", "exports"]:
            return {"manifests": queries.manifests(limit)}
        raise FileNotFoundError(f"no such endpoint: /{'/'.join(parts)}")

    # ---------- Maintenance Copilot: the read-only boundary, over GET ----------

    def _copilot_index(self) -> dict[str, Any]:
        """What may be asked, what the boundary forbids, and whether any provider is wired in."""
        ok, reason = self.copilot.available()
        return {
            # Stated from what this repository actually contains, not from an aspiration: nothing
            # here holds a model client, an endpoint, an API key or an outbound call. Answers below
            # are deterministic SQL over the read-only role.
            "provider": None,
            "provider_status": "not_connected",
            "provider_note": "No copilot provider is configured in this repository. Answers are "
                             "deterministic SQL over the SELECT-only PostgreSQL role; see "
                             "docs/HERMES_MAINTENANCE_COPILOT.md to connect one.",
            "analysis_mode": "deterministic",
            "human_approval_required": True,
            "available": ok,
            "reason": reason,
            "questions": [{"id": key, "question_th": entry["th"], "needs_robot": entry["needs_robot"]}
                          for key, entry in COPILOT_QUESTIONS.items()],
            "boundary": maintenance.BOUNDARY,
        }

    def _copilot_answer(self, question: str, params: dict[str, list[str]], robot: str | None) -> dict[str, Any]:
        entry = COPILOT_QUESTIONS.get(question)
        if entry is None:
            raise FileNotFoundError(f"no such copilot question: {question!r}")
        if entry["needs_robot"] and robot is None:
            raise contracts.ContractError(f"copilot question {question!r} requires a robot_id")
        method = getattr(self.copilot, entry["method"])
        if question == "evidence":
            try:
                around_ms = int(params.get("around_ms", ["0"])[0])
            except (TypeError, ValueError):
                raise contracts.ContractError("around_ms must be an integer millisecond timestamp")
            answer = method(robot, around_ms=around_ms)
        else:
            answer = method(robot) if entry["needs_robot"] else method()
        # `provider` travels with every answer so a screenshot can never imply a live model wrote it.
        return {**answer.as_dict(), "question_id": question, "provider": None,
                "analysis_mode": "deterministic", "human_approval_required": True}


def serve(host: str = "127.0.0.1", port: int = 8099, settings: db.Settings | None = None,
          readonly_settings: db.Settings | None = None) -> ThreadingHTTPServer:
    """History over `settings`; the copilot boundary over the SELECT-only role, deliberately apart."""
    handler = type("BoundHandler", (Handler,), {
        "queries": HistoryQueries(settings),
        "copilot": maintenance.MaintenanceContext(readonly_settings),
    })
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="CargoShield read-only fleet history API")
    parser.add_argument("--host", default="127.0.0.1", help="loopback by default; do not expose publicly")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    server = serve(args.host, args.port)
    print(f"read-only history API on http://{args.host}:{args.port}/api")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
