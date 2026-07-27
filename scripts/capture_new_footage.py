"""Capture high resolution (1920x1080) footage and screenshots of CargoShield AI from current HEAD.

Saves assets to video-production/cargoshield-intro/public/assets/current-capture/
Generates video-production/cargoshield-intro/capture_manifest.json
"""

import os
import json
import time
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "video-production" / "cargoshield-intro" / "public" / "assets" / "current-capture"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = ROOT / "video-production" / "cargoshield-intro" / "capture_manifest.json"

HEAD_SHA = "acc5931ec39f8776b7f5b2e20cc61bbea1bd0704"

# Chrome launch args for WebGL
LAUNCH_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

def main():
    print("Starting background Python services...")
    python_bin = sys.executable

    procs = []
    try:
        # Start MQTT service
        p_mqtt = subprocess.Popen([python_bin, "-m", "cargo.mqtt_service"], cwd=str(ROOT))
        procs.append(p_mqtt)
        
        # Start Fleet service
        p_fleet = subprocess.Popen([python_bin, "-m", "cargo.fleet_service"], cwd=str(ROOT))
        procs.append(p_fleet)

        # Start History API
        p_hist = subprocess.Popen([python_bin, "-m", "cargo.history_api", "--port", "8099"], cwd=str(ROOT))
        procs.append(p_hist)

        # Start Web Server
        p_web = subprocess.Popen([python_bin, "-m", "http.server", "8080", "--bind", "127.0.0.1", "--directory", "webapp"], cwd=str(ROOT))
        procs.append(p_web)

        time.sleep(3)  # Wait for servers to warm up

        manifest_entries = []

        with sync_playwright() as play:
            browser = play.chromium.launch(headless=True, args=LAUNCH_ARGS)

            video_dir = OUTPUT_DIR / "videos"
            video_dir.mkdir(parents=True, exist_ok=True)
            
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(video_dir),
                record_video_size={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            console_errors = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))

            # --- MISSION PROTECTION CONSOLE ---
            url_mission = "http://127.0.0.1:8080/index.html"
            page.goto(url_mission, wait_until="load")
            page.wait_for_selector("#link-text")
            page.wait_for_function("() => document.getElementById('link-text').textContent === 'เชื่อมต่อแล้ว'", timeout=15000)
            page.wait_for_timeout(1000)

            def add_entry(filename, state, action, provenance, steps, is_video=False):
                captured_at = datetime.now(timezone.utc).isoformat()
                manifest_entries.append({
                    "filename": f"public/assets/current-capture/{filename}",
                    "HEAD_SHA": HEAD_SHA,
                    "captured_at": captured_at,
                    "page_url": url_mission if "fleet" not in filename else "http://127.0.0.1:8080/fleet.html",
                    "viewport": "1920x1080",
                    "state": state,
                    "action": action,
                    "provenance": provenance,
                    "steps_to_reproduce": steps,
                    "console_errors": list(console_errors),
                    "is_video_or_still": "video" if is_video else "still"
                })

            # 1. IDLE
            shot_idle = "01_mission_idle.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_idle))
            add_entry(shot_idle, "IDLE", "Loaded initial page", "DATASET", "Open index.html and wait for connection")

            # 2. Fragile cargo
            page.select_option("#cargo", "fragile")
            page.wait_for_timeout(500)
            shot_fragile = "02_mission_fragile_cargo.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_fragile))
            add_entry(shot_fragile, "IDLE (Fragile)", "Selected fragile cargo", "DATASET", "Select fragile option in #cargo dropdown")

            # Reset back to standard for demo run
            page.select_option("#cargo", "standard")
            page.click('button[data-cmd="reset"]')
            page.wait_for_timeout(500)

            # 3. MOVING
            page.click('button[data-cmd="start"]')
            page.wait_for_timeout(1200)
            shot_moving = "03_mission_moving.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_moving))
            add_entry(shot_moving, "MOVING", "Clicked start button", "DATASET", "Click button[data-cmd='start']")

            # 4. Overview Camera
            page.click('button[data-camera-mode="overview"]')
            page.wait_for_timeout(800)
            shot_overview = "04_mission_camera_overview.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_overview))
            add_entry(shot_overview, "MOVING (Overview)", "Switched camera to Overview", "DATASET", "Click button[data-camera-mode='overview']")

            # 5. Follow Camera
            page.click('button[data-camera-mode="follow"]')
            page.wait_for_timeout(800)
            shot_follow = "05_mission_camera_follow.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_follow))
            add_entry(shot_follow, "MOVING (Follow)", "Switched camera to Follow", "DATASET", "Click button[data-camera-mode='follow']")

            # 6. Robot POV
            page.click('button[data-camera-mode="robot-pov"]')
            page.wait_for_timeout(800)
            shot_pov = "06_mission_camera_robot_pov.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_pov))
            add_entry(shot_pov, "MOVING (Robot POV)", "Switched camera to Robot POV", "DATASET", "Click button[data-camera-mode='robot-pov']")

            # 7. HOLD UNCERTAIN
            try:
                page.wait_for_function("() => document.getElementById('status').dataset.status === 'HOLDING'", timeout=15000)
                shot_hold = "07_mission_hold_uncertain.png"
                page.screenshot(path=str(OUTPUT_DIR / shot_hold))
                add_entry(shot_hold, "HOLD_UNCERTAIN", "Safety core held on low confidence", "DATASET", "Replay window with confidence < 0.55")
            except Exception as e:
                print("Notice on HOLD_UNCERTAIN wait:", e)

            # 8. Wait for completion
            try:
                page.wait_for_function("() => document.getElementById('status').dataset.status === 'COMPLETED'", timeout=30000)
                shot_completed = "08_mission_completed.png"
                page.screenshot(path=str(OUTPUT_DIR / shot_completed))
                add_entry(shot_completed, "COMPLETED", "Replay run completed", "DATASET", "Wait for dataset replay 10 windows completion")
            except Exception as e:
                print("Notice on COMPLETED wait:", e)

            # 9. SLOW DOWN & SAFE STOP
            page.click('button[data-cmd="start"]')
            page.wait_for_timeout(1000)
            page.fill("#obstacle-value", "50")
            page.click("#obstacle-send")
            page.wait_for_timeout(1000)
            shot_slow = "09_mission_slow_down.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_slow))
            add_entry(shot_slow, "SLOW_DOWN", "Set obstacle distance to 50 cm", "SIMULATED", "Fill #obstacle-value with 50 and send")

            page.fill("#obstacle-value", "20")
            page.click("#obstacle-send")
            page.wait_for_timeout(1000)
            shot_safestop = "10_mission_safe_stopped.png"
            page.screenshot(path=str(OUTPUT_DIR / shot_safestop))
            add_entry(shot_safestop, "SAFE_STOPPED", "Set obstacle distance to 20 cm", "SIMULATED", "Fill #obstacle-value with 20 and send")

            context.close()

            # --- FLEET GUARDIAN ---
            context_fleet = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(video_dir),
                record_video_size={"width": 1920, "height": 1080}
            )
            page_fleet = context_fleet.new_page()

            url_fleet = "http://127.0.0.1:8080/fleet.html?api=http%3A%2F%2F127.0.0.1%3A8099"
            page_fleet.goto(url_fleet, wait_until="load")
            page_fleet.wait_for_timeout(2000)

            # 11. Fleet overview
            shot_fleet_main = "11_fleet_overview.png"
            page_fleet.screenshot(path=str(OUTPUT_DIR / shot_fleet_main))
            add_entry(shot_fleet_main, "Fleet Overview", "Loaded Fleet Guardian page", "SIMULATED", "Navigate to fleet.html")

            # 12. Safety Events Page 1 & 2
            page_fleet.locator("#events-heading").evaluate("(n) => n.scrollIntoView({block: 'start'})")
            page_fleet.wait_for_timeout(500)
            shot_events_p1 = "12_fleet_safety_events_p1.png"
            page_fleet.screenshot(path=str(OUTPUT_DIR / shot_events_p1))
            add_entry(shot_events_p1, "Safety Events Page 1", "Scroll to Safety Events", "SIMULATED", "Scroll to Safety Events section")

            if not page_fleet.is_disabled("#event-next"):
                page_fleet.click("#event-next")
                page_fleet.wait_for_timeout(500)
                shot_events_p2 = "13_fleet_safety_events_p2.png"
                page_fleet.screenshot(path=str(OUTPUT_DIR / shot_events_p2))
                add_entry(shot_events_p2, "Safety Events Page 2", "Clicked next page on Safety Events", "SIMULATED", "Click #event-next")

            # 13. Filtered Safety Events
            page_fleet.select_option("#event-severity", "critical")
            page_fleet.wait_for_timeout(500)
            shot_events_crit = "14_fleet_safety_events_critical.png"
            page_fleet.screenshot(path=str(OUTPUT_DIR / shot_events_crit))
            add_entry(shot_events_crit, "Safety Events Critical Filter", "Filtered events by critical severity", "SIMULATED", "Select 'critical' in #event-severity")

            # 14. Mission History
            page_fleet.locator("#missions-heading").evaluate("(n) => n.scrollIntoView({block: 'start'})")
            page_fleet.wait_for_timeout(500)
            shot_missions = "15_fleet_mission_history.png"
            page_fleet.screenshot(path=str(OUTPUT_DIR / shot_missions))
            add_entry(shot_missions, "Mission History", "Scroll to Mission History", "SIMULATED", "Scroll to Mission History section")

            # 15. Maintenance Assistant
            page_fleet.locator("#copilot-heading").evaluate("(n) => n.scrollIntoView({block: 'start'})")
            page_fleet.wait_for_timeout(500)
            page_fleet.click('#copilot-questions button[data-question="inspection"]')
            page_fleet.wait_for_timeout(1000)
            shot_maint = "16_fleet_maintenance_assistant.png"
            page_fleet.screenshot(path=str(OUTPUT_DIR / shot_maint))
            add_entry(shot_maint, "Maintenance Assistant", "Clicked inspection question", "SIMULATED", "Click button[data-question='inspection']")

            context_fleet.close()
            browser.close()

        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest_entries, f, indent=2, ensure_ascii=False)

        print("Footage captured successfully! Manifest written to:", MANIFEST_PATH)

    finally:
        print("Terminating background processes...")
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                p.kill()

if __name__ == "__main__":
    main()
