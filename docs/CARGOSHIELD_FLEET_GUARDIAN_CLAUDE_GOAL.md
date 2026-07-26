# CargoShield Fleet Guardian — Claude Goal Prompt

> **Historical execution prompt:** Phases 0–7 were implemented and verified. Do not run this prompt
> again as if the repository were still a single-robot baseline. Current status is maintained in
> `README.md`, `docs/CARGOSHIELD_IMPLEMENTATION_PLAN.md`, and
> `docs/FLEET_GUARDIAN_FINAL_REPORT.md`. Revalidation on commit `6a9153d` passed
> **177 tests + 174 subtests**.

Copy the prompt below into Claude after starting a long-running `/goal`.

---

You are the lead engineer for the CargoShield Fleet Guardian prototype.

Repository:

`C:\Users\User\Downloads\arjan_TESA`

## Goal

Turn the current single-robot CargoShield demo into a verified, local-network-first, multi-robot Fleet Guardian prototype that:

1. preserves the existing deterministic Safety Core;
2. receives and clearly labels simulated TESAIoT/Bitstream sensor data;
3. supports multiple robots concurrently through robot-scoped MQTT topics;
4. stores fleet history centrally in PostgreSQL;
5. detects sensor and robot-health faults in real time without an LLM;
6. provides a polished Thai-first Live Operations view and a separate Fleet Intelligence dashboard;
7. exports provenance-rich data for later model training;
8. prepares a read-only Maintenance Copilot boundary for Hermes Agent;
9. contains no knowingly unused production code, speculative adapters, fabricated hardware behavior, or misleading claims.

Continue autonomously through safe, in-scope work until the acceptance criteria are genuinely met or a concrete blocker is proven. Do not stop merely to report intermediate progress. Ask the user only when a missing choice would materially change the result or requires new authority.

## Non-negotiable boundaries

- Work from the real checkout and runtime state. Do not rely on old summaries or test counts.
- Preserve all existing user/other-agent working-tree changes. Inspect `git status` and diffs before editing. Never use `git reset --hard`, `git checkout --`, or destructive cleanup.
- Do not commit, push, create a PR, publish, install system-wide software, modify credentials, or expose a service outside the local machine/LAN without explicit user approval.
- Python remains authoritative for safety decisions. PostgreSQL, the dashboard, and any Agent must never sit in the synchronous Stop/Slow/Hold decision path.
- The system must continue making safe decisions if PostgreSQL, Hermes, the dashboard, or the network historian is unavailable.
- Hermes must be asynchronous and read-only. It may explain, summarize, compare history, and draft maintenance checklists. It must not publish robot commands, clear Safe Stop, change thresholds, modify models, or write directly to operational tables.
- Never describe a simulated obstacle, named-zone map, Digital Twin pose, or dataset replay as real localization, SLAM, physical movement, or hardware performance.
- Every state/event/sample must carry explicit provenance such as `SIMULATED`, `DATASET`, or `HARDWARE`.
- Do not claim a camera, microphone, distance sensor, current sensor, motor driver, or repair capability unless the exact hardware interface, voltage, driver, field mapping, and live behavior are verified.
- “Self-healing” means bounded software recovery: reconnecting transport, quarantining bad channels, resetting rolling buffers, entering degraded mode, choosing a safer next route, and requesting maintenance. It does not mean physically repairing hardware.
- Do not add TimescaleDB, Redis, Kafka, Kubernetes, microservices, a generic plugin system, or speculative interfaces unless measured evidence proves the simpler design insufficient.
- Prefer the smallest implementation that meets the verified requirement. Reuse existing modules and patterns before creating new ones.
- No browser-to-PostgreSQL connection. Historical data must be exposed through a narrow read-only API.
- No external CDN dependency in the demo. Preserve the existing local Three.js setup.

## Use subagents deliberately

Create bounded subagents for independent evidence gathering and review. Recommended roles:

