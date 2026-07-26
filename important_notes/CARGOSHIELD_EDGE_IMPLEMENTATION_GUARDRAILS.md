# CargoShield Edge: important implementation guardrails

- The existing BLE decoder confirms BMI270 accel/gyro fields but not CareerCon-equivalent calibration; BLE inference is therefore disabled rather than guessed.
- Dataset Replay uses train-disjoint validation IMU windows and a real trained baseline. It is not
  live telemetry and never substitutes for held-out test metrics.
- The obstacle slider/actions, named-zone risk map, and route costs are prototype inputs. They do not represent a distance sensor, SLAM, certified stopping distance, or autonomous avoidance.
- Cargo policy is deliberately deterministic and collision priority latches a safe stop until explicit manual resume.
- Bitstream transport is delivered as a local MQTT bridge (`cargo.mqtt_service`, `mqtt://127.0.0.1:1883`); see `docs/BITSTREAM_INTEGRATION.md`. Python stays authoritative for inference and safety decisions, and the bridge must not destabilize the local desktop demo.
- Incoming `device/+/devkit-twin/telemetry` is diagnostic-only and rate-limited to 1 message/second; BMI270 fields must be explicitly mapped before any inference runs on it.
