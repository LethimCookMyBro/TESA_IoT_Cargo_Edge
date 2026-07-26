# Known limitations

- Dataset windows are from another physical platform; Dataset Demo Mode is not board proof.
- BMI270 needs calibration plus matching 128-window collection before inference can be enabled.
- Obstacle distance, named zone, and robot movement are simulated demo inputs.
- No SLAM, safety certification, measured board inference time, or Ethos-U55 deployment is claimed.
- Route distance is a named-map demo cost, not metres or path-planning accuracy.
- Live BMI270 ingest is not implemented. The placeholder that used to acknowledge BLE samples was removed
  rather than left as a stub implying support; when a board is available its samples arrive through the fleet
  telemetry contract (`cargo/contracts.py`) and are validated against the installed sensor catalog by `cargo/health.py`.
- Every fleet record is `SIMULATED` or `DATASET`. No `HARDWARE` row exists anywhere in this prototype.
- The multi-robot simulator synthesises sensor channels in the installed catalog's units. Those channels are not
  measurements and are not a unit conversion of the CareerCon dataset; only the model predictions over stored
  windows are real model output.
- Latency figures are local-simulator ingest-to-decision measurements on this workstation, never board performance.
- The confidence threshold (0.55) reaches only 0.50 selective accuracy at 36% coverage on the validation split.
  The 0.75 target was not reachable; `models/confidence_policy.json` records that honestly rather than hiding it.
- No board pinout or connector evidence exists in this repository, so no expansion module is authorised.
  See `docs/HARDWARE_EXPANSION_MATRIX.md`.
