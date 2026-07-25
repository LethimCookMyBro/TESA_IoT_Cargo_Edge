# Bitstream Studio visual-flow capabilities

Verified on 2026-07-25 from the bundled `vsix/bitstream-studio-0.1.9.vsix`, the active VS Code extension `TERNIONDEV.bitstream-studio` 0.1.9, and the separately installed 0.1.12 catalog.

## Editor and persistence

- The visual editor is **Sensor Studio**. The active command is `bitstream-studio.openBitstreamSensorStudio`; in 0.1.9 its palette title is **Open Bitstream Studio (Sensor Studio tab)**.
- A real Studio panel was opened during inspection. The same-day persisted workbench state records its `library`, `assets`, `flow`, and `inspector` layout. The captured panel did not render a flow canvas, so no graph screenshot is presented as proof.
- Sensor Studio auto-saves and can export/import a JSON graph. An embedded 0.1.9 preset proves the format marker is `trn-flow-preset`; it includes `document.nodes`, `document.edges`, `rootNodes`, and `rootEdges`. A generated flow must be created and exported through the UI; this repository intentionally does **not** hand-author a `.trn-flow-preset.json`.

## Built-in nodes verified in the active 0.1.9 bundle

| Area | Verified node IDs |
|---|---|
| Sensor | `bmi270-input`, `bmm350-input`, `dps368-input`, `sht40-input` |
| Utility | `math`, `compare`, `logic-gate`, `multiplexer`, `json-pack`, `sensor-snapshot` |
| Transport | `mqtt-publisher`, `mqtt-subscriber`, `websocket-publisher`, `websocket-subscriber` |
| Displays | `indicator`, `numeric-display`, `message-viewer`, `plotter`, `sparkline`, `radial-gauge`, `bar-meter`, `progress-bar` |
| Dashboard | `dashboard-output`, `dashboard-button`, `dashboard-led`, `dashboard-text`, `dashboard-gauge`, `dashboard-knob`, `dashboard-switch`, `dashboard-select`, `dashboard-formatted-text`, `dashboard-image`, `dashboard-slider`, `dashboard-status`, `dashboard-group`, `dashboard-tab`, `dashboard-theme` |
| 3D scene | `model-select`, `model-viewer`, `scene-output`, `environment`, `camera-view` |

The 0.1.12 catalog additionally exposes BMI270 `accel`, `gyro`, and `euler` as `vector3`; `temp` and `samples` as `number`; and `quaternion` as `quaternion`. Its rendered primitive types include `number`, `boolean`, `string`, `vector3`, and `quaternion`. Configure exact handles in the currently active Studio UI before wiring; no handle names are inferred here.

## Transport

- The active extension hosts MQTT TCP at `mqtt://127.0.0.1:1883` and MQTT-over-WebSocket at `ws://127.0.0.1:8883/mqtt`. Anonymous MQTT CONNECT was verified locally.
- Native MQTT TCP is the Python bridge transport because the bundled Live Data SDK exports it for Node/Python clients. The proprietary T3D WebSocket (`ws://127.0.0.1:9998`) is not used.
- The existing DevKit demo topic is `device/{deviceId}/devkit-twin/telemetry`; its documented payload is JSON with a `channels` object. The examples do not document a BMI270 MQTT field schema, so CargoShield treats DevKit MQTT BMI data as unsupported until explicitly mapped.

## Not verified / intentionally unsupported

- No custom-node, plugin-node, or Script node API was found.
- No manually fabricated flow JSON is supplied.
- A live Digital Twin model binding and a Sensor Studio canvas screenshot were not independently verified in this session.
