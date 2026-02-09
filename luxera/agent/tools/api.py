from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from luxera.agent.audit import append_audit_event
from luxera.ai.assistant import propose_luminaire_layout
from luxera.core.hashing import sha256_file
from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.export.en12464_report import build_en12464_report_model
from luxera.export.en13032_pdf import render_en13032_pdf
from luxera.export.roadway_report import render_roadway_report_html
from luxera.geometry.scene_prep import clean_scene_surfaces, detect_room_volumes_from_surfaces
from luxera.io.geometry_import import import_geometry_file
from luxera.project.schema import CalcGrid, JobSpec
from luxera.export.backend_comparison import render_backend_comparison_html
from luxera.export.client_bundle import export_client_bundle
from luxera.export.debug_bundle import export_debug_bundle
from luxera.project.diff import ProjectDiff
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.validator import validate_project_for_job, ProjectValidationError
from luxera.results.grid_viz import write_grid_heatmap_and_isolux
from luxera.runner import run_job, RunnerError


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    requires_approval: bool = False
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class AgentTools:
    """
    Strict tool surface for agent operations.
    """

    def open_project(self, project_path: str):
        p = Path(project_path).expanduser().resolve()
        project = load_project_schema(p)
        return project, p

    def save_project(self, project, project_path: Path) -> ToolResult:
        save_project_schema(project, project_path)
        return ToolResult(ok=True, message="Project saved", data={"project_path": str(project_path)})

    def add_asset(self, project, file_path: str, asset_id: Optional[str] = None) -> ToolResult:
        p = Path(file_path).expanduser()
        if not p.exists():
            return ToolResult(ok=False, message=f"Asset file not found: {file_path}")
        suffix = p.suffix.lower()
        if suffix not in (".ies", ".ldt"):
            return ToolResult(ok=False, message=f"Unsupported asset format: {p.suffix}")
        aid = asset_id or p.stem
        if any(a.id == aid for a in project.photometry_assets):
            return ToolResult(ok=False, message=f"Asset id already exists: {aid}")
        fmt = "IES" if suffix == ".ies" else "LDT"
        content_hash = sha256_file(str(p))
        from luxera.project.schema import PhotometryAsset  # local import to avoid cycle risk

        project.photometry_assets.append(
            PhotometryAsset(
                id=aid,
                format=fmt,
                path=str(p),
                content_hash=content_hash,
                metadata={"filename": p.name},
            )
        )
        append_audit_event(
            project,
            action="agent.tools.add_asset",
            plan="Add photometry asset via tool API.",
            metadata={"asset_id": aid, "path": str(p), "format": fmt, "hash": content_hash},
        )
        return ToolResult(ok=True, message="Asset added", data={"asset_id": aid, "hash": content_hash})

    def inspect_asset(self, project, asset_id: str) -> ToolResult:
        asset = next((a for a in project.photometry_assets if a.id == asset_id), None)
        if asset is None:
            return ToolResult(ok=False, message=f"Asset not found: {asset_id}")
        info = {
            "asset_id": asset.id,
            "format": asset.format,
            "path": asset.path,
            "content_hash": asset.content_hash,
            "metadata": asset.metadata or {},
        }
        return ToolResult(ok=True, message="Asset info", data=info)

    def hash_asset(self, project, asset_id: str) -> ToolResult:
        asset = next((a for a in project.photometry_assets if a.id == asset_id), None)
        if asset is None:
            return ToolResult(ok=False, message=f"Asset not found: {asset_id}")
        if not asset.path:
            return ToolResult(ok=False, message=f"Asset has no file path: {asset_id}")
        h = sha256_file(asset.path)
        asset.content_hash = h
        append_audit_event(
            project,
            action="agent.tools.hash_asset",
            plan="Hash photometry asset via tool API.",
            metadata={"asset_id": asset_id, "path": asset.path, "hash": h},
        )
        return ToolResult(ok=True, message="Asset hashed", data={"asset_id": asset_id, "hash": h})

    def validate_project(self, project, job_id: Optional[str] = None) -> ToolResult:
        try:
            if job_id is None:
                for j in project.jobs:
                    validate_project_for_job(project, j)
            else:
                job = next((j for j in project.jobs if j.id == job_id), None)
                if job is None:
                    return ToolResult(ok=False, message=f"Job not found: {job_id}")
                validate_project_for_job(project, job)
            return ToolResult(ok=True, message="Project validation passed")
        except ProjectValidationError as e:
            return ToolResult(ok=False, message=str(e))

    def diff_preview(self, diff: ProjectDiff) -> ToolResult:
        preview = [{"op": op.op, "kind": op.kind, "id": op.id} for op in diff.ops]
        return ToolResult(ok=True, message="Diff preview generated", data={"ops": preview, "count": len(preview)})

    def propose_layout_diff(self, project, target_lux: float, constraints: Optional[Dict[str, Any]] = None) -> ToolResult:
        diff = propose_luminaire_layout(project, target_lux, constraints=constraints or {})
        preview = [{"op": op.op, "kind": op.kind, "id": op.id} for op in diff.ops]
        return ToolResult(
            ok=True,
            message="Layout diff proposed",
            data={"diff": diff, "preview": {"ops": preview, "count": len(preview)}},
        )

    def apply_diff(self, project, diff: ProjectDiff, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="Apply diff requires explicit approval")
        before = len(project.agent_history)
        diff.apply(project)
        append_audit_event(
            project,
            action="agent.tools.apply_diff",
            plan="Apply approved diff via tool API.",
            diffs=[{"ops": len(diff.ops)}],
        )
        return ToolResult(ok=True, message="Diff applied", data={"history_before": before, "history_after": len(project.agent_history)})

    def run_job(self, project, job_id: str, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="Run job requires explicit approval")
        try:
            ref = run_job(project, job_id)
        except RunnerError as e:
            return ToolResult(ok=False, message=str(e))
        return ToolResult(ok=True, message="Job completed", data={"job_id": ref.job_id, "job_hash": ref.job_hash, "result_dir": ref.result_dir})

    def export_debug_bundle(self, project, job_id: str, out_zip: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = export_debug_bundle(project, ref, Path(out_zip))
        append_audit_event(
            project,
            action="agent.tools.export_debug_bundle",
            plan="Export audit bundle via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Debug bundle exported", data={"path": str(out)})

    def export_client_bundle(self, project, job_id: str, out_zip: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = export_client_bundle(project, ref, Path(out_zip))
        append_audit_event(
            project,
            action="agent.tools.export_client_bundle",
            plan="Export client bundle via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Client bundle exported", data={"path": str(out)})

    def export_backend_compare(self, project, job_id: str, out_html: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = render_backend_comparison_html(Path(ref.result_dir), Path(out_html))
        append_audit_event(
            project,
            action="agent.tools.export_backend_compare",
            plan="Export backend comparison report via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Backend comparison exported", data={"path": str(out)})

    def export_roadway_report(self, project, job_id: str, out_html: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = render_roadway_report_html(Path(ref.result_dir), Path(out_html))
        append_audit_event(
            project,
            action="agent.tools.export_roadway_report",
            plan="Export roadway HTML report from result artifacts.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Roadway report exported", data={"path": str(out)})

    def import_geometry(self, project, file_path: str, fmt: Optional[str] = None) -> ToolResult:
        try:
            res = import_geometry_file(file_path, fmt=fmt)
        except Exception as e:
            return ToolResult(ok=False, message=f"Geometry import failed: {e}")
        existing_rooms = {r.id for r in project.geometry.rooms}
        existing_surfs = {s.id for s in project.geometry.surfaces}
        added_rooms = 0
        added_surfs = 0
        for r in res.rooms:
            rid = r.id
            if rid in existing_rooms:
                rid = f"{rid}_import"
                r.id = rid
            project.geometry.rooms.append(r)
            existing_rooms.add(rid)
            added_rooms += 1
        for s in res.surfaces:
            sid = s.id
            if sid in existing_surfs:
                sid = f"{sid}_import"
                s.id = sid
            project.geometry.surfaces.append(s)
            existing_surfs.add(sid)
            added_surfs += 1
        append_audit_event(
            project,
            action="agent.tools.import_geometry",
            plan="Import external geometry into project schema.",
            metadata={"file": file_path, "format": res.format, "rooms": added_rooms, "surfaces": added_surfs},
            warnings=res.warnings,
        )
        return ToolResult(ok=True, message="Geometry imported", data={"rooms_added": added_rooms, "surfaces_added": added_surfs, "warnings": res.warnings})

    def clean_geometry(self, project, detect_rooms: bool = True) -> ToolResult:
        cleaned, report = clean_scene_surfaces(project.geometry.surfaces)
        project.geometry.surfaces = cleaned
        detected = 0
        if detect_rooms:
            existing = {r.id for r in project.geometry.rooms}
            for room in detect_room_volumes_from_surfaces(cleaned):
                if room.id not in existing:
                    project.geometry.rooms.append(room)
                    existing.add(room.id)
                    detected += 1
        append_audit_event(
            project,
            action="agent.tools.clean_geometry",
            plan="Clean geometry topology and optionally detect rooms.",
            metadata={"report": report.to_dict() if hasattr(report, "to_dict") else report.__dict__, "rooms_detected": detected},
            warnings=report.warnings,
        )
        return ToolResult(ok=True, message="Geometry cleaned", data={"rooms_detected": detected, "report": report.__dict__})

    def add_grid(self, project, name: str, width: float, height: float, elevation: float, nx: int, ny: int) -> ToolResult:
        gid = f"grid_{len(project.grids)+1}"
        grid = CalcGrid(
            id=gid,
            name=name,
            origin=(0.0, 0.0, 0.0),
            width=width,
            height=height,
            elevation=elevation,
            nx=nx,
            ny=ny,
        )
        if project.geometry.rooms:
            grid.room_id = project.geometry.rooms[0].id
        project.grids.append(grid)
        append_audit_event(project, action="agent.tools.add_grid", plan="Add calculation grid via tool API.", metadata={"grid_id": gid})
        return ToolResult(ok=True, message="Grid added", data={"grid_id": gid})

    def add_job(self, project, job_id: str, job_type: str = "direct", backend: str = "cpu", settings: Optional[Dict[str, Any]] = None) -> ToolResult:
        if any(j.id == job_id for j in project.jobs):
            return ToolResult(ok=False, message=f"Job already exists: {job_id}")
        job = JobSpec(id=job_id, type=job_type, backend=backend, settings=settings or {})
        project.jobs.append(job)
        append_audit_event(project, action="agent.tools.add_job", plan="Add job via tool API.", metadata={"job_id": job_id, "type": job_type, "backend": backend})
        return ToolResult(ok=True, message="Job added", data={"job_id": job_id})

    def summarize_results(self, project, job_id: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        return ToolResult(ok=True, message="Result summary", data={"job_id": ref.job_id, "job_hash": ref.job_hash, "summary": ref.summary})

    def render_heatmap(self, project, job_id: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        result_dir = Path(ref.result_dir)
        csv_path = result_dir / "grid.csv"
        meta_path = result_dir / "result.json"
        if not csv_path.exists():
            return ToolResult(ok=False, message="Result has no grid.csv for heatmap rendering")
        if not meta_path.exists():
            return ToolResult(ok=False, message="Result has no result.json")
        try:
            rows = np.loadtxt(csv_path, delimiter=",", skiprows=1)
            if rows.ndim == 1:
                rows = rows.reshape(1, -1)
            points = rows[:, 0:3]
            values = rows[:, 3]
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            job_meta = meta.get("job", {})
            nx = int(job_meta.get("settings", {}).get("grid_nx", 0))
            ny = int(job_meta.get("settings", {}).get("grid_ny", 0))
            if nx <= 0 or ny <= 0:
                grid = next((g for g in project.grids), None)
                if grid is not None:
                    nx, ny = int(grid.nx), int(grid.ny)
            if nx <= 0 or ny <= 0:
                return ToolResult(ok=False, message="Cannot determine grid resolution (nx, ny)")
            out = write_grid_heatmap_and_isolux(result_dir, points, values, nx=nx, ny=ny)
        except Exception as e:
            return ToolResult(ok=False, message=f"Heatmap render failed: {e}")
        append_audit_event(
            project,
            action="agent.tools.render_heatmap",
            plan="Render heatmap/isolux artifacts from existing result.",
            artifacts=[str(v) for v in out.values()],
            job_hashes=[ref.job_hash],
            metadata={"job_id": job_id},
        )
        return ToolResult(ok=True, message="Heatmap rendered", data={"artifacts": {k: str(v) for k, v in out.items()}})

    def build_pdf(self, project, job_id: str, report_type: str, out_path: str) -> ToolResult:
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = Path(out_path).expanduser().resolve()
        try:
            if report_type.lower() == "en12464":
                model = build_en12464_report_model(project, ref)
                render_en12464_pdf(model, out)
            elif report_type.lower() == "en13032":
                from luxera.export.report_model import build_en13032_report_model
                model = build_en13032_report_model(project, ref)
                render_en13032_pdf(model, out)
            else:
                return ToolResult(ok=False, message=f"Unsupported report type: {report_type}")
        except Exception as e:
            return ToolResult(ok=False, message=f"PDF build failed: {e}")
        append_audit_event(
            project,
            action="agent.tools.build_pdf",
            plan="Build standards PDF report via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
            metadata={"job_id": job_id, "report_type": report_type},
        )
        return ToolResult(ok=True, message="PDF report built", data={"path": str(out), "report_type": report_type})
