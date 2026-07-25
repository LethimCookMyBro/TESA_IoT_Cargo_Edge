# CargoShield visual-flow runbook

## Start the verified local services

1. Open VS Code with the currently active Bitstream Studio 0.1.9 extension.
2. Run **Bitstream Studio: Start MQTT Broker** if port 1883 is not already live.
3. From the project root, start the Python service:

```powershell
.\.venv\Scripts\python.exe -m cargo.mqtt_service --host 127.0.0.1 --port 1883
```

It subscribes to `cargoshield/cargo-robot-01/command` and publishes state on `cargoshield/cargo-robot-01/state`.

With the broker and service running, verify the same command/state route independently of the Studio canvas:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_mqtt_flow.py
```

Append `--dataset-demo` to verify the ten-window curated dataset replay over the same broker connection. For a full command/state/obstacle sweep that writes machine-readable evidence to `reports/demo_e2e_evidence.json`:

```powershell
.\.venv\Scripts\python.exe scripts\demo_e2e_check.py
```

Demo pacing is `--interval` on the service (default `1.0` s per window, ten windows, about ten seconds per run).

## Open and build the visual flow

1. Press `Ctrl+Shift+P`.
2. Run **Open Bitstream Studio (Sensor Studio tab)** (`bitstream-studio.openBitstreamSensorStudio`).
3. Use [the build sheet](../visual-flow/CARGOSHIELD_SENSOR_STUDIO_FLOW_BUILD.md) to add only verified nodes.
4. Configure MQTT nodes through the Inspector: host `127.0.0.1`, TCP port `1883` where the node supports TCP, or `ws://127.0.0.1:8883/mqtt` when the Studio node requires WebSocket.

   Both transports are verified against this broker: `1883` (TCP) and `8883` (WebSocket) are served by the same broker process, and a WebSocket subscriber receives the retained state immediately on connect at path `/mqtt` **and** at `/`. The check is `websocket_transport` in `reports/demo_e2e_evidence.json`, re-runnable with `scripts/demo_e2e_check.py --ws-port 8883`. Port `9001` is closed; do not use it.
5. Export the graph from Sensor Studio after it is visibly wired. Do not write or edit a flow JSON by hand.

## Click-by-click build steps

Sensor Studio runs as a webview inside the IDE, so the graph is built by hand. Node IDs below are the ones verified in [the capability audit](BITSTREAM_VISUAL_FLOW_CAPABILITIES.md); do not substitute names that are not in that table.

**Why no automated export exists** (checked against the installed `terniondev.bitstream-studio-0.1.9`):

- Its 38 contributed VS Code commands include `openBitstreamSensorStudio`, `startMqttBroker` and `exportLiveDataSdk`, but **no** command that builds, opens, or exports a flow graph.
- `exportFlowGraphJson` appears only inside the webview bundle `out/webview/assets/SensorStudioApp-*.js`, where it serialises live canvas state (`rootNodes`, `rootEdges`, `viewport`, `canvasPreferences`, `workbenchLayout`, `studioAssetDescriptors`) into a browser `Blob` download triggered by a click in the canvas.
- The only shipped CLI is `out/cli/download-free-pack.js`, an asset downloader.

So the preset file cannot be produced without a human building the graph and clicking Export, and its schema must never be hand-written. `visual-flow/cargoshield-edge.trn-flow-preset.json` therefore does not exist yet; the Python side it talks to is fully verified and evidenced in `reports/demo_e2e_evidence.json`.

## What Sensor Studio 0.1.9 can and cannot be here

The installed build runs release profile `minimal-sensor`, which disables the **Dashboard operator HMI pane** and the whole **Dashboard palette category**. All three shipped tier profiles (`tier-basic`, `tier-pro`, `tier-pro-plus`) disable them too, so no tier in this build brings them back. The `scene` and `generator` categories are off as well. Evidence and the full table are in [the capability audit](BITSTREAM_VISUAL_FLOW_CAPABILITIES.md).

That means there is **no `dashboard-button`, `dashboard-select`, `dashboard-slider` or `dashboard-knob` in the Library**, and therefore no way to build an operator control surface on the canvas. Earlier revisions of this runbook told you to drag those nodes; they cannot appear, and those steps have been removed.

