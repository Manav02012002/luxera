from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from luxera.gui.commands import cmd_run_job
from luxera.compliance.evaluate import evaluate_emergency, evaluate_indoor, evaluate_roadway
from luxera.project.diff import DiffOp, ProjectDiff
from luxera.project.io import load_project_schema
from luxera.project.schema import ProjectVariant


@dataclass(frozen=True)
class ComplianceSkillOutput:
    plan: str
    diff: ProjectDiff
    run_manifest: Dict[str, object]


def build_compliance_skill(
    project_path: str,
    domain: str = "indoor",
    profile_id: Optional[str] = None,
    job_id: Optional[str] = None,
    ensure_run: bool = True,
    create_variant: bool = False,
    variant_name: Optional[str] = None,
) -> ComplianceSkillOutput:
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    selected_job = _pick_job(project, domain=domain, job_id=job_id)
    if selected_job is None:
        raise ValueError(f"Compliance skill could not find a job for domain={domain!r}")

    run_manifest: Dict[str, object] = {
        "skill": "compliance",
        "domain": domain,
        "job_id": selected_job.id,
        "profile_id": profile_id,
    }

    if ensure_run and not any(r.job_id == selected_job.id for r in project.results):
        ref = cmd_run_job(str(ppath), selected_job.id)
        run_manifest["run_result"] = {"job_hash": ref.job_hash, "result_dir": ref.result_dir}
        project = load_project_schema(ppath)

    result = next((r for r in reversed(project.results) if r.job_id == selected_job.id), None)
    if result is None:
        raise ValueError(f"Compliance skill requires a result for job: {selected_job.id}")

    if domain.lower() == "roadway":
        evaluation = evaluate_roadway(result.summary)
    elif domain.lower() == "emergency":
        evaluation = evaluate_emergency(result.summary)
    else:
        evaluation = evaluate_indoor(result.summary)
    failed_checks = list(evaluation.failed_checks)
    proposals = _build_fix_proposals(project, failed_checks)
    selected_diff = proposals[0][2] if proposals else ProjectDiff()
    variant_diff = _build_variant_diff(project, selected_diff, variant_name=variant_name) if create_variant and selected_diff.ops else ProjectDiff()

    run_manifest["compliance_summary"] = dict(evaluation.source)
    run_manifest["compliance_status"] = evaluation.status
    run_manifest["failed_checks"] = failed_checks
    run_manifest["explanations"] = list(evaluation.explanations)
    run_manifest["create_variant"] = bool(create_variant)
    run_manifest["proposals"] = [
        {"name": name, "reason": reason, "op_count": len(diff.ops)}
        for name, reason, diff in proposals
    ]
    if variant_diff.ops:
        run_manifest["variant_proposal"] = {"op_count": len(variant_diff.ops), "variant_id": variant_diff.ops[0].id}
        selected_diff = variant_diff

    return ComplianceSkillOutput(
        plan="Evaluate compliance summary, identify failing checks, and propose corrective diffs for approval.",
        diff=selected_diff,
        run_manifest=run_manifest,
    )


def _pick_job(project, domain: str, job_id: Optional[str]):
    if job_id:
        return next((j for j in project.jobs if j.id == job_id), None)
    domain = (domain or "indoor").lower()
    allowed = {
        "indoor": {"direct", "radiosity"},
        "roadway": {"roadway"},
        "emergency": {"emergency"},
    }.get(domain, {"direct", "radiosity", "roadway", "emergency"})
    return next((j for j in project.jobs if j.type in allowed), None)

