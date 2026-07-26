from __future__ import annotations

import csv
import io
import unittest

from cargo import contracts
from cargo.export import csv_bytes
from cargo.history_api import (
    CSV_MAX_ROWS,
    Handler,
    HistoryQueries,
    _CsvDownload,
    _pagination,
)


class PaginationContractTests(unittest.TestCase):
    def test_defaults_to_twenty_rows_on_page_one(self):
        self.assertEqual(_pagination({}), (1, 20, 0))

    def test_page_and_limit_produce_a_parameterized_offset(self):
        self.assertEqual(_pagination({"page": ["3"], "limit": ["20"]}), (3, 20, 40))

    def test_malformed_or_out_of_range_values_are_rejected(self):
        for params in (
            {"page": [""]},
            {"page": ["0"]},
            {"page": ["-1"]},
            {"page": ["1.5"]},
            {"page": ["one"]},
            {"page": ["1", "2"]},
            {"limit": [""]},
            {"limit": ["0"]},
            {"limit": ["-1"]},
            {"limit": ["21"]},
            {"limit": ["twenty"]},
            {"limit": ["20", "10"]},
        ):
            with self.subTest(params=params), self.assertRaises(contracts.ContractError):
                _pagination(params)

    def test_events_and_missions_have_stable_tie_breakers_and_offsets(self):
        queries = object.__new__(HistoryQueries)
        calls = []
        queries._query = lambda sql, args: calls.append((sql, args)) or []

        queries.events(None, 0, 99, None, 21, 20)
        queries.missions(None, 21, 20)

        event_sql, event_args = calls[0]
        mission_sql, mission_args = calls[1]
        self.assertIn("ORDER BY observed_ms DESC, event_id DESC", event_sql)
        self.assertIn("LIMIT %s OFFSET %s", event_sql)
        self.assertEqual(event_args[-2:], (21, 20))
        self.assertIn("ORDER BY m.started_ms DESC, m.mission_id DESC", mission_sql)
        self.assertIn("LIMIT %s OFFSET %s", mission_sql)
        self.assertEqual(mission_args[-2:], (21, 20))


class CsvContractTests(unittest.TestCase):
    FIELDS = ("robot_id", "note", "provenance")

    def parse(self, raw: bytes):
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertTrue(text.startswith("robot_id,note,provenance\r\n"))
        self.assertTrue(text.endswith("\r\n"))
        return list(csv.DictReader(io.StringIO(text, newline="")))

    def test_excel_utf8_bom_thai_and_rfc4180_escaping(self):
        rows = [{
            "robot_id": "robot-thai",
            "note": 'ภาษาไทย, "quoted"\nnext line',
            "provenance": "SIMULATED",
        }]
        parsed = self.parse(csv_bytes(rows, self.FIELDS))
        self.assertEqual(parsed, rows)

    def test_formula_injection_prefixes_are_neutralized(self):
        for dangerous in ("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "\t=1+1", "  @cmd"):
            with self.subTest(dangerous=dangerous):
                parsed = self.parse(csv_bytes([{
                    "robot_id": "robot-a",
                    "note": dangerous,
                    "provenance": "DATASET",
                }], self.FIELDS))
                self.assertEqual(parsed[0]["note"], f"'{dangerous}")

    def test_empty_export_keeps_the_fixed_header(self):
        raw = csv_bytes([], self.FIELDS)
        self.assertEqual(raw.decode("utf-8-sig"), "robot_id,note,provenance\r\n")


class CsvEndpointTests(unittest.TestCase):
    class Queries:
        def __init__(self, rows):
            self.rows = rows
            self.event_call = None
            self.mission_call = None

        def events(self, *args):
            self.event_call = args
            return self.rows

        def missions(self, *args):
            self.mission_call = args
            return self.rows

    def handler(self, rows):
        handler = object.__new__(Handler)
        handler.queries = self.Queries(rows)
        return handler

    def test_event_csv_uses_active_filters_and_iso_timestamps(self):
        handler = self.handler([{
            "event_id": "evt-1",
            "robot_id": "robot-a",
            "mission_id": "mission-a",
            "kind": "safety_decision",
            "code": "SAFE_STOP",
            "severity": "critical",
            "observed_ms": 0,
            "received_ms": 1_000,
            "provenance": "DATASET",
            "zone": "A1",
            "status": "SAFE_STOPPED",
            "health_state": "HEALTHY",
            "action": "SAFE_STOP",
            "speed_ratio": 0,
            "reason": "=danger",
        }])
        result = handler._route(
            ["api", "events.csv"],
            {"robot_id": ["robot-a"], "severity": ["critical"], "from_ms": ["0"], "to_ms": ["1000"]},
        )

        self.assertIsInstance(result, _CsvDownload)
        self.assertEqual(result.row_count, 1)
        self.assertRegex(result.filename, r"^cargoshield_safety_events_\d{8}T\d{6}Z\.csv$")
        rows = list(csv.DictReader(io.StringIO(result.body.decode("utf-8-sig"), newline="")))
        self.assertEqual(rows[0]["observed_at"], "1970-01-01T00:00:00.000Z")
        self.assertEqual(rows[0]["received_at"], "1970-01-01T00:00:01.000Z")
        self.assertEqual(rows[0]["reason"], "'=danger")
        self.assertEqual(handler.queries.event_call[:4], ("robot-a", 0, 1000, "critical"))
        self.assertEqual(handler.queries.event_call[-2:], (CSV_MAX_ROWS + 1, 0))

    def test_mission_csv_is_not_limited_to_the_visible_page(self):
        rows = [{
            "mission_id": f"mission-{index:02d}",
            "robot_id": "robot-a",
            "cargo_type": "standard",
            "route": ["A1", "C2"],
            "route_cost": 1,
            "route_reason": "shortest",
            "started_ms": index,
            "ended_ms": None,
            "provenance": "SIMULATED",
        } for index in range(45)]
        result = self.handler(rows)._route(["api", "missions.csv"], {"robot_id": ["robot-a"]})

        self.assertEqual(result.row_count, 45)
        parsed = list(csv.DictReader(io.StringIO(result.body.decode("utf-8-sig"), newline="")))
        self.assertEqual(len(parsed), 45)
        self.assertEqual(parsed[0]["route"], "A1 \u2192 C2")

    def test_empty_csv_is_identified_without_inventing_rows(self):
        result = self.handler([])._route(["api", "events.csv"], {})
        self.assertEqual(result.row_count, 0)
        self.assertEqual(len(result.body.decode("utf-8-sig").splitlines()), 1)

    def test_export_over_the_documented_ceiling_is_rejected(self):
        rows = [{"event_id": str(index)} for index in range(CSV_MAX_ROWS + 1)]
        with self.assertRaisesRegex(contracts.ContractError, str(CSV_MAX_ROWS)):
            self.handler(rows)._route(["api", "events.csv"], {})


if __name__ == "__main__":
    unittest.main()
