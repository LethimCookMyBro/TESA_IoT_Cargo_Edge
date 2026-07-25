# Vibration-risk method

The prototype computes the norm of per-axis linear-acceleration standard deviation for a 128-sample window. Low/medium/high boundaries are the training split's 50th and 80th percentiles, stored in `models/feature_config.json`. They are data-derived demo bands, not physical safety thresholds.
