from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import json

from luxera.export.report_model import AuditHeader, build_report_model
from luxera.project.schema import Project, JobResultRef


@dataclass(frozen=True)
class EN12464ReportModel:
    audit: AuditHeader
    compliance: Dict[str, Any]
    inputs: Dict[str, Any]
    luminaire_schedule: list[Dict[str, Any]]
    per_grid_stats: list[Dict[str, Any]]
    tables: Dict[str, Any]
    worst_case_summary: Dict[str, Any]
    assumptions: list[str]
    result_dir: str


def build_en12464_report_model(project: Project, job_ref: JobResultRef) -> EN12464ReportModel:
    result_dir = Path(job_ref.result_dir)
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    unified = build_report_model(project, job_ref.job_id, job_ref)

    audit = AuditHeader(
        project_name=project.name,
        schema_version=project.schema_version,
        job_id=job_ref.job_id,
        job_hash=job_ref.job_hash,
        solver=meta.get("solver", {}),
        settings=meta.get("job", {}),
        asset_hashes=meta.get("assets", {}),
        coordinate_convention=meta.get("coordinate_convention"),
        units=meta.get("units", {}),
        assumptions=meta.get("assumptions", []),
        unsupported_features=meta.get("unsupported_features", []),
    )

    summary = meta.get("summary", {})
    compliance = summary.get("compliance", {}) if isinstance(summary, dict) else {}
    compliance_payload = unified.get("compliance", {}) if isinstance(unified, dict) else {}
    if isinstance(compliance_payload, dict) and isinstance(compliance_payload.get("reasons"), list):
        compliance = dict(compliance) if isinstance(compliance, dict) else {}
        compliance["pass_fail_reasons"] = list(compliance_payload.get("reasons", []))
    inputs = {
        "rooms": [r.__dict__ for r in project.geometry.rooms],
        "reflectances": [
            {
                "room_id": r.id,
                "floor_reflectance": r.floor_reflectance,
                "wall_reflectance": r.wall_reflectance,
                "ceiling_reflectance": r.ceiling_reflectance,
            }
            for r in project.geometry.rooms
        ],
        "grids": [g.__dict__ for g in project.grids],
        "vertical_planes": [vp.__dict__ for vp in project.vertical_planes],
        "point_sets": [ps.__dict__ for ps in project.point_sets],
    }
    luminaire_schedule = unified.get("luminaire_schedule", []) if isinstance(unified, dict) else []
    per_grid_stats = summary.get("calc_objects", []) if isinstance(summary, dict) else []
    tables = unified.get("tables", {}) if isinstance(unified, dict) else {}
    worst_case_summary = unified.get("worst_case_summary", {}) if isinstance(unified, dict) else {}
    audit_payload = unified.get("audit", {}) if isinstance(unified, dict) else {}
    assumptions = list(audit_payload.get("assumptions", [])) if isinstance(audit_payload, dict) else []

    return EN12464ReportModel(
        audit=audit,
        compliance=compliance,
        inputs=inputs,
        luminaire_schedule=luminaire_schedule,
        per_grid_stats=per_grid_stats if isinstance(per_grid_stats, list) else [],
        tables=tables if isinstance(tables, dict) else {},
        worst_case_summary=worst_case_summary if isinstance(worst_case_summary, dict) else {},
        assumptions=assumptions,
        result_dir=str(result_dir),
    )
