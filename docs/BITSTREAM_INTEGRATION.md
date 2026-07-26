# Bitstream integration

CargoShield now includes a local MQTT bridge at `cargo.mqtt_service`. It uses Bitstream Studio's verified native MQTT endpoint, `mqtt://127.0.0.1:1883`, and keeps the existing Python engine authoritative for inference and safety decisions.

- commands: `cargoshield/cargo-robot-01/command`
- current retained state: `cargoshield/cargo-robot-01/state`
- CargoShield-defined diagnostic topic: `device/+/devkit-twin/telemetry` — **not** an existing Bitstream or TESAIoT topic (it appears nowhere in the installed extension). Diagnostic-only; nothing is inferred from it.

The installed Studio 0.1.9 profile can host a minimal subscriber/state viewer, but its dashboard and
3D categories are disabled. The working operator controls and Three.js visualization are in
`webapp/`. See [the capability audit](BITSTREAM_VISUAL_FLOW_CAPABILITIES.md) and
[runbook](CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md). The bridge is local and anonymous only because the
active local broker accepted a credential-free local connection; do not expose it on an untrusted
network.
