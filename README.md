# CargoShield Edge

Local Python engine for cargo-aware surface classification, safety policy, route selection, and Bitstream Sensor Studio integration over MQTT.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m training.prepare_dataset
.\.venv\Scripts\python.exe -m training.train_baseline
.\.venv\Scripts\python.exe -m training.evaluate_baseline
.\.venv\Scripts\python.exe -m pytest -q
```

## Run

Start the Bitstream Studio MQTT broker on `127.0.0.1:1883`, then run:

```powershell
.\.venv\Scripts\python.exe -m cargo.mqtt_service
```

Publishing `{"action":"start"}` to `cargoshield/cargo-robot-01/command` replays a curated ten-window dataset demonstration sequence over about ten seconds (`--interval` retunes the pacing). Obstacle commands re-decide live from the latest inference while a mission is active; a safe stop latches until `manual_resume`.

Verify the whole path against a running broker:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_mqtt_flow.py --dataset-demo
.\.venv\Scripts\python.exe scripts\demo_e2e_check.py
```

See `docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md` for the Sensor Studio flow and `reports/demo_e2e_evidence.json` for the recorded end-to-end result.

Live BMI270 inference remains disabled until its calibration and 128-sample window are verified.
