# CargoShield Fleet Guardian (TESA IoT Cargo Edge)

Payload-aware service-robot prototype: Edge-AI surface classification from stored IMU windows, a
deterministic Python Safety Core, multi-robot MQTT contracts, a central PostgreSQL fleet historian,
and two operator surfaces — a Thai-first Dataset Replay console and a Fleet Intelligence dashboard.

**Every record in this system is `SIMULATED` or `DATASET`.** There is no camera, microphone,
distance sensor, current sensor, motor driver, localization or SLAM. See
`docs/KNOWN_LIMITATIONS.md` for the full list of what is not claimed.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m training.prepare_dataset
.\.venv\Scripts\python.exe -m training.train_baseline
.\.venv\Scripts\python.exe -m training.select_confidence
.\.venv\Scripts\python.exe -m training.evaluate_baseline
```

The fleet historian is a local PostgreSQL container, reachable only on loopback:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m cargo.db          # migrations + the SELECT-only copilot role
```

Credentials come from the environment; copy `.env.example` to `.env` to change them.

## Run

Start the MQTT broker on `127.0.0.1:1883` (Bitstream Studio's embedded Aedes broker serves both
`1883` TCP and `8883` WebSocket), then:

```powershell
# single-robot operator console
.\.venv\Scripts\python.exe -m cargo.mqtt_service

# multi-robot fleet guardian + read-only history API
.\.venv\Scripts\python.exe -m cargo.fleet_service
.\.venv\Scripts\python.exe -m cargo.history_api --port 8099

# serve the two UI surfaces
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory webapp
```

- Dataset Replay Operations: <http://127.0.0.1:8080/index.html>
- Fleet Intelligence: <http://127.0.0.1:8080/fleet.html>

Publishing `{"action":"start"}` to `cargoshield/cargo-robot-01/command` replays a curated
ten-window sequence from the train-disjoint validation split. This is streaming replay, not live
sensor measurement and not a held-out metric. A safe stop latches until `manual_resume`.

## The whole fleet demo in one command

```powershell
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
```

Three robots publish concurrently over the production contracts: one healthy, one accumulating
vibration until an impact latches a Safe Stop and its *next* mission picks a safer route, and one
emitting stale, malformed, out-of-order and contradictory data. Mid-run the historian's database is
taken away to prove the Safety Core does not depend on it. Evidence lands in
`reports/fleet_scenario_evidence.json`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q cargo training scripts tests
.\.venv\Scripts\python.exe scripts\smoke_mqtt_flow.py --dataset-demo
.\.venv\Scripts\python.exe scripts\demo_e2e_check.py
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
.\.venv\Scripts\python.exe scripts\webapp_ui_check.py --url "http://127.0.0.1:8080/?device=ui-verify"
```

`docs/FLEET_GUARDIAN_FINAL_REPORT.md` records the observed results, measured latency, and the
claims that remain prohibited. `docs/FLEET_GUARDIAN_PHASE0_BASELINE.md` is the pre-change baseline.

## Documentation

| Document | What it covers |
| --- | --- |
| `docs/FLEET_GUARDIAN_PHASE0_BASELINE.md` | Factual baseline before any change, incl. a corrected finding |
| `docs/FLEET_GUARDIAN_FINAL_REPORT.md` | Outcome, architecture, contracts, schema, verification results |
| `docs/KNOWN_LIMITATIONS.md` | What this system does **not** do |
| `docs/HARDWARE_EXPANSION_MATRIX.md` | Why no expansion module is authorised |
| `docs/HERMES_MAINTENANCE_COPILOT.md` | The read-only copilot boundary and how it is enforced |
| `docs/ML_EVALUATION.md` | Held-out metrics and the validation-selected confidence threshold |
| `docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md` | Bitstream Sensor Studio flow |