1. **Research and hardware auditor** — read all three PDFs in `research/`, board notes, Bitstream documentation, and the installed Bitstream release profile. Report supported claims and prohibited claims with file/page evidence.
2. **Code and dead-code auditor** — trace imports, production callers, dynamic callbacks, CLI entry points, MQTT callbacks, tests, and UI contracts. Produce a keep/merge/wire/remove table. Do not delete code based on a single grep result.
3. **Fleet/data architect** — design the minimal MQTT contracts, PostgreSQL schema, ingestion boundary, indexes, retention, and export path.
4. **Safety/performance reviewer** — trace sensor-to-decision flow, define latency budgets, fault states, backpressure behavior, and fail-safe rules.
5. **UI/UX reviewer** — inspect the existing Three.js console and propose the smallest coherent split between Live Operations and Fleet Intelligence.
6. **Verification reviewer** — independently review the final diff, run acceptance checks, look for dead code, unsafe coupling, misleading simulation claims, and flaky tests.

Subagents should be read-only during discovery. During implementation, assign disjoint file ownership or serialize overlapping edits. The lead agent must reconcile all findings against the real checkout; do not blindly accept subagent conclusions.

## Phase 0 — Establish the factual baseline

Before changing production code:

1. Read repository guidance and inspect:
   - `README.md`
   - `cargo/`
   - `training/`
   - `webapp/`
   - `scripts/`
   - `tests/`
   - `docs/`
   - `important_notes/`
   - `visual-flow/`
   - all PDFs in `research/`
2. Record:
   - current Git branch/status and unrelated dirty files;
   - current test, compile, smoke, browser, and MQTT results;
   - current processes/listeners relevant to MQTT, Bitstream, PostgreSQL, and the web app;
   - current schemas/topics and exact runtime payloads;
   - installed Bitstream Studio version and active `release.modules.json`.
3. Inspect the live Bitstream telemetry catalog when available. Re-verify rather than assume the earlier catalog:
   - BMI270 acceleration, gyro, temperature, Euler angles, quaternion;
   - BMM350 magnetic vector and temperature;
   - SHT40 temperature and humidity;
   - DPS368 pressure and temperature;
   - ADC potentiometer channels;
   - switch/button state and counters.
4. Identify production call paths and dead/incomplete paths. Pay special attention to:
   - `MissionController.accept_ble_sample`;
   - the optional `on_change` callback;
   - the label-filter branch of `DatasetReplaySource.indices`;
   - DevKit telemetry currently treated as diagnostic-only;
   - validation split creation and how it is or is not used;
   - `.env.example`;
   - duplicate state/schema/display constants;
   - documentation that still claims unavailable Sensor Studio Dashboard/Stage features.
5. Produce a short baseline report before implementation:
   - **Keep**
   - **Merge**
   - **Wire completely**
   - **Remove**
   - **Blocked pending hardware**

Do not count tests as proof of a feature unless the feature is exercised through its production path.

## Phase 1 — Freeze versioned fleet contracts

Define minimal versioned JSON contracts before database/UI changes.

Required MQTT topic families:

```text
cargoshield/{robot_id}/state
cargoshield/{robot_id}/telemetry
cargoshield/{robot_id}/events
cargoshield/{robot_id}/command
cargoshield/fleet/status
```

Requirements:

- Validate `robot_id` and payloads at trust boundaries.
- Include schema version, unique event/sample identifier, robot ID, observed timestamp, received timestamp, provenance, source mode, and sequence number where available.
- Distinguish raw telemetry, derived features, model prediction, deterministic safety decision, fault/health event, mission event, and maintenance finding.
- Define duplicate and out-of-order handling.
- Retain only appropriate last-known state. Do not retain transient errors, raw high-rate telemetry, or one-off diagnostics.
- Keep command authorization separate from read-only state/history.
- Preserve backward compatibility only where it has a real caller. Otherwise update all callers and tests together instead of carrying an unused compatibility layer.
- Document the contract with real example payloads generated by tests, not hand-waved examples.

