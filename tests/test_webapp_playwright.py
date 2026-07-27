from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

from cargo.export import csv_bytes


ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
AFTER_SHOTS = ROOT / "reports" / "screenshots" / "after"


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


EVENTS = [{
    "event_id": f"event-{index:03d}",
    "robot_id": "robot-alpha" if index % 2 else "robot-bravo",
    "mission_id": f"mission-{index:03d}",
    "kind": "safety_decision",
    "code": "SLOW_DOWN" if index % 2 else "MOVE",
    "severity": "warning" if index % 2 else "info",
    "observed_ms": 2_000_000 - index,
    "received_ms": 2_000_100 - index,
    "provenance": "SIMULATED",
    "zone": "A1",
    "status": "SLOWING" if index % 2 else "MOVING",
    "health_state": "HEALTHY",
    "action": "SLOW_DOWN" if index % 2 else "MOVE",
    "speed_ratio": 0.5 if index % 2 else 1,
    "reason": f"stable-{index:03d}",
} for index in range(45)]

MISSIONS = [{
    "mission_id": f"mission-{index:03d}",
    "robot_id": "robot-alpha",
    "cargo_type": "standard",
    "route": ["A1", "B2", "C2"],
    "route_cost": index + 0.5,
    "route_reason": "lowest known vibration exposure",
    "started_ms": 2_000_000 - index,
    "ended_ms": 2_000_500 - index,
    "provenance": "SIMULATED",
} for index in range(45)]

FLEET_ROBOTS = [
    {"robot_id": "robot-alpha"},
    {"robot_id": "robot-bravo"},
]

EVENT_COLUMNS = (
    "event_id", "robot_id", "mission_id", "severity", "code", "kind", "observed_at",
    "received_at", "provenance", "zone", "status", "health_state", "action", "speed_ratio",
    "reason",
)
MISSION_COLUMNS = (
    "mission_id", "robot_id", "cargo_type", "route", "route_cost", "route_reason",
    "started_at", "ended_at", "provenance",
)


def page_payload(name, rows, query):
    page = int(query.get("page", ["1"])[0])
    limit = int(query.get("limit", ["20"])[0])
    offset = (page - 1) * limit
    shown = rows[offset:offset + limit]
    return {
        name: shown,
        "page": page,
        "page_size": limit,
        "has_previous": page > 1,
        "has_more": offset + limit < len(rows),
        "range_start": offset + 1 if shown else 0,
        "range_end": offset + len(shown) if shown else 0,
    }


class FleetPlaywrightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(QuietStaticHandler, directory=str(WEBAPP))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True)
        self.page = self.context.new_page()
        self.console_errors = []
        self.predictions = []
        self.samples = []
        self.page.on(
            "console",
            lambda message: self.console_errors.append(message.text) if message.type == "error" else None,
        )
        self.page.on("pageerror", lambda error: self.console_errors.append(str(error)))
        self.api_available = True
        self.page.route("http://127.0.0.1:8099/**", self.route_api)

    def tearDown(self):
        self.context.close()

    def route_api(self, route):
        parsed = urlparse(route.request.url)
        path, query = parsed.path, parse_qs(parsed.query, keep_blank_values=True)
        if not self.api_available:
            payload = (
                {"reachable": False, "database": "readonly@test", "reason": "test API unavailable"}
                if path == "/api/health"
                else {"provider": None, "questions": []}
            )
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(payload))
            return
        if path == "/api/health":
            payload = {"reachable": True, "database": "readonly@test", "reason": "ready"}
        elif path == "/api/fleet":
            payload = {"robots": FLEET_ROBOTS}
        elif path == "/api/events":
            severity = query.get("severity", [None])[0]
            rows = [row for row in EVENTS if not severity or row["severity"] == severity]
            payload = page_payload("events", rows, query)
        elif path == "/api/missions":
            payload = page_payload("missions", MISSIONS, query)
        elif path == "/api/zones":
            payload = {"zones": []}
        elif path == "/api/maintenance":
            payload = {"findings": []}
        elif path == "/api/data-quality":
            payload = {"provenance": [{"provenance": "SIMULATED", "samples": 45}]}
        elif path == "/api/exports":
            payload = {"manifests": []}
        elif path == "/api/copilot":
            payload = {"provider": None, "questions": []}
        elif path in ("/api/predictions", "/api/telemetry"):
            payload = (
                {"predictions": self.predictions}
                if path.endswith("predictions")
                else {"samples": self.samples}
            )
        elif path == "/api/events.csv":
            severity = query.get("severity", [None])[0]
            rows = [row for row in EVENTS if not severity or row["severity"] == severity]
            export_rows = [{**row, "observed_at": "1970-01-01T00:00:00.000Z",
                            "received_at": "1970-01-01T00:00:00.100Z"} for row in rows]
            self.fulfill_csv(route, csv_bytes(export_rows, EVENT_COLUMNS),
                             "cargoshield_safety_events_20260726T120000Z.csv", len(rows))
            return
        elif path == "/api/missions.csv":
            rows = [{**row, "route": " → ".join(row["route"]),
                     "started_at": "1970-01-01T00:00:00.000Z",
                     "ended_at": "1970-01-01T00:00:01.000Z"} for row in MISSIONS]
            self.fulfill_csv(route, csv_bytes(rows, MISSION_COLUMNS),
                             "cargoshield_mission_history_20260726T120000Z.csv", len(rows))
            return
        else:
            route.fulfill(status=404, content_type="application/json", body='{"error":"not found"}')
            return
        route.fulfill(status=200, content_type="application/json; charset=utf-8",
                      body=json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def fulfill_csv(route, body, filename, row_count):
        route.fulfill(
            status=200,
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Row-Count": str(row_count),
                "Access-Control-Expose-Headers": "Content-Disposition, X-Row-Count",
            },
            body=body,
        )

    def open_fleet(self):
        self.page.goto(f"{self.base}/fleet.html?mqtt=off", wait_until="load")
        self.page.wait_for_function("document.querySelectorAll('#event-rows tr').length === 20")
        self.page.wait_for_function("document.querySelectorAll('#mission-rows tr').length === 20")

    def screenshot(self, name):
        AFTER_SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(AFTER_SHOTS / f"{name}.png"))

    def test_loading_and_intentional_disconnected_states(self):
        self.page.add_init_script("""
          const liveFetch = window.fetch.bind(window);
          let releaseHistory;
          const historyGate = new Promise((resolve) => { releaseHistory = resolve; });
          window.__releaseHistory = releaseHistory;
          window.fetch = (input, init) => {
            const url = String(input);
            return url.includes('/api/events') || url.includes('/api/missions')
              ? historyGate.then(() => liveFetch(input, init))
              : liveFetch(input, init);
          };
        """)
        self.page.goto(f"{self.base}/fleet.html?mqtt=off", wait_until="load")
        self.page.wait_for_function(
            "document.querySelector('#event-rows').textContent.includes('กำลังโหลดข้อมูล')"
            " && document.querySelector('#mission-rows').textContent.includes('กำลังโหลดข้อมูล')")
        self.assertTrue(self.page.locator("#event-prev").is_disabled())
        self.assertTrue(self.page.locator("#event-next").is_disabled())
        self.assertTrue(self.page.locator("#mission-prev").is_disabled())
        self.assertTrue(self.page.locator("#mission-next").is_disabled())
        self.assertIn("MQTT ปิดอยู่", self.page.locator("#link-text").inner_text())
        self.page.evaluate("window.__releaseHistory()")
        self.page.wait_for_function("document.querySelectorAll('#event-rows tr').length === 20")
        self.page.wait_for_function("document.querySelectorAll('#mission-rows tr').length === 20")
        self.assertEqual(self.console_errors, [])

    def test_pagination_edges_filter_reset_and_independent_state(self):
        self.open_fleet()
        self.assertTrue(self.page.locator("#event-prev").is_disabled())
        self.assertFalse(self.page.locator("#event-next").is_disabled())
        self.assertEqual(self.page.locator("#event-rows tr").count(), 20)
        self.assertEqual(self.page.locator("#event-rows tr").first.locator("td").nth(3).inner_text(),
                         "safety_decision")

        self.page.locator("#event-next").click()
        self.page.wait_for_function("document.querySelector('#event-page').textContent.includes('2')")
        self.assertEqual(self.page.locator("#event-rows tr").count(), 20)
        self.assertFalse(self.page.locator("#event-prev").is_disabled())
        self.assertFalse(self.page.locator("#event-next").is_disabled())
        self.assertIn("หน้า 1", self.page.locator("#mission-page").inner_text())

        self.page.locator("#event-next").click()
        self.page.wait_for_function(
            "document.querySelector('#event-page').textContent.includes('3')"
            " && document.querySelectorAll('#event-rows tr').length === 5")
        self.assertEqual(self.page.locator("#event-rows tr").count(), 5)
        self.assertTrue(self.page.locator("#event-next").is_disabled())

        self.page.locator("#event-severity").select_option("warning")
        self.page.wait_for_function("document.querySelector('#event-page').textContent.includes('1')")
        self.assertLessEqual(self.page.locator("#event-rows tr").count(), 20)
        severities = self.page.locator("#event-rows tr td:nth-child(3)").all_inner_texts()
        self.assertTrue(severities and set(severities) == {"warning"})
        self.assertIn("หน้า 1", self.page.locator("#mission-page").inner_text())
        self.assertEqual(self.console_errors, [])

    def test_history_roster_fills_robot_selectors_without_mqtt(self):
        self.open_fleet()
        expected = [robot["robot_id"] for robot in FLEET_ROBOTS]
        self.assertEqual(self.page.locator("#series-robot option").all_text_contents(), expected)
        self.assertEqual(self.page.locator("#copilot-robot option").all_text_contents(), expected)
        self.assertEqual(self.console_errors, [])

    def test_csv_download_uses_active_filter_and_exports_beyond_visible_page(self):
        self.open_fleet()
        self.page.locator("#event-severity").select_option("warning")
        with self.page.expect_download() as event_info:
            self.page.locator("#event-download").click()
        event_download = event_info.value
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / event_download.suggested_filename
            event_download.save_as(event_path)
            raw = event_path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
        self.assertTrue(rows and {row["severity"] for row in rows} == {"warning"})
        self.assertIn("สำเร็จ", self.page.locator("#event-download-status").inner_text())

        with self.page.expect_download() as mission_info:
            self.page.locator("#mission-download").click()
        mission_download = mission_info.value
        self.assertRegex(mission_download.suggested_filename,
                         r"^cargoshield_mission_history_\d{8}T\d{6}Z\.csv$")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / mission_download.suggested_filename
            mission_download.save_as(path)
            rows = list(csv.DictReader(io.StringIO(
                path.read_bytes().decode("utf-8-sig"), newline="")))
        self.assertEqual(len(rows), 45)
        self.screenshot("Fleet_CSV_success_mock")
        self.assertEqual(self.console_errors, [])

    def test_sparkline_breaks_the_line_across_missing_samples(self):
        self.samples = [
            {"channels": {"sht40.temperatureC": 40}},
            {"channels": {"sht40.temperatureC": 30}},
            {"channels": {}},
            {"channels": {"sht40.temperatureC": 20}},
            {"channels": {"sht40.temperatureC": 10}},
        ]
        self.open_fleet()
        self.page.evaluate("""() => {
          const select = document.querySelector('#series-robot');
          select.append(new Option('robot-alpha', 'robot-alpha'));
          select.value = 'robot-alpha';
          select.dispatchEvent(new Event('change'));
        }""")
        temperature = self.page.locator("#series-charts .series-item").nth(2)
        temperature.locator("polyline").nth(1).wait_for(state="attached")
        self.assertEqual(temperature.locator("polyline").count(), 2)

    def test_empty_error_keyboard_focus_targets_and_responsive_overflow(self):
        self.open_fleet()
        self.page.locator("#event-severity").select_option("critical")
        self.page.wait_for_function(
            "document.querySelector('#event-rows').textContent.includes('ไม่พบเหตุการณ์')")
        self.assertTrue(self.page.locator("#event-prev").is_disabled())
        self.assertTrue(self.page.locator("#event-next").is_disabled())
        self.screenshot("Fleet_empty_state")
        downloads = []
        self.page.on("download", lambda download: downloads.append(download))
        self.page.locator("#event-download").click()
        self.page.wait_for_function(
            "document.querySelector('#event-download-status').textContent.includes('ไม่มีไฟล์')")
        self.assertEqual(downloads, [])

        self.page.locator("#event-severity").select_option("")
        self.page.wait_for_function("!document.querySelector('#event-next').disabled")
        self.page.evaluate("document.activeElement.blur()")
        for _ in range(40):
            self.page.keyboard.press("Tab")
            if self.page.evaluate("document.activeElement?.id") == "event-next":
                break
        focus = self.page.evaluate("""() => {
          const e = document.activeElement, s = getComputedStyle(e);
          return { id: e.id, visible: e.matches(':focus-visible'), width: parseFloat(s.outlineWidth) };
        }""")
        self.assertEqual(focus["id"], "event-next")
        self.assertTrue(focus["visible"])
        self.assertGreaterEqual(focus["width"], 2)
        self.page.keyboard.press("Enter")
        self.page.wait_for_function("document.querySelector('#event-page').textContent.includes('2')")

        for width, height in ((1920, 1080), (1440, 900), (1280, 720), (1024, 768), (960, 540)):
            with self.subTest(viewport=(width, height)):
                self.page.set_viewport_size({"width": width, "height": height})
                overflow = self.page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth")
                self.assertLessEqual(overflow, 0)
        target_sizes = self.page.locator(
            "button:visible, select:visible, input:visible, summary:visible").evaluate_all(
                """(nodes) => nodes.map((node) => ({
                  tag: node.tagName, id: node.id, height: node.getBoundingClientRect().height
                }))""")
        self.assertTrue(target_sizes)
        self.assertGreaterEqual(min(item["height"] for item in target_sizes), 44, target_sizes)
        self.assertFalse(self.page.locator("#data-tools").get_attribute("open"))

        self.page.set_viewport_size({"width": 1440, "height": 900})
        self.api_available = False
        self.page.reload(wait_until="load")
        self.page.wait_for_function(
            "document.querySelector('#api-error') && !document.querySelector('#api-error').hidden")
        self.assertIn("unavailable", self.page.locator("#event-rows").inner_text())
        self.assertIn("unavailable", self.page.locator("#mission-rows").inner_text())
        self.page.locator("#events-heading").evaluate(
            "(node) => node.scrollIntoView({ block: 'start' })")
        self.screenshot("Fleet_API_unavailable")
        self.assertEqual(self.console_errors, [])

    def test_mission_timeline_stays_inside_its_card(self):
        self.page.set_viewport_size({"width": 1280, "height": 720})
        self.page.goto(f"{self.base}/index.html?device=timeline-layout-test",
                       wait_until="domcontentloaded")
        self.page.evaluate("""() => {
          const list = document.getElementById('timeline');
          list.replaceChildren(...Array.from({ length: 60 }, (_, index) => {
            const item = document.createElement('li');
            item.innerHTML =
              `<time>20:${String(index).padStart(2, '0')}:00</time>`
              + '<span>prediction hard_tiles_large_space (0.62): MOVE</span>';
            return item;
          }));
        }""")
        self.page.locator("#timeline-heading").evaluate(
            "(node) => node.scrollIntoView({ block: 'center' })")
        layout = self.page.evaluate("""() => {
          const list = document.getElementById('timeline');
          const card = list.closest('.deck-card');
          const rect = card.getBoundingClientRect();
          const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.bottom + 8);
          return {
            contentEscapesCard: Boolean(hit?.closest('#timeline')),
            visibleHeight: list.clientHeight,
            contentHeight: list.scrollHeight,
          };
        }""")
        self.assertFalse(layout["contentEscapesCard"], layout)
        self.assertGreaterEqual(layout["visibleHeight"], 80, layout)
        self.assertGreater(layout["contentHeight"], layout["visibleHeight"], layout)
        self.page.locator("#timeline").focus()
        self.page.keyboard.press("PageDown")
        self.page.wait_for_timeout(100)
        self.assertGreater(self.page.locator("#timeline").evaluate("node => node.scrollTop"), 0)

    def test_mission_scroll_does_not_cover_controls(self):
        self.page.set_viewport_size({"width": 1280, "height": 720})
        self.page.goto(f"{self.base}/index.html?device=scroll-layout-test",
                       wait_until="domcontentloaded")
        self.page.locator("#controls-heading").evaluate(
            "(node) => node.scrollIntoView({ block: 'start' })")
        overlap = self.page.evaluate("""() => {
          const protection = document.getElementById('protection').getBoundingClientRect();
          const controls = document.getElementById('controls-heading')
            .closest('.panel').getBoundingClientRect();
          return Math.max(
            0,
            Math.min(protection.bottom, controls.bottom)
              - Math.max(protection.top, controls.top),
          );
        }""")
        self.assertLessEqual(overlap, 0)

    def test_sidebar_cards_follow_controls_without_a_large_gap_at_high_zoom(self):
        self.page.set_viewport_size({"width": 2560, "height": 1440})
        self.page.goto(f"{self.base}/index.html?device=sidebar-layout-test",
                       wait_until="domcontentloaded")
        gap = self.page.evaluate("""() => {
          const tech = document.querySelector('aside details.tech').getBoundingClientRect();
          const deck = document.querySelector('.deck').getBoundingClientRect();
          return deck.top - tech.bottom;
        }""")
        self.assertLessEqual(gap, 16, gap)


if __name__ == "__main__":
    unittest.main()
