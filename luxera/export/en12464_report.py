from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import json

from luxera.export.report_model import AuditHeader
from luxera.project.schema import Project, JobResultRef


@dataclass(frozen=True)
class EN12464ReportModel:
    audit: AuditHeader
    compliance: Dict[str, Any]


def build_en12464_report_model(project: Project, job_ref: JobResultRef) -> EN12464ReportModel:
    result_dir = Path(job_ref.result_dir)
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))

    audit = AuditHeader(
        project_name=project.name,
        schema_version=project.schema_version,
        job_id=job_ref.job_id,
        job_hash=job_ref.job_hash,
        solver=meta.get("solver", {}),
        settings=meta.get("job", {}),
        asset_hashes=meta.get("assets", {}),
    )

    summary = meta.get("summary", {})
    compliance = summary.get("compliance", {}) if isinstance(summary, dict) else {}

    return EN12464ReportModel(audit=audit, compliance=compliance)