## Phase 2 — Deterministic real-time health and safety

Keep the real-time path in memory:

```text
sensor input
  -> validation and timestamp checks
  -> rolling health/feature state
  -> deterministic safety policy
  -> state/command result
  -> non-blocking event queue for persistence
```

Implement only checks supported by available signals:

- finite/range validation using verified catalog limits;
- stale/timeout detection based on configured sample rates;
- sequence/timestamp regression;
- flatline/stuck channel;
- abrupt spike/impact;
- quaternion norm and orientation sanity;
- magnetic-field plausibility and heading discontinuity;
- environmental threshold and rate-of-change checks;
- disagreement among available temperature channels;
- transport disconnect/reconnect and dropped-event counters;
- bounded queues and explicit backpressure behavior.

Use explicit health states, for example:

- `HEALTHY`
- `DEGRADED`
- `UNSAFE`
- `OFFLINE`

Map them through a deterministic policy to normal operation, reduced speed, Hold, or Safe Stop. An LLM must never choose these transitions.

Implement bounded software recovery where justified:

- reconnect MQTT/telemetry with backoff;
- clear only invalid rolling windows;
- quarantine an unhealthy channel while preserving valid channels;
- enter degraded mode with an operator-visible reason;
- require manual acknowledgement where a safety latch demands it;
- use accumulated route risk only when planning the next mission, never mutate the displayed route mid-run.

Define and measure simulator-only performance budgets. At minimum report sensor-ingest-to-safety-decision p50/p95/max and prove persistence/dashboard failure does not materially change it. Label all results as local simulator measurements, not board performance.

## Phase 3 — PostgreSQL Central Fleet Historian

PostgreSQL is the central historian on the private/local network because multi-robot operation is a confirmed requirement.

Use a single central database and the smallest practical ingestion service. Add only the required PostgreSQL driver/dependencies. Do not introduce an ORM unless it measurably reduces complexity.

The schema should minimally cover:

- robots and last-seen/health state;
- missions and route snapshots;
- telemetry samples or bounded telemetry batches;
- derived features;
- model predictions;
- safety/fault/health events;
- maintenance findings and acknowledgements;
- dataset export manifests and provenance.

Requirements:

- migrations are versioned and repeatable;
- foreign keys and constraints protect data integrity;
- indexes support robot/time, mission/time, event severity/time, and unresolved maintenance queries;
- credentials come from environment variables and are never committed;
- `.env.example` must become genuinely used or be removed;
- database writes happen through a bounded asynchronous queue/batch writer;
- database failure cannot block the Safety Core;
- expose queue depth, dropped records, retries, and database health;
- no silent unbounded in-memory growth;
- browser clients never receive database credentials;
- provide a minimal read-only history API for the dashboard;
- export CSV/JSONL plus a manifest containing schema version, filters, time range, robot IDs, labels, and provenance.

For the current no-board prototype, do not implement an unused per-robot SQLite layer. Document SQLite as the future durable edge outbox once real hardware and offline-sync semantics can be tested.

If Docker is available, a local PostgreSQL compose setup is acceptable. If it is unavailable, report the blocker and provide a reproducible native/local alternative. Do not silently skip database integration tests and still claim the historian works.

## Phase 4 — Multi-robot simulator and evidence

Build a deterministic simulator/harness for at least three robot IDs using verified simulated or stored data:

1. one healthy robot on a low-risk route;
2. one robot accumulating high vibration/impact exposure and selecting a safer route on its next mission;
3. one robot with stale, malformed, out-of-order, or contradictory sensor data entering degraded/unsafe state.

The simulator must:

