# CargoShield architecture

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
  └─ bounded historian queue ──► PostgreSQL ──► read-only History API
                                                └─► Fleet Intelligence
                                                └─► read-only MaintenanceContext
```

- `cargo.mqtt_service` runs the single-robot validation-window replay.
- `cargo.fleet_service` accepts versioned robot-scoped fleet telemetry.
- `cargo.historian` drops and counts overflow rather than blocking a safety decision.
- Browsers never connect directly to PostgreSQL.
- `cargo.maintenance` has no MQTT publisher or database write path.

## Current truth boundary

Dataset Replay feeds real stored CareerCon validation windows to the model, but it is not a live
board measurement. Fleet telemetry, named zones, obstacle distance, and 3D movement are simulated.
Live BMI270 inference remains disabled until units, calibration, sampling rate, timestamps, and
128-sample compatibility are verified. The project does not claim SLAM, physical navigation,
certified stopping distance, or board inference performance.
