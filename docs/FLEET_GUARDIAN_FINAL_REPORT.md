# CargoShield Fleet Guardian — final report

Every number here was measured on this checkout on 2026-07-26. Nothing is carried over from an
earlier summary. Where a claim is not supported by evidence in this repository, it is listed in
§13 as prohibited rather than softened.

## 1. Outcome

The single-robot CargoShield demo is now a multi-robot Fleet Guardian prototype:

- versioned, robot-scoped MQTT contracts with explicit provenance on every record;
- a deterministic in-memory health and safety core covering 11 sensor-fault classes, mapped to
  `HEALTHY / DEGRADED / UNSAFE / OFFLINE` and from there to Move / Slow / Hold / Safe Stop;
- a central PostgreSQL fleet historian behind a bounded asynchronous writer that **cannot** block
  or change a safety decision;
- a narrow read-only history API, with no browser-to-database path anywhere;
- a one-command three-robot scenario that also proves database-outage survival and per-robot
  isolation;
- two coherent UI surfaces — the existing Thai-first Three.js Live Operations console, plus a new
  Fleet Intelligence dashboard;
- the previously unused 1 824-window validation split now selects the confidence-rejection
  threshold, and that choice measurably improves held-out behaviour;
- a read-only maintenance copilot boundary enforced by a SELECT-only PostgreSQL role;
- **two pre-existing flaky verification harnesses fixed at the root cause**, and one incorrect
  Phase 0 finding retracted with evidence.

Two things the goal asked for that are **not** delivered, and why:
- **No Hermes integration.** By instruction, Hermes is not installed until Phases 0–6 pass. The
  boundary it would sit behind exists and is tested; `docs/HERMES_MAINTENANCE_COPILOT.md` is the
  integration guide.
- **No populated hardware expansion matrix.** No board pinout or connector evidence exists in this
  repository, so every candidate module is `unsupported — no pinout evidence`. See §12.

## 2. Architecture and data flow

```
                        ┌──────────────────────────── real-time, in memory ─────────────────────────────┐
 robot telemetry        │                                                                               │
 cargoshield/{id}/      │   contracts.validate_envelope ──► SequenceGate ──► HealthMonitor (per robot)   │
   telemetry  ──────────┼──►  (trust boundary)             (dup / order)    (11 deterministic checks)    │
                        │           │                           │                      │                 │
                        │      reject + count            reject + count          HEALTHY/DEGRADED/        │
                        │                                                       UNSAFE/OFFLINE           │
                        │                                                              ▼                 │
                        │                                             decide(CargoPolicy, health)  ◄── the
                        │                                              Move / Slow / Hold / Safe Stop    │
                        └───────────────────────────────────┬───────────────────────────────────────────┘
                                                            │  non-blocking submit(); never awaited
                    ┌───────────────────────────────────────┼────────────────────────────┐
                    ▼                                       ▼                            ▼
   cargoshield/{id}/state (retained)         Historian: bounded queue (5000)     cargoshield/fleet/status
   cargoshield/{id}/events (NOT retained)    → batch writer thread → PostgreSQL       (retained)
                    │                                       │
                    ▼                                       ▼
        Live Operations (MQTT/WS)              read-only history API :8099 ──► Fleet Intelligence
                                                            │
                                                            ▼
                                        MaintenanceContext (SELECT-only role) ──► future copilot
```

The three rules this diagram exists to make checkable:

1. Nothing below the dashed real-time box can block anything inside it. `FleetGuardian.sink` is
   called after the decision is made, and a sink that raises is counted and ignored.
2. The browser never reaches PostgreSQL. It has two inputs: MQTT for live state, HTTP GET for
   history.
3. Commands travel only on `cargoshield/{robot_id}/command`. The history API is GET-only and the
   maintenance context has no transport at all.

## 3. Files changed and why

### New production modules

