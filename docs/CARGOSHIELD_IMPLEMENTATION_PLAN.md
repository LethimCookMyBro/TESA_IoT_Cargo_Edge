# CargoShield Edge implementation plan

## Verified baseline

- Entry point: `python -m cargo.mqtt_service`.
- Dataset: `X_data.npy` is `(7626, 128, 10)`; verified baseline channels are gyro `4:7` and linear acceleration `7:10`.
- The project contains only the CargoShield engine, training pipeline, tests, and Sensor Studio integration notes.

## Delivered phases

1. Inspect and split dataset by group with no overlap.
2. Train/evaluate an interpretable RandomForest baseline and save generated artifacts.
3. Add an isolated `cargo/` pipeline for telemetry validation, inference, risk memory, routing, and deterministic decisions.
4. Expose commands and state through the local MQTT broker.
5. Keep live BMI270 inference withheld until units, calibration, and a compatible 128-sample window are demonstrated.

## Next phase

Build and export the verified Sensor Studio flow. Do not hand-write its JSON schema.