Split the job accordingly:

| Job | Where | Status |
|---|---|---|
| Show live mission state | Sensor Studio flow: an MQTT subscriber into display nodes from the enabled `connectivity`/`output` categories | to be built and confirmed in the UI |
| Send operator commands | `webapp/index.html`, a local page using the extension's own bundled Live-Data SDK over MQTT-over-WebSocket | built; command contract covered by `tests/test_webapp_controls.py` |

Do not name a node in this runbook that you have not seen in the 0.1.9 Library.

## Operator controls — local console (`webapp/`)

`webapp/index.html` sends exactly the documented commands and renders the verified state paths. It uses `webapp/live-data.browser.js`, copied unmodified from the installed extension (`out/live-data-sdk/`), so there is nothing to install.

Serve it with the extension's own commands:

1. `Ctrl+Shift+P` → **Serve Web App Folder over HTTP** (`bitstream-studio.serveWebAppFolder`), choose the repository's `webapp` folder.
2. `Ctrl+Shift+P` → **Open in Browser (Dev Server)** (`bitstream-studio.openInBrowser`). Use **Set Local Web App Port (Browser)** first if the default port is taken.
3. The page defaults to device `cargo-robot-01` and `ws://127.0.0.1:8883`. Override per URL when needed: `?device=cargo-robot-01&url=ws://127.0.0.1:8883`.

Because state is retained, the page renders the last known mission the moment it opens, before you press anything.

What is proven and what is not:

- **Proven:** every payload the page can emit is accepted by the engine, the page's zone options match `DEMO_GRAPH`, and every path the page binds exists in a real state payload — `tests/test_webapp_controls.py` reads these straight out of `webapp/controls.js` via node, so the page and engine cannot drift apart silently. MQTT-over-WebSocket on `8883` delivers retained state (`websocket_transport` in `reports/demo_e2e_evidence.json`).
- **Not proven:** the page has not been opened in a browser from this session. The vendor bundle is a browser ESM build and refuses to run under Node, so its rendering and the SDK's browser transport are unverified here. Open it once and confirm before demonstrating.

### Before you start clicking

The Python side is locked and evidenced (`reports/demo_e2e_evidence.json`, 14/14 checks). Two behaviours will otherwise look like flow bugs:

- **The subscriber shows state before you press anything.** State is retained, so a freshly wired `mqtt-subscriber` renders the last known state on connect. That is correct, not a stale node.
- **Standard and fragile pick the same route on the very first run.** Route cost uses the learned `risk_map`, which starts empty. Run the demo once, then switch cargo type and run again; the second run is where the route diverges. Speed ratios differ on every run.

### Step 1 — minimum state flow

1. In the **Library** panel, search `mqtt` and drag **MQTT Subscriber** (`mqtt-subscriber`) onto the canvas.
2. Drag **Message Viewer** (`message-viewer`) to its right.
3. Click the **MQTT Subscriber** node. In **Inspector**, set Topic `cargoshield/cargo-robot-01/state` and point the connection at Studio's own preset `bitstream-local-mqtt`: host `127.0.0.1`, port `8883`, transport `ws`, path `/`. If the node exposes a plain host/port pair with TCP, `127.0.0.1:1883` works too; both ports are the same broker.
4. Drag from the subscriber's **Message** output port to the Message Viewer's **Message** input port. Leave **Connected**, **Topic**, and **Received** unwired.
5. Press the Studio **Run/Play** control. The subscriber's `Connected` port should read `true`.

`HOLD_UNCERTAIN` is displayed as `HOLDING`: it is an amber, non-fatal pause with speed ratio `0.0`, distinct from red `ERROR` and red `SAFE_STOPPED`. It can be paused, reset, or superseded by the next valid replay window; it does not set the manual-resume latch.

### Step 2 — commands

Commands do **not** come from the canvas in this build: the Dashboard input widgets are gated off. Use the local console described above (`webapp/index.html`) and leave the flow as a subscriber.

With the console open, choose **Fragile**. The Message Viewer from step 1 must show `"cargo_type":"fragile"`, proving the canvas and the console are talking to the same engine.