| File | Why |
| --- | --- |
| `cargo/contracts.py` | The only place a wire payload is built or validated: topics, schema strings, provenance, envelope, robot-id validation, duplicate/out-of-order gate |
| `cargo/health.py` | Deterministic per-robot health. Channel limits come from the **installed** Bitstream catalog, not generic datasheets |
| `cargo/fleet.py` | Multi-robot ingest → health → policy → event hand-off. Structural per-robot isolation |
| `cargo/fleet_service.py` | MQTT front door: wildcard telemetry in, retained state and fleet status out, optional command token |
| `cargo/historian.py` | Bounded async PostgreSQL writer. Drops and counts rather than blocking |
| `cargo/db.py` | Connection settings from env, versioned repeatable migrations, SELECT-only role creation |
| `cargo/history_api.py` | Narrow read-only HTTP API on stdlib `ThreadingHTTPServer` — no web framework added |
| `cargo/export.py` | Provenance-rich CSV/JSONL export plus a manifest that states what the data is not |
| `cargo/maintenance.py` | The read-only copilot boundary |
| `cargo/simulator.py` | Deterministic three-profile simulator over the production contracts |
| `migrations/001_fleet_historian.sql` | Schema, constraints and indexes |
| `scripts/fleet_scenario.py` | The one-command fleet demo and evidence report |
| `training/select_confidence.py` | Makes the validation split earn its existence |
| `webapp/fleet.html`, `webapp/fleet.js` | Fleet Intelligence surface |
| `docker-compose.yml` | Loopback-only local PostgreSQL |

### Modified

| File | Change |
| --- | --- |
| `cargo/decision_engine.py` | `decide()` takes `health_state`/`health_reason`; `load_policy()` reads the validation-selected threshold; default raised 0.45 → 0.55 |
| `cargo/mqtt_service.py` | **Fixed the race behind the flaky e2e check** (see §9.1) |
| `cargo/controller.py` | Uses the loaded policy; removed the dead `on_change` callback and the `accept_ble_sample` placeholder |
| `cargo/sources.py` | Removed the never-called label-filter branch; `window()` returns the ground-truth label directly; added a finiteness check |
| `cargo/inference.py`, `cargo/risk_map.py` | Removed write-only attributes |
| `scripts/webapp_ui_check.py` | **Fixed the missing edge detection behind the flaky UI check** (§9.1); added the Fleet Intelligence probe |
| `webapp/app.js` | `data-status`/`data-states` for deterministic checking; provenance shown in the contract's vocabulary; "จำลอง" on the obstacle readout; bounded command retry across a reconnect |
| `webapp/index.html`, `webapp/styles.css` | Nav between the two surfaces; scoped Fleet Intelligence styles |
| `webapp/scene.js`, `webapp/controls.js` | Removed the never-called `dispose()`/`disposeTree`; un-exported an unimported constant |
| `training/evaluate_baseline.py` | Reports coverage vs rejection at the validation-selected threshold, worst classes by F1, and provenance |
| `.env.example` | Now genuinely used — every variable is read by `cargo/db.py` and `docker-compose.yml` |
| `requirements.txt` | Added `psycopg[binary]`, and `playwright` which the documented UI run already imported |
| `docs/*`, `visual-flow/*` | Corrected four misleading capability claims (§13.3) |

### Deleted (each proven unreachable first)

`cargo/telemetry.py` (its only production caller was the dead BLE placeholder),
`models/preprocessing_config.json` (written, never read).

## 4. Keep / merge / wire / remove results

- **Kept** — every verified production path: the deterministic policy, dataset replay, routing,
  zone risk, the DevKit diagnostic path (wired and rate-limited), all `controls.js` exports except
  one.
- **Merged** — `SurfaceClassifier.models_dir` and `ZoneRiskMap._history_size` folded away as
  write-only attributes; `MOVING_STATUSES` un-exported to its single internal use.
- **Wired completely** — the validation split (§6); robot-id validation as a real trust boundary;
  `.env.example` as real configuration.
