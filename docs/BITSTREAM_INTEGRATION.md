# Bitstream integration

CargoShield now includes a local MQTT bridge at `cargo.mqtt_service`. It uses Bitstream Studio's verified native MQTT endpoint, `mqtt://127.0.0.1:1883`, and keeps the existing Python engine authoritative for inference and safety decisions.

- commands: `cargoshield/cargo-robot-01/command`
- live state: `cargoshield/cargo-robot-01/state`
- existing DevKit telemetry: `device/+/devkit-twin/telemetry` (diagnostic-only until BMI270 fields are explicitly mapped)

See [the capability audit](BITSTREAM_VISUAL_FLOW_CAPABILITIES.md) and [runbook](CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md). The bridge is local and anonymous only because the active local broker accepted a credential-free local connection; do not expose it on an untrusted network.