def _build_fix_proposals(project, failed_checks: List[str]) -> List[Tuple[str, str, ProjectDiff]]:
    if not project.luminaires:
        return []
    wants_more_light = any(k in failed_checks for k in ("avg_ok", "min_lux_ok", "luminance_ok", "status"))
    glare_risk = any(k in failed_checks for k in ("ugr_ok", "ti_ok"))
    uniformity_risk = any(k in failed_checks for k in ("uniformity_ok", "uo_ok", "ul_ok"))

    proposals: List[Tuple[str, str, ProjectDiff]] = []
    spacing_diff = _spacing_tweak_diff(project, shrink=0.92 if uniformity_risk else 1.06)
    proposals.append(("spacing_tweak", "Adjust luminaire spacing to improve distribution consistency.", spacing_diff))

    if wants_more_light:
        add_diff = _add_row_column_diff(project)
        proposals.append(("add_row_column", "Increase luminaire count to raise minimum/average illuminance.", add_diff))

    mount_delta = 0.2 if glare_risk else (-0.2 if wants_more_light else -0.1)
    mount_diff = _mounting_adjust_diff(project, delta_z=mount_delta)
    proposals.append(("mounting_adjust", "Raise/lower mounting height to rebalance glare and workplane lux.", mount_diff))

    flux_factor = 0.9 if glare_risk else (1.1 if wants_more_light else 1.0)
    dimming_diff = _flux_adjust_diff(project, factor=flux_factor)
    proposals.append(("dimming_changes", "Adjust luminaire output using flux multiplier tuning.", dimming_diff))
    return [(name, reason, diff) for name, reason, diff in proposals if diff.ops]


def _spacing_tweak_diff(project, shrink: float) -> ProjectDiff:
    xs = [float(l.transform.position[0]) for l in project.luminaires]
    ys = [float(l.transform.position[1]) for l in project.luminaires]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    ops: List[DiffOp] = []
    for lum in project.luminaires:
        x, y, z = lum.transform.position
        nx = cx + (x - cx) * shrink
        ny = cy + (y - cy) * shrink
        updated = deepcopy(lum.transform)
        updated.position = (float(nx), float(ny), float(z))
        ops.append(DiffOp(op="update", kind="luminaire", id=lum.id, payload={"transform": updated}))
    return ProjectDiff(ops=ops)


def _estimate_spacing(project) -> float:
    xs = sorted(float(l.transform.position[0]) for l in project.luminaires)
    if len(xs) <= 1:
        return 0.8
    span = xs[-1] - xs[0]
    return max(0.4, span / max(1, len(xs) - 1))


def _add_row_column_diff(project) -> ProjectDiff:
    step = _estimate_spacing(project) * 0.7
    ops: List[DiffOp] = []
    for lum in project.luminaires:
        clone = deepcopy(lum)
        clone.id = f"{lum.id}_add_{uuid.uuid4().hex[:8]}"
        x, y, z = clone.transform.position
        clone.transform.position = (float(x + step), float(y), float(z))
        ops.append(DiffOp(op="add", kind="luminaire", id=clone.id, payload=clone))
    return ProjectDiff(ops=ops)


def _mounting_adjust_diff(project, delta_z: float) -> ProjectDiff:
    ops: List[DiffOp] = []
    for lum in project.luminaires:
        x, y, z = lum.transform.position
        updated = deepcopy(lum.transform)
        updated.position = (float(x), float(y), float(max(0.1, z + delta_z)))
        payload = {"transform": updated}
        if lum.mounting_height_m is not None:
            payload["mounting_height_m"] = float(max(0.1, lum.mounting_height_m + delta_z))
        ops.append(DiffOp(op="update", kind="luminaire", id=lum.id, payload=payload))
    return ProjectDiff(ops=ops)


def _flux_adjust_diff(project, factor: float) -> ProjectDiff:
    if abs(factor - 1.0) < 1e-9:
        return ProjectDiff()
    ops: List[DiffOp] = []
    for lum in project.luminaires:
        new_flux = max(0.05, min(5.0, float(lum.flux_multiplier) * factor))
        ops.append(DiffOp(op="update", kind="luminaire", id=lum.id, payload={"flux_multiplier": new_flux}))
    return ProjectDiff(ops=ops)


def _build_variant_diff(project, candidate_diff: ProjectDiff, variant_name: Optional[str] = None) -> ProjectDiff:
    existing = {v.id for v in project.variants}
    idx = 1
    vid = f"variant_compliance_{idx}"
    while vid in existing:
        idx += 1
        vid = f"variant_compliance_{idx}"
    vname = variant_name or f"Compliance Variant {idx}"
    variant = ProjectVariant(
        id=vid,
        name=vname,
        description="Proposed by compliance skill",
        diff_ops=[
            {"op": op.op, "kind": op.kind, "id": op.id, "payload": dict(op.payload)}
            for op in candidate_diff.ops
        ],
    )
    return ProjectDiff(ops=[DiffOp(op="add", kind="variant", id=variant.id, payload=variant)])
