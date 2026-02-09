from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from luxera.project.schema import Project, JobResultRef, PhotometryAsset
from luxera.compliance.en13032 import evaluate_en13032


@dataclass(frozen=True)
class AuditHeader:
    project_name: str
    schema_version: int
    job_id: str
    job_hash: str
    solver: Dict[str, Any]
    settings: Dict[str, Any]
    asset_hashes: Dict[str, str]
    coordinate_convention: Optional[str] = None
    units: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    unsupported_features: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PhotometryEntry:
    asset_id: str
    format: str
    filename: Optional[str]
    content_hash: Optional[str]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class EN13032ReportModel:
    audit: AuditHeader
    photometry: List[PhotometryEntry]
    summary: Dict[str, Any]
    geometry: Dict[str, Any]
    method: Dict[str, Any]
    compliance: Optional[Dict[str, Any]] = None


def _load_result_meta(result_dir: Path) -> Dict[str, Any]:
    path = result_dir / "result.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_en13032_report_model(project: Project, job_ref: JobResultRef) -> EN13032ReportModel:
    result_dir = Path(job_ref.result_dir)
    meta = _load_result_meta(result_dir)

    asset_hashes = meta.get("assets", {})
    solver = meta.get("solver", {})
    settings = meta.get("job", {})

    photometry_entries: List[PhotometryEntry] = []
    for asset in project.photometry_assets:
        photometry_entries.append(
            PhotometryEntry(
                asset_id=asset.id,
                format=asset.format,
                filename=asset.metadata.get("filename") if asset.metadata else None,
                content_hash=asset.content_hash,
                metadata=asset.metadata or {},
            )
        )

    audit = AuditHeader(
        project_name=project.name,
        schema_version=project.schema_version,
        job_id=job_ref.job_id,
        job_hash=job_ref.job_hash,
        solver=solver,
        settings=settings,
        asset_hashes=asset_hashes,
        coordinate_convention=meta.get("coordinate_convention"),
        units=meta.get("units", {}),
        assumptions=meta.get("assumptions", []),
        unsupported_features=meta.get("unsupported_features", []),
    )

    summary = meta.get("summary", {})
    compliance = summary.get("compliance") if isinstance(summary, dict) else None
    en13032 = evaluate_en13032(summary).to_dict() if isinstance(summary, dict) else None

    geometry = {
        "rooms": [r.__dict__ for r in project.geometry.rooms],
        "grids": [g.__dict__ for g in project.grids],
    }
    method = {
        "job": meta.get("job", {}),
        "solver": meta.get("solver", {}),
        "coordinate_convention": meta.get("coordinate_convention"),
    }

    return EN13032ReportModel(
        audit=audit,
        photometry=photometry_entries,
        summary=summary,
        geometry=geometry,
        method=method,
        compliance={"en12464": compliance, "en13032": en13032},
    )
