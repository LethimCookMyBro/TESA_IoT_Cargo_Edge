# CargoShield implementation status and next plan

## Delivered

1. Group-disjoint train/validation/test split with generated dataset reports.
2. RandomForest surface baseline, validation-selected confidence threshold, and held-out metrics.
3. Single-robot Dataset Replay with deterministic cargo, obstacle, route, risk, pause, and Safe Stop
   behaviour.
4. Robot-scoped MQTT contracts, validation, sequence checks, health state, and fleet isolation.
5. Bounded asynchronous PostgreSQL historian, migrations, GET-only History API, and export path.
6. Three-robot simulator with database-outage evidence and next-mission route replanning.
7. Thai-first Three.js Dataset Replay console with Overview, Follow, and Robot POV cameras,
   responsive layouts, reduced-motion support, and a no-WebGL fallback.
8. Fleet Intelligence dashboard with independent 20-row pagination and filtered CSV downloads for
   safety events and mission history.
9. Provider-neutral read-only Maintenance Copilot boundary.
10. Automated unit, integration, MQTT, fleet, and browser evidence.
11. Source-backed Secure Edge design covering threat model, provisioning, mTLS, Secure Boot,
    protected update, failure policy, and verification milestones. It is a design, not a deployment.

## Current verification

- `177 passed, 174 subtests` on commit `6a9153d`
- Last pushed documentation baseline: `c791ec8`; it changed Markdown only, so code verification
  remains anchored to `6a9153d`
- MQTT end-to-end: `14/14`
- Fleet scenario: `12/12`
- Browser verification: passed with zero console errors, no horizontal overflow at the tested
  1280×720, 1440×900, 1920×1080, and effective 200% zoom viewports
- Dataset Replay: validation-only; train and held-out test windows are excluded

See `FLEET_GUARDIAN_FINAL_REPORT.md` for measured evidence and `KNOWN_LIMITATIONS.md` for prohibited
claims.

## Next work, in order

1. Produce the required five-page A4 portrait proposal PDF from the current evidence. No submission
   PDF exists in the repository yet.
2. Review every proposal claim against the CURRENT/PROPOSED boundary, then verify page count,
   Thai font size, file size, and required filename before submission.
3. When the competition board is available, run Secure Edge milestone M1: confirm whether the
   root of trust is a discrete OPTIGA Trust M or the SoC secure enclave, then verify bootloader,
   eFuse, flash, swap/scratch, connector, and electrical constraints.
4. Capture and label real BMI270 windows; verify units, axes, cadence, timestamps, and calibration
   before enabling live inference.
5. Add real range/localization/motor adapters only after their hardware contracts exist.
6. Optionally build and export the minimal Sensor Studio state viewer by hand. The installed 0.1.9
   profile cannot host the control dashboard or 3D scene, so the working web application remains
   the primary operator surface.

Do not hand-write a Sensor Studio export schema, describe Dataset Replay as live telemetry, or
report local simulator latency as board performance.
