"""PostgreSQL historian, read-only history API, export provenance and the copilot boundary.

These run against a real, separate `cargoshield_test` database so demo evidence is never touched.
If PostgreSQL is unreachable every test here is SKIPPED with a printed reason -- they are never
reported as passed. Start it with `docker compose up -d` then `python -m cargo.db`.
"""

from __future__ import annotations

import io
import csv
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from cargo import contracts, db
from cargo.export import ExportFilters, export
from cargo.fleet import FleetGuardian, sample
from cargo.historian import Historian
from cargo.history_api import COPILOT_QUESTIONS, Handler, serve
from cargo.maintenance import BOUNDARY, MaintenanceContext
from scripts.fleet_scenario import _current_run_history_complete, _database_rows_for_missions

TEST_DATABASE = "cargoshield_test"
GOOD = {"bmi270.accelX": 0.1, "bmi270.accelZ": 9.81}
CONFIDENT = {"confidence": 0.95, "vibration_risk": "low", "vibration_score": 0.2, "label": "tiled"}


def _owner_settings() -> db.Settings:
    return db.settings_from_env(database=TEST_DATABASE)


def _create_test_database() -> tuple[bool, str]:
    """Create the throwaway test database. Returns (ok, reason) and never raises."""
    admin = db.settings_from_env(database="postgres")
    try:
        with db.connect(admin, connect_timeout=3) as connection:
            connection.autocommit = True
            exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                        (TEST_DATABASE,)).fetchone()
            if not exists:
                connection.execute(f'CREATE DATABASE "{TEST_DATABASE}"')
        return True, "ready"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


AVAILABLE, REASON = _create_test_database()
if AVAILABLE:
    try:
        db.migrate(_owner_settings())
        db.ensure_readonly_role(_owner_settings())
    except Exception as exc:  # pragma: no cover - reported as a skip reason
        AVAILABLE, REASON = False, f"migration failed: {type(exc).__name__}: {exc}"

SKIP = unittest.skipUnless(AVAILABLE, f"PostgreSQL test database unavailable: {REASON}")


def _readonly_settings() -> db.Settings:
    base = db.readonly_settings_from_env()
    return db.Settings(base.host, base.port, TEST_DATABASE, base.user, base.password)


def _truncate() -> None:
    with db.connect(_owner_settings()) as connection:
        connection.execute("TRUNCATE robots, missions, telemetry_samples, derived_features,"
                           " model_predictions, fleet_events, maintenance_findings,"
                           " export_manifests RESTART IDENTITY CASCADE")
        connection.commit()


def _seed(robots=("robot-alpha", "robot-bravo", "robot-charlie"), steps=6) -> Historian:
    historian = Historian(_owner_settings())
    historian.start()
    guardian = FleetGuardian(sink=historian.submit, expected_interval_ms=100)
    for robot_id in robots:
        guardian.start_mission(robot_id, pickup="A1", destination="C2",
                               cargo_type="standard", mission_id=f"m-{robot_id}")
    for step in range(1, steps + 1):
        for robot_id in robots:
            guardian.ingest(sample(robot_id, seq=step, observed_ms=step * 100, channels=GOOD,
                                   zone="A1", prediction=CONFIDENT), now_ms=step * 100)
    historian.flush(timeout=15)
    historian.stop(timeout=5)
    return historian


class HistoryTransportUnitTests(unittest.TestCase):
    def test_rejected_write_drains_its_small_body_before_replying(self):
        handler = object.__new__(Handler)
        handler.headers = {"Content-Length": "2"}
        handler.rfile = io.BytesIO(b"{}")
        handler.wfile = io.BytesIO()
        handler.request_version = "HTTP/1.1"
        handler.command = "PUT"
        handler.path = "/api/fleet"
        handler.requestline = "PUT /api/fleet HTTP/1.1"
        handler.client_address = ("127.0.0.1", 1)
        handler._reject_write()
        self.assertEqual(handler.rfile.tell(), 2)
        self.assertIn(b"405 Method Not Allowed", handler.wfile.getvalue())