If a later Studio build re-enables the Dashboard category, the command shape to rebuild on-canvas is control → `json-pack` → `mqtt-publisher` on `cargoshield/cargo-robot-01/command`, with the payloads listed in `webapp/controls.js`.

### Step 3 — output bindings

Wire the subscriber's **Message** output into display nodes from the enabled `output` category and set each display's path field using the verified table in [the build sheet](../visual-flow/CARGOSHIELD_SENSOR_STUDIO_FLOW_BUILD.md).

Candidate display nodes present in the bundle and belonging to the enabled `output` category: `indicator`, `numeric-display`, `message-viewer`, `plotter`, `sparkline`, `radial-gauge`, `bar-meter`, `progress-bar`. Confirm each one in the Library before wiring; `dashboard-gauge`, `dashboard-text`, `dashboard-status` and `dashboard-led` are **not** available.

Suggested bindings once you have confirmed the nodes exist:

| Value | Path | Node |
|---|---|---|
| Speed ratio | `last.decision.speed_ratio` | `radial-gauge` or `bar-meter` (range 0-1) |
| Progress | `last.progress` | `progress-bar` (range 0-1) |
| Safety action | `last.decision.action` | `indicator` |
| Vibration score | `last.vibration_score` | `sparkline` or `plotter` |
| Confidence | `last.confidence` | `numeric-display` |
| Route / risk map / events | `route`, `risk_map`, `events` | `message-viewer` (objects and arrays) |

### Step 4 — IMU diagnostic branch (optional)

`bmi270-input` → `sensor-snapshot`, publishing to `device/<id>/devkit-twin/telemetry` only. The Python service answers with a rate-limited diagnostic string, not inference.

### 3D branch — not available

`model-select`, `model-viewer` and `scene-output` are in the `scene` category and the Stage 3D pane is disabled in every profile of this build, so the Digital Twin branch cannot be built here at all. Do not describe one as working.

### Export

Use the Studio's own Export command and save to `visual-flow/cargoshield-edge.trn-flow-preset.json`. Do not hand-write that file. After exporting, re-import it into a fresh Studio tab to confirm it round-trips, and check that it contains no host names other than `127.0.0.1` and no credentials.

## Demonstration sequence

1. Publish or wire `{ "action": "start" }`. The service replays the ten-window curated dataset demonstration sequence over about ten seconds, emitting prediction, confidence, vibration risk, decision, route, zone and progress for each window. The run walks `A1 -> C2` and shows `MOVE` at low, medium and high vibration risk plus `HOLD_UNCERTAIN` on the below-threshold windows — every value is the trained model's real output for those stored windows.
2. Choose **Standard**, start, let it finish; then choose **Fragile** and start again. Identical windows return different speed ratios: `1.0 / 0.75 / 0.5` for standard against `0.8 / 0.45 / 0.25` for fragile, with a `stability-first` route reason.
3. Mid-run send `{ "action": "pause" }`; progress freezes. Send `{ "action": "manual_resume" }` to continue the same run.
4. Mid-run send `{ "action": "set_obstacle", "distance": 50 }` for `SLOWING`, then `20` for `SAFE_STOPPED`. The safe stop latches and ends that run at the instant it is raised — whether the operator caused it or a replayed window did. `{ "action": "clear_obstacle" }` does **not** release the latch; only `{ "action": "manual_resume" }` does, and the operator then presses **Start** to run again. Progress stays frozen where it stopped, and the mission returns to `READY` rather than claiming `MOVING`, because nothing is stepping windows. Restarting while the obstacle is still inside the stop region latches again instead of driving through it.
5. After a run has ended (`COMPLETED`), the obstacle controls only record `obstacle_distance`; no action is recomputed from the finished run's inference.
6. Verify Digital Twin/dashboard reception by checking that the `mqtt-subscriber` state message updates the bound dashboard displays. A 3D scene is optional until an actual model binding has been configured and observed.

## BMI270 later

Use `bmi270-input` for the visual sensor side and preserve its values through the Studio MQTT publisher. Before enabling AI inference, collect/calibrate a matching 128-sample BMI270 window and add an explicit field mapping to the Python service. Existing DevKit MQTT examples do not establish that mapping, so the current service reports a diagnostic instead of guessing.
