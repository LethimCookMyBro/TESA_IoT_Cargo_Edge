# Bitstream Studio visual-flow capabilities

Verified on 2026-07-25 from the bundled `vsix/bitstream-studio-0.1.9.vsix`, the active VS Code extension `TERNIONDEV.bitstream-studio` 0.1.9, and the separately installed 0.1.12 catalog.

## Editor and persistence

- The visual editor is **Sensor Studio**. The active command is `bitstream-studio.openBitstreamSensorStudio`; in 0.1.9 its palette title is **Open Bitstream Studio (Sensor Studio tab)**.
- A real Studio panel was opened during inspection. The same-day persisted workbench state records its `library`, `assets`, `flow`, and `inspector` layout. The captured panel did not render a flow canvas, so no graph screenshot is presented as proof.
- Sensor Studio auto-saves and can export/import a JSON graph. An embedded 0.1.9 preset proves the format marker is `trn-flow-preset`; it includes `document.nodes`, `document.edges`, `rootNodes`, and `rootEdges`. A generated flow must be created and exported through the UI; this repository intentionally does **not** hand-author a `.trn-flow-preset.json`.

## Release-profile gating — read this before naming any node

**Being compiled into the bundle does not make a node usable.** The installed build ships a release profile that removes whole palette categories and workbench panes from the UI. The active profile is `release.modules.json`, `profileId: minimal-sensor`, whose own description reads *"Minimal v0.1 — Sensor Telemetry + Sensor Studio flow/output (no Stage 3D, Dashboard, or special families)."*

Palette categories in the active profile:

| Category | State | Category | State |
|---|---|---|---|
| `sensor` | **enabled** | `scene` | disabled |
| `input` | **enabled** | `dashboard` | **disabled** |
| `transform` | **enabled** | `generator` | disabled |
| `logic` | **enabled** | `audio` | disabled |
| `output` | **enabled** | special families (audio, vision, physics, materials) | disabled |
| `utility` | **enabled** | | |
| `connectivity` | **enabled** | | |

Workbench panes: `library`, `assets`, `flow`, `inspector`, `devkit-twin`, `devkit-twin-scene`, `actuator-config` are enabled; **`dashboard` (operator HMI pane)**, `stage` (3D viewport), `stage-outliner`, `model-outliner` and `inspector-pinned` are disabled.

The same gating holds in all three shipped tier profiles — `release.profiles/tier-basic.json`, `tier-pro.json`, `tier-pro-plus.json` all set `workbenchPanes.dashboard` and `paletteCategories.dashboard` to `false`. There is no tier in this build that turns the Dashboard on.

**Consequence:** Sensor Studio 0.1.9 as installed has **no interactive input widgets**. There is no `dashboard-button`, `dashboard-select`, `dashboard-slider` or `dashboard-knob` in the Library, so the canvas cannot be an operator control surface. Operator controls live in `webapp/` instead; see the runbook.

## Node IDs present in the 0.1.9 bundle

Presence here means the identifier exists in `out/webview/assets/SensorStudioApp-*.js`. Cross-check the Gating table above, then confirm in the Library before wiring — this repository does not claim a node is usable until it has been seen in the palette.

| Area | Node IDs in the bundle | Reachable in the UI? |
|---|---|---|
| Sensor | `bmi270-input`, `bmm350-input`, `dps368-input`, `sht40-input` | category enabled |
| Utility / logic | `math`, `compare`, `logic-gate`, `multiplexer`, `json-pack`, `sensor-snapshot` | categories enabled |
| Transport | `mqtt-publisher`, `mqtt-subscriber`, `websocket-publisher`, `websocket-subscriber` | `connectivity` enabled |
| Displays | `indicator`, `numeric-display`, `message-viewer`, `plotter`, `sparkline`, `radial-gauge`, `bar-meter`, `progress-bar` | `output` enabled |
| Dashboard | `dashboard-output`, `dashboard-button`, `dashboard-led`, `dashboard-text`, `dashboard-gauge`, `dashboard-knob`, `dashboard-switch`, `dashboard-select`, `dashboard-slider`, `dashboard-status`, `dashboard-group`, `dashboard-tab`, `dashboard-theme` | **no — category disabled in every profile** |
| Constants | `number-constant`, `boolean-constant`, `vector-constant`, `quaternion-constant` | **no — `generator` category disabled** |
| 3D scene | `model-select`, `model-viewer`, `scene-output`, `environment`, `camera-view` | **no — `scene` category and Stage pane disabled** |

The 0.1.12 catalog additionally exposes BMI270 `accel`, `gyro`, and `euler` as `vector3`; `temp` and `samples` as `number`; and `quaternion` as `quaternion`. Its rendered primitive types include `number`, `boolean`, `string`, `vector3`, and `quaternion`. Configure exact handles in the currently active Studio UI before wiring; no handle names are inferred here.

## Transport

- The active extension hosts MQTT TCP at `mqtt://127.0.0.1:1883` and MQTT-over-WebSocket at port `8883`, both from the same broker process. Anonymous CONNECT was verified locally on both, and a WebSocket subscriber receives the retained state on connect at path `/` **and** at `/mqtt`.
- Studio's own connectivity preset is `bitstream-local-mqtt`: `host 127.0.0.1`, `port 8883`, `transport ws`, `path /`, described in the bundle as *"Embedded Aedes broker started with Bitstream Studio (MQTT-over-WebSocket)"*. Use those values in the node Inspector.
- The Python engine uses MQTT TCP `1883` via `paho-mqtt`. The bundled Live-Data SDK is JavaScript only (`out/live-data-sdk/live-data.browser.js`, ESM, exports `LiveDataClient`); `webapp/` uses it over WebSocket `8883`. The proprietary T3D WebSocket (`ws://127.0.0.1:9998`) is not used; port `9001` is closed.
- The existing DevKit demo topic is `device/{deviceId}/devkit-twin/telemetry`; its documented payload is JSON with a `channels` object. The examples do not document a BMI270 MQTT field schema, so CargoShield treats DevKit MQTT BMI data as unsupported until explicitly mapped.

## Not verified / intentionally unsupported

- No custom-node, plugin-node, or Script node API was found.
- No manually fabricated flow JSON is supplied.
- A live Digital Twin model binding and a Sensor Studio canvas screenshot were not independently verified in this session.
- **No flow has been built or run in the 0.1.9 UI by this repository.** The gating table above comes from the shipped profile JSON, not from the palette. Every node named as usable still needs one look at the Library before it is wired, and no claim about a working flow may be made until it is seen running.
- The per-node palette category could not be read reliably out of the minified webview bundle, so this document does not state which category each individual node lands in — only which categories the profile enables.
