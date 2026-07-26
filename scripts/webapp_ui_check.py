"""Drive the operator console in a real browser against the real broker and record the evidence.

Needs the broker on 127.0.0.1:1883/8883, `python -m cargo.mqtt_service` running, and the webapp
folder served over HTTP (Bitstream Studio's **Serve Web App Folder over HTTP**, or any static
server). Then:

    .\\.venv\\Scripts\\python.exe scripts/webapp_ui_check.py --url http://127.0.0.1:8080/

Writes reports/webapp_ui_evidence.json and reports/screenshots/*.png.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "reports" / "screenshots" / "after"
DOWNLOADS = ROOT / "reports" / "downloads"

# Chromium needs a software rasteriser to give a headless page a WebGL context.
LAUNCH_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
MISSION_COMPLETION_TIMEOUT_S = 90


# Emitted by the vendored MQTT SDK when a publish races a WebSocket reconnect. It is transport
# noise, not an application fault: app.js now retries the command across the reconnect window, so
# the operator's action still lands. Counted and reported separately rather than hidden.
TRANSPORT_NOISE = ("WebSocket is already in CLOSING or CLOSED state",)


class Console:
    """Every console message and uncaught error the page produced, in order."""

    def __init__(self, page) -> None:
        self.messages: list[dict] = []
        page.on("console", lambda m: self.messages.append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: self.messages.append({"type": "pageerror", "text": str(e)}))
        page.on("requestfailed", lambda r: self.messages.append({"type": "requestfailed", "text": f"{r.url} {r.failure}"}))

    @property
    def _raw_errors(self) -> list[dict]:
        return [m for m in self.messages if m["type"] in {"error", "pageerror", "requestfailed"}]

    @property
    def transport_noise(self) -> list[dict]:
        return [m for m in self._raw_errors if any(marker in m["text"] for marker in TRANSPORT_NOISE)]

    @property
    def errors(self) -> list[dict]:
        """Strict gate: every browser error, including a failed request or transport write."""
        return self._raw_errors


def status(page) -> str:
    """The raw engine enum, not the rendered label, so translating the UI cannot break the check."""
    return (page.get_attribute("#status", "data-status") or "").strip()


def states_rendered(page) -> int:
    """How many states the engine has published to this page so far."""
    return int(page.get_attribute("#status", "data-states") or 0)


def wait_status(page, *wanted: str, timeout: float = 30.0, since: int = 0) -> str:
    """Wait for a state the engine published *after* `since`.

    Without the `since` guard this returned immediately whenever the page already showed a wanted
    value, so a step could pass before its command had even reached the broker and the next step
    would then race a command still in flight. That was one of two causes of the flaky baseline
    recorded in docs/FLEET_GUARDIAN_PHASE0_BASELINE.md.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if states_rendered(page) > since and status(page) in wanted:
            return status(page)
        page.wait_for_timeout(60)
    raise AssertionError(
        f"timed out waiting for {wanted} after state #{since}; "
        f"page shows {status(page)!r} at state #{states_rendered(page)}"
    )


def snapshot(page, name: str) -> str:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path))
    return str(path.relative_to(ROOT)).replace("\\", "/")


def set_obstacle(page, centimetres: int) -> None:
    # Exercise the operator-facing number field, not just the range input.
    page.fill("#obstacle-value", str(centimetres))
    page.click("#obstacle-send")


def probe_variant(browser, url: str, *, reduced_motion: str | None = None, block_webgl: bool = False) -> dict:
    """Open the console once more under a hostile condition and check it still works."""
    context = browser.new_context(viewport={"width": 1600, "height": 950}, reduced_motion=reduced_motion)
    page = context.new_page()
    console = Console(page)
    if block_webgl:
        page.add_init_script(
            "HTMLCanvasElement.prototype.getContext = new Proxy(HTMLCanvasElement.prototype.getContext,"
            " { apply: (fn, self, a) => (String(a[0]).startsWith('webgl') ? null : Reflect.apply(fn, self, a)) });"
        )
    try:
        page.goto(url, wait_until="load")
        # WebGL/reduced-motion are rendering contracts, independent of whether retained MQTT state
        # arrives in this short-lived second context.
        page.wait_for_selector("#stage-fallback", state="attached")
        page.wait_for_timeout(800)
        name = "reduced_motion" if reduced_motion else "no_webgl"
        if reduced_motion:
            page.click('button[data-camera-mode="robot-pov"]')
            page.wait_for_function(
                "() => document.getElementById('stage').dataset.cameraMode === 'robot-pov'")
        return {
            "status_rendered": page.inner_text("#status"),
            "controls_usable": page.is_enabled('button[data-cmd="start"]'),
            "camera_mode": page.get_attribute("#stage", "data-camera-mode"),
            "camera_buttons_disabled": page.eval_on_selector_all(
                "button[data-camera-mode]", "nodes => nodes.every(node => node.disabled)"),
            "telemetry_rendered": page.inner_text("#v-route_nodes"),
            "canvas_visible": page.is_visible("#stage"),
            "fallback_shown": page.is_visible("#stage-fallback"),
            "console_errors": console.errors,
            "screenshot": snapshot(page, name),
        }
    finally:
        context.close()


