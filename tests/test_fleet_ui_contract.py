from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "webapp" / "fleet.html").read_text(encoding="utf-8")
JS = (ROOT / "webapp" / "fleet.js").read_text(encoding="utf-8")


class FleetUiContractTests(unittest.TestCase):
    def test_events_and_missions_have_independent_pagers_and_downloads(self):
        for prefix in ("event", "mission"):
            for suffix in ("prev", "next", "page", "range", "download", "download-status"):
                self.assertIn(f'id="{prefix}-{suffix}"', HTML)

    def test_information_order_puts_operations_before_collapsed_data_tools(self):
        positions = [
            HTML.index('id="events-heading"'),
            HTML.index('id="missions-heading"'),
            HTML.index('id="copilot-heading"'),
            HTML.index('id="data-tools"'),
        ]
        self.assertEqual(positions, sorted(positions))
        details = HTML[HTML.index('<details id="data-tools"'):HTML.index('</details>') + 10]
        self.assertNotIn('<details id="data-tools" open', details)
        for retained in ("zone-rows", "series-charts", "quality-list", "export-command"):
            self.assertIn(f'id="{retained}"', details)

    def test_frontend_uses_the_twenty_row_api_contract(self):
        self.assertIn("const PAGE_SIZE = 20;", JS)
        self.assertNotIn("MAX_ROWS = 50", JS)
        self.assertIn("page: String(current.page)", JS)
        self.assertIn("/api/events?${query}", JS)
        self.assertIn("page=${state.missions.page}", JS)

    def test_filter_reset_and_csv_download_paths_are_explicit(self):
        self.assertIn("state.events.page = 1", JS)
        self.assertIn("/api/events.csv", JS)
        self.assertIn("/api/missions.csv", JS)
        self.assertIn("URL.createObjectURL", JS)
        self.assertNotIn("alert(", JS)

    def test_production_uses_the_same_origin_mqtt_proxy_without_exposing_db_details(self):
        self.assertIn("const isLocalHost", JS)
        self.assertIn("${location.host}/mqtt", JS)
        self.assertNotIn("text(health.database)", JS)
        self.assertIn("History พร้อมใช้งาน", JS)

    def test_deployment_starts_the_fleet_telemetry_consumer(self):
        start = (ROOT / "deploy" / "start.sh").read_text(encoding="utf-8")
        self.assertIn("python3 -m cargo.fleet_service &", start)


if __name__ == "__main__":
    unittest.main()