@SKIP
class MigrationTests(unittest.TestCase):
    def test_migrations_are_repeatable(self):
        first = db.migrate(_owner_settings())
        second = db.migrate(_owner_settings())
        self.assertEqual(second, [], f"re-running migrations applied {second} again")
        self.assertIsInstance(first, list)

    def test_every_expected_table_exists(self):
        with db.connect(_owner_settings()) as connection:
            names = {row[0] for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        for table in ("robots", "missions", "telemetry_samples", "derived_features",
                      "model_predictions", "fleet_events", "maintenance_findings",
                      "export_manifests", "schema_migrations"):
            self.assertIn(table, names)

    def test_indexes_support_the_queries_the_dashboard_runs(self):
        with db.connect(_owner_settings()) as connection:
            indexes = {row[0] for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
        for index in ("telemetry_robot_time", "events_robot_time", "events_mission_time",
                      "events_severity_time", "missions_robot_time", "maintenance_unresolved"):
            self.assertIn(index, indexes)

    def test_constraints_reject_bad_data(self):
        _truncate()
        with db.connect(_owner_settings()) as connection:
            cases = [
                ("bad robot id", "INSERT INTO robots (robot_id, provenance, first_seen_ms, last_seen_ms)"
                                 " VALUES ('BAD ID', 'SIMULATED', 1, 1)"),
                ("unknown provenance", "INSERT INTO robots (robot_id, provenance, first_seen_ms, last_seen_ms)"
                                       " VALUES ('robot-01', 'MADE_UP', 1, 1)"),
                ("negative time", "INSERT INTO robots (robot_id, provenance, first_seen_ms, last_seen_ms)"
                                  " VALUES ('robot-01', 'SIMULATED', -5, 1)"),
                ("orphan telemetry", "INSERT INTO telemetry_samples (event_id, robot_id, observed_ms,"
                                     " received_ms, provenance, source_mode, channels)"
                                     " VALUES ('e1', 'robot-nope', 1, 1, 'SIMULATED', 'sim', '{}')"),
                ("unknown severity", "INSERT INTO fleet_events (event_id, robot_id, kind, severity,"
                                     " observed_ms, received_ms, provenance)"
                                     " VALUES ('e2', 'robot-01', 'health_event', 'apocalyptic', 1, 1, 'SIMULATED')"),
            ]
            for label, statement in cases:
                with self.subTest(case=label):
                    with self.assertRaises(Exception):
                        connection.execute(statement)
                        connection.commit()
                    connection.rollback()


@SKIP
class HistorianWriteTests(unittest.TestCase):
    def test_every_robot_gets_history_and_kinds_land_in_their_own_tables(self):
        _truncate()
        historian = _seed()
        self.assertEqual(historian.health()["failed_rows"], 0, historian.health()["last_error"])
        with db.connect(_owner_settings()) as connection:
            counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                      for table in ("robots", "missions", "telemetry_samples",
                                    "model_predictions", "fleet_events")}
            per_robot = dict(connection.execute(
                "SELECT robot_id, count(*) FROM telemetry_samples GROUP BY robot_id").fetchall())
        self.assertEqual(counts["robots"], 3)
        self.assertEqual(counts["missions"], 3)
        self.assertEqual(counts["telemetry_samples"], 18)
        self.assertEqual(counts["model_predictions"], 18)
        self.assertGreater(counts["fleet_events"], 0)
        self.assertEqual(set(per_robot.values()), {6})

    def test_a_duplicate_delivery_is_idempotent(self):
        _truncate()
        historian = Historian(_owner_settings())
        historian.start()
        guardian = FleetGuardian(sink=historian.submit, expected_interval_ms=100)
        guardian.start_mission("robot-01", pickup="A1", destination="C2",
                               cargo_type="standard", mission_id="m1")
        payload = sample("robot-01", seq=1, observed_ms=100, channels=GOOD, zone="A1",
                         prediction=CONFIDENT)
        guardian.ingest(payload, now_ms=100)
        # Same event_id delivered twice must not become two history rows.
        historian.submit({**payload, "mission_id": "m1"})
        historian.flush(timeout=15)
        historian.stop(timeout=5)
        with db.connect(_owner_settings()) as connection:
            rows = connection.execute("SELECT count(*) FROM telemetry_samples").fetchone()[0]
        self.assertEqual(rows, 1)

    def test_safety_continues_and_drops_are_counted_while_the_database_is_down(self):
        unreachable = db.Settings("127.0.0.1", 1, TEST_DATABASE, "nobody", "nothing")
        historian = Historian(unreachable, max_queue=20)
        historian.start()
        guardian = FleetGuardian(sink=historian.submit, expected_interval_ms=100)
        for step in range(1, 121):
            # Vary the channel slightly: 120 byte-identical samples would (correctly) trip the
            # flatline rule, and this test is about the database being down, not about health.
            moving = {"bmi270.accelX": 0.1 + step * 1e-3, "bmi270.accelZ": 9.81 + step * 1e-3}
            result = guardian.ingest(sample("robot-01", seq=step, observed_ms=step * 100,
                                            channels=moving, prediction=CONFIDENT), now_ms=step * 100)
            self.assertTrue(result["accepted"])
            self.assertEqual(result["status"], "MOVING",
                             f"a dead database changed the decision: {result}")
        # The writer's connect attempt has its own timeout, so give it a moment to report the
        # failure rather than racing it. The point is that the failure is *visible*, not silent.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and historian.health()["last_error"] is None:
            time.sleep(0.1)
        health = historian.health()
        historian.stop(timeout=5)
        self.assertFalse(health["connected"])
        self.assertGreater(health["dropped"], 0, "a full queue against a dead database must drop")
        self.assertIsNotNone(health["last_error"], "a database outage must be reported, not silent")
        self.assertEqual(guardian.robots["robot-01"].samples, 120)

    def test_stale_rows_cannot_prove_current_run_persistence(self):
        _truncate()
        _seed()
        expected = {"robot-alpha", "robot-bravo", "robot-charlie"}
        with db.connect(_owner_settings()) as connection:
            stale = _database_rows_for_missions(
                connection, [f"m-{robot_id}" for robot_id in expected])
            current = _database_rows_for_missions(
                connection, [f"new-run-m1-{robot_id}" for robot_id in expected])
        self.assertEqual(set(stale), expected)
        self.assertEqual(current, {})
        self.assertFalse(_current_run_history_complete(
            current, expected, writer_written=sum(stale.values())))
        self.assertTrue(_current_run_history_complete(
            stale, expected, writer_written=sum(stale.values())))


@SKIP
class HistoryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _truncate()
        _seed()
        # History reads as the owner; the copilot endpoints read as the SELECT-only role, which is
        # the whole point of keeping the two settings apart.
        cls.server = serve(port=8098, settings=_owner_settings(),
                           readonly_settings=_readonly_settings())
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:8098{path}", timeout=10) as response:
            return response.status, json.load(response)

    def test_every_read_endpoint_answers(self):
        for path in ("/api", "/api/health", "/api/fleet", "/api/events", "/api/predictions",
                     "/api/missions", "/api/maintenance", "/api/zones", "/api/data-quality",
                     "/api/exports", "/api/telemetry?robot_id=robot-alpha"):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIsInstance(body, dict)

    def test_the_api_never_returns_a_credential(self):
        _status, body = self.get("/api/health")
        self.assertNotIn(db.settings_from_env().password, json.dumps(body))
        self.assertIn("@", body["database"])  # redacted identity only

    def test_write_methods_are_refused_by_the_transport(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                request = urllib.request.Request("http://127.0.0.1:8098/api/fleet",
                                                 method=method, data=b"{}")
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=10)
                self.assertEqual(caught.exception.code, 405)

    def test_bad_input_is_rejected_not_executed(self):
        for path in ("/api/telemetry?robot_id=BAD%20ID", "/api/events?robot_id=%27%3B%20DROP--",
                     "/api/events?severity=apocalyptic", "/api/telemetry",
                     "/api/events?page=", "/api/events?page=0", "/api/events?page=one",
                     "/api/events?limit=21", "/api/missions?page=1&page=2"):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://127.0.0.1:8098{path}", timeout=10)
                self.assertEqual(caught.exception.code, 400)
        with db.connect(_owner_settings()) as connection:
            self.assertGreater(connection.execute("SELECT count(*) FROM robots").fetchone()[0], 0)

    def test_operator_tables_return_at_most_twenty_rows_and_page_metadata(self):
        for endpoint, key in (("/api/events", "events"), ("/api/missions", "missions")):
            with self.subTest(endpoint=endpoint):
                _status, body = self.get(endpoint)
                self.assertLessEqual(len(body[key]), 20)
                self.assertEqual(body["page"], 1)
                self.assertEqual(body["page_size"], 20)
                self.assertFalse(body["has_previous"])
                self.assertEqual(body["range_end"], len(body[key]))

    def test_csv_response_uses_active_filter_bom_and_download_headers(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:8098/api/events.csv?severity=info", timeout=10) as response:
            raw = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "text/csv; charset=utf-8")
            self.assertRegex(response.headers["Content-Disposition"],
                             r'attachment; filename="cargoshield_safety_events_\d{8}T\d{6}Z.csv"')
            self.assertEqual(int(response.headers["X-Row-Count"]),
                             len(list(csv.DictReader(io.StringIO(
                                 raw.decode("utf-8-sig"), newline="")))))
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")):
            self.assertEqual(row["severity"], "info")

    def test_unknown_endpoint_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen("http://127.0.0.1:8098/api/secrets", timeout=10)
        self.assertEqual(caught.exception.code, 404)

    def test_fleet_lists_every_seeded_robot(self):
        _status, body = self.get("/api/fleet")
        self.assertEqual({row["robot_id"] for row in body["robots"]},
                         {"robot-alpha", "robot-bravo", "robot-charlie"})

    # ---------- Maintenance Copilot endpoints ----------

    def test_the_copilot_index_states_its_boundary_and_its_provider_truthfully(self):
        _status, body = self.get("/api/copilot")
        # No provider is configured anywhere in this repository, and the API must say so rather
        # than imply a live model wrote the answers.
        self.assertIsNone(body["provider"])
        self.assertEqual(body["provider_status"], "not_connected")
        self.assertEqual(body["analysis_mode"], "deterministic")
        self.assertTrue(body["human_approval_required"])
        self.assertEqual({entry["id"] for entry in body["questions"]}, set(COPILOT_QUESTIONS))
        self.assertIn("publish any MQTT command", body["boundary"]["may_not"])
        self.assertIn("acknowledge a maintenance finding", body["boundary"]["may_not"])

    def test_every_curated_question_answers_with_its_evidence(self):
        for question, entry in COPILOT_QUESTIONS.items():
            path = f"/api/copilot/{question}"
            if entry["needs_robot"]:
                path += "?robot_id=robot-bravo"
            if question == "evidence":
                path += "&around_ms=1000"
            with self.subTest(question=question):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertEqual(body["question_id"], question)
                self.assertTrue(body["summary"])
                self.assertIsInstance(body["evidence"], list)
                self.assertIsNone(body["provider"])

    def test_a_question_outside_the_allowlist_has_no_endpoint(self):
        for path in ("/api/copilot/_query", "/api/copilot/available", "/api/copilot/drop-table"):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://127.0.0.1:8098{path}", timeout=10)
                self.assertEqual(caught.exception.code, 404)

    def test_a_per_robot_question_refuses_a_missing_or_invalid_robot(self):
        for path in ("/api/copilot/why-stop", "/api/copilot/checklist",
                     "/api/copilot/why-stop?robot_id=BAD%20ID"):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://127.0.0.1:8098{path}", timeout=10)
                self.assertEqual(caught.exception.code, 400)

    def test_the_copilot_endpoints_refuse_every_write_method(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                request = urllib.request.Request("http://127.0.0.1:8098/api/copilot",
                                                 method=method, data=b"{}")
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=10)
                self.assertEqual(caught.exception.code, 405)


@SKIP
class ExportTests(unittest.TestCase):
    def test_export_carries_provenance_and_a_truthful_manifest(self):
        _truncate()
        _seed()
        with tempfile.TemporaryDirectory() as directory:
            result = export(Path(directory), fmt="jsonl", settings=_owner_settings())
            self.assertGreater(result.row_count, 0)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["provenance"], ["SIMULATED"])
            self.assertEqual(sorted(manifest["robot_ids"]),
                             ["robot-alpha", "robot-bravo", "robot-charlie"])
            self.assertFalse(manifest["claims"]["contains_real_hardware_data"])
            self.assertIn("never be mixed into a held-out metric", manifest["claims"]["note"])
            rows = [json.loads(line) for line in
                    result.path.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(rows), result.row_count)
            for row in rows:
                self.assertIn(row["provenance"], contracts.PROVENANCE)

    def test_filters_narrow_the_slice_and_are_recorded(self):
        _truncate()
        _seed()
        with tempfile.TemporaryDirectory() as directory:
            result = export(Path(directory), fmt="csv", settings=_owner_settings(),
                            filters=ExportFilters(robot_ids=("robot-alpha",)))
            self.assertEqual(result.manifest["robot_ids"], ["robot-alpha"])
            self.assertEqual(result.manifest["filters"]["robot_ids"], ["robot-alpha"])
            header = result.path.read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("provenance", header)

    def test_an_invalid_filter_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(contracts.ContractError):
                export(Path(directory), fmt="jsonl", settings=_owner_settings(),
                       filters=ExportFilters(robot_ids=("BAD ID",)))
            with self.assertRaises(contracts.ContractError):
                export(Path(directory), fmt="parquet", settings=_owner_settings())


