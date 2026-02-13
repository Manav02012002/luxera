from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from luxera.gui.commands import cmd_export_audit_bundle, cmd_export_report, cmd_run_job
from luxera.project.io import load_project_schema


@dataclass(frozen=True)
class ReportingSkillOutput:
    plan: str
    diff_preview: Dict[str, object]
    run_manifest: Dict[str, object]
    artifacts: Dict[str, str]


def build_reporting_skill(project_path: str, job_id: str, template: str = "en12464", ensure_run: bool = True) -> ReportingSkillOutput:
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    artifacts: Dict[str, str] = {}
    run_manifest: Dict[str, object] = {"skill": "reporting", "job_id": job_id, "template": template}
    existing_ref = next((r for r in project.results if r.job_id == job_id), None)
    has_valid_result = False
    if existing_ref is not None:
        result_json = Path(existing_ref.result_dir) / "result.json"
        has_valid_result = result_json.exists()
    if ensure_run and not has_valid_result:
        ref = cmd_run_job(str(ppath), job_id)
        run_manifest["run_result"] = {"job_hash": ref.job_hash, "result_dir": ref.result_dir}
        project = load_project_schema(ppath)
    report_path = cmd_export_report(str(ppath), job_id, template)
    bundle_path = cmd_export_audit_bundle(str(ppath), job_id)
    artifacts["report"] = str(report_path)
    artifacts["audit_bundle"] = str(bundle_path)
    return ReportingSkillOutput(
        plan="Run job if needed, export standards report, and export audit bundle.",
        diff_preview={"ops": [], "count": 0},
        run_manifest=run_manifest,
        artifacts=artifacts,
    )
