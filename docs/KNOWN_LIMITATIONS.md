# Known limitations

- Dataset Replay uses train-disjoint validation windows from another physical platform. It is
  neither live measurement nor board proof; the test split remains reserved for reported metrics.
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
- Secure Edge is design-only. No OPTIGA API call, device certificate provisioning, mTLS,
  Secure Boot, protected update, or anti-rollback flow has been deployed or proven on hardware.
- The actual competition-board root of trust is unverified: the TESAIoT guide names OPTIGA Trust M,
  while the Infineon product page, user guide, and Zephyr board page do not list a discrete OPTIGA.
  Milestone M1 in `docs/CARGOSHIELD_SECURE_EDGE_DESIGN.md` must resolve this before implementation.
- The model artifact is loaded without cryptographic authenticity verification. Local SHA-256
  checking and signed-manifest verification are both planned but not implemented.
- The Maintenance Assistant is deterministic SQL, not a language model. No copilot provider is
  configured: `/api/copilot` reports `provider: null` and the panel shows
  "Hermes provider: Not connected". A `hermes-agent` CLI happens to be installed on the development
  workstation, but nothing in this repository references, configures, launches or talks to it, and
  no Hermes endpoint or tool contract has been proven. Do not describe the integration as active.
- CSV endpoints intentionally cap a single export at 5,000 rows and do not stream arbitrarily
  large history. Use narrower filters for larger datasets.
- Headless SwiftShader performance is highly load-dependent; the latest headed GPU evidence records
  180 fps (median of five samples) on an RTX 4050. This measures web rendering on one workstation
  and says nothing about inference performance on the target board.
