# Phase 0 — Factual baseline (before any production change)

> **Historical snapshot:** this file records the state before Fleet Guardian implementation.
> It is not the current project status. See `README.md` and `CARGOSHIELD_IMPLEMENTATION_PLAN.md`
> for the latest verified state.

Recorded from the real checkout and a live runtime on 2026-07-26. Nothing in this file is
carried over from an earlier summary; every number was re-measured.

## 1. Repository state

- Branch `main` at `aa77246`. **No commits, pushes, or resets performed.**
- Pre-existing uncommitted working-tree changes were present at session start and are preserved:
  - deleted: `important_notes/TESAIoT_Hardware_and_NavShield_Specs.md`
  - modified: `webapp/app.js`, `webapp/index.html`, `webapp/styles.css`,
    `scripts/webapp_ui_check.py`, `reports/webapp_ui_evidence.json`,
    `reports/screenshots/*.png` (10 files)
  - untracked: `docs/CARGOSHIELD_FLEET_GUARDIAN_CLAUDE_GOAL.md`
- `reports/webapp_ui_evidence.json` and `reports/screenshots/*` are regenerated evidence
  artefacts; the verification runs below rewrote them. That is their purpose.

## 2. Runtime environment as measured

| Fact | Value | How verified |
| --- | --- | --- |
| Python | 3.10.6 in `.venv` | `.venv\Scripts\python.exe -V` |
| Installed packages | numpy 2.2.6, scikit-learn 1.7.2, joblib 1.5.3, paho-mqtt 2.1.0, pytest 9.1.1, playwright 1.61.0 | `pip freeze` |
| `requirements.txt` | does **not** list `playwright`, which `scripts/webapp_ui_check.py:19` imports | file read + grep |
| MQTT broker | listening on `127.0.0.1:1883` (TCP) and `:8883` (WebSocket), owned by VS Code PID 43288 — the Bitstream Studio extension host | `Get-NetTCPConnection`, `Get-Process` |
| Static web server | `python -m http.server 8080` on 127.0.0.1 | `Get-CimInstance Win32_Process` |
| Docker | CLI + Compose v2.40.3 present; **engine was stopped at session start**, started during Phase 0; server 28.5.1 now reachable | `docker version` |
| PostgreSQL | **no native install, `psql` not on PATH, no Windows service.** Docker is the available route | PATH + service query |
| Bitstream Studio | VS Code extension `terniondev.bitstream-studio-0.1.9`; profile `minimal-sensor` | `release.modules.json` |

### 2.1 The "two engines" reading was wrong — corrected

A process listing showed **two** `cargo.mqtt_service` entries per launched command (e.g. PID 33324
running `.venv\Scripts\python.exe` and PID 19832 running the system Python 3.10), and this was
first read as two engines racing on one robot id.

That conclusion was wrong, and the follow-up evidence retracts it:

- `Win32_Process.ParentProcessId` shows 19832's parent **is** 33324, and in a second launched pair,
  28496's parent **is** 1020. They are parent and child, not peers.
- `Get-NetTCPConnection -RemotePort 1883 -State Established` shows sockets owned **only** by the
  child PIDs (19832, 28496). The `.venv\Scripts\python.exe` parents hold no connection at all.

So this venv's `python.exe` is a launcher shim that re-execs the base interpreter, and each launched
command is exactly **one** logical engine with one MQTT client. There was no collision.

The first browser-verification failure is therefore attributed to the harness defect in §3.1 —
`wait_status` had no edge detection, so a step could pass against retained state left by an earlier
session before its own command had landed. Nothing here indicates a robot-identity design gap.
Robot-id validation still exists in the new contracts, but as a trust-boundary check on untrusted
payloads, not as a fix for a collision that was never happening.

## 3. Verification results at baseline

Reported honestly as passed / failed / flaky / blocked / not run.

| Check | Command | Result |
| --- | --- | --- |
| Unit + integration tests | `.venv\Scripts\python.exe -m pytest -q` | **PASSED** — 58 passed, 27 subtests passed, 21.43 s |
| Byte-compile | `python -m compileall -q cargo training scripts tests` | **PASSED** — exit 0 |
| MQTT smoke | `python scripts\smoke_mqtt_flow.py --dataset-demo` | **PASSED** — reached `COMPLETED`, `cargoshield.state.v1` |
| End-to-end evidence | `python scripts\demo_e2e_check.py` | **FLAKY** — run 1 failed `obstacle_contract_holds` (`stopped_action: null`), run 2 passed all 14 checks. Same code, same broker |
| Browser/UI evidence | `python scripts\webapp_ui_check.py` | **FLAKY** — runs 1 and 2 failed at different steps (`start → MOVING`, then `→ READY`); run 3 passed with zero console errors. Same code, same broker. Cause in §3.1 |
| PostgreSQL integration | — | **NOT RUN** — no database existed at baseline |
| Multi-robot scenario | — | **NOT RUN** — no such harness existed |
| Latency measurement | — | **NOT RUN** — no instrumentation existed |

### 3.1 The flakiness is a harness defect, and it is in scope

