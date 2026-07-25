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
4. Configure MQTT nodes through the Inspector: host `127.0.0.1`, TCP port `1883` where the node supports TCP, or the extension's documented MQTT-over-WebSocket profile `ws://127.0.0.1:8883/mqtt` when the Studio node requires WebSocket.
5. Export the graph from Sensor Studio after it is visibly wired. Do not write or edit a flow JSON by hand.

## Click-by-click build steps

Sensor Studio runs as a webview inside the IDE, so the graph is built by hand. Node IDs below are the ones verified in [the capability audit](BITSTREAM_VISUAL_FLOW_CAPABILITIES.md); do not substitute names that are not in that table.

**Why no automated export exists** (checked against the installed `terniondev.bitstream-studio-0.1.9`):

- Its 38 contributed VS Code commands include `openBitstreamSensorStudio`, `startMqttBroker` and `exportLiveDataSdk`, but **no** command that builds, opens, or exports a flow graph.
- `exportFlowGraphJson` appears only inside the webview bundle `out/webview/assets/SensorStudioApp-*.js`, where it serialises live canvas state (`rootNodes`, `rootEdges`, `viewport`, `canvasPreferences`, `workbenchLayout`, `studioAssetDescriptors`) into a browser `Blob` download triggered by a click in the canvas.
- The only shipped CLI is `out/cli/download-free-pack.js`, an asset downloader.

So the preset file cannot be produced without a human building the graph and clicking Export, and its schema must never be hand-written. `visual-flow/cargoshield-edge.trn-flow-preset.json` therefore does not exist yet; the Python side it talks to is fully verified and evidenced in `reports/demo_e2e_evidence.json`.

### Step 1 — minimum state flow

1. In the **Library** panel, search `mqtt` and drag **MQTT Subscriber** (`mqtt-subscriber`) onto the canvas.
2. Drag **Message Viewer** (`message-viewer`) to its right.
3. Click the **MQTT Subscriber** node. In **Inspector**, set Host `127.0.0.1`, Port `1883`, Topic `cargoshield/cargo-robot-01/state`. If the node only offers a URL field, use `mqtt://127.0.0.1:1883`; if it is WebSocket-only, use `ws://127.0.0.1:8883/mqtt`.
4. Drag from the subscriber's **Message** output port to the Message Viewer's **Message** input port. Leave **Connected**, **Topic**, and **Received** unwired.
5. Press the Studio **Run/Play** control. The subscriber's `Connected` port should read `true`.

`HOLD_UNCERTAIN` is displayed as `HOLDING`: it is an amber, non-fatal pause with speed ratio `0.0`, distinct from red `ERROR` and red `SAFE_STOPPED`. It can be paused, reset, or superseded by the next valid replay window; it does not set the manual-resume latch.

### Step 2 — cargo command flow

1. Drag **Dashboard Select** (`dashboard-select`), **JSON Pack** (`json-pack`), and **MQTT Publisher** (`mqtt-publisher`).
2. Inspector on the select node: options `standard` and `fragile`.
3. Inspector on `json-pack`: key `action` = constant `set_cargo`; key `cargo_type` = the select node's value input.
4. Wire select **Value** → `json-pack` `cargo_type` input, then `json-pack` **Object/JSON** output → publisher **Message** input.
5. Inspector on the publisher: Host `127.0.0.1`, Port `1883`, Topic `cargoshield/cargo-robot-01/command`.
6. Choose **Fragile**. The Message Viewer from step 1 must show `"cargo_type":"fragile"` and a `route.reason` of `stability-first; …`.

### Steps 3-6 — remaining command branches

Each branch is the same shape: control → `json-pack` → the **same** `mqtt-publisher` (or a copy with identical settings).

| Branch | Control nodes | `json-pack` keys |
|---|---|---|
| Mission | four `dashboard-button` (Start, Pause, Reset, **Resume / Clear Safe Stop**) | `action` = `start` / `pause` / `reset` / `manual_resume` |
| Collision | `dashboard-slider` (0-200), `dashboard-button` (Clear) | `action` = `set_obstacle` + `distance` = slider value; and `action` = `clear_obstacle` |
| Location | two `dashboard-select` (pickup, destination; options `A1 A2 B1 B2 C1 C2`) | `action` = `set_mission`, `pickup`, `destination` |
| IMU diagnostic | `bmi270-input` → `sensor-snapshot` | publish to `device/<id>/devkit-twin/telemetry` only; the Python service answers with a diagnostic string, not inference |

### Step 7 — output bindings

Wire the subscriber's **Message** output to each display and set the display's path field using the verified table in [the build sheet](../visual-flow/CARGOSHIELD_SENSOR_STUDIO_FLOW_BUILD.md). Use `dashboard-gauge` for `last.decision.speed_ratio` (range 0-1), `dashboard-text` for `route.reason`, `dashboard-status`/`dashboard-led` for `last.vibration_risk`, `indicator` for `last.decision.action`, `message-viewer` for `risk_map`, and `sparkline`/`plotter` for `last.vibration_score`.

### Step 8 — 3D branch

Add `model-select` → `model-viewer` → `scene-output` only after picking a real model in the Asset Manager. Nothing in this repository has tested a live robot binding; do not describe one as working until it is seen moving.

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
