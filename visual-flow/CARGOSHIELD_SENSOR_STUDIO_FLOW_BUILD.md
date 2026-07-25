# CargoShield Sensor Studio flow build sheet

Create this graph in **Sensor Studio**, then use its Export command to save the resulting JSON. This file is a build sheet, not an invented flow-schema file.

## External-processing contract

Start `cargo.mqtt_service` first. It makes the Python CargoShield engine the sole source of inference, vibration risk, policy, routing, and safe-stop decisions.

| Direction | MQTT topic | Real payload |
|---|---|---|
| Studio → Python | `cargoshield/cargo-robot-01/command` | `{"action":"start"}`; `pause`; `reset`; `manual_resume`; `clear_obstacle`; `{"action":"set_cargo","cargo_type":"standard"}` or `fragile`; `{"action":"set_obstacle","distance":20}`; `{"action":"set_mission","pickup":"A1","destination":"C2"}` |
| Python → Studio | `cargoshield/cargo-robot-01/state` | `cargoshield.state.v1` JSON emitted by `CargoMqttService.publish_state()` |
| DevKit → Python | `device/+/devkit-twin/telemetry` | Existing Bitstream JSON; currently diagnostic-only until BMI270 field mapping is verified |

## Verified state field paths

Verified from `cargoshield/cargo-robot-01/state` on 2026-07-25 against the running service, its regression tests, and the end-to-end sweep recorded in `reports/demo_e2e_evidence.json`. Values come from the ten-window **curated dataset demonstration sequence** (`cargo.mqtt_service.DEMO_SEQUENCE`), which is a fixed set of real stored windows chosen for coverage — it is a demonstration, not an evaluation result; held-out metrics live only in `reports/metrics.json`. Bind Studio displays to these **exact** paths. The convenient short names used in planning notes (`mission_state`, `surface_class`, `safety_action`, …) are not keys in the payload; the real paths are below.

| Display intent | Real JSON path | Verified values |
|---|---|---|
| Mission state | `status` | `IDLE`, `READY`, `MOVING`, `SLOWING`, `HOLDING`, `PAUSED`, `SAFE_STOPPED`, `COMPLETED`, `ERROR` |
| Cargo type | `cargo_type` | `standard`, `fragile` |
| Surface class | `last.label` | `hard_tiles_large_space`, `hard_tiles`, `tiled`, `soft_pvc` |
| Confidence | `last.confidence` | `0.705`, `0.620`, `0.326`, `0.212` |
| Vibration score | `last.vibration_score` | `1.828` |
| Vibration risk | `last.risk` | `low`, `medium`, `high` (`last.vibration_risk` remains the source field) |
| Speed ratio | `last.decision.speed_ratio` | `0.8` fragile/low, `0.5` warning region, `0.0` stop/hold |
| Safety action | `last.decision.action` | `MOVE`, `SLOW_DOWN`, `SAFE_STOP`, `HOLD_UNCERTAIN` |
| Safety reason | `last.decision.reason` | `fragile cargo with low vibration risk` |
| Manual-resume latch | `last.decision.manual_resume_required` | `true` after a safe stop |
| Current zone | `last.zone` | `A1`, `A2`, `B1`, `B2`, `C1`, `C2` (walks the planned route) |
| Progress | `last.progress` | `0.1`, `0.2`, … `1.0` (ten curated windows) |
| Inference time | `last.inference_ms` | `58.1` |
| Route | `route.nodes`, `route.cost`, `route.reason` | `["A1","B1","C1","C2"]`, `1.688`, `stability-first; …` |
| Obstacle | `obstacle_distance` | `null`, `20`, `50` |
| Risk map | `risk_map.<zone>.score` / `.observations` / `.surface` / `.updated_ms` | `A1.score = 0.596`, `observations = 3`, `surface = hard_tiles` |
| Event log | `events[].message` | `prediction soft_pvc (0.51); MOVE` |
| Envelope | `schema`, `device_id` | `cargoshield.state.v1`, `cargo-robot-01` |
| Error / diagnostic | `error`, `source_diagnostic` | present only on the failing message |

Studio display nodes read a single value, so point each one at a leaf path. Send the whole message to `message-viewer` for `risk_map`, `route`, and `events`, which are objects/arrays.

## Required visual branches

1. **IMU:** `bmi270-input` → `sensor-snapshot` → `json-pack` → `mqtt-publisher` → Python service. The Python state returns through `mqtt-subscriber` to `message-viewer`, `numeric-display`, `indicator`, and `sparkline`/`plotter`.
2. **Cargo:** `dashboard-select` (Standard/Fragile) → `json-pack` → `mqtt-publisher` command.
3. **Collision:** `dashboard-slider` and `dashboard-button` (Clear obstacle) → `compare`/`logic-gate` for visual warning → command publisher. Python's returned `SAFE_STOP` remains authoritative.
4. **Mission:** `dashboard-select` for pickup/destination plus Start/Pause/Reset `dashboard-button` controls → command publisher. Bind returned route/status to dashboard displays.
5. **Feedback:** Bind returned `risk_map` state to `message-viewer`/`plotter`; it represents the Python engine's learned zone-risk feedback into later route cost.
6. **Output:** Bind returned `speed_ratio`, route, vibration risk, and safety action to `dashboard-gauge`, `dashboard-text`, `dashboard-status`, and `dashboard-led`. Add `model-viewer` → `scene-output` only after a real 3D model is selected in Studio; do not claim a live binding before testing it.

Every Studio transport node must use the exact command/state topic above. Set MQTT details in the node inspector rather than editing a generated JSON file.
