"""Bounded, asynchronous PostgreSQL writer for the fleet historian.

The Safety Core hands events here through ``submit``, which never blocks and never raises. If the
queue is full or the database is down, records are dropped and counted -- deliberately, because a
missing history row is survivable and a stalled safety decision is not.

Nothing in this module is on the sensor-to-decision path. ``FleetGuardian`` only calls ``submit``.
"""

from __future__ import annotations

import json
import queue
import threading
from time import monotonic
from typing import Any

from . import db

# Bounded on purpose. At the simulator's rates this is many seconds of buffer; past that, dropping
# is the correct behaviour and the counter makes it visible instead of silent.
MAX_QUEUE = 5000
BATCH_SIZE = 200
FLUSH_INTERVAL_S = 0.5
RECONNECT_BACKOFF_S = (0.5, 1.0, 2.0, 5.0, 10.0)

TELEMETRY_COLUMNS = ("event_id", "robot_id", "mission_id", "seq", "observed_ms", "received_ms",
                     "provenance", "source_mode", "zone", "channels")
EVENT_COLUMNS = ("event_id", "robot_id", "mission_id", "kind", "code", "severity", "observed_ms",
                 "received_ms", "provenance", "zone", "status", "health_state", "action",
                 "speed_ratio", "reason", "payload")
PREDICTION_COLUMNS = ("event_id", "robot_id", "mission_id", "observed_ms", "provenance", "label",
                      "confidence", "vibration_score", "vibration_risk", "accepted")
FEATURE_COLUMNS = ("event_id", "robot_id", "mission_id", "observed_ms", "provenance", "features")

EVENT_KINDS = frozenset({"safety_decision", "health_event", "mission_event"})


def _placeholders(columns: tuple[str, ...]) -> str:
    return ", ".join(["%s"] * len(columns))


