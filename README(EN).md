# CargoShield Fleet Guardian

[ฉบับภาษาไทย](README.md)

A multi-robot cargo-service prototype for TESA IoT Cargo Edge. It combines surface classification
from recorded IMU windows, a deterministic Python Safety Core, robot-scoped MQTT contracts, a
PostgreSQL fleet historian, a Three.js Dataset Replay console, and a Fleet Intelligence dashboard.

> **Current data status:** every record is `DATASET` or `SIMULATED`. The repository does not yet
> contain live board measurements, real localization, SLAM, a range sensor, motor control, or
> physical robot motion.

## What works today

- Replay validation-split IMU windows through the model one window at a time.
- Classify surfaces, estimate vibration risk, and choose `MOVE`, `SLOW_DOWN`,
  `HOLD_UNCERTAIN`, or `SAFE_STOP`.
- Apply different policies to standard and fragile cargo and retain zone risk for the next route.
- Isolate multiple robots and detect duplicates, ordering faults, jumps, and non-finite values.
- Persist telemetry, predictions, events, and missions to PostgreSQL through a queue that cannot
  block the Safety Core.
- Render the replay in a Three.js warehouse and show fleet/history data in Fleet Intelligence.
- Expose a read-only Maintenance Copilot boundary with no robot-command or Safety Core authority.

## How the dataset is used

The dataset is not used only for training. Groups are split without overlap:

| Split | Purpose |
| --- | --- |
| Train | Fit the RandomForest and derive vibration-risk boundaries |
| Validation | Select the confidence threshold and supply Dataset Replay windows |
| Test | Produce final metrics in `reports/metrics.json` only |

Dataset Replay feeds recorded inputs through the pipeline in sequence to demonstrate decisions. It
is neither live measurement nor a result from the held-out test split.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

To regenerate dataset/model artifacts:

```powershell
.\.venv\Scripts\python.exe -m training.prepare_dataset
.\.venv\Scripts\python.exe -m training.train_baseline
.\.venv\Scripts\python.exe -m training.select_confidence
.\.venv\Scripts\python.exe -m training.evaluate_baseline
```

Start the loopback-only PostgreSQL fleet historian:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m cargo.db
```

Connection settings come from the environment; copy `.env.example` to `.env` to override them.

## Run

An MQTT broker must listen on `127.0.0.1:1883`, with MQTT-over-WebSocket on
`127.0.0.1:8883` (Bitstream Studio's broker supports this profile). Then run:

```powershell
# Single-robot Dataset Replay engine
.\.venv\Scripts\python.exe -m cargo.mqtt_service

# Fleet Guardian and read-only History API
.\.venv\Scripts\python.exe -m cargo.fleet_service
.\.venv\Scripts\python.exe -m cargo.history_api --port 8099

# Serve both web surfaces
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory webapp
```

- 3D Dataset Replay: <http://127.0.0.1:8080/index.html>
- Fleet Intelligence: <http://127.0.0.1:8080/fleet.html>

The **Start Dataset Replay** button publishes `{"action":"start"}` to
`cargoshield/cargo-robot-01/command` and replays ten validation windows in about ten seconds.
A Safe Stop remains latched until an operator sends `manual_resume`.

## Fleet demo

```powershell
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
```

The scenario runs three simulated robots concurrently: one healthy, one that accumulates vibration
and latches a Safe Stop after an impact, and one that emits faulty data. PostgreSQL is deliberately
removed mid-run to prove that the Safety Core continues deciding. Evidence is written to
`reports/fleet_scenario_evidence.json`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q cargo training scripts tests
.\.venv\Scripts\python.exe scripts\smoke_mqtt_flow.py --dataset-demo
.\.venv\Scripts\python.exe scripts\demo_e2e_check.py
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
.\.venv\Scripts\python.exe scripts\webapp_ui_check.py --url "http://127.0.0.1:8080/?device=ui-verify"
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Latest verified result on this checkout: **131 tests + 111 subtests**, MQTT E2E **14/14**, Fleet
Scenario **12/12**, browser verification with zero console errors, and no known vulnerabilities
reported by `pip-audit`. Latency numbers describe the local simulator, not board performance.

## Main documentation

| Document | Contents |
| --- | --- |
| [`docs/FLEET_GUARDIAN_FINAL_REPORT.md`](docs/FLEET_GUARDIAN_FINAL_REPORT.md) | Current outcome, architecture, evidence, and prohibited claims |
| [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) | Unimplemented and unverified capabilities |
| [`docs/ML_EVALUATION.md`](docs/ML_EVALUATION.md) | Data splits, held-out metrics, and confidence selection |
| [`docs/HARDWARE_EXPANSION_MATRIX.md`](docs/HARDWARE_EXPANSION_MATRIX.md) | Missing evidence before camera, microphone, range, or motor expansion |
| [`docs/HERMES_MAINTENANCE_COPILOT.md`](docs/HERMES_MAINTENANCE_COPILOT.md) | Read-only copilot boundary |
| [`docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md`](docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md) | MQTT/Bitstream Sensor Studio workflow and build limits |
| [`docs/FLEET_GUARDIAN_PHASE0_BASELINE.md`](docs/FLEET_GUARDIAN_PHASE0_BASELINE.md) | Historical pre-Fleet-Guardian baseline |
