# CargoShield AI architecture

## Product hierarchy

One product, three parts. Fleet Guardian is a module inside CargoShield AI, not a second product,
and Dataset Replay is how data is fed while there is no hardware, not a headline capability.

```text
CargoShield AI
├── Mission Protection          webapp/index.html + cargo/{inference,decision_engine,controller}.py
│   ├── Surface AI              cargo/inference.py
│   ├── Cargo Policy            cargo/decision_engine.py::CargoPolicy
│   ├── Safety Core             cargo/decision_engine.py::decide
│   └── Route Risk Memory       cargo/risk_map.py + cargo/routing.py
│
├── 3D Mission Demo             webapp/scene.js
│   └── Dataset Replay          cargo/sources.py + cargo/mqtt_service.py::DEMO_SEQUENCE
│
└── Fleet Guardian              webapp/fleet.html + cargo/fleet_service.py
    ├── Multi-robot Monitoring  cargo/fleet.py + cargo/health.py
    ├── PostgreSQL Historian    cargo/historian.py + cargo/db.py
    ├── Fleet Intelligence      cargo/history_api.py
    └── Maintenance Copilot     cargo/maintenance.py (read-only)
        └── Hermes boundary     not connected; see docs/HERMES_MAINTENANCE_COPILOT.md
```

## Synchronous safety path

```text
DATASET / SIMULATED telemetry
        ↓
contract validation + sequence gate
        ↓
per-robot health checks
        ↓
48 features from a 128 × 6 IMU window
        ↓
local RandomForest + confidence gate
        ↓
deterministic cargo / obstacle policy
        ↓
robot-scoped state + event
```

The Python Safety Core owns every `MOVE`, `SLOW_DOWN`, `HOLD_UNCERTAIN`, and `SAFE_STOP`
decision. PostgreSQL, web UIs, Sensor Studio, and a future agent are outside this path and cannot
delay or override it.

## Operational and history paths

```text
CargoShield services
  ├─ MQTT retained state ──► Three.js Dataset Replay console
  │                       └─► optional Sensor Studio state viewer
  ├─ MQTT fleet state/events
  └─ bounded historian queue ──► PostgreSQL ──► GET-only History API
                                                └─► Fleet Intelligence
                                                └─► SELECT-only MaintenanceContext
```

- `cargo.mqtt_service` runs the single-robot validation-window replay.
- `cargo.fleet_service` accepts versioned robot-scoped fleet telemetry.
- `cargo.historian` drops and counts overflow rather than blocking a safety decision.
- Browsers never connect directly to PostgreSQL.
- `cargo.maintenance` has no MQTT publisher or database write path.
- `cargo.history_api` exposes only GET endpoints, but its general history queries use the owner
  database role. The Maintenance Copilot alone reads through `MaintenanceContext` with the
  SELECT-only role. Its question set is an allowlist
  (`history_api.COPILOT_QUESTIONS`); a question outside it has no endpoint at all.
- `/api/events` and `/api/missions` are stable, read-only, independently paginated views with a
  hard maximum of 20 rows per page. Their CSV siblings (`/api/events.csv`,
  `/api/missions.csv`) reuse the same filters, cap exports at 5,000 rows, and never enter the
  synchronous safety path.
- Fleet Intelligence presents operational history in this order: Safety Events, Mission History,
  Maintenance Assistant, then collapsed advanced data tools. Event and mission page state are
  independent; changing the event severity resets only the event page.

## Presentation boundary

The browser renames what Python decided and never decides anything itself:

- `webapp/controls.js::protectionState` maps the engine's `status` to a Cargo Protection State
  (`PROTECTED`, `SLOWING`, `HOLDING`, `SAFE_STOP`, …). It is a lookup keyed on a published field.
- `webapp/controls.js::explain` builds the "what is happening now" sentences from published
  `action`, `risk`, `label`, `confidence`, `speed_ratio` and `reason` only. A field that was not
  published produces no sentence rather than an invented one.
- `webapp/controls.js::actionTone` gives `HOLD_UNCERTAIN` its own colour in the 3D stage so an
  uncertain model is visually distinct from a deliberate slow-down.
- `webapp/scene.js` owns three presentation-only cameras (Overview, Follow, Robot POV). Camera
  selection publishes no MQTT command and cannot change engine state. Route phases are native
  Three.js plane geometry with distinct widths, so the active route does not depend on unsupported
  WebGL line-width behaviour.
- `tests/test_webapp_visual.py` pins all three against the engine's own status and action sets, so
  a new engine status cannot silently render blank.

## Current truth boundary

Dataset Replay feeds real stored CareerCon validation windows to the model, but it is not a live
board measurement. Fleet telemetry, named zones, obstacle distance, and 3D movement are simulated.
Live BMI270 inference remains disabled until units, calibration, sampling rate, timestamps, and
128-sample compatibility are verified. The project does not claim SLAM, physical navigation,
certified stopping distance, or board inference performance. Secure Edge is likewise a
source-backed target design, not a deployed capability; see
`docs/CARGOSHIELD_SECURE_EDGE_DESIGN.md`.