def probe_fleet_page(browser, url: str, api: str) -> dict:
    """Fleet Intelligence is a separate surface; it must stand up on its own evidence."""
    # `url` may already carry a query string (e.g. ?device=...), so build the fleet URL from its
    # path rather than concatenating onto it.
    base = urlsplit(url)
    directory = base.path.rsplit("/", 1)[0] + "/"
    fleet_url = urlunsplit((base.scheme, base.netloc, directory + "fleet.html",
                            urlencode({"api": api}), ""))
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    console = Console(page)
    try:
        page.goto(fleet_url, wait_until="load")
        # Live summary arrives over MQTT from the retained fleet status topic.
        page.wait_for_function("() => document.getElementById('count-total').textContent !== '—'", timeout=20000)
        # History arrives over the read-only API, which reports its own reachability.
        page.wait_for_function("() => document.getElementById('api-text').textContent !== 'กำลังตรวจสอบ…'", timeout=20000)
        # MQTT supplies the robot selector while HTTP supplies its series. Waiting a fixed delay
        # raced those two independent callbacks and sometimes captured the placeholder rows.
        page.wait_for_function(
            "() => document.querySelectorAll('.series-item').length >= 1",
            timeout=20000,
        )
        page.wait_for_function(
            "() => document.querySelectorAll('#event-rows tr').length > 0"
            " && document.querySelectorAll('#mission-rows tr').length > 0",
            timeout=20000,
        )
        rows = page.eval_on_selector_all("#robot-rows tr", "nodes => nodes.length")
        page.keyboard.press("Tab")
        first_focus = page.evaluate("() => document.activeElement?.className || document.activeElement?.tagName")
        evidence = {
            "robot_rows": rows,
            "fleet_total": page.inner_text("#count-total"),
            "history_api": page.inner_text("#api-text"),
            "history_api_ok": page.evaluate("() => document.getElementById('api-dot').className.includes('dot-go')"),
            "simulated_badge": page.inner_text("#provenance-badge"),
            "simulated_notice_visible": page.is_visible(".sim-notice"),
            "zone_rows": page.eval_on_selector_all("#zone-rows tr", "nodes => nodes.length"),
            "event_rows": page.eval_on_selector_all("#event-rows tr", "nodes => nodes.length"),
            "mission_rows": page.eval_on_selector_all("#mission-rows tr", "nodes => nodes.length"),
            "series_charts": page.eval_on_selector_all(".series-item", "nodes => nodes.length"),
            "export_command": page.inner_text("#export-command"),
            "first_tab_stop": first_focus,
            "horizontal_overflow_px": page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"),
            "console_errors": console.errors,
            "url": fleet_url,
            "screenshot": snapshot(page, "Fleet_overview_1440x900"),
        }

        page.locator("#events-heading").evaluate(
            "(node) => node.scrollIntoView({ block: 'start' })")
        page.wait_for_timeout(250)
        page.locator("#event-page").evaluate(
            "(node) => node.scrollIntoView({ block: 'center' })")
        evidence["events_page_1"] = {
            "page": page.inner_text("#event-page"),
            "rows": page.locator("#event-rows tr").count(),
            "previous_disabled": page.is_disabled("#event-prev"),
            "next_disabled": page.is_disabled("#event-next"),
            "screenshot": snapshot(page, "Fleet_safety_events_page_1"),
        }
        page.click("#event-next")
        page.wait_for_function(
            "() => document.getElementById('event-page').textContent.includes('2')"
            " && document.querySelectorAll('#event-rows tr').length === 20")
        evidence["events_page_2"] = {
            "page": page.inner_text("#event-page"),
            "rows": page.locator("#event-rows tr").count(),
            "previous_disabled": page.is_disabled("#event-prev"),
            "next_disabled": page.is_disabled("#event-next"),
            "screenshot": snapshot(page, "Fleet_safety_events_page_2"),
        }
        page.select_option("#event-severity", "critical")
        page.wait_for_function(
            "() => document.getElementById('event-page').textContent.includes('1')"
            " && document.querySelectorAll('#event-rows tr td:nth-child(3)').length > 0"
            " && [...document.querySelectorAll('#event-rows tr td:nth-child(3)')]"
            ".every(node => node.textContent === 'critical')")
        evidence["filtered_events"] = {
            "filter": page.input_value("#event-severity"),
            "page": page.inner_text("#event-page"),
            "rows": page.locator("#event-rows tr").count(),
            "screenshot": snapshot(page, "Fleet_filtered_events"),
        }

        page.locator("#missions-heading").scroll_into_view_if_needed()
        page.click("#mission-next")
        page.wait_for_function(
            "() => document.getElementById('mission-page').textContent.includes('2')"
            " && document.querySelectorAll('#mission-rows tr').length === 20")
        evidence["mission_pagination"] = {
            "page": page.inner_text("#mission-page"),
            "rows": page.locator("#mission-rows tr").count(),
            "previous_disabled": page.is_disabled("#mission-prev"),
            "screenshot": snapshot(page, "Fleet_mission_pagination"),
        }

        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        with page.expect_download() as download_info:
            page.click("#event-download")
        download = download_info.value
        download_path = DOWNLOADS / download.suggested_filename
        download.save_as(download_path)
        raw = download_path.read_bytes()
        csv_rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
        page.wait_for_function(
            "() => document.getElementById('event-download-status').textContent.includes('สำเร็จ')")
        evidence["csv_download"] = {
            "path": str(download_path.relative_to(ROOT)).replace("\\", "/"),
            "filename": download.suggested_filename,
            "utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
            "rows": len(csv_rows),
            "filter": "critical",
            "filtered": bool(csv_rows) and {row["severity"] for row in csv_rows} == {"critical"},
            "screenshot": snapshot(page, "Fleet_CSV_success"),
        }

        page.locator("#data-tools").scroll_into_view_if_needed()
        evidence["data_tools"] = {
            "collapsed": page.get_attribute("#data-tools", "open") is None,
            "screenshot": snapshot(page, "Fleet_collapsed_data_tools"),
        }

        page.set_viewport_size({"width": 1920, "height": 1080})
        page.evaluate("() => scrollTo(0, 0)")
        page.wait_for_timeout(400)
        evidence["desktop_overflow_px"] = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        evidence["screenshot_desktop"] = snapshot(page, "Fleet_overview_1920x1080")
        page.set_viewport_size({"width": 1280, "height": 720})
        page.wait_for_timeout(300)
        evidence["laptop_overflow_px"] = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        evidence["screenshot_1280x720"] = snapshot(page, "Fleet_overview_1280x720")
        page.set_viewport_size({"width": 1440, "height": 900})
        evidence["maintenance_assistant"] = probe_maintenance_assistant(page)
        evidence["console_errors"] = console.errors
        return evidence
    finally:
        context.close()


