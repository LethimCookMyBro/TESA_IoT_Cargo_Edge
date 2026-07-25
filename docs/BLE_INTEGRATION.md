# BLE integration

Existing `Bs2BleSession` scan/connect/chunk/decode lifecycle is unchanged. The Cargo page receives decoded BMI270 samples only after the existing UI's accepted-sample path.

Current BLE inference is intentionally withheld: the decoder exposes `accelX/Y/Z` and `gyroX/Y/Z`, but their calibration and 128-sample compatibility with CareerCon have not been proven. No obstacle-distance field exists; obstacle controls are explicitly simulated.