- **Removed** — `accept_ble_sample`, `normalize_bmi270` and the `Telemetry` record; the `on_change`
  callback; the label-filter branch of `DatasetReplaySource.indices`; `scene.js` `dispose()` and
  `disposeTree`; `models/preprocessing_config.json`; a dead CSS rule; a stale `.gitignore` entry.
- **Blocked pending hardware** — live BMI270 ingest, and every expansion module (§12).

Live BMI270 ingest was **removed rather than stubbed**. A placeholder that only ever said "inference
withheld" implies a path that does not exist. When a board arrives its samples enter through the
fleet telemetry contract and are validated against the installed catalog by `cargo/health.py` — a
documented, real entry point.

## 5. Database schema and migrations

`migrations/001_fleet_historian.sql`, applied by `python -m cargo.db`, which records applied
versions in `schema_migrations` and is a no-op on re-run (proven by
`MigrationTests::test_migrations_are_repeatable`).

Tables: `robots`, `missions`, `telemetry_samples`, `derived_features`, `model_predictions`,
`fleet_events`, `maintenance_findings`, `export_manifests`.

Integrity is enforced in the database, not only in Python — `robot_id` must match
`^[a-z0-9][a-z0-9-]{1,31}$`, `provenance` is constrained to `SIMULATED|DATASET|HARDWARE`, severities
and health states are constrained, timestamps must be non-negative, `ended_ms >= started_ms`, and
telemetry has a foreign key to `robots`. `ConstraintTests` proves five of these reject bad rows.

Indexes match the four queries actually run: `(robot_id, observed_ms DESC)` on telemetry,
predictions, features and events; `(mission_id, observed_ms DESC)`; `(severity, observed_ms DESC)`;
and a **partial** index on unresolved maintenance findings.

Per the goal, **no per-robot SQLite layer was built.** SQLite is the right future durable edge
outbox once real hardware and offline-sync semantics can be tested; adding it now would be an
untested layer with no caller.

## 6. Making the validation split earn its existence

Before: `models/split_indices.npz` held 4 348 train / **1 824 validation** / 1 454 test windows, and
only `train` and `test` were ever read. `minimum_confidence = 0.45` was a magic number.

Now `training/select_confidence.py` sweeps thresholds on the **validation split only**, measuring
coverage and selective accuracy, and asserts group-disjointness against both train and test before
doing so. It selected **0.55**, and recorded honestly that the 0.75 selective-accuracy target was
**not reachable** at acceptable coverage (validation: 0.503 at 36 % coverage).

Measured on the held-out **test** split, at that validation-chosen threshold:

| Metric | Value |
| --- | --- |
| macro F1 / weighted F1 | 0.5156 / 0.5449 |
| accuracy if nothing is rejected | 0.5743 |
| **selective accuracy on accepted windows** | **0.7210** |
| coverage | 52.8 % (767 accepted, 687 → `HOLD_UNCERTAIN`) |
| worst classes by F1 | `hard_tiles_large_space` 0.046, `soft_tiles` 0.455, `fine_concrete` 0.456 |

Rejecting low-confidence windows raises accuracy on acted-upon windows from 0.574 to 0.721. The
threshold was chosen without ever reading the test split, and a test
(`test_confidence_threshold_matches_the_validation_selection`) pins the constant, the file and the
loader together so they cannot drift.

## 7. MQTT contracts and example payloads

```text
cargoshield/{robot_id}/state       cargoshield.state.v2          RETAINED
cargoshield/{robot_id}/telemetry   cargoshield.telemetry.v1      not retained
cargoshield/{robot_id}/events      cargoshield.event.v1          not retained
cargoshield/{robot_id}/command     cargoshield.command.v1        not retained
cargoshield/fleet/status           cargoshield.fleet_status.v1   RETAINED
```

Only last-known state is retained; transient errors, raw telemetry and one-off diagnostics are not
(`test_only_last_known_state_is_retained`, `test_state_is_retained_but_events_are_not`).

