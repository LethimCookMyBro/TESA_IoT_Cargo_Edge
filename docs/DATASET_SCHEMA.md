# Dataset schema

- `X_data.npy`: 7,626 × 128 × 10 `float64` windows; axis 1 is temporal.
- `label.npy`: integer-coded surface labels; `groups.npy`: 80 group ids.
- Channels 0–3: orientation quaternion XYZW; 4–6: angular velocity XYZ; 7–9: linear acceleration XYZ.
- The baseline deliberately uses only channels 4–9. There are no NaN or Inf values.

Run `python -m training.inspect_dataset` to regenerate `reports/dataset_summary.json`.
