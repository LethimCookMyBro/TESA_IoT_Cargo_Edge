"""Provenance-rich dataset export for later model training.

Exporting never retrains and never deploys anything. It writes a slice plus a manifest that records
exactly which rows it contains and where they came from, so a future training run cannot silently
mix simulated records into a real held-out metric.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any, Sequence
from uuid import uuid4

from . import contracts, db

EXPORT_SCHEMA_VERSION = 1

COLUMNS = ("event_id", "robot_id", "mission_id", "seq", "observed_ms", "received_ms", "provenance",
           "source_mode", "zone", "label", "confidence", "vibration_score", "vibration_risk",
           "accepted", "health_state", "channels")


@dataclass(frozen=True)
class ExportFilters:
    robot_ids: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    from_ms: int = 0
    to_ms: int = 2 ** 62

    def as_dict(self) -> dict[str, Any]:
        return {"robot_ids": list(self.robot_ids), "labels": list(self.labels),
                "provenance": list(self.provenance), "from_ms": self.from_ms, "to_ms": self.to_ms}


@dataclass
class ExportResult:
    export_id: str
    path: Path
    manifest_path: Path
    row_count: int
    manifest: dict[str, Any] = field(default_factory=dict)


def _select(filters: ExportFilters, settings: db.Settings | None) -> list[dict[str, Any]]:
    for robot_id in filters.robot_ids:
        contracts.validate_robot_id(robot_id)
    for value in filters.provenance:
        if value not in contracts.PROVENANCE:
            raise contracts.ContractError(f"unknown provenance filter: {value!r}")
    sql = (
        "SELECT t.event_id, t.robot_id, t.mission_id, t.seq, t.observed_ms, t.received_ms,"
        " t.provenance, t.source_mode, t.zone, p.label, p.confidence, p.vibration_score,"
        " p.vibration_risk, p.accepted,"
        " (SELECT e.health_state FROM fleet_events e"
        "   WHERE e.robot_id = t.robot_id AND e.observed_ms = t.observed_ms"
        "     AND e.kind = 'safety_decision' LIMIT 1) AS health_state,"
        " t.channels"
        " FROM telemetry_samples t"
        " LEFT JOIN model_predictions p"
        "   ON p.robot_id = t.robot_id AND p.observed_ms = t.observed_ms"
        " WHERE t.observed_ms BETWEEN %s AND %s"
        "   AND (cardinality(%s::text[]) = 0 OR t.robot_id = ANY(%s::text[]))"
        "   AND (cardinality(%s::text[]) = 0 OR t.provenance = ANY(%s::text[]))"
        "   AND (cardinality(%s::text[]) = 0 OR p.label = ANY(%s::text[]))"
        " ORDER BY t.observed_ms, t.robot_id"
    )
    robots, provenance, labels = list(filters.robot_ids), list(filters.provenance), list(filters.labels)
    with db.connect(settings or db.settings_from_env(), connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (filters.from_ms, filters.to_ms, robots, robots,
                                 provenance, provenance, labels, labels))
            names = [description[0] for description in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]


def _write_rows(path: Path, rows: Sequence[dict[str, Any]], fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, default=str) + "\n")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: (json.dumps(row[key], default=str) if key == "channels" else row.get(key))
                             for key in COLUMNS})


def export(destination: Path, *, fmt: str = "jsonl", filters: ExportFilters | None = None,
           settings: db.Settings | None = None, record: bool = True) -> ExportResult:
    """Write a slice plus its manifest. Returns the manifest so a caller can show it before download."""
    if fmt not in {"csv", "jsonl"}:
        raise contracts.ContractError("format must be csv or jsonl")
    filters = filters or ExportFilters()
    rows = _select(filters, settings)
    export_id = uuid4().hex
    destination = Path(destination)
    data_path = destination / f"cargoshield_export_{export_id[:12]}.{fmt}"
    manifest_path = data_path.with_suffix(data_path.suffix + ".manifest.json")
    _write_rows(data_path, rows, fmt)

    observed = [row["observed_ms"] for row in rows if row.get("observed_ms") is not None]
    manifest = {
        "export_id": export_id,
        "schema_version": EXPORT_SCHEMA_VERSION,
        "created_ms": int(time() * 1000),
        "format": fmt,
        "row_count": len(rows),
        "columns": list(COLUMNS),
        "filters": filters.as_dict(),
        "observed_range_ms": [min(observed), max(observed)] if observed else None,
        "robot_ids": sorted({row["robot_id"] for row in rows}),
        "labels": sorted({row["label"] for row in rows if row.get("label")}),
        "provenance": sorted({row["provenance"] for row in rows if row.get("provenance")}),
        "path": str(data_path),
        # Stated on every export so a downstream training run cannot mistake this for field data.
        "claims": {
            "contains_real_hardware_data": False,
            "note": "Rows are SIMULATED or DATASET records produced by the local CargoShield fleet "
                    "simulator. They are not measurements from a physical robot and must never be "
                    "mixed into a held-out metric reported as real-world performance.",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if record:
        with db.connect(settings or db.settings_from_env(), connect_timeout=5) as connection:
            connection.execute(
                "INSERT INTO export_manifests (export_id, created_ms, schema_version, format,"
                " row_count, from_ms, to_ms, robot_ids, labels, provenance, filters, path)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (export_id, manifest["created_ms"], EXPORT_SCHEMA_VERSION, fmt, len(rows),
                 manifest["observed_range_ms"][0] if observed else None,
                 manifest["observed_range_ms"][1] if observed else None,
                 manifest["robot_ids"], manifest["labels"], manifest["provenance"],
                 json.dumps(filters.as_dict()), str(data_path)),
            )
            connection.commit()
    return ExportResult(export_id, data_path, manifest_path, len(rows), manifest)


def _split(value: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip()) if value else ()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export a provenance-rich CargoShield dataset slice")
    parser.add_argument("--out", default="reports/exports", help="directory to write into")
    parser.add_argument("--format", default="jsonl", choices=("jsonl", "csv"))
    parser.add_argument("--robots", help="comma-separated robot ids")
    parser.add_argument("--labels", help="comma-separated surface labels")
    parser.add_argument("--provenance", help="comma-separated: SIMULATED,DATASET,HARDWARE")
    parser.add_argument("--from-ms", type=int, default=0)
    parser.add_argument("--to-ms", type=int, default=2 ** 62)
    args = parser.parse_args()

    result = export(Path(args.out), fmt=args.format,
                    filters=ExportFilters(_split(args.robots), _split(args.labels),
                                          _split(args.provenance), args.from_ms, args.to_ms))
    print(json.dumps({"rows": result.row_count, "data": str(result.path),
                      "manifest": str(result.manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