Every payload carries `schema`, `kind`, `robot_id`, `event_id`, `seq`, `observed_ms`, `received_ms`,
`provenance` and `source_mode`. `kind` distinguishes `raw_telemetry`, `derived_feature`,
`model_prediction`, `safety_decision`, `health_event`, `mission_event` and `maintenance_finding`, so
a model's opinion can never be read back as a measurement.

A real telemetry payload, generated by `cargo.fleet.sample` — the same builder the simulator and the
tests use:

```json
{
  "schema": "cargoshield.telemetry.v1", "kind": "raw_telemetry", "robot_id": "robot-bravo",
  "event_id": "6f1c2f0f1a5c4a7f9e2b3d4c5a6b7c8d", "seq": 12,
  "observed_ms": 1785042001234, "received_ms": 1785042001236,
  "provenance": "SIMULATED", "source_mode": "simulator:high_vibration", "zone": "B2",
  "channels": {
    "bmi270.accelX": 19.5, "bmi270.accelY": -0.8123, "bmi270.accelZ": 10.4412,
    "bmi270.gyroX": 0.0731, "bmi270.temperatureC": 27.04,
    "sht40.temperatureC": 25.11, "sht40.humidityPct": 47.32, "dps368.pressureHpa": 1011.28
  },
  "prediction": {
    "label": "concrete", "confidence": 0.712, "vibration_risk": "high",
    "vibration_score": 0.981, "features": {"accel_spread": 4.7419},
    "window_index": 42, "ground_truth": "concrete", "model_input_provenance": "DATASET"
  }
}
```

**Duplicate and out-of-order handling.** `SequenceGate` keeps a bounded per-robot memory (512
entries). A repeated `seq` is `duplicate`; a `seq` or `observed_ms` older than the high-water mark
is `out_of_order`. Neither extends a rolling window nor moves a decision; both increment a visible
counter. Memory is bounded and per-robot, so one robot's disordered stream cannot reject another's
(`test_duplicate_and_out_of_order_are_named_not_merged`, `test_gate_memory_is_bounded`).

**Backward compatibility** was deliberately *not* carried. `cargoshield.state.v1` had exactly one
consumer — the operator console — which was updated in the same change. No unused compatibility
shim exists.

## 8. Real-time health rules and recovery

Channel limits come from the installed Bitstream Studio 0.1.9 catalog (version `2026-07-13`), which
disagrees with generic datasheets in ways that matter: accel is **m/s² in −20…20** (not ±16 g), gyro
is **rad/s in −5…5** (not ±2000 °/s), BMM350 is **±1000 µT** (not ±2000). A test asserts a 100 rad/s
reading is rejected even though 100 °/s would be plausible.

| Check | Verdict |
| --- | --- |
| non-finite value | UNSAFE |
| outside catalog range | UNSAFE |
| abrupt spike beyond the plausible per-sample step | UNSAFE |
| quaternion norm ≠ 1 ± 0.05 | UNSAFE |
| stale beyond 2× tolerance / within tolerance | UNSAFE / DEGRADED |
| timestamp or sequence regression | DEGRADED |
| flatline across a full window | DEGRADED |
| temperature channels disagree > 15 °C | DEGRADED |
| magnetic norm outside 10–100 µT | DEGRADED |
| transport disconnected | OFFLINE |

Mapping, in `decide()` and nowhere else: UNSAFE → `SAFE_STOP` **latched**; OFFLINE →
`HOLD_UNCERTAIN`; DEGRADED → speed capped at 0.4 with an operator-visible reason; HEALTHY → normal.
An LLM participates in none of it.

Bounded software recovery, all implemented: MQTT/telemetry reconnect with backoff (0.5→10 s);
rolling windows cleared on disconnect because values across a gap are not neighbours; an unhealthy
channel quarantined after 3 strikes **while every other channel keeps its history**; degraded mode
with a visible reason; a safety latch that requires explicit operator acknowledgement; and
accumulated route risk used only when planning the next mission, never mutating a running route.

## 9. Verification — exact commands and observed results