def probe_maintenance_assistant(page) -> dict:
    """The read-only copilot panel: curated buttons only, and an answer that carries its evidence."""
    page.wait_for_function("() => document.querySelectorAll('#copilot-questions button').length > 0",
                           timeout=20000)
    questions = page.eval_on_selector_all(
        "#copilot-questions button", "nodes => nodes.map(n => n.dataset.question)")
    # Ask the fleet-wide question that needs no robot selection, so the answer is deterministic.
    page.click('#copilot-questions button[data-question="inspection"]')
    page.wait_for_function("() => document.querySelector('#copilot-answer .answer-summary')", timeout=20000)
    page.locator("#copilot-answer").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    return {
        "questions": questions,
        "provider_line": page.inner_text("#copilot-provider"),
        "badges": page.inner_text("#copilot-badges"),
        "answer_summary": page.inner_text("#copilot-answer .answer-summary"),
        "answer_meta": page.inner_text("#copilot-answer .answer-meta"),
        "evidence_rows": page.eval_on_selector_all("#copilot-answer tbody tr", "nodes => nodes.length"),
        # There must be no free-text box: the page can only ask the allowlisted questions.
        "free_text_inputs": page.eval_on_selector_all(
            "#copilot-answer input, #copilot-questions input, textarea", "nodes => nodes.length"),
        "screenshot": snapshot(page, "FLEET_maintenance_assistant"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Browser verification of the CargoShield operator console")
    parser.add_argument("--url", default="http://127.0.0.1:8080/")
    parser.add_argument("--api", default="http://127.0.0.1:8099", help="read-only history API base URL")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    evidence: dict = {"url": args.url, "steps": [], "screenshots": {}}

    with sync_playwright() as play:
        # Headed Chromium gets the real GPU; the software rasteriser is only needed headless.
        browser = play.chromium.launch(headless=not args.headed, args=[] if args.headed else LAUNCH_ARGS)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        console = Console(page)
        page.goto(args.url, wait_until="load")
        page.wait_for_selector("#link-text")
        page.wait_for_function("() => document.getElementById('link-text').textContent === 'เชื่อมต่อแล้ว'", timeout=20000)

        # 1. Retained state must render before the operator touches anything.
        page.wait_for_function("() => document.getElementById('status').textContent !== '—'", timeout=10000)
        evidence["retained_state_on_open"] = {
            "status": status(page),
            "age": page.inner_text("#age"),
            "rendered_before_any_click": True,
        }
        evidence["provenance_ui"] = {
            "source": page.inner_text("#v-source"),
            "progress_label": page.inner_text("#progress-label"),
            "start_button": page.inner_text('button[data-cmd="start"]'),
        }
        evidence["webgl"] = {
            "canvas_visible": page.is_visible("#stage"),
            "fallback_shown": page.is_visible("#stage-fallback"),
            "renderer": page.evaluate(
                "() => { const c = document.createElement('canvas').getContext('webgl2');"
                " const d = c && c.getExtension('WEBGL_debug_renderer_info');"
                " return d ? c.getParameter(d.UNMASKED_RENDERER_WEBGL) : (c ? 'webgl2' : null); }"
            ),
        }

        def step(name: str, action, *wanted: str, timeout: float = 30.0, shot: str | None = None) -> None:
            # Count states before acting, so the wait can only be satisfied by the engine's answer.
            before = states_rendered(page)
            action()
            reached = wait_status(page, *wanted, timeout=timeout, since=before)
            record = {"step": name, "status": reached}
            if shot:
                evidence["screenshots"][shot] = snapshot(page, shot)
                record["screenshot"] = evidence["screenshots"][shot]
            evidence["steps"].append(record)

        try:
            run_sequence(page, evidence, step, console)
            fallbacks = {
                "reduced_motion": probe_variant(browser, args.url, reduced_motion="reduce"),
                "no_webgl": probe_variant(browser, args.url, block_webgl=True),
            }
            evidence["fallbacks"] = fallbacks
            fleet = probe_fleet_page(browser, args.url, args.api)
            evidence["fleet_intelligence"] = fleet
            # Without WebGL the panels must carry the demo on their own, and neither variant may error.
            evidence["passed"] = (
                evidence["passed"]
                and "ไม่ใช่การวัดสด" in evidence["provenance_ui"]["source"]
                and "replay" in evidence["provenance_ui"]["progress_label"].casefold()
                and "dataset replay" in evidence["provenance_ui"]["start_button"].casefold()
                and fallbacks["no_webgl"]["fallback_shown"]
                and fallbacks["no_webgl"]["controls_usable"]
                and fallbacks["no_webgl"]["camera_buttons_disabled"]
                and fallbacks["reduced_motion"]["camera_mode"] == "robot-pov"
                and not fallbacks["no_webgl"]["console_errors"]
                and not fallbacks["reduced_motion"]["console_errors"]
                # Fleet Intelligence must render real fleet rows, reach the read-only history API,
                # keep its simulated-data badge visible, fit both viewports, and log nothing.
                and not fleet["console_errors"]
                and fleet["robot_rows"] >= 3
                and fleet["history_api_ok"]
                and fleet["simulated_notice_visible"]
                and "SIMULATED" in fleet["simulated_badge"]
                and fleet["series_charts"] >= 1
                and fleet["horizontal_overflow_px"] <= 0
                and fleet["desktop_overflow_px"] <= 0
                and fleet["laptop_overflow_px"] <= 0
                and fleet["first_tab_stop"] == "skip-link"
                and fleet["events_page_1"]["rows"] <= 20
                and fleet["events_page_1"]["previous_disabled"]
                and fleet["events_page_2"]["rows"] <= 20
                and not fleet["events_page_2"]["previous_disabled"]
                and fleet["filtered_events"]["page"].endswith("1")
                and fleet["mission_pagination"]["rows"] <= 20
                and fleet["csv_download"]["utf8_bom"]
                and fleet["csv_download"]["filtered"]
                and fleet["csv_download"]["rows"] > 20
                and fleet["data_tools"]["collapsed"]
                # The Maintenance Assistant offers the curated questions only, states its provider
                # honestly, and cites evidence rows rather than asserting a conclusion.
                and len(fleet["maintenance_assistant"]["questions"]) == 7
                and "Not connected" in fleet["maintenance_assistant"]["provider_line"]
                and "READ-ONLY" in fleet["maintenance_assistant"]["badges"]
                and "HUMAN APPROVAL REQUIRED" in fleet["maintenance_assistant"]["badges"]
                and fleet["maintenance_assistant"]["evidence_rows"] >= 1
                and fleet["maintenance_assistant"]["free_text_inputs"] == 0
            )
        except Exception as exc:  # a failed demo rehearsal is evidence too
            evidence["failure"] = {"error": f"{type(exc).__name__}: {exc}", "screenshot": snapshot(page, "FAILURE"),
                                   "timeline": page.inner_text("#timeline")[:2000],
                                   "console": console.messages[-20:]}
            evidence["passed"] = False
        browser.close()

    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "webapp_ui_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({k: evidence[k] for k in ("passed", "retained_state_on_open", "webgl", "fps", "console", "screenshots", "failure") if k in evidence}, indent=2))
    if not evidence["passed"]:
        raise SystemExit("browser verification failed; see reports/webapp_ui_evidence.json")


def run_sequence(page, evidence: dict, step, console: Console) -> None:
        # 2. The mandated demo sequence, every transition decided by the engine.
        # Normalise the mission first so the run is the documented A1 -> C2 standard-cargo demo.
        for selector, value in (("#cargo", "standard"), ("#pickup", "A1"), ("#destination", "C2")):
            page.select_option(selector, value)
            page.wait_for_timeout(400)
        step("reset", lambda: page.click('button[data-cmd="reset"]'), "IDLE", shot="IDLE")
        step("start", lambda: page.click('button[data-cmd="start"]'), "MOVING", "SLOWING", "HOLDING",
             timeout=MISSION_COMPLETION_TIMEOUT_S, shot="MOVING")
        # DEMO_SEQUENCE deliberately contains windows below the selected confidence threshold, so
        # the engine reaches HOLD_UNCERTAIN inside every run. Waiting for it here records the
        # "the model is not sure, so it stops rather than guessing" state as evidence.
        step("hold on low confidence", lambda: None, "HOLDING",
             timeout=MISSION_COMPLETION_TIMEOUT_S, shot="HOLD_UNCERTAIN")
        evidence["hold_uncertain"] = {
            "protection_state": page.get_attribute("#protection-state", "data-protection"),
            "protection_label": page.inner_text("#protection-label"),
            "action": page.inner_text("#v-action"),
            # Secondary telemetry lives in the collapsed "technical details" block, which renders no
            # inner_text; text_content reads it without forcing the panel open for a screenshot.
            "confidence": page.text_content("#v-confidence"),
            "explanation": page.inner_text("#explain"),
        }
        step("run to completion", lambda: None, "COMPLETED",
             timeout=MISSION_COMPLETION_TIMEOUT_S, shot="COMPLETED")

        step("start again", lambda: page.click('button[data-cmd="start"]'), "MOVING", "SLOWING", "HOLDING",
             timeout=MISSION_COMPLETION_TIMEOUT_S)
        step("obstacle 50 cm", lambda: set_obstacle(page, 50), "SLOWING", shot="SLOW_DOWN")
        evidence["slow_down"] = {
            "action": page.inner_text("#v-action"),
            "speed_ratio": page.inner_text("#v-speed_ratio"),
            "obstacle": page.inner_text("#v-obstacle_distance"),
        }

        page.wait_for_timeout(500)
        step("obstacle 20 cm", lambda: set_obstacle(page, 20), "SAFE_STOPPED", shot="SAFE_STOPPED")
        evidence["safe_stop"] = {
            "action": page.inner_text("#v-action"),
            "speed_ratio": page.inner_text("#v-speed_ratio"),
            "obstacle": page.inner_text("#v-obstacle_distance"),
        }

        step("manual resume", lambda: page.click('button[data-cmd="manual_resume"]'), "READY", timeout=40)
        page.wait_for_timeout(500)

        def clear_obstacle() -> None:
            page.click('button[data-cmd="clear_obstacle"]')
            # Status is already READY, so wait on the value the command actually changes.
            page.wait_for_function("() => document.getElementById('v-obstacle_distance').textContent === 'N/A'", timeout=10000)

        # Clearing an obstacle re-decides from the last real inference, so the engine's correct
        # answer is READY when that window was confident and HOLDING when it was not. Both are
        # right; pinning only READY made this step pass or fail on which window the safe stop
        # happened to land on. The confidence that explains the outcome is recorded alongside it.
        step("clear obstacle", clear_obstacle, "READY", "HOLDING", shot="READY")
        evidence["after_clear"] = {
            "obstacle": page.inner_text("#v-obstacle_distance"),
            "status": status(page),
            "confidence_of_last_window": page.text_content("#v-confidence"),
            "action": page.inner_text("#v-action"),
        }

        step("start after clearing", lambda: page.click('button[data-cmd="start"]'), "MOVING", "SLOWING", "HOLDING",
             timeout=MISSION_COMPLETION_TIMEOUT_S)
        step("second run completes", lambda: None, "COMPLETED",
             timeout=MISSION_COMPLETION_TIMEOUT_S, shot="COMPLETED_second_run")

        # 3. The remaining controls, each answered by the engine over the real broker.
        page.select_option("#cargo", "fragile")
        page.wait_for_function("() => document.getElementById('v-cargo_type').textContent === 'สินค้าเปราะบาง'", timeout=10000)
        evidence["cargo_switch"] = {"fragile": page.inner_text("#v-cargo_type"), "screenshot": snapshot(page, "FRAGILE_cargo")}
        page.select_option("#pickup", "A2")
        page.select_option("#destination", "C1")
        page.wait_for_function("() => document.getElementById('v-route_nodes').textContent.startsWith('A2')", timeout=10000)
        evidence["route_switch"] = {"nodes": page.inner_text("#v-route_nodes"), "policy": page.inner_text("#v-route_reason")}
        page.select_option("#cargo", "standard")
        page.select_option("#pickup", "A1")
        page.select_option("#destination", "C2")
        page.wait_for_timeout(600)
        step("pause", lambda: page.click('button[data-cmd="pause"]'), "PAUSED")
        step("reset again", lambda: page.click('button[data-cmd="reset"]'), "IDLE")

        # Camera screenshots are deliberately after every MQTT command. SwiftShader screenshot
        # readback is CPU-heavy; taking three during inference can starve the local WebSocket proxy
        # long enough to turn a visual check into a transport failure.
        camera_modes = {}
        for mode, shot in (("follow", "Follow_camera"), ("robot-pov", "Robot_POV"),
                           ("overview", "Overview_camera")):
            page.click(f'button[data-camera-mode="{mode}"]')
            page.wait_for_function(
                f"() => document.getElementById('stage').dataset.cameraMode === '{mode}'")
            page.wait_for_timeout(700)
            camera_modes[mode] = {
                "pressed": page.get_attribute(
                    f'button[data-camera-mode="{mode}"]', "aria-pressed") == "true",
                "canvas_mode": page.get_attribute("#stage", "data-camera-mode"),
                "screenshot": snapshot(page, shot),
            }
        evidence["camera_modes"] = camera_modes

        # 4. Laptop viewport: the layout must still fit without a sideways scroll.
        page.set_viewport_size({"width": 1440, "height": 900})
        page.evaluate("() => scrollTo(0, 0)")
        page.wait_for_timeout(600)
        evidence["laptop_viewport"] = {
            "size": "1440x900",
            "horizontal_overflow_px": page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth"),
            "canvas_size": page.evaluate("() => { const c = document.getElementById('stage'); return [c.clientWidth, c.clientHeight]; }"),
            "screenshot": snapshot(page, "Mission_1440x900"),
        }
        page.set_viewport_size({"width": 1280, "height": 720})
        page.evaluate("() => scrollTo(0, 0)")
        page.wait_for_timeout(400)
        evidence["viewport_1280x720"] = {
            "size": "1280x720",
            "horizontal_overflow_px": page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"),
            "screenshot": snapshot(page, "Mission_1280x720"),
        }

        # At 200% browser zoom a 1920x1080 display exposes a 960x540 CSS viewport. Resizing the CSS
        # viewport exercises the same media-query/reflow path instead of merely enlarging pixels.
        page.set_viewport_size({"width": 960, "height": 540})
        page.evaluate("() => scrollTo(0, 0)")
        page.wait_for_timeout(400)
        evidence["zoom_200_percent"] = {
            "method": "1920x1080 at 200%: effective CSS viewport 960x540",
            "effective_css_viewport": page.evaluate("() => [innerWidth, innerHeight]"),
            "horizontal_overflow_px": page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"),
            "stage_overlays_overlap": page.evaluate("""() => {
              const a = document.querySelector('.stage-note').getBoundingClientRect();
              const b = document.querySelector('.stage-toolbar').getBoundingClientRect();
              return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
            }"""),
            "screenshot": snapshot(page, "Mission_200_percent_zoom"),
        }
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.wait_for_timeout(400)

        # 5. Keyboard reachability of the mission controls.
        page.evaluate("() => document.activeElement?.blur()")
        focused = []
        keyboard_camera = False
        for _ in range(32):
            page.keyboard.press("Tab")
            item = page.evaluate("""() => {
              const node = document.activeElement, style = getComputedStyle(node);
              return {
                id: node?.id || node?.dataset?.cameraMode || node?.tagName,
                focus_visible: Boolean(node?.matches(':focus-visible')),
                outline_px: Number.parseFloat(style.outlineWidth) || 0,
              };
            }""")
            focused.append(item)
            if item["id"] == "robot-pov":
                page.keyboard.press("Enter")
                page.wait_for_function(
                    "() => document.getElementById('stage').dataset.cameraMode === 'robot-pov'")
                keyboard_camera = True
                break
        evidence["keyboard_focus_order"] = focused
        evidence["keyboard_camera_activation"] = keyboard_camera

        fps_samples = []
        for _ in range(5):
            page.wait_for_timeout(1000)
            value = page.inner_text("#fps").split()[0]
            if value.isdigit():
                fps_samples.append(int(value))
        evidence["fps"] = {
            "samples": fps_samples,
            "min": min(fps_samples) if fps_samples else None,
            "median": statistics.median(fps_samples) if fps_samples else None,
            "max": max(fps_samples) if fps_samples else None,
            "renderer": evidence["webgl"]["renderer"],
        }

        evidence["console"] = {"errors": console.errors, "message_count": len(console.messages),
                               "transport_noise": console.transport_noise}
        # With a WebGL context available the 3D stage must be the thing on screen, not the fallback.
        evidence["passed"] = (
            not console.errors
            and len(evidence["screenshots"]) >= 5
            and evidence["webgl"]["canvas_visible"]
            and not evidence["webgl"]["fallback_shown"]
            and evidence["laptop_viewport"]["horizontal_overflow_px"] <= 0
            and evidence["viewport_1280x720"]["horizontal_overflow_px"] <= 0
            and evidence["zoom_200_percent"]["effective_css_viewport"] == [960, 540]
            and evidence["zoom_200_percent"]["horizontal_overflow_px"] <= 0
            and not evidence["zoom_200_percent"]["stage_overlays_overlap"]
            and all(item["pressed"] and item["canvas_mode"] == mode
                    for mode, item in evidence["camera_modes"].items())
            and evidence["keyboard_camera_activation"]
            and any(item["focus_visible"] and item["outline_px"] >= 2
                    for item in evidence["keyboard_focus_order"])
            and len(evidence["fps"]["samples"]) >= 3
            # Every mandated state must have been photographed, not merely reached.
            and {"IDLE", "MOVING", "HOLD_UNCERTAIN", "SLOW_DOWN", "SAFE_STOPPED", "COMPLETED"}
                <= set(evidence["screenshots"])
            # The headline is a Cargo Protection State the engine's own status produced.
            and evidence["hold_uncertain"]["protection_state"] == "HOLDING"
            and evidence["hold_uncertain"]["explanation"].strip() != ""
        )


if __name__ == "__main__":
    main()
