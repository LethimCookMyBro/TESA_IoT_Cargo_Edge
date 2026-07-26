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
- two coherent UI surfaces — the existing Thai-first Three.js Dataset Replay console, plus a new
  Fleet Intelligence dashboard;
- the previously unused 1 824-window validation split now selects the confidence-rejection
  threshold, and that choice measurably improves held-out behaviour;
- a read-only maintenance copilot boundary enforced by a SELECT-only PostgreSQL role;
- **nine flaky verification defects fixed at the root cause**, and one incorrect
  Phase 0 finding retracted with evidence.

Two things the goal asked for that are **not** delivered, and why:
- **No Hermes integration.** By instruction, Hermes is not installed until Phases 0–6 pass. The
  boundary it would sit behind exists and is tested; `docs/HERMES_MAINTENANCE_COPILOT.md` is the
  integration guide. *(Superseded in part — see §16: the boundary is now exposed read-only in the
  UI as the deterministic Maintenance Assistant. Hermes itself remains not connected.)*
- **No populated hardware expansion matrix.** No board pinout or connector evidence exists in this
  repository, so every candidate module is `unsupported — no pinout evidence`. See §12.

## 2. Architecture and data flow

```
                        ┌──────────────────── synchronous safety path, in memory ───────────────────────┐
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
        Dataset Replay (MQTT/WS)               read-only history API :8099 ──► Fleet Intelligence
                                                            │
                                                            ▼
                                        MaintenanceContext (SELECT-only role) ──► future copilot
```

The three rules this diagram exists to make checkable:

1. Nothing below the dashed safety-path box can block anything inside it. `FleetGuardian.sink` is
   called after the decision is made, and a sink that raises is counted and ignored.
2. The browser never reaches PostgreSQL. It has two inputs: MQTT for current retained state, HTTP GET for
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
`models/preprocessing_config.json` (written, never read); its generator was removed too, and a
regression test proves training cannot recreate it.

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
| 1 | `python -m pytest -q` | **PASSED — 131 passed, 111 subtests** (40.02 s). Baseline was 58 passed |
| 2 | `python -m compileall -q cargo training scripts tests` | **PASSED** — exit 0 |
| 3 | `python scripts\smoke_mqtt_flow.py --dataset-demo` | **PASSED** — status `COMPLETED` |
| 4 | `python scripts\demo_e2e_check.py` | **PASSED** — all 14 checks (was flaky at baseline) |
| 5 | `python scripts\fleet_scenario.py` | **PASSED** — all 12 checks; unique `run_id` and current-run-only database query |
| 6 | `python scripts\webapp_ui_check.py --url "http://127.0.0.1:8080/?device=ui-verify"` | **PASSED** — **0 console errors**, 12 screenshots, both surfaces |
| 7 | `python -m cargo.db` | **PASSED** — migration applied once, second run a no-op |
| 8 | `python -m training.select_confidence` | **PASSED** — threshold 0.55 written |
| 9 | `python -m training.evaluate_baseline` | **PASSED** — §6 |
| 10 | `python -m cargo.maintenance --robot robot-bravo` | **PASSED** — answers returned; all writes refused by PostgreSQL |

**Skipped with reason:** none. The PostgreSQL integration tests are written to skip with a printed
reason if the database is unreachable, but on this run the database was reachable and all 23 ran.

**Blocked:** the hardware expansion matrix (§12) and any live-board verification — no board.

**Not run:** nothing that was claimed.

### 9.1 Nine flaky verification defects, fixed at the root cause

The failures below were reproduced and repaired at their actual fault boundary.

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

3. **A WebSocket reconnect could silently swallow an operator command.**
   The console now retries the command across the reconnect window with a bounded attempt count.

4. **A non-finite sensor value failed a whole PostgreSQL batch.**
   `NaN` cannot be stored in `jsonb`; it is now stored as `null` plus a `_nonfinite` list so the
   invalid reading remains visible rather than dropping the batch.

