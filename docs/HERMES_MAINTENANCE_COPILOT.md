# Hermes Maintenance Copilot — integration guide

## Status: not connected

Hermes is **not integrated**. What exists today is the provider-neutral, read-only boundary it
would have to sit behind: `cargo/maintenance.py`, now reachable over GET through
`cargo/history_api.py` and surfaced in Fleet Guardian as
**"Maintenance Assistant — Deterministic Read-only Analysis"**.

What was actually checked on this workstation, so the claim is precise:

| Check | Result |
| --- | --- |
| Reference to Hermes anywhere in this repository's code or configuration | none — only this document and prose in the READMEs |
| Hermes endpoint configured for CargoShield | none |
| Hermes process listening on any port | none |
| `hermes` executable present on the workstation | yes — `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe` |
| Proven endpoint or tool contract wired into CargoShield | **no** |

A CLI existing on the same machine is not an integration. `/api/copilot` therefore reports
`"provider": null`, `"provider_status": "not_connected"`, `"analysis_mode": "deterministic"`, and
the panel prints **"Hermes provider: Not connected"**. Nothing was installed or configured to make
that sentence true — it is simply what the repository contains.

**Every answer the panel shows today is deterministic SQL over curated `SELECT` statements. No
language model is in that path.** Do not present it as an active agent integration.

## What is shipped today

- `GET /api/copilot` — the curated question list, the boundary object, and the provider status.
- `GET /api/copilot/{question}` — one answer plus its evidence rows.
- The Fleet Guardian panel renders the questions as buttons. **There is no free-text input**, so the
  page can only ask what the allowlist permits, and a prompt cannot widen the contract.
- `history_api.COPILOT_QUESTIONS` is that allowlist: the method behind each question is named in
  Python, never taken from the URL. `/api/copilot/_query` is a 404, not a method call.

## What the boundary already enforces

Three independent mechanisms, strongest first. Each is covered by a test in
`tests/test_fleet_historian.py::MaintenanceBoundaryTests`.

| # | Mechanism | Where | Proven by |
| --- | --- | --- | --- |
| 1 | A PostgreSQL role with `SELECT` and nothing else | `cargo/db.py::ensure_readonly_role` | `test_the_role_cannot_mutate_any_operational_table` — INSERT, UPDATE, DELETE, TRUNCATE and DROP all raise `InsufficientPrivilege` |
| 2 | No transport in the module: no MQTT client, no publisher, no command builder | `cargo/maintenance.py` | `test_the_module_exposes_no_transport_and_no_mutator` |
| 3 | Every SQL statement in the module is a literal `SELECT` | `cargo/maintenance.py` | `test_every_sql_statement_in_the_module_is_a_select` — parsed with `ast`, not grepped |

The copilot therefore **cannot** publish a robot command, clear a Safe Stop, change a threshold or
a model, acknowledge a maintenance finding, or write to any operational table. Acknowledgement
remains an operator action on `cargoshield/{robot_id}/command`, which this module cannot reach.

## The seven questions it can answer

All from curated data, each returning its evidence rows so an answer can cite rather than invent:

1. `why_did_robot_stop(robot_id)` — the most recent warning/critical events with their reasons.
2. `evidence_for_conclusion(robot_id, around_ms=...)` — the telemetry samples around an event.
3. `highest_vibration_exposure()` — accumulated vibration per zone across the fleet's history.
4. `robots_needing_inspection()` — unresolved findings or non-healthy state.
5. `maintenance_checklist(robot_id)` — a **draft** for a human, ending with "an operator must
   acknowledge the finding; no copilot may acknowledge it".
6. `shift_summary(since_ms=...)` — events and missions over a shift.
7. `exportable_ranges()` — ranges by robot and provenance, with the note that SIMULATED and
   DATASET rows must never be reported as real-world performance.

Try it, on the command line or over the read-only API:

```powershell
.\.venv\Scripts\python.exe -m cargo.maintenance --robot robot-bravo

# or, with `cargo.history_api` running:
curl http://127.0.0.1:8099/api/copilot
curl "http://127.0.0.1:8099/api/copilot/why-stop?robot_id=robot-bravo"
curl http://127.0.0.1:8099/api/copilot/vibration-exposure
```

The endpoint ids are `why-stop`, `inspection`, `vibration-exposure`, `shift-summary`, `checklist`,
`evidence` and `export-ranges`. `why-stop`, `checklist` and `evidence` require `robot_id`, which is
validated by `contracts.validate_robot_id` before it reaches SQL.

Every answer carries the `BOUNDARY` object describing what a copilot may and may not do, so a
prompt cannot quietly widen the contract.

## If Hermes is added later

Do this only after Phases 0–6 pass independently, which they do as of
`docs/FLEET_GUARDIAN_FINAL_REPORT.md`.

- **Model endpoint.** Prefer a local or self-hosted endpoint on the private network. This project
  ships no model client, no API key handling and no outbound network call.
- **Database access.** Give it the `cargoshield_readonly` role, or better, only the read-only HTTP
  API on `127.0.0.1:8099`. Never the owner role.
- **Credentials.** No MQTT command credentials. If `--command-token` is set on
  `cargo.fleet_service`, the copilot must not receive it.
- **Tools.** No terminal, no file-write, no browser control in the demo profile.
- **Configuration.** No autonomous threshold, model or config changes. The confidence threshold is
  selected by `training/select_confidence.py` on the validation split and pinned by a test.
- **Human approval.** Every proposed maintenance acknowledgement or configuration change is a
  suggestion until a human performs it in the UI.
- **Audit log.** Record the question, the retrieved evidence rows, the model's answer, and the
  model name and version. `Answer.as_dict()` already returns question, summary, evidence and
  `generated_ms`; the model identity is the caller's to add.
- **Fallback.** `MaintenanceContext.available()` returns `(ok, reason)` and never raises, and
  `python -m cargo.maintenance` prints a structured unavailable result with the note that robot
  safety is unaffected. A slow or missing copilot must never surface as a robot fault.

## Latency

Hermes latency is **not** part of the synchronous safety budget. By the time anything reads this
boundary, the deterministic Safety Core has already decided and acted — measured at
p50 0.1574 ms / p95 0.3140 ms ingest-to-decision in the latest local simulator evidence.
Explanations may arrive
seconds later without any safety consequence.

## OpenClaw

Not required for this prototype. Consider it only if a messaging-channel gateway becomes a real
requirement; nothing in the current design depends on one.