Two independent non-determinisms were identified by reading the code that produced the failures:

1. **`scripts/webapp_ui_check.py:46-53` `wait_status` has no edge detection.** It returns as soon
   as the rendered status *already equals* a wanted value. `step("reset", click, "IDLE")` therefore
   returns instantly when the engine's retained state is already `IDLE`, potentially before the
   `reset` command has even been published — so the next step races against a command still in
   flight.
2. **`cargo/mqtt_service.py:131-132` rejects a `start` while the previous replay thread is still
   alive.** `_replay_dataset` publishes `COMPLETED` (`:174`) *before* the thread returns, so a
   client that reacts to `COMPLETED` can issue `start` inside the window where
   `self._replay.is_alive()` is still true. `handle_command` then answers with an error instead of
   a run. This is the mechanism behind `obstacle_contract_holds: false`, where
   `stopped_action` was `null` because no mission was ever under way to stop.

Both are fixed in Phase 2. Neither is an acceptable "known flake".

## 4. Bitstream Studio — what the installed profile actually allows

Profile `minimal-sensor` (`release.modules.json`). Modules **enabled and published**:
`sensor-telemetry`, `sensor-studio`. **Disabled**: `course-studio`, `hmi-studio`,
`simulation-data`, `screen-composer`.

Sensor Studio panes enabled: `library`, `assets`, `flow`, `inspector`, `devkit-twin`,
`devkit-twin-scene`, `actuator-config`.
Sensor Studio panes **disabled**: **`stage` (3D viewport)**, **`dashboard` (operator HMI)**,
`model-outliner`, `stage-outliner`, `inspector-pinned`.

Palette categories enabled: `sensor`, `input`, `transform`, `logic`, `output`, `utility`,
`connectivity` (MQTT / WebSocket pub-sub).
Palette categories **disabled**: `audio`, `scene`, `dashboard`, **`generator` (sine/ramp/noise)**.

Special node families **all disabled**: `audio`, **`vision` (camera / video texture / MediaPipe)**,
`physics`, `materials`.

**Consequences that bind this project:**
- No Sensor Studio Dashboard pane and no Stage 3D exist in the installed build. Any documentation
  promising them is describing software this machine does not have.
- No vision/audio node families exist, so no camera or microphone claim is available even in
  simulation.
- `connectivity` (MQTT) is enabled, which is exactly what the CargoShield contracts rely on.

## 5. Production call paths — keep / merge / wire / remove / blocked

Derived from a full-tree symbol trace (imports, dynamic callbacks, MQTT handlers, CLI entry
points, tests, DOM/CSS contracts), not from single greps.

### Remove — proven to have no valid production path

| Item | Evidence |
| --- | --- |
| `MissionController.accept_ble_sample` (`cargo/controller.py:113`) | Only caller repo-wide is `tests/test_cargo_core.py:144`. No BLE ingress exists in this tree; `_on_message` routes only command vs diagnostic. Its sole effect is a placeholder `self.last` that `_last_inference()` (`:55`) is written to reject |
| `cargo/telemetry.py::normalize_bmi270` | Only production call site is inside `accept_ble_sample`; its return value is discarded apart from a `is not None` test |
| `Telemetry.source` / `.timestamp_ms` / `.gyro` | Zero readers repo-wide |
| `on_change` parameter of `MissionController.__init__` (`:22-23`, fired `:33`) | Every construction site passes one positional argument (`cargo/mqtt_service.py:33`, six test sites). Permanently-false branch, and a silent duplicate of `publish_state()` — wiring it would double-publish |
| `DatasetReplaySource.indices(label=…)` branch (`cargo/sources.py:22-23`) | The only caller, `cargo/mqtt_service.py:147`, passes no argument |
| `SurfaceClassifier.models_dir` (`cargo/inference.py:22`), `ZoneRiskMap._history_size` (`cargo/risk_map.py:21`) | Write-only attributes; the code on the following lines reads the *parameter* |
| `scene.js` `dispose()` + `disposeTree` | No caller anywhere |
| `models/preprocessing_config.json` | Written by `training/train_baseline.py:32`, read by nothing |
| `.env.example` (all four variables) | `os.environ`, `os.getenv`, `dotenv`, `process.env` return **zero** hits repo-wide. Equivalent values are CLI flags and query parameters |
| `.gitignore` `.cargoshield-demo.pid` | No code writes or reads a pid file |
| `styles.css:266 .obstacle output` | Dead as of the current working tree, which replaced that `<output>` with `<input type="number">` |

### Wire completely — incomplete, must not stay a placeholder

| Item | Evidence |
| --- | --- |
| **The validation split** | `models/split_indices.npz` holds `train (4348,)`, `validation (1824,)`, `test (1454,)`. Only `["train"]` (`training/train_baseline.py:24`) and `["test"]` (`training/evaluate_baseline.py:37`) are ever read. 1 824 windows — 24 % of the dataset — are held out and used for nothing, while `CargoPolicy.minimum_confidence = 0.45` (`cargo/decision_engine.py:13`) is an unjustified magic number and `risk_quantiles` are computed on the **train** split |
| Robot identity | No validation of `robot_id` anywhere. Not a live collision (§2.1), but the fleet contracts accept ids from untrusted payloads and topics, so they need a boundary check |
| `_on_connect` subscription list | `tests/test_mqtt_service.py:28` populates `FakeClient.subscriptions` and never asserts it, so the DevKit wildcard topic string is untested |