5. **`HistoryApiTests` intermittently aborted POST/PUT with Windows error 10053.**
   The read-only handler returned 405 without consuming the two-byte request body. Windows can
   reset a socket that closes with unread receive data, discarding the response before the client
   sees it. The handler now drains bounded small bodies before replying, closes explicitly, and
   the test server closes and joins cleanly. Repro before the fix failed at request 91/2 000;
   the same 2 000-request probe had zero failures after the fix.

6. **Fleet Intelligence verification sometimes captured only placeholder rows.**
   The page combines a retained MQTT robot list with HTTP history, but the verifier waited a fixed
   1.5 seconds after API health instead of waiting for those independent callbacks to finish.
   It now waits for the first rendered series chart—the same readiness condition asserted later.

7. **A completed replay could miss the UI verifier's fixed 40-second deadline under host load.**
   One reproduced run published `mission completed` after about 43 seconds, while the page was
   correctly still `MOVING` at the deadline. Both completion waits now share a 90-second budget;
   state-edge checks still ensure an old retained `COMPLETED` cannot satisfy them.

8. **A UI command could disappear without an error.**
   The browser published sparse operator commands at MQTT QoS 0, whose resolved promise only
   confirmed the socket write. A reproduced `clear_obstacle` click produced neither a console error
   nor a backend event. Commands now use QoS 1 and wait for the broker's PUBACK; high-rate state
   telemetry remains QoS 0.

9. **The MQTT evidence script could skip a response that arrived quickly.**
   It captured its message cursor after publishing a command. A fast backend could answer in that
   gap, making a real `SAFE_STOPPED` state invisible to the check. Every command now captures the
   cursor before its QoS 1 publish, and each assertion scans from that exact marker.

### 9.2 Evidence-integrity closeout

The old fleet persistence check queried all historical telemetry and only required three robot ids.
It could therefore pass with stale rows while the current post-outage writer reported
`written: 0`. The scenario now creates a unique `run_id`, embeds it in every mission id, queries
only those mission ids, requires current-run rows for every expected robot, and separately requires
the post-outage writer to write at least one record. Historian counters are preserved by phase and
summed explicitly. `Historian.flush()` now waits for in-flight batches as well as queued batches;
an empty queue alone is no longer reported as durable completion.

## 10. Measured performance, throughput, queue depth, and limits

**These are local simulator measurements on this workstation. They are not board performance.**
The label travels with the data: `latency_summary()` returns
`"measurement": "local simulator ingest-to-decision, not board performance"`, and a test asserts it.

Sensor-ingest-to-safety-decision, 68 samples across 3 robots, from `reports/fleet_scenario_evidence.json`:

| p50 | p95 | max | mean |
| --- | --- | --- | --- |
| **0.1574 ms** | **0.3140 ms** | 0.8507 ms | 0.1844 ms |

Persistence does not materially change it: `test_a_slow_sink_does_not_slow_the_decision_materially`
runs 200 samples through a guardian whose sink is a real historian queue and asserts p95 < 5 ms;
observed p95 stays sub-millisecond. During the deliberate database outage the guardian decided **27
further samples** with no change in behaviour.

Historian under outage (`max_queue=50`, database pointed at a closed port): queue filled to 50,
**61 records dropped and counted**, 0 written, `connected: false`. Nothing blocked, nothing grew
without limit, and the drop count is exposed on `cargoshield/fleet/status` and in the dashboard.

Persistence evidence is scoped to the final invocation, not the accumulated database: **41 current-run
telemetry rows** (`robot-alpha: 14`, `robot-bravo: 14`, `robot-charlie: 13`). The final post-outage
writer committed 93 records; all healthy writer phases committed 174 records total. Accumulated
table totals remain visible for operations but are explicitly excluded from acceptance.

**Limitations of these numbers.** Single workstation, one broker, three robots, ~50 ms nominal
sample interval, ~70 decisions per measured run. The `max` of 0.8507 ms is a scheduling outlier, not a
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
10. **A read-only explanation outside the synchronous safety path** — `python -m cargo.maintenance`.

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
   p50 0.1574 ms / p95 0.3140 ms ingest-to-decision **in the local simulator**.
