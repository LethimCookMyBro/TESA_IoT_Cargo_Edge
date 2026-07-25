# CargoShield architecture

```text
Dataset window
  -> telemetry validation / replay source
  -> 128x6 feature extraction -> local RandomForest
  -> vibration band -> deterministic safety decision
  -> named-zone risk memory + demo route selection
  -> local MQTT state
  -> Bitstream Sensor Studio dashboard
```

Dataset replay sends real stored windows to the model. Live BMI270 inference stays disabled until its units, calibration, sampling rate, timestamp, and 128-sample window are verified. The named zone and obstacle source are supplied by the demo; this is neither SLAM nor autonomous obstacle avoidance.