### Fix, do not delete

| Item | Evidence |
| --- | --- |
| `webapp/index.html:108` | Hardcodes `≤ 30 ซม.` / `≤ 80 ซม.` as Thai prose with **nothing pinning it to `CargoPolicy`**. Every other copy of those thresholds is test-pinned; this one silently lies if the policy changes |
| `requirements.txt` | Missing `playwright`, which the documented UI-evidence run imports |
| `reports/dataset_summary.json:3-6` | Contains four absolute `C:\Users\User\...` paths from `training/inspect_dataset.py:18` |
| `webapp/app.js:60` `sentAt` Map | Never pruned. Bounded in practice by the finite payload space, but unacknowledged |
| Colour constants | `styles.css:13-16` and `scene.js:19` **already disagree**: `hold` is `f5a524` vs `f59e0b`, `stop` is `f0575a` vs `ef4444` |

### Keep — verified live production paths

`ACTIVE_STATUSES`, `STATUS_BY_ACTION`, `select`, `set_obstacle`, `process_dataset_window`,
`start/pause/complete/reset/manual_resume`, `snapshot`, `decide`, `CargoPolicy`,
`SurfaceClassifier.predict`, `ZoneRiskMap.observe/get/score/as_dict`, `choose_route`, `DEMO_GRAPH`,
`DatasetReplaySource.window`, `DEMO_SEQUENCE`, `REPLAY_INTERVAL_S`, the whole DevKit diagnostic
path (`devkit_telemetry_topic` → `_diagnostic_due` → `source_diagnostic` → non-retained publish,
displayed at `webapp/app.js:202`), and every `controls.js` export except `MOVING_STATUSES`
(which has no importer and should lose its `export`).

### Blocked pending hardware

- Live BMI270 inference: calibration and 128-sample window compatibility with the CareerCon
  training distribution are unverified. Correctly withheld today.
- Any camera, microphone, ToF/ultrasonic, current-sensing, or motor-driver claim: no board
  pinout, connector, or voltage evidence exists in this repository, and the installed Bitstream
  profile disables the `vision` and `audio` node families outright.

## 6. Data-flow as it exists today (single robot)

```
dataset/X_data.npy ──► DatasetReplaySource.window
                            │
                            ▼
              MissionController.process_dataset_window
                  │              │              │
                  ▼              ▼              ▼
         SurfaceClassifier   ZoneRiskMap    decide(CargoPolicy)
              (sklearn)      (per-zone)     (deterministic)
                  └──────────────┴──────────────┘
                                 ▼
                        controller.snapshot()
                                 ▼
              publish  cargoshield/{device_id}/state   (retained)
                                 ▼
                  webapp  (MQTT over WebSocket :8883)
```

Commands flow the other way on `cargoshield/{device_id}/command` only. There is **no** telemetry
topic, **no** events topic, **no** fleet topic, and **no** persistence of any kind at baseline.

## 7. What the browser contract actually is

The page reads exactly these paths from the retained state payload: `status`, `cargo_type`,
`source`, `obstacle_distance`, `error`, `source_diagnostic`, `route.nodes`, `route.reason`,
`last.{label,confidence,risk,zone,progress}`, `last.decision.{action,speed_ratio,reason}`,
`risk_map[zone].{score,surface}`, `events[].{timestamp_ms,message}`.

Published but never read: `schema`, `device_id`, `route.cost`, `risk_map[].observations`,
`risk_map[].updated_ms`, `last.vibration_score`, `last.vibration_risk` (the same value is on the
wire twice — the browser reads the `risk` alias created at `controller.py:107`),
`last.inference_ms`, `last.ground_truth`, `last.source`, `last.decision.manual_resume_required`.

`DISPLAY_PATHS.status` (`webapp/controls.js:24`) resolves to `#v-status`, **which does not exist in
`index.html`** — the loop hits `continue`; status is rendered separately at `app.js:199`.

## 8. Honest claims available at baseline, and prohibited ones

Supported today: deterministic Python safety policy; real scikit-learn inference over stored
CareerCon IMU windows; transparent risk-weighted routing over a named six-node demo graph;
retained MQTT state consumable by Sensor Studio's `connectivity` nodes; a Thai-first operator
console with a local (non-CDN) Three.js scene and a working no-WebGL fallback.

Prohibited today and after this work unless new evidence appears: any camera, microphone,
distance sensor, current sensor, or motor-driver claim; real localization, SLAM, or physical
movement (the robot pose in the scene is interpolated from `zone` + `progress`, which is derived,
not measured); a Sensor Studio Dashboard or Stage 3D demonstration; an RL navigation system;
"self-healing" in any sense beyond bounded software recovery.