Environment: MQTT broker on `127.0.0.1:1883`/`8883` (Bitstream Studio's embedded Aedes),
PostgreSQL 16 in Docker on `127.0.0.1:5433`, one `cargo.mqtt_service --device-id ui-verify`, one
`cargo.history_api --port 8099`, `http.server 8080` serving `webapp/`.

| # | Command | Result |
| --- | --- | --- |
| 1 | `python -m pytest -q` | **PASSED — 124 passed, 111 subtests, 3 consecutive runs** (27.7 s / 29.2 s / 27.3 s). Baseline was 58 passed |
| 2 | `python -m compileall -q cargo training scripts tests` | **PASSED** — exit 0 |
| 3 | `python scripts\smoke_mqtt_flow.py --dataset-demo` | **PASSED** — 3 consecutive runs |
| 4 | `python scripts\demo_e2e_check.py` | **PASSED** — all 14 checks, 3 consecutive runs (was flaky at baseline) |
| 5 | `python scripts\fleet_scenario.py` | **PASSED** — all 11 checks, 3 consecutive runs |
| 6 | `python scripts\webapp_ui_check.py --url "http://127.0.0.1:8080/?device=ui-verify"` | **PASSED** — 3 consecutive runs, **0 console errors**, 12 screenshots, both surfaces |
| 7 | `python -m cargo.db` | **PASSED** — migration applied once, second run a no-op |
| 8 | `python -m training.select_confidence` | **PASSED** — threshold 0.55 written |
| 9 | `python -m training.evaluate_baseline` | **PASSED** — §6 |
| 10 | `python -m cargo.maintenance --robot robot-bravo` | **PASSED** — answers returned; all writes refused by PostgreSQL |

**Skipped with reason:** none. The PostgreSQL integration tests are written to skip with a printed
reason if the database is unreachable, but on this run the database was reachable and all 23 ran.

**Blocked:** the hardware expansion matrix (§12) and any live-board verification — no board.

**Not run:** nothing that was claimed.

### 9.1 Two pre-existing flaky harnesses, fixed at the root cause

Both were failing intermittently at baseline and both are now deterministic across three runs.

1. **`scripts/demo_e2e_check.py` — `obstacle_contract_holds` failed ~50 % of runs.**
   Root cause in *production* code: `_replay_dataset` published `COMPLETED` before its thread was
   scheduled to exit, so a client reacting to `COMPLETED` by pressing Start was told
   "dataset replay is already running". No mission ran, so the obstacle had nothing to stop and
   `stopped_action` was `null`. Fixed in `cargo/mqtt_service.py`: `mission_running` is now the
   authority on whether windows are still being stepped, it is cleared *before* the terminal
   publish, and a finished run's thread is joined with a short handover timeout.

2. **`scripts/webapp_ui_check.py` — failed at a different step each run.**
   Root cause: `wait_status` had no edge detection and returned as soon as the page *already*
   showed a wanted value, so a step could pass against retained state before its own command had
   landed, and the next step then raced a command still in flight. Fixed by exposing
   `data-states` (a counter of states actually published by the engine) and `data-status` (the raw
   enum) on `#status`, and requiring every wait to be satisfied by a state newer than the one
   observed before the action. As a bonus this decouples the harness from the Thai UI labels.

Two further real defects were found *by* those fixes and repaired: a WebSocket reconnect could
silently swallow an operator command (now retried, bounded), and `NaN` from a faulty sensor could
not be stored in `jsonb`, failing whole batches (now stored as `null` plus a `_nonfinite` list, so
the fact is kept).

## 10. Measured performance, throughput, queue depth, and limits

**These are local simulator measurements on this workstation. They are not board performance.**
The label travels with the data: `latency_summary()` returns
`"measurement": "local simulator ingest-to-decision, not board performance"`, and a test asserts it.

Sensor-ingest-to-safety-decision, 68 samples across 3 robots, from `reports/fleet_scenario_evidence.json`:

| p50 | p95 | max | mean |
| --- | --- | --- | --- |
| **0.245 ms** | **0.375 ms** | 1.87 ms | 0.266 ms |

Persistence does not materially change it: `test_a_slow_sink_does_not_slow_the_decision_materially`
runs 200 samples through a guardian whose sink is a real historian queue and asserts p95 < 5 ms;
observed p95 stays sub-millisecond. During the deliberate database outage the guardian decided **24
further samples** with no change in behaviour.

Historian under outage (`max_queue=50`, database pointed at a closed port): queue filled to 50,
**144 records dropped and counted**, 0 written, `connected: false`. Nothing blocked, nothing grew
without limit, and the drop count is exposed on `cargoshield/fleet/status` and in the dashboard.

Persistence in the healthy case: 309 telemetry samples, 313 predictions, 313 derived features, 424
fleet events, 6 missions, 5 robots — with per-robot row counts confirming all three scenario robots
were ingested concurrently.

**Limitations of these numbers.** Single workstation, one broker, three robots, ~50 ms nominal
sample interval, ~70 decisions per measured run. The `max` of 1.87 ms is a scheduling outlier, not a
worst case under load. No sustained-throughput or many-robot test was run, so no throughput ceiling
is claimed. Windows `sleep()` overshoot means the simulator's real cadence is looser than nominal —
which is why `observed_ms` is stamped from the wall clock.

## 11. Multi-robot demo instructions

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m cargo.db
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
```

What it demonstrates, all asserted in `reports/fleet_scenario_evidence.json`:

1. **Three robots connected simultaneously** over the production topics — `three_robots_ingested`.
2. **A healthy mission** — `robot-alpha` finished HEALTHY, never latched.
3. **A vibration/impact event changing safety behaviour immediately** — `robot-bravo` latched a Safe
   Stop with the precise reason
   `bmi270.accelX jumped 20.0015 m/s^2 in one sample (impact or fault)`.
4. **Accumulated route risk affecting the next mission, not the active one** — the running route
   stayed `A1 → A2 → B2 → C2` for the whole mission; the next mission planned
   `A1 → B1 → C1 → C2`.
5. **A faulty sensor causing degraded/unsafe state with a precise reason** — `robot-charlie` reached
   UNSAFE with reasons including
   `temperature channels disagree by 65.0 degC: bmi270.temperatureC=70.0, sht40.temperatureC=5.0`,
   and 9 samples rejected as duplicate/out-of-order.
6. **PostgreSQL receiving fleet history without affecting decision latency** — §10.
7. **Both UI surfaces showing the same authoritative state** — Fleet Intelligence renders the
   retained `cargoshield/fleet/status` published by the same guardian.
8. **A provenance-rich export** — `python -m cargo.export --format jsonl`.
9. **PostgreSQL unavailable while safety continues** — `safety_core_survived_database_outage`.
10. **A read-only explanation outside the real-time path** — `python -m cargo.maintenance`.

To drive the two UI surfaces, add `python -m cargo.mqtt_service`, `python -m cargo.history_api`, and
a static server for `webapp/`, then open `index.html` and `fleet.html`.

## 12. Remaining hardware-only blockers

- **No board pinout, connector diagram, or voltage/current budget exists in this repository.** Every
  candidate expansion module is therefore `unsupported — no pinout evidence`
  (`docs/HARDWARE_EXPANSION_MATRIX.md`). No purchasing recommendation is made.
- **Live BMI270 inference** remains blocked: BLE/board units and window compatibility with the
  CareerCon training distribution are unverified. Concretely, 128 samples spans **6.4 s** at the
  catalog's 50 ms BMI270 default and **1.28 s** at the 10 ms floor — so the board *can* reach the
  rate the vibration paper uses, but not at its default configuration. That is a testable
  statement, not a promise.
- **No board-side performance figure** can be produced without a board.
- **The DevKit topic `device/+/devkit-twin/telemetry` is CargoShield's own invention.** It appears
  nowhere in the installed extension; the TESAIoT platform uses `device/{DEVICE_ID}/telemetry`.
  Three documents used to call it "existing"; that is corrected.

## 13. Claims

### 13.1 Honest and defensible before judges

1. Three simulated robots ingest concurrently through versioned, robot-scoped MQTT contracts, with
   per-robot isolation proven by test and by scenario evidence.
2. A deterministic Python Safety Core makes every Stop/Slow/Hold/Move decision, measured at
   p50 0.245 ms / p95 0.375 ms ingest-to-decision **in the local simulator**.
3. Robot safety survives a PostgreSQL outage; 24 decisions were made with the database gone, and
   144 dropped history records were counted rather than lost silently.
4. Surface classification is a real scikit-learn model over real stored CareerCon windows:
   macro F1 0.5156 on a group-disjoint held-out split — comparable to the source paper's own
   XGBoost result of 59.5 % accuracy on the same dataset.
5. The confidence-rejection threshold was selected on the validation split and raises accuracy on
   acted-upon windows from 0.574 to 0.721 at 52.8 % coverage on the untouched test split.
6. The maintenance copilot boundary cannot write: PostgreSQL refuses INSERT, UPDATE, DELETE,
   TRUNCATE and DROP from its role, and the module contains no transport and only literal SELECTs.
7. Two flaky verification harnesses were diagnosed to root cause and fixed; the full suite passes
   three consecutive times with zero browser console errors.
8. Exact sensor channels, units, ranges and default publish rates are taken from the installed
   Bitstream Studio 0.1.9 catalog, and the health rules enforce those catalog values.

### 13.2 Prohibited — never claim these

- Any camera, microphone, ToF/ultrasonic, current sensor, motor driver, or repair capability.
  The board's audio codec (TLV320DAC3100) is a **DAC — output only** — and the installed profile
  disables the `vision` and `audio` node families outright.
- Real localization, SLAM, mapping, or physical movement. The robot's pose in the 3D scene is
  interpolated from `zone` + `progress`; `zone` is a node of a planned route, not a measurement.
- A real obstacle sensor. Obstacle distance is an operator input, now labelled "จำลอง" in the UI.
- An RL/PPO navigation system. Routing is transparent risk-weighted cost.
- "Self-healing" beyond bounded software recovery. Nothing repairs hardware.
- On-board / Ethos-U55 / NPU inference, or any measured board inference time. The model is a 53 MB
  RandomForest running in host Python; `single_window_ms` is host batch prediction.
- A working Sensor Studio flow, a Dashboard pane, or Stage 3D — all disabled in the installed
  profile, and no flow has been built or seen running by this repository.
- Any figure from the three research papers as if it were CargoShield's. In particular the
  vibration paper's 97.5 % is its own 4-class roughness data on a LiDAR+SLAM robot, and the package
  paper's 94.5 %/95.8 % are precision at a tuned threshold on a proprietary, unavailable dataset.
- Certified safety thresholds. The vibration bands are the training split's 50th/80th percentiles.
- Any expansion-module integration or purchase recommendation (§12).

### 13.3 Corrections made during this work

- **Retracted a Phase 0 finding of my own.** Two `cargo.mqtt_service` processes per launched command
  were first read as "two engines racing on one robot id". Follow-up evidence — `ParentProcessId`
  and `Get-NetTCPConnection` showing sockets held only by the child — proved the venv's
  `python.exe` is a launcher shim and each command is **one** engine. There was no collision; the
  real cause was the harness defect in §9.1. `docs/FLEET_GUARDIAN_PHASE0_BASELINE.md` §2.1 records
  both the wrong conclusion and its retraction.
- **Scalar constant nodes are available**, contrary to two documents that said otherwise:
  `number-constant`, `boolean-constant`, `float-constant` and `integer-constant` are in the enabled
  `utility` category; only `vector-constant` and `quaternion-constant` are in the disabled
  `generator` category.
- **No Sensor Studio node supports MQTT over TCP.** All four shipped endpoint presets are
  `transport: "ws"`, and the nodes run in a browser webview. The runbook's TCP hedge is removed.
- **`device/+/devkit-twin/telemetry` is not an existing topic** (§12).