- use the same production MQTT contracts as future hardware;
- support reproducible seeds/scenarios;
- label every record `SIMULATED` or `DATASET`;
- never claim physical localization or a real obstacle sensor;
- exercise concurrent ingestion into PostgreSQL;
- demonstrate that one robot’s failure does not corrupt another robot’s state;
- demonstrate PostgreSQL/dashboard outage while the Safety Core continues;
- provide one command that runs the full fleet scenario and writes a bounded evidence report.

Do not fabricate unavailable Bitstream Studio nodes or manually invent an exported Sensor Studio flow schema. Use only features confirmed in the installed release profile.

## Phase 5 — Two coherent UI surfaces

Preserve the existing Three.js console where it is useful. Do not rewrite it merely to change frameworks.

### Live Operations

Purpose: operate and understand one selected robot now.

Include:

- robot selector and connection/provenance badges;
- third-person overview as the default;
- optional follow and virtual robot-POV camera modes clearly labeled as simulated views, not a physical camera;
- mission controls and deterministic safety state;
- current route, zone, surface, vibration, environment, sensor freshness, health state, queue/database status;
- visible degraded/Safe Stop reason and acknowledgement requirements;
- event timeline;
- Thai-first labels with concise English technical terms where useful.

### Fleet Intelligence

Purpose: historical and cross-robot analysis.

Include:

- fleet summary and online/degraded/offline counts;
- robot health table with last seen and unresolved faults;
- time-series plots for vibration, confidence, environmental channels, and health;
- route/zone risk comparison;
- mission and safety-event history;
- maintenance queue and acknowledgement;
- data-quality/provenance breakdown;
- dataset export controls and export manifest preview;
- explicit simulated-data badges.

Requirements:

- use MQTT for live state and the read-only API for history;
- remain useful without WebGL;
- responsive at laptop and desktop sizes;
- keyboard accessible and understandable without color alone;
- no console errors;
- no unbounded DOM/event growth;
- no direct PostgreSQL connection from the browser;
- preserve authoritative Python decisions rather than reimplementing policy in JavaScript.

## Phase 6 — Training and research alignment

Use the papers in `research/` to support, not exaggerate, the implementation:

- surface classification from IMU windows;
- embedded package-event classification and confidence rejection;
- vibration-aware condition monitoring and next-mission route cost.

Make the existing validation split earn its existence:

- use validation data for confidence-threshold selection, rejection/uncertainty policy, or another explicitly documented model-selection step;
- keep the held-out test split untouched until final evaluation;
- prevent group leakage;
- report macro/weighted metrics, class-level failures, coverage versus rejection, and provenance;
- never mix simulator-generated labels into real held-out metrics;
- export live/simulated records for future training without automatically retraining or deploying a model.

Do not add PPO/RL merely because the paper uses it. The current named graph and amount of data do not justify claiming an RL navigation system. Keep transparent risk-weighted routing unless a separate, validated RL experiment is explicitly scoped.

## Phase 7 — Hermes Maintenance Copilot boundary

Do not install or integrate Hermes until Phases 0–6 pass independently.

First implement a provider-neutral, read-only maintenance context/API that can answer from curated data:

- why a robot stopped or degraded;
- which sensors/evidence caused the conclusion;
- which routes/zones have the highest accumulated vibration exposure;
- which robots need inspection;
- a maintenance checklist;
- a shift/day summary;
- which data ranges are suitable for export.

Then provide an optional Hermes integration guide:

- local/self-hosted model endpoint where practical;
- read-only database user or, preferably, access only to curated read-only API/views;
- no MQTT command credentials;
- no terminal/file-write/browser-control tools in the demo profile;
- no autonomous threshold/model/config changes;
- human approval for every proposed maintenance acknowledgement or configuration change;
- full audit log of question, retrieved evidence, model answer, and model/version;
- graceful fallback when Hermes/model is absent or slow.

Hermes latency is not part of the real-time safety budget. Immediate alerts and recovery are deterministic; Hermes explanations may arrive seconds later.

OpenClaw is not required for this prototype. Consider it later only if a messaging-channel gateway becomes a real requirement.

