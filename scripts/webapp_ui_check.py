"""Drive the operator console in a real browser against the real broker and record the evidence.

Needs the broker on 127.0.0.1:1883/8883, `python -m cargo.mqtt_service` running, and the webapp
folder served over HTTP (Bitstream Studio's **Serve Web App Folder over HTTP**, or any static
server). Then:

    .\\.venv\\Scripts\\python.exe scripts/webapp_ui_check.py --url http://127.0.0.1:8080/

Writes reports/webapp_ui_evidence.json and reports/screenshots/*.png.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "reports" / "screenshots"

# Chromium needs a software rasteriser to give a headless page a WebGL context.
LAUNCH_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]


class Console:
    """Every console message and uncaught error the page produced, in order."""

    def __init__(self, page) -> None:
        self.messages: list[dict] = []
        page.on("console", lambda m: self.messages.append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: self.messages.append({"type": "pageerror", "text": str(e)}))
        page.on("requestfailed", lambda r: self.messages.append({"type": "requestfailed", "text": f"{r.url} {r.failure}"}))

    @property
    def errors(self) -> list[dict]:
        return [m for m in self.messages if m["type"] in {"error", "pageerror", "requestfailed"}]


def status(page) -> str:
    return page.inner_text("#status").strip()


def wait_status(page, *wanted: str, timeout: float = 30.0) -> str:
    """Poll the rendered status; every value here is published by the engine, not by the page."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if status(page) in wanted:
            return status(page)
        page.wait_for_timeout(60)
    raise AssertionError(f"timed out waiting for {wanted}; page shows {status(page)!r}")


def snapshot(page, name: str) -> str:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path))
    return str(path.relative_to(ROOT)).replace("\\", "/")


def set_obstacle(page, centimetres: int) -> None:
    page.eval_on_selector(
        "#obstacle",
        "(el, v) => { el.value = String(v); el.dispatchEvent(new Event('input', { bubbles: true })); }",
        centimetres,
    )
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
        page.wait_for_function("() => document.getElementById('status').textContent !== '—'", timeout=15000)
        name = "reduced_motion" if reduced_motion else "no_webgl"
        return {
            "status_rendered": page.inner_text("#status"),
            "controls_usable": page.is_enabled('button[data-cmd="start"]'),
            "telemetry_rendered": page.inner_text("#v-route_nodes"),
            "canvas_visible": page.is_visible("#stage"),
            "fallback_shown": page.is_visible("#stage-fallback"),
            "console_errors": console.errors,
            "screenshot": snapshot(page, f"fallback_{name}"),
        }
    finally:
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Browser verification of the CargoShield operator console")
    parser.add_argument("--url", default="http://127.0.0.1:8080/")
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
        page.wait_for_function("() => document.getElementById('link-text').textContent === 'connected'", timeout=20000)

        # 1. Retained state must render before the operator touches anything.
        page.wait_for_function("() => document.getElementById('status').textContent !== '—'", timeout=10000)
        evidence["retained_state_on_open"] = {
            "status": status(page),
            "age": page.inner_text("#age"),
            "rendered_before_any_click": True,
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
            action()
            reached = wait_status(page, *wanted, timeout=timeout)
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
            # Without WebGL the panels must carry the demo on their own, and neither variant may error.
            evidence["passed"] = (
                evidence["passed"]
                and fallbacks["no_webgl"]["fallback_shown"]
                and fallbacks["no_webgl"]["controls_usable"]
                and not fallbacks["no_webgl"]["console_errors"]
                and not fallbacks["reduced_motion"]["console_errors"]
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
        step("reset", lambda: page.click('button[data-cmd="reset"]'), "IDLE")
        step("start", lambda: page.click('button[data-cmd="start"]'), "MOVING", "SLOWING", "HOLDING", shot="MOVING")
        step("run to completion", lambda: None, "COMPLETED", timeout=40, shot="COMPLETED")

        step("start again", lambda: page.click('button[data-cmd="start"]'), "MOVING", "SLOWING", "HOLDING")
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

        step("manual resume", lambda: page.click('button[data-cmd="manual_resume"]'), "READY")
        page.wait_for_timeout(500)

        def clear_obstacle() -> None:
            page.click('button[data-cmd="clear_obstacle"]')
            # Status is already READY, so wait on the value the command actually changes.
            page.wait_for_function("() => document.getElementById('v-obstacle_distance').textContent === 'N/A'", timeout=10000)

        step("clear obstacle", clear_obstacle, "READY", shot="READY")
        evidence["after_clear"] = {"obstacle": page.inner_text("#v-obstacle_distance")}

        step("start after clearing", lambda: page.click('button[data-cmd="start"]'), "MOVING", "SLOWING", "HOLDING")
        step("second run completes", lambda: None, "COMPLETED", timeout=40, shot="COMPLETED_second_run")

        # 3. The remaining controls, each answered by the engine over the real broker.
        page.select_option("#cargo", "fragile")
        page.wait_for_function("() => document.getElementById('v-cargo_type').textContent === 'fragile'", timeout=10000)
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

        # 4. Laptop viewport: the layout must still fit without a sideways scroll.
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(600)
        evidence["laptop_viewport"] = {
            "size": "1440x900",
            "horizontal_overflow_px": page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth"),
            "canvas_size": page.evaluate("() => { const c = document.getElementById('stage'); return [c.clientWidth, c.clientHeight]; }"),
            "screenshot": snapshot(page, "READY_laptop_1440x900"),
        }
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.wait_for_timeout(400)

        # 5. Keyboard reachability of the mission controls.
        # Click a non-focusable region first so tabbing restarts from the top of the document.
        page.click("header.topbar", position={"x": 600, "y": 20})
        focused = []
        for _ in range(8):
            page.keyboard.press("Tab")
            focused.append(page.evaluate("() => document.activeElement?.id || document.activeElement?.tagName"))
        evidence["keyboard_focus_order"] = focused

        evidence["fps"] = page.inner_text("#fps")
        evidence["console"] = {"errors": console.errors, "message_count": len(console.messages)}
        # With a WebGL context available the 3D stage must be the thing on screen, not the fallback.
        evidence["passed"] = (
            not console.errors
            and len(evidence["screenshots"]) >= 5
            and evidence["webgl"]["canvas_visible"]
            and not evidence["webgl"]["fallback_shown"]
            and evidence["laptop_viewport"]["horizontal_overflow_px"] <= 0
        )


if __name__ == "__main__":
    main()