@SKIP
class MaintenanceBoundaryTests(unittest.TestCase):
    """The copilot boundary. Enforced by PostgreSQL, not by good intentions."""

    def setUp(self):
        _truncate()
        _seed()
        self.context = MaintenanceContext(_readonly_settings())

    def test_the_role_can_read(self):
        ok, reason = self.context.available()
        self.assertTrue(ok, reason)
        self.assertGreater(len(self.context.robots_needing_inspection().evidence) + 1, 0)

    def test_the_role_cannot_mutate_any_operational_table(self):
        statements = [
            "INSERT INTO robots (robot_id, provenance, first_seen_ms, last_seen_ms)"
            " VALUES ('robot-hack', 'SIMULATED', 1, 1)",
            "UPDATE robots SET status = 'HACKED'",
            "DELETE FROM fleet_events",
            "UPDATE fleet_events SET action = 'MOVE'",
            "INSERT INTO maintenance_findings (robot_id, opened_ms, severity, reason)"
            " VALUES ('robot-alpha', 1, 'info', 'self-acknowledged')",
            "UPDATE maintenance_findings SET acknowledged_ms = 1, acknowledged_by = 'hermes'",
            "TRUNCATE telemetry_samples",
            "DROP TABLE robots",
        ]
        with db.connect(_readonly_settings()) as connection:
            for statement in statements:
                with self.subTest(statement=statement[:48]):
                    with self.assertRaises(Exception):
                        connection.execute(statement)
                        connection.commit()
                    connection.rollback()
        # And nothing changed.
        with db.connect(_owner_settings()) as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM robots WHERE robot_id = 'robot-hack'").fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM robots WHERE status = 'HACKED'").fetchone()[0], 0)

    def test_every_sql_statement_in_the_module_is_a_select(self):
        """Parsed, not grepped: prose about INSERT is fine, an actual INSERT is not."""
        import ast

        import cargo.maintenance as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        statements = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_query" and node.args):
                # SQL is written as adjacent string literals, which the parser folds into one node.
                self.assertIsInstance(node.args[0], ast.Constant,
                                      "SQL must be a literal, never assembled from input")
                statements.append(node.args[0].value)
        self.assertGreaterEqual(len(statements), 7, "expected one query per curated question")
        for statement in statements:
            with self.subTest(sql=statement[:48]):
                self.assertTrue(statement.lstrip().upper().startswith("SELECT"))
                for verb in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE", "DROP ", "ALTER ", "GRANT "):
                    self.assertNotIn(verb, statement.upper())

    def test_the_module_exposes_no_transport_and_no_mutator(self):
        import cargo.maintenance as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("import paho", "paho.mqtt", ".publish(", "subprocess", "os.system"):
            self.assertNotIn(forbidden, source, f"maintenance context references {forbidden!r}")
        public = [name for name in dir(self.context) if not name.startswith("_")]
        for name in public:
            self.assertFalse(any(verb in name for verb in ("write", "publish", "send", "set_",
                                                           "update", "delete", "acknowledge", "clear")),
                             f"{name} looks like a mutator")

    def test_every_curated_question_answers_with_its_evidence(self):
        answers = [
            self.context.why_did_robot_stop("robot-alpha"),
            self.context.evidence_for_conclusion("robot-alpha", around_ms=300),
            self.context.highest_vibration_exposure(),
            self.context.robots_needing_inspection(),
            self.context.maintenance_checklist("robot-alpha"),
            self.context.shift_summary(since_ms=0),
            self.context.exportable_ranges(),
        ]
        for answer in answers:
            with self.subTest(question=answer.question):
                self.assertTrue(answer.summary)
                self.assertIsInstance(answer.evidence, list)
                self.assertEqual(answer.as_dict()["boundary"], BOUNDARY)

    def test_the_declared_boundary_forbids_the_dangerous_actions(self):
        forbidden = " ".join(BOUNDARY["may_not"]).lower()
        for phrase in ("publish", "safe stop", "threshold", "acknowledge", "operational table"):
            self.assertIn(phrase, forbidden)
        self.assertEqual(BOUNDARY["real_time_role"],
                         "none; the deterministic Safety Core has already acted")

    def test_it_degrades_gracefully_when_the_database_is_gone(self):
        offline = MaintenanceContext(db.Settings("127.0.0.1", 1, TEST_DATABASE, "nobody", "nothing"))
        ok, reason = offline.available()
        self.assertFalse(ok)
        self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