## Optional hardware expansion research

Because the real board is not currently available, do not create production adapters for camera, microphone, ToF/ultrasonic, current sensing, or motor control.

Create only an evidence-based expansion matrix covering:

- candidate low-cost module;
- intended value to CargoShield;
- board connector/bus;
- voltage/current compatibility;
- available driver/library;
- expected sampling/data rate;
- effect on compute/power;
- whether the current board/NPU can process it;
- exact evidence source;
- status: verified, plausible pending board, or unsupported.

No purchasing recommendation or integration claim is valid without verified board pinout and connector evidence.

## Dead-code and cleanup policy

At the end of every phase:

1. search all production callers, tests, dynamic registration, callbacks, CLI entry points, and documented commands;
2. remove unused branches and duplicated constants only after proving no valid path uses them;
3. wire an incomplete feature fully or remove it—do not leave permanent placeholders that imply support;
4. keep hardware-bound code only when it has a documented future entry point and cannot misrepresent current capability;
5. update all docs/tests/schema examples in the same change;
6. run a dead-code/static pass and review manually;
7. inspect `git diff` for unrelated changes and accidental generated files.

Do not perform broad refactors unrelated to the Fleet Guardian goal.

## Verification requirements

Create the smallest tests that prove the new behavior, including:

- payload/schema validation;
- three concurrent robot IDs;
- isolation between robots;
- duplicate/out-of-order samples;
- stale, malformed, non-finite, spike, and flatline inputs;
- deterministic health-to-action transitions;
- safe behavior while PostgreSQL is down;
- bounded queue/backpressure behavior;
- asynchronous persistence not blocking safety decisions;
- retained-state policy;
- migration repeatability and database constraints;
- read-only history API;
- training export provenance;
- validation-threshold selection without test leakage;
- Hermes boundary cannot publish commands or mutate operational data;
- UI rendering, Thai labels, accessibility basics, responsive layout, WebGL fallback, and zero console errors.

Run the project’s real verification suite, not a guessed subset:

- `pytest -q`;
- `python -m compileall` for project Python;
- existing MQTT smoke and full E2E evidence scripts;
- PostgreSQL integration tests against an actual reachable test database;
- deterministic multi-robot scenario;
- browser/UI checks at representative viewports;
- performance measurement for the local simulator path;
- the full suite at least three consecutive times if concurrency/timing code changed.

Do not report “passed” for skipped infrastructure tests. Separate:

- passed;
- skipped with reason;
- blocked;
- not run.

## Final acceptance demonstration

The finished local demo should show:

1. three simulated robots connected simultaneously;
2. a healthy mission;
3. a vibration/impact event that immediately changes deterministic safety behavior;
4. accumulated route risk affecting the next mission’s route, not changing the active route;
5. a stale/faulty sensor causing degraded or unsafe state with a precise reason;
6. PostgreSQL receiving fleet history without affecting decision latency;
7. Live Operations and Fleet Intelligence showing the same authoritative state;
8. export of a provenance-rich dataset slice;
9. PostgreSQL or Hermes becoming unavailable while robot safety continues;
10. optional Hermes/read-only explanation of the event, clearly outside the real-time path.

## Required final report

When genuinely complete, report:

1. concise outcome;
2. architecture and data-flow diagram;
3. files changed and why;
4. keep/merge/wire/remove results;
5. database schema/migrations;
6. MQTT contracts and example payloads;
7. real-time health rules and recovery behavior;
8. multi-robot demo instructions;
9. exact verification commands and observed results;
10. measured simulator latency, throughput, queue depth, and limitations;
11. screenshots/evidence paths;
12. remaining hardware-only blockers;
13. honest claims suitable for judges and claims that remain prohibited.

Do not claim completion while required work remains. If blocked, exhaust safe local alternatives, identify the exact blocker with evidence, and leave the repository in a tested, understandable state.