3. Robot safety survives a PostgreSQL outage; 27 decisions were made with the database gone, and
   61 dropped history records were counted rather than lost silently.
4. Surface classification is a real scikit-learn model over real stored CareerCon windows:
   macro F1 0.5156 on a group-disjoint held-out split — comparable to the source paper's own
   XGBoost result of 59.5 % accuracy on the same dataset.
5. The confidence-rejection threshold was selected on the validation split and raises accuracy on
   acted-upon windows from 0.574 to 0.721 at 52.8 % coverage on the untouched test split.
6. The maintenance copilot boundary cannot write: PostgreSQL refuses INSERT, UPDATE, DELETE,
   TRUNCATE and DROP from its role, and the module contains no transport and only literal SELECTs.
7. Nine flaky verification defects were diagnosed to root cause and fixed; the full suite passes
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

---

## 16. Addendum — Product consolidation round (CargoShield AI)

This section records a later round of work. It **adds to** the report above and does not restate or
revise the run records in §1–§15, which remain the evidence for their own round.

### 16.1 What changed and why

The system did many things but told a scattered story: the console called itself a "Dataset Replay
demo centre", Fleet Guardian read as a competing second product, and the three values that actually
matter (vibration risk, the AI's action, the resulting speed) were buried as small rows in the
fourth and fifth panels. The work was to make one product legible in five seconds without removing
any capability that has a user.

| Area | Change |
| --- | --- |
| Product naming | One product, **CargoShield AI — ระบบปกป้องสินค้าเปราะบางสำหรับหุ่นยนต์ขนส่ง**. Fleet Guardian is a module under it; Dataset Replay is a demonstration method, not a headline. |
| Mission Protection UI | A **Cargo Protection State** headline (`PROTECTED` / `SLOWING` / `HOLDING — LOW CONFIDENCE` / `SAFE STOP` / …), then Risk, Action and Speed as three large tiles, then a "เกิดอะไรขึ้นตอนนี้?" panel explaining the decision in sentences. Secondary telemetry moved into an expandable technical block; nothing was deleted. |
| Provenance | `DATASET REPLAY` / `SIMULATION` promoted from a telemetry row to a permanent badge in the top bar, plus a provenance line in the summary. |
| 3D stage | Lighting and palette lifted out of near-black; geometry and materials shared across the eight racks; shadow casting narrowed to the shelves; a ground ring now carries the engine's own action (green / amber / violet / red). |
| Fleet Guardian | Re-ranked to health overview → critical robots and Safe Stops → zone risk → events and missions → trends → data quality → export → Maintenance Assistant. PostgreSQL and the History API moved from headline to a backend-status block. |
| Maintenance Assistant | The existing read-only `MaintenanceContext` exposed over GET and surfaced in the UI. |

### 16.2 The presentation boundary is tested, not asserted

`webapp/controls.js` gained `protectionState`, `explain` and `actionTone`. All three are pure
lookups over already-published fields — the browser still decides nothing.
`tests/test_webapp_visual.py` pins them against the engine: every status in
`cargo.controller.STATUS_BY_ACTION` (plus the terminal ones) must have a protection state with a
label **and a glyph**, so colour is never the only signal; every action must have a distinct tone;
and `explain({status: 'IDLE'})` must return `[]` rather than invent a sentence.

### 16.3 Maintenance Copilot over HTTP

`cargo/history_api.py` gained `GET /api/copilot` and `GET /api/copilot/{question}`, reading through
the SELECT-only role via a separate `readonly_settings`. The question set is an allowlist
(`COPILOT_QUESTIONS`); the method behind each question is named in Python and never taken from the
URL, so `/api/copilot/_query` is a 404 rather than a method call. The UI renders the allowlist as
buttons and has **no free-text input**. Five new tests cover the index, all seven answers, the
allowlist, robot-id validation, and refusal of every write verb.

**Hermes remains not connected.** A `hermes-agent` CLI exists on the development workstation, but
nothing in this repository references, configures or contacts it, and no endpoint or tool contract
was proven. `/api/copilot` reports `provider: null` and the panel prints
"Hermes provider: Not connected". Nothing was installed to change that.

### 16.4 Defects found and fixed during this round

1. **Deck row overlapped the control column.** The bottom deck used an `auto` grid row while its
   timeline grows to 60 entries, so the row expanded past the viewport and covered the entire
   right-hand column — the Reset button was unclickable. Caught by the browser check, not by eye.
   Fixed by clamping the row height and letting the lists scroll inside it.
2. **The five-second answer could scroll away.** Focusing a control scrolled the side column and
   took the protection headline off screen at 1440×900. The summary is now `position: sticky`.
3. **`HOLD_UNCERTAIN` broke mid-word** as `HOLD_UN / CERTAIN`. The Thai word and the raw enum are
   now separated deliberately, and the action tile is the widest of the three.
4. **Thai output broke the contract test on Windows.** `subprocess.run(..., text=True)` decoded
   node's stdout with the system ANSI codepage (cp874) and raised `UnicodeDecodeError` on the first
   Thai byte; the extractor now decodes UTF-8 explicitly.
5. **Vital values sat at different heights** when a label wrapped; they are now bottom-aligned.
6. **Red meant two things** in the 3D legend — zone risk and Safe Stop. Zone risk now has a
   green→amber→red ramp swatch, distinct from the flat red perimeter.

### 16.5 Dead code removed, with proof

Each removal was confirmed by a repository-wide search returning exactly one hit: the definition
itself. Nothing was removed on suspicion.

| Removed | Where | Proof |
| --- | --- | --- |
| `id="tech-details"` | `webapp/index.html` | 1 hit; styled via `details.tech` |
| `id="backend-details"` | `webapp/fleet.html` | 1 hit; styled via `details.tech` |
| `id="fleet-summary"` | `webapp/fleet.html` | 1 hit; styled via `.summary` |
| `id` on five `<table>` elements | `webapp/fleet.html` | 1 hit each; the JS and the check script use the `<tbody>` ids |
| `.chip-sim` | `webapp/styles.css` | 1 hit; the badge it modified was replaced by `.provenance` |
| `class="deck-explain"` | `webapp/index.html` | 1 hit; matched no CSS rule anywhere |

Checked and deliberately **kept**: `tone-*`, `spark-*`, `dot-*`, `.toast`, `glyph-*` and every
`v-*` id are built by template literals (`` $(`v-${key}`) ``, `` `tone-${...}` ``) and look dead
only to a naive search. `OBSTACLE_POLICY`, `PROTECTION_STATES` and `SURFACE_TINTS` have no browser
importer but are pinned by `tests/test_webapp_visual.py`. `DISPLAY_PATHS.status` resolves to a
`#v-status` element that does not exist — the lookup is a guarded no-op, and the entry is kept
because `test_webapp_controls.py` uses it to assert `status` is present in the state payload.

### 16.6 Verification for this round

| # | Command | Result |
| --- | --- | --- |
| 1 | `python -m pytest -q` | **141 passed, 139 subtests** (was 131 + 111; +10 tests) |
| 2 | `python -m compileall -q cargo training scripts tests` | clean |
| 3 | `scripts/smoke_mqtt_flow.py --dataset-demo` | COMPLETED, schema `cargoshield.state.v1` |
| 4 | `scripts/demo_e2e_check.py` | **14/14** |
| 5 | `scripts/fleet_scenario.py` | **12/12**, 93 rows written, 0 dropped |
| 6 | `scripts/webapp_ui_check.py` | **passed**, exit 0, zero application console errors |

Browser evidence now covers `IDLE`, `MOVING`, `HOLD_UNCERTAIN`, `SLOW_DOWN`, `SAFE_STOPPED`,
`COMPLETED`, Fleet Guardian, the Maintenance Assistant, 1920×1080, 1440×900, no-WebGL and
reduced-motion. `HOLD_UNCERTAIN` is deterministic: `DEMO_SEQUENCE` contains windows at confidence
0.45 and 0.30, below the selected 0.55 threshold, so every run reaches it.

Frame rate: **26–32 fps** headless on SwiftShader software rendering across four runs (26, 28, 29,
32), and **177 fps** on an RTX 4050. Both measure web rendering on a workstation and say nothing
about board inference performance. The headless figure is reported as the observed range rather
than the best sample.

### 16.7 Contracts confirmed unchanged

MQTT topics, `cargoshield.state.v1` / `.v2` payloads, every command action and its payload shape,
and all ten pre-existing History API endpoints are byte-for-byte unchanged. The copilot routes are
additive. `tests/test_webapp_controls.py` still feeds every payload the page can emit into
`CargoMqttService.handle_command` and asserts the engine accepts it.

---

## 17. Addendum — Pagination, CSV, camera, and accessibility verification

This section records the 2026-07-26 verification round. It extends the existing implementation
without changing MQTT topics, Safety Core decisions, or command payloads.

### 17.1 Baseline measured before this round

| Check | Baseline result |
| --- | --- |
| `python -m pytest -q` | **141 passed, 139 subtests** in 47.37 s |
| `python -m compileall -q cargo training scripts tests` | passed |
| `scripts/smoke_mqtt_flow.py --dataset-demo` | `COMPLETED`, schema `cargoshield.state.v1` |
| `scripts/demo_e2e_check.py` | **14/14** |
| `scripts/fleet_scenario.py` | **12/12** |
| `pip-audit` | no known vulnerabilities |

The baseline browser run exposed intermittent MQTT/reconnect failures and captured 12 before
screenshots. The presentation defects were small control targets and type, route phases with
insufficient width distinction, no camera-mode controls, Fleet history without pagination or CSV,
advanced data tools appearing before the assistant/history flow, and nested vertical scrolling.

### 17.2 Design system and scoped implementation

The existing dark CargoShield palette and components were retained. The round added only reusable
CSS tokens already supported by the browser: 16 px base type, 44 px minimum interactive targets,
consistent spacing, visible `:focus-visible`, responsive wrapping, and document-level vertical
scrolling. Native HTML/CSS/JS, Python stdlib `csv`, and the repository's existing Three.js were
enough; **no dependency or third-party asset was added**. The CSV button uses the native Unicode
character `↓`, so no icon attribution or license entry is required.

### 17.3 Mission Protection before and after

The before set covers `IDLE`, `MOVING`, `SLOW_DOWN`, `HOLD_UNCERTAIN`, `SAFE_STOPPED`, `COMPLETED`,
1440×900, no-WebGL, and reduced motion. The after set covers those states plus `READY`, Overview,
Follow, Robot POV, 1280×720, 1440×900, and an effective 200% zoom viewport. The route is now built
from separate plane geometry with distinct widths for lane, travelled, remaining, and current
segments; this works on WebGL implementations where `LineBasicMaterial.linewidth` is ignored.
No-WebGL retains a readable fallback and disables unavailable camera controls. Reduced-motion
camera changes are immediate rather than animated.

### 17.4 Fleet Guardian before and after

History is ordered as Safety Events → Mission History → Maintenance Assistant → collapsed Data
Tools. After evidence includes overview at 1920×1080, 1440×900, and 1280×720; safety-event pages 1
and 2; filtered events; mission pagination; Maintenance Assistant; collapsed tools; CSV success;
empty state; and History API unavailable. The page no longer creates a nested vertical scroll
region or horizontal overflow at the tested targets.

### 17.5 Pagination behavior

- Events and missions have independent Previous/Next state and a fixed maximum of 20 rows.
- Page 1 disables Previous; the last page disables Next; invalid, zero, negative, decimal,
  duplicate, and out-of-range pagination inputs are rejected.
- Event sorting is stable by `observed_ms DESC, event_id DESC`; mission sorting is stable by
  `started_ms DESC, mission_id DESC`.
- Changing an event filter resets only the event page to 1; mission pagination is preserved.
- Browser tests exercised pages 1, 2, and 3 and verified ranges and edge states against real DOM
  rows, not only source strings.

### 17.6 CSV contract and security

`/api/events.csv` and `/api/missions.csv` export the active filters independently of the current
20-row page, with fixed columns, ISO-8601 UTC times, CRLF records, UTF-8 BOM, and RFC 4180 quoting.
Cells whose trimmed value starts with `=`, `+`, `-`, or `@` receive a leading apostrophe to prevent
formula execution. Exports are capped at 5,000 rows and return a header for an empty result.

Playwright performed a real browser download and checked the active filter and BOM. Microsoft
Excel 16.0 opened
`reports/downloads/cargoshield_safety_events_20260726T141348Z.csv` as 351 rows including the header
and 15 columns. A temporary contract file additionally proved Thai text, commas, and embedded
newlines survived; the injected `=1+1` opened as the text `'=1+1` with `HasFormula=false`. The
temporary file was removed after verification.

### 17.7 Three.js and performance

Overview, Follow, and Robot POV were exercised through the UI. The selected mode is exposed through
the stage dataset and ARIA pressed state. Headed WebGL used an NVIDIA GeForce RTX 4050; observed
final runs were 172–181 fps, with the latest five samples all 180 fps. These are workstation
rendering figures, **not board inference or physical-robot performance**.

### 17.8 Accessibility and browser verification

Playwright verified keyboard Tab/Enter navigation, a visible focus ring of at least 2 px, 44 px
targets, 1920/1440/1280/1024/960 responsive widths, no horizontal overflow, explicit loading,
empty, disconnected, and error states, reduced motion, and no-WebGL. The final headed run recorded
zero application console errors and zero failed transports. The 200% zoom check used an effective
960×540 CSS viewport for a 1920×1080 display and found zero horizontal overflow and no summary/
control overlap.

All **42 current evidence images** (12 before and 30 after) were opened and visually inspected.
The latest three Playwright images overwritten by the final suite (`Fleet_CSV_success_mock`,
`Fleet_empty_state`, and `Fleet_API_unavailable`) were opened again individually after that run.

### 17.9 Final verification

| Check | Final result |
| --- | --- |
| `python -m pytest -q` | **165 passed, 169 subtests** in 56.55 s |
| `python -m compileall -q cargo training scripts tests` | passed |
| Node syntax checks for `app.js`, `controls.js`, `fleet.js`, `scene.js` | passed |
| `scripts/smoke_mqtt_flow.py --dataset-demo` | `COMPLETED`, `cargoshield.state.v1` |
| `scripts/demo_e2e_check.py` | **14/14** |
| `scripts/fleet_scenario.py` | **12/12**, 97 rows, 0 dropped |
| `scripts/webapp_ui_check.py` | passed; zero console errors |
| `pip-audit` | no known vulnerabilities |
| `git diff --check` | passed |

The simulator historian latency was p50 0.291 ms and p95 0.4875 ms. This is a local software
scenario only. Board latency, sensors, localization/SLAM, physical motion, and real route
readability on robot hardware are **ยังไม่พิสูจน์**.

### 17.10 Contract, cleanup, and evidence boundaries

`cargo/contracts.py`, the Safety decision engine, existing MQTT topics, existing state schemas, and
existing command payloads were not changed. The browser publish path now checks
`client.connected`, and its bounded retry window is 1.6 s so a reconnect can finish before a
command is abandoned. Regression tests feed the unchanged command payloads through the real
handler.

No selector, class, function, or dynamic template family was removed in this round. In particular,
`tone-*`, `v-*`, and `glyph-*` remain untouched. `.gitignore` and package manifests were not
changed. No commit or push was made. Evidence lives in:

- `reports/screenshots/before/`
- `reports/screenshots/after/`
- `reports/webapp_ui_evidence.json`
- `reports/demo_e2e_evidence.json`
- `reports/fleet_scenario_evidence.json`
- `reports/downloads/cargoshield_safety_events_20260726T141348Z.csv`