class Historian:
    """One writer thread, one bounded queue, one connection. Start it, submit to it, stop it."""

    def __init__(self, settings: db.Settings | None = None, *, max_queue: int = MAX_QUEUE,
                 batch_size: int = BATCH_SIZE, flush_interval_s: float = FLUSH_INTERVAL_S) -> None:
        self.settings = settings or db.settings_from_env()
        self.batch_size, self.flush_interval_s = batch_size, flush_interval_s
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._connection = None
        self._lock = threading.Lock()
        self.dropped = 0
        self.written = 0
        self.retries = 0
        self.failed_rows = 0
        self.connected = False
        self.last_error: str | None = None

    # ---------- producer side: called from the real-time path ----------

    def submit(self, event: dict[str, Any]) -> bool:
        """Enqueue without blocking. False means the record was dropped, and `dropped` counts it."""
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            with self._lock:
                self.dropped += 1
            return False

    def health(self) -> dict[str, Any]:
        """Everything an operator needs to trust or distrust the history, in one object."""
        return {
            "database": self.settings.redacted(),
            "connected": self.connected,
            "queue_depth": self._queue.qsize(),
            "queue_capacity": self._queue.maxsize,
            "dropped": self.dropped,
            "written": self.written,
            "retries": self.retries,
            "failed_rows": self.failed_rows,
            "last_error": self.last_error,
        }

    # ---------- lifecycle ----------

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="cargoshield-historian", daemon=True)
        self._worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout)
        self._close()

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until queued and in-flight records finish. Never called by the core."""
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            self._stop.wait(0.02)
        return self._queue.unfinished_tasks == 0

    # ---------- consumer side ----------

    def _connect(self) -> bool:
        try:
            self._connection = db.connect(self.settings, connect_timeout=3, autocommit=False)
            self.connected, self.last_error = True, None
            return True
        except Exception as exc:
            self.connected = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def _close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
        self._connection, self.connected = None, False

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            if self._connection is None and not self._connect():
                # Reconnect with backoff. The queue keeps buffering and then keeps dropping; the
                # Safety Core is not told and does not care.
                self._stop.wait(RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)])
                attempt += 1
                continue
            attempt = 0
            batch = self._drain()
            if not batch:
                continue
            wrote = self._write(batch)
            for _event in batch:
                self._queue.task_done()
            if not wrote:
                self.retries += 1
                self._close()
        # Best-effort final drain so a clean shutdown does not discard buffered history.
        if self._connection is not None or self._connect():
            remaining = self._drain(block=False)
            if remaining:
                self._write(remaining)
                for _event in remaining:
                    self._queue.task_done()
        self._close()

    def _drain(self, *, block: bool = True) -> list[dict[str, Any]]:
        batch: list[dict[str, Any]] = []
        try:
            first = self._queue.get(timeout=self.flush_interval_s) if block else self._queue.get_nowait()
            batch.append(first)
        except queue.Empty:
            return batch
        while len(batch) < self.batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _write(self, batch: list[dict[str, Any]]) -> bool:
        try:
            with self._connection.cursor() as cursor:
                self._write_batch(cursor, batch)
            self._connection.commit()
            self.written += len(batch)
            return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            try:
                self._connection.rollback()
            except Exception:
                return False
            # One bad row must not cost the other 199. Retry the batch row by row and count the
            # genuine failures rather than silently losing everything.
            return self._write_individually(batch)

    def _write_individually(self, batch: list[dict[str, Any]]) -> bool:
        ok = True
        for index, event in enumerate(batch):
            try:
                with self._connection.cursor() as cursor:
                    self._write_batch(cursor, [event])
                self._connection.commit()
                self.written += 1
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.failed_rows += 1
                try:
                    self._connection.rollback()
                except Exception:
                    self.failed_rows += len(batch) - index - 1
                    ok = False
                    break
        return ok

    def _write_batch(self, cursor, batch: list[dict[str, Any]]) -> None:
        # Dependency order: robots, then missions, then everything that references them.
        self._upsert_robots(cursor, batch)
        self._upsert_missions(cursor, batch)
        telemetry, events, predictions, features, findings = [], [], [], [], []
        for event in batch:
            kind = event.get("kind")
            if kind == "raw_telemetry":
                telemetry.append(self._telemetry_row(event))
            elif kind in EVENT_KINDS:
                events.append(self._event_row(event))
            elif kind == "model_prediction":
                predictions.append(self._prediction_row(event))
            elif kind == "derived_feature":
                features.append(self._feature_row(event))
            elif kind == "maintenance_finding":
                findings.append(event)
        self._insert(cursor, "telemetry_samples", TELEMETRY_COLUMNS, telemetry)
        self._insert(cursor, "fleet_events", EVENT_COLUMNS, events)
        self._insert(cursor, "model_predictions", PREDICTION_COLUMNS, predictions)
        self._insert(cursor, "derived_features", FEATURE_COLUMNS, features)
        for finding in findings:
            cursor.execute(
                "INSERT INTO maintenance_findings"
                " (event_id, robot_id, mission_id, opened_ms, severity, reason, note)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (event_id) DO NOTHING",
                (finding["event_id"], finding["robot_id"], self._mission(finding),
                 finding["observed_ms"], finding.get("severity", "info"),
                 finding.get("reason", ""), finding.get("note")),
            )

    @staticmethod
    def _insert(cursor, table: str, columns: tuple[str, ...], rows: list[tuple]) -> None:
        if not rows:
            return
        # event_id is the primary key, so a duplicate delivery is idempotent rather than an error.
        cursor.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({_placeholders(columns)})"
            " ON CONFLICT (event_id) DO NOTHING",
            rows,
        )

    @staticmethod
    def _mission(event: dict[str, Any]) -> str | None:
        mission = event.get("mission_id")
        return mission if isinstance(mission, str) and mission else None

    def _upsert_robots(self, cursor, batch: list[dict[str, Any]]) -> None:
        latest: dict[str, dict[str, Any]] = {}
        for event in batch:
            robot_id = event.get("robot_id")
            if isinstance(robot_id, str):
                latest[robot_id] = event
        for robot_id, event in latest.items():
            cursor.execute(
                "INSERT INTO robots (robot_id, provenance, first_seen_ms, last_seen_ms, status, health_state)"
                " VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (robot_id) DO UPDATE SET"
                "  last_seen_ms = GREATEST(robots.last_seen_ms, EXCLUDED.last_seen_ms),"
                "  status = COALESCE(EXCLUDED.status, robots.status),"
                "  health_state = COALESCE(EXCLUDED.health_state, robots.health_state)",
                (robot_id, event.get("provenance", "SIMULATED"), event["received_ms"], event["received_ms"],
                 event.get("status") or "IDLE", event.get("health_state") or "HEALTHY"),
            )

    def _upsert_missions(self, cursor, batch: list[dict[str, Any]]) -> None:
        for event in batch:
            if event.get("kind") != "mission_event" or not self._mission(event):
                continue
            route = event.get("route")
            cursor.execute(
                "INSERT INTO missions (mission_id, robot_id, cargo_type, route, route_cost, route_reason, started_ms)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (mission_id) DO NOTHING",
                (event["mission_id"], event["robot_id"], event.get("cargo_type", "standard"),
                 json.dumps(route) if route is not None else None, event.get("route_cost"),
                 event.get("route_reason"), event["observed_ms"]),
            )

    @staticmethod
    def _storable_channels(channels: Any) -> str:
        """JSON that PostgreSQL's jsonb will accept.

        A faulty sensor legitimately reports NaN or Infinity, and the health check depends on
        seeing it -- but `jsonb` rejects those tokens outright. Rather than lose the whole row, the
        offending channel is stored as null and named in `_nonfinite`, so the history still records
        that the channel was non-finite and which one it was.
        """
        if not isinstance(channels, dict):
            return json.dumps({})
        clean, nonfinite = {}, []
        for name, value in channels.items():
            if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
                clean[name], _ = None, nonfinite.append(name)
            else:
                clean[name] = value
        if nonfinite:
            clean["_nonfinite"] = sorted(nonfinite)
        return json.dumps(clean, allow_nan=False)

    def _telemetry_row(self, event: dict[str, Any]) -> tuple:
        return (event["event_id"], event["robot_id"], self._mission(event), event.get("seq"),
                event["observed_ms"], event["received_ms"], event["provenance"],
                event.get("source_mode", "unknown"), event.get("zone"),
                self._storable_channels(event.get("channels", {})))

    def _event_row(self, event: dict[str, Any]) -> tuple:
        known = set(EVENT_COLUMNS) | {"schema", "seq", "channels", "prediction"}
        return (event["event_id"], event["robot_id"], self._mission(event), event["kind"],
                event.get("code"), event.get("severity", "info"), event["observed_ms"],
                event["received_ms"], event["provenance"], event.get("zone"), event.get("status"),
                event.get("health_state"), event.get("action"), event.get("speed_ratio"),
                event.get("reason"),
                json.dumps({key: value for key, value in event.items() if key not in known}))

    def _prediction_row(self, event: dict[str, Any]) -> tuple:
        return (event["event_id"], event["robot_id"], self._mission(event), event["observed_ms"],
                event["provenance"], event.get("label"), event.get("confidence"),
                event.get("vibration_score"), event.get("vibration_risk"), event.get("accepted"))

    def _feature_row(self, event: dict[str, Any]) -> tuple:
        return (event["event_id"], event["robot_id"], self._mission(event), event["observed_ms"],
                event["provenance"], json.dumps(event.get("features", {})))


class NullHistorian:
    """Stand-in used when PostgreSQL is deliberately absent. Same surface, keeps no history."""

    def __init__(self, reason: str = "historian disabled") -> None:
        self.reason, self.dropped = reason, 0

    def submit(self, _event: dict[str, Any]) -> bool:
        self.dropped += 1
        return False

    def start(self) -> None:
        return None

    def stop(self, timeout: float = 0.0) -> None:
        return None

    def flush(self, timeout: float = 0.0) -> bool:
        return True

    def health(self) -> dict[str, Any]:
        return {"database": None, "connected": False, "queue_depth": 0, "queue_capacity": 0,
                "dropped": self.dropped, "written": 0, "retries": 0, "failed_rows": 0,
                "last_error": self.reason}
