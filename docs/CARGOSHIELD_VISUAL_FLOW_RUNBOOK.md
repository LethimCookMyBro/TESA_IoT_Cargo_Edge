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
| Send operator commands | `webapp/`, a local page using the extension's own bundled Live-Data SDK over MQTT-over-WebSocket | built and driven in a browser; contract covered by `tests/test_webapp_controls.py` |
| Show the mission in 3D | `webapp/scene.js`, a local Three.js warehouse fed by the same retained state | built and driven in a browser; evidence in `reports/webapp_ui_evidence.json` |

Do not name a node in this runbook that you have not seen in the 0.1.9 Library.

## Operator console — 3D operator console (`webapp/`)

`webapp/` is a full-screen industrial control surface: a procedurally built Three.js warehouse on the
left, the mission controls and telemetry on the right. It sends exactly the documented commands and
renders the verified state paths, using `webapp/live-data.browser.js` copied unmodified from the
installed extension (`out/live-data-sdk/`), so there is nothing to install.

**The 3D scene is visualization only.** Every status, decision, speed ratio, surface class, zone risk
and route it draws is read out of a published `cargoshield.state.v1` message. The Python engine
decides; the browser paints. Nothing in `webapp/` runs inference, applies a policy or advances a
mission — the robot only moves on screen while the engine reports `MOVING` or `SLOWING`, its animation
speed is the engine's own `last.decision.speed_ratio`, and `PAUSED`, `HOLDING`, `SAFE_STOPPED` and
`COMPLETED` freeze it exactly where the last published state put it. Where the engine has published no
value the panels read `N/A` and the corresponding 3D object stays hidden.

| File | Job |
|---|---|
| `webapp/index.html` | Layout, import map, panels |
| `webapp/styles.css` | Dark control-room theme, responsive at 1920×1080 and laptop widths |
| `webapp/app.js` | MQTT transport, commands, telemetry panels, event timeline |
| `webapp/scene.js` | Three.js renderer: warehouse, zones, route, robot, obstacle |
| `webapp/controls.js` | Pure command/display/visual contract shared with the tests |
| `webapp/vendor/three/` | three.js r0.180.0, vendored locally (see below) |

### Three.js provenance

three.js **0.180.0** from the npm registry (`npm pack three@0.180.0`), **MIT licence**. Only three files
are copied, unmodified: `build/three.module.min.js`, `build/three.core.min.js` and
`examples/jsm/controls/OrbitControls.js`, plus the upstream `LICENSE`. Details in
`webapp/vendor/three/NOTICE.md`.

It is vendored rather than pulled from a CDN because **the demo machine may have no internet access**.
No GLB/GLTF models, textures or font files are shipped: the warehouse, racks, robot, cargo and all
labels are built from three.js primitives and canvas-drawn textures at runtime, so there is no asset of
unknown licence anywhere in the page.

### Serve and open

1. `Ctrl+Shift+P` → **Serve Web App Folder over HTTP** (`bitstream-studio.serveWebAppFolder`), choose the repository's `webapp` folder.
2. `Ctrl+Shift+P` → **Open in Browser (Dev Server)** (`bitstream-studio.openInBrowser`). Use **Set Local Web App Port (Browser)** first if the default port is taken.
3. The page defaults to device `cargo-robot-01` and `ws://127.0.0.1:8883`. Override per URL when needed: `?device=cargo-robot-01&url=ws://127.0.0.1:8883`.

Any static server works and needs no VS Code — the page is plain ES modules, no build step:

```powershell
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory webapp
# then open http://127.0.0.1:8080/
```

Because state is retained, the page renders the last known mission the moment it opens, before you
press anything.

### Reading the scene

- **Zones** `A1 A2 B1 B2 C1 C2` are the `DEMO_GRAPH` nodes; the faint lanes between them are its edges. Each pad is tinted by that zone's observed Surface AI class and ringed by a green→red heat overlay from `risk_map[zone].score`. A zone the engine has not observed reads `risk N/A` and gets no heat.
- **Route** the published `route.nodes`, one ribbon per hop: green behind the robot, cyan for the hop it is on, grey ahead of it. A cyan ring marks the reported `last.zone`.
- **Robot** the beacon takes the mission status colour. Standard cargo is an opaque steel crate; fragile cargo is a translucent amber crate with a red strap, labelled on the model.
- **Obstacle** appears only when `obstacle_distance` is set, placed ahead of the robot at 1 m per 20 cm of the reported distance: amber inside the engine's warning region, red with a pulsing safety ring inside its stop region. A `SAFE_STOPPED` mission also draws a red perimeter around the robot.
- **Reset camera** returns the orbit camera to its framing; drag to orbit, right-drag to pan, wheel to zoom.

### Verifying the page

```powershell
.\.venv\Scripts\python.exe scripts\webapp_ui_check.py --url http://127.0.0.1:8080/
# add --headed to drive a visible browser on the real GPU
```

It drives the whole mandated sequence against the running broker (reset → start → completed →
obstacle 50 → obstacle 20 → resume → clear → start → completed), plus pause, cargo and route
switching, then records `reports/webapp_ui_evidence.json` and `reports/screenshots/*.png`. It fails on
any console error, on a missing 3D canvas, on horizontal overflow at 1440×900, or if the WebGL-disabled
fallback stops being usable. Needs `pip install playwright` and `python -m playwright install chromium`.

What is proven and what is not:

- **Proven:** every payload the page can emit is accepted by the engine, its zone options match `DEMO_GRAPH`, and every path it binds exists in a real state payload (`tests/test_webapp_controls.py`). Its floor plan, obstacle colour bands, animation rule and route interpolation are pinned to the Python policy and the trained label set (`tests/test_webapp_visual.py`). Both read `webapp/controls.js` through node, so the page and the engine cannot drift apart silently. The page has been opened in a real browser against the real broker and driven through the full sequence with no console errors (`reports/webapp_ui_evidence.json`).
- **Not proven:** the page has only been driven through Chromium 149 on this machine — Firefox and Safari are untested. Serving via the extension's own **Serve Web App Folder over HTTP** command was not exercised from this session; verification used `python -m http.server` on port 8080, which serves the same static files.

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

### 3D branch — not available on the canvas

`model-select`, `model-viewer` and `scene-output` are in the `scene` category and the Stage 3D pane is disabled in every profile of this build, so the Digital Twin branch cannot be built here at all. Do not describe one as working.

The 3D simulation therefore lives in the local console instead — `webapp/scene.js`, described above. It subscribes to the same retained `cargoshield/cargo-robot-01/state` topic the canvas would have used, so both views show the same engine at the same time.

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
