# BLE integration

This checkout has no BLE session, scanner, or `Bs2BleSession` implementation. Live board samples
would enter through the versioned fleet telemetry contract in `cargo/contracts.py`, but no
BLE-to-contract adapter exists yet.

Live BMI270 inference is intentionally withheld until units, axes, calibration, cadence,
timestamps, and 128-sample compatibility with CareerCon are proven. No obstacle-distance sensor
field exists; obstacle controls are explicitly simulated.
