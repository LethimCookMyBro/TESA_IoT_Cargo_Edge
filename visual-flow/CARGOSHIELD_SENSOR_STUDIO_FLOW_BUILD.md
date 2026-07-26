# CargoShield Sensor Studio flow build sheet

Create this graph in **Sensor Studio**, then use its Export command to save the resulting JSON. This file is a build sheet, not an invented flow-schema file.

## External-processing contract

Start `cargo.mqtt_service` first. It makes the Python CargoShield engine the sole source of inference, vibration risk, policy, routing, and safe-stop decisions.

| Direction | MQTT topic | Real payload |
|---|---|---|
| Studio → Python | `cargoshield/cargo-robot-01/command` | `{"action":"start"}`; `pause`; `reset`; `manual_resume`; `clear_obstacle`; `{"action":"set_cargo","cargo_type":"standard"}` or `fragile`; `{"action":"set_obstacle","distance":20}`; `{"action":"set_mission","pickup":"A1","destination":"C2"}` |
| Python → Studio | `cargoshield/cargo-robot-01/state` | `cargoshield.state.v1` JSON emitted by `CargoMqttService.publish_state()` |
| Optional diagnostic → Python | `device/+/devkit-twin/telemetry` | CargoShield-defined diagnostic topic; no Bitstream payload schema is claimed and no inference is performed |

## Verified state field paths

Verified from `cargoshield/cargo-robot-01/state` on 2026-07-26 against the current service,
regression tests, and `reports/demo_e2e_evidence.json`. Values come from ten curated validation
windows that are disjoint from train and held-out test. This is Dataset Replay, not live telemetry
or an evaluation result. Bind Studio displays to these **exact** paths. Convenient short names used
in planning notes (`mission_state`, `surface_class`, `safety_action`, …) are not payload keys.

| Display intent | Real JSON path | Verified values |
|---|---|---|
| Mission state | `status` | `IDLE`, `READY`, `MOVING`, `SLOWING`, `HOLDING`, `PAUSED`, `SAFE_STOPPED`, `COMPLETED`, `ERROR` |
| Cargo type | `cargo_type` | `standard`, `fragile` |
| Surface class | `last.label` | `carpet`, `soft_pvc`, `concrete`, `hard_tiles`, `tiled` |
| Confidence | `last.confidence` | current replay spans about `0.300`–`0.704` |
| Vibration score | `last.vibration_score` | current replay spans about `0.388`–`6.307` |
| Vibration risk | `last.risk` | `low`, `medium`, `high` (`last.vibration_risk` remains the source field) |
| Speed ratio | `last.decision.speed_ratio` | `0.8` fragile/low, `0.5` warning region, `0.0` stop/hold |
| Safety action | `last.decision.action` | `MOVE`, `SLOW_DOWN`, `SAFE_STOP`, `HOLD_UNCERTAIN` |
| Safety reason | `last.decision.reason` | `fragile cargo with low vibration risk` |
| Manual-resume latch | `last.decision.manual_resume_required` | `true` after a safe stop |
| Current zone | `last.zone` | `A1`, `A2`, `B1`, `B2`, `C1`, `C2` (walks the planned route) |
| Progress | `last.progress` | `0.1`, `0.2`, … `1.0` (ten curated windows) |
| Inference time | `last.inference_ms` | runtime-dependent local Python timing; not board performance |
| Route | `route.nodes`, `route.cost`, `route.reason` | fresh standard run: `["A1","A2","B2","C2"]`, `3.0`, `shortest-first; …` |
| Obstacle | `obstacle_distance` | `null`, `20`, `50` |
| Risk map | `risk_map.<zone>.score` / `.observations` / `.surface` / `.updated_ms` | values accumulate during replay; use the published object |
| Event log | `events[].message` | prediction/action messages from the current replay |
| Envelope | `schema`, `device_id` | `cargoshield.state.v1`, `cargo-robot-01` |
| Error / diagnostic | `error`, `source_diagnostic` | present only on the failing message |

Studio display nodes read a single value, so point each one at a leaf path. Send the whole message to `message-viewer` for `risk_map`, `route`, and `events`, which are objects/arrays.

## What this build can actually host

The installed 0.1.9 runs release profile `minimal-sensor`, which disables the Dashboard pane, the whole `dashboard` palette category, and the `scene` and `generator` categories — in every shipped tier. See [the capability audit](../docs/BITSTREAM_VISUAL_FLOW_CAPABILITIES.md) for the profile evidence.

So the canvas here is a **state display**, not a control surface. Operator commands come from `webapp/index.html`; the Studio flow subscribes and renders.

## Visual branches that are possible in this build

1. **State in:** `mqtt-subscriber` on `cargoshield/cargo-robot-01/state` → `message-viewer`, plus display nodes from the enabled `output` category (`indicator`, `numeric-display`, `radial-gauge`, `bar-meter`, `progress-bar`, `sparkline`, `plotter`).
2. **Feedback:** bind returned `risk_map` to `message-viewer`; it is the engine's learned zone-risk that feeds later route cost.
3. **IMU diagnostic (optional):** `bmi270-input` → `sensor-snapshot` → `json-pack` → `mqtt-publisher` to `device/<id>/devkit-twin/telemetry`. The service answers with a rate-limited diagnostic string, never inference.

`mqtt-subscriber` and `message-viewer` were manually confirmed on the 0.1.9 canvas and received the
retained state. Confirm every other node above in the Library before wiring it; those identifiers
come from the bundle and enabled profile categories, not a saved flow artifact.

## Branches that are not possible in this build

- **Any on-canvas control** (cargo select, obstacle slider, Start/Pause/Reset/Resume buttons, pickup/destination selects) — the `dashboard` category is off. Use `webapp/index.html`; its payloads live in `webapp/controls.js` and are covered by `tests/test_webapp_controls.py`.
- **Digital Twin / 3D** (`model-select`, `model-viewer`, `scene-output`) — the `scene` category and the Stage 3D pane are off.
- **Vector/quaternion constants** (`vector-constant`, `quaternion-constant`) — these two are in the `generator` category, which is off.
  Scalar and boolean literals (`number-constant`, `boolean-constant`, `float-constant`, `integer-constant`) are in `utility`, which **is** enabled, so a literal *can* be introduced on-canvas. An earlier revision of this sheet said otherwise and was wrong.

Every Studio transport node must use the exact command/state topic above. Set MQTT details in the node inspector rather than editing a generated JSON file. Studio's own connection preset is `bitstream-local-mqtt`: `127.0.0.1`, port `8883`, transport `ws`, path `/`.
