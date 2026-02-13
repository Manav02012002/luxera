from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from luxera.agent.audit import append_audit_event
from luxera.agent.summarize import summarize_project
from luxera.core.hashing import sha256_file
from luxera.design.placement import place_array_rect
from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.ops.base import OpContext
from luxera.ops.scene_ops import assign_material_to_surface_set, create_room as create_room_op, extrude_room_to_surfaces
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, RotationSpec, TransformSpec
from luxera.project.diff import ProjectDiff
from luxera.project.diff import DiffOp
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.history import push_snapshot, undo as undo_project_history, redo as redo_project_history
from luxera.project.validator import validate_project_for_job, ProjectValidationError
from luxera.gui.commands import (
    cmd_apply_diff,
    cmd_add_daylight_job,
    cmd_add_emergency_job,
    cmd_add_variant,
    cmd_add_escape_route,
    cmd_add_workplane_grid,
    cmd_detect_rooms,
    cmd_export_backend_compare,
    cmd_export_client_bundle,
    cmd_export_audit_bundle,
    cmd_export_roadway_report,
    cmd_compare_variants,
    cmd_export_report,
    cmd_clean_geometry,
    cmd_import_ifc,
    cmd_import_geometry,
    cmd_mark_opening_as_aperture,
    cmd_propose_layout,
    cmd_render_heatmap,
    cmd_run_job,
    cmd_summarize_results,
    cmd_optimize_search,
    cmd_optimize_candidates,
)
from luxera.runner import RunnerError


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

    def __init__(self):
        self._current_project_path: Optional[Path] = None

    @staticmethod
    def _agent_ctx(approved: bool) -> OpContext:
        return OpContext(user="agent", source="agent", require_approval=True, approved=bool(approved))

    def open_project(self, project_path: str):
        p = Path(project_path).expanduser().resolve()
        project = load_project_schema(p)
        self._current_project_path = p
        return project, p

    def save_project(self, project, project_path: Path) -> ToolResult:
        save_project_schema(project, project_path)
        return ToolResult(ok=True, message="Project saved", data={"project_path": str(project_path)})

    def save_session_artifact(self, project, runtime_id: str, payload: Dict[str, Any]) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Session artifact requires an opened project path context")
        root = self._current_project_path.parent / ".luxera" / "agent_sessions"
        root.mkdir(parents=True, exist_ok=True)
        out = root / f"{runtime_id}.json"
        with out.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        append_audit_event(
            project,
            action="agent.tools.save_session_artifact",
            plan="Persist deterministic runtime session payload for replay/audit.",
            artifacts=[str(out)],
            metadata={"runtime_id": runtime_id},
        )
        return ToolResult(ok=True, message="Session artifact saved", data={"path": str(out)})

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
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Layout proposal requires an opened project path context")
        diff = cmd_propose_layout(str(self._current_project_path), target_lux=target_lux, constraints=constraints or {})
        preview = [{"op": op.op, "kind": op.kind, "id": op.id} for op in diff.ops]
        return ToolResult(
            ok=True,
            message="Layout diff proposed",
            data={"diff": diff, "preview": {"ops": preview, "count": len(preview)}},
        )

    def optimize_layout_search(
        self,
        project,
        job_id: str,
        constraints: Optional[Dict[str, Any]] = None,
        max_rows: int = 6,
        max_cols: int = 6,
        top_n: int = 8,
    ) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Optimization requires an opened project path context")
        try:
            data = cmd_optimize_search(
                str(self._current_project_path),
                job_id,
                constraints={str(k): float(v) for k, v in (constraints or {}).items()} if constraints else None,
                max_rows=max_rows,
                max_cols=max_cols,
                top_n=top_n,
            )
        except Exception as e:
            return ToolResult(ok=False, message=f"Optimization failed: {e}")

        ops = [DiffOp(op="remove", kind="luminaire", id=l.id) for l in project.luminaires]
        for lum in data.get("best_layout", []):
            ops.append(DiffOp(op="add", kind="luminaire", id=lum.id, payload=lum))
        diff = ProjectDiff(ops=ops)
        preview = [{"op": op.op, "kind": op.kind, "id": op.id} for op in diff.ops]
        return ToolResult(
            ok=True,
            message="Optimization completed",
            data={
                "best": data.get("best", {}),
                "top": data.get("top", []),
                "artifact_json": data.get("artifact_json", ""),
                "diff": diff,
                "preview": {"ops": preview, "count": len(preview)},
            },
        )

    def optimize_layout_candidates(
        self,
        project,
        job_id: str,
        candidate_limit: int = 12,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Optimization requires an opened project path context")
        try:
            artifacts = cmd_optimize_candidates(
                str(self._current_project_path),
                job_id=job_id,
                candidate_limit=max(1, int(candidate_limit)),
                constraints={str(k): float(v) for k, v in (constraints or {}).items()} if constraints else None,
            )
        except Exception as e:
            return ToolResult(ok=False, message=f"Optimizer run failed: {e}")
        append_audit_event(
            project,
            action="agent.tools.optimize_layout_candidates",
            plan="Run deterministic optimizer candidate evaluation and emit ranked artifacts.",
            artifacts=[
                artifacts["candidates_csv"],
                artifacts["topk_csv"],
                artifacts["best_diff_json"],
                artifacts["optimizer_manifest_json"],
            ],
            metadata={"job_id": job_id, "candidate_limit": candidate_limit},
        )
        return ToolResult(
            ok=True,
            message="Optimizer completed",
            data={
                "candidates_csv": artifacts["candidates_csv"],
                "topk_csv": artifacts["topk_csv"],
                "best_diff_json": artifacts["best_diff_json"],
                "optimizer_manifest_json": artifacts["optimizer_manifest_json"],
            },
        )

    def apply_diff(self, project, diff: ProjectDiff, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="Apply diff requires explicit approval")
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Apply diff requires an opened project path context")
        before = len(project.agent_history)
        push_snapshot(project, label="assistant_apply_diff")
        save_project_schema(project, self._current_project_path)
        cmd_apply_diff(str(self._current_project_path), diff)
        loaded = load_project_schema(self._current_project_path)
        project.geometry = loaded.geometry
        project.materials = loaded.materials
        project.photometry_assets = loaded.photometry_assets
        project.luminaires = loaded.luminaires
        project.grids = loaded.grids
        project.jobs = loaded.jobs
        project.results = loaded.results
        append_audit_event(
            project,
            action="agent.tools.apply_diff",
            plan="Apply approved diff via tool API.",
            diffs=[{"ops": len(diff.ops)}],
        )
        return ToolResult(ok=True, message="Diff applied", data={"history_before": before, "history_after": len(project.agent_history)})

    def undo_assistant_change(self, project) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Undo requires an opened project path context")
        if not undo_project_history(project):
            return ToolResult(ok=False, message="No undo snapshot available")
        save_project_schema(project, self._current_project_path)
        return ToolResult(ok=True, message="Assistant change undone")

    def redo_assistant_change(self, project) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Redo requires an opened project path context")
        if not redo_project_history(project):
            return ToolResult(ok=False, message="No redo snapshot available")
        save_project_schema(project, self._current_project_path)
        return ToolResult(ok=True, message="Assistant change redone")

    def run_job(self, project, job_id: str, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="Run job requires explicit approval")
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Run job requires an opened project path context")
        try:
            ref = cmd_run_job(str(self._current_project_path), job_id)
            loaded = load_project_schema(self._current_project_path)
            project.results = loaded.results
        except RunnerError as e:
            return ToolResult(ok=False, message=str(e))
        return ToolResult(ok=True, message="Job completed", data={"job_id": ref.job_id, "job_hash": ref.job_hash, "result_dir": ref.result_dir})

    def export_debug_bundle(self, project, job_id: str, out_zip: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Export requires an opened project path context")
        try:
            out = cmd_export_audit_bundle(str(self._current_project_path), job_id, out_path=out_zip)
        except Exception as e:
            return ToolResult(ok=False, message=f"Debug bundle export failed: {e}")
        ref = next((r for r in project.results if r.job_id == job_id), None)
        job_hashes = [ref.job_hash] if ref is not None else []
        append_audit_event(
            project,
            action="agent.tools.export_debug_bundle",
            plan="Export audit bundle via tool API.",
            artifacts=[str(out)],
            job_hashes=job_hashes,
        )
        return ToolResult(ok=True, message="Debug bundle exported", data={"path": str(out)})

    def export_client_bundle(self, project, job_id: str, out_zip: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Export requires an opened project path context")
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = cmd_export_client_bundle(str(self._current_project_path), job_id, out_path=out_zip)
        append_audit_event(
            project,
            action="agent.tools.export_client_bundle",
            plan="Export client bundle via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Client bundle exported", data={"path": str(out)})

    def export_backend_compare(self, project, job_id: str, out_html: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Export requires an opened project path context")
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = cmd_export_backend_compare(str(self._current_project_path), job_id, out_path=out_html)
        append_audit_event(
            project,
            action="agent.tools.export_backend_compare",
            plan="Export backend comparison report via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Backend comparison exported", data={"path": str(out)})

    def export_roadway_report(self, project, job_id: str, out_html: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Export requires an opened project path context")
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        out = cmd_export_roadway_report(str(self._current_project_path), job_id, out_path=out_html)
        append_audit_event(
            project,
            action="agent.tools.export_roadway_report",
            plan="Export roadway HTML report from result artifacts.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash],
        )
        return ToolResult(ok=True, message="Roadway report exported", data={"path": str(out)})

    def import_geometry(self, project, file_path: str, fmt: Optional[str] = None) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Geometry import requires an opened project path context")
        try:
            save_project_schema(project, self._current_project_path)
            diff = cmd_import_geometry(str(self._current_project_path), file_path, fmt=fmt)
            before_rooms = len(project.geometry.rooms)
            before_surfs = len(project.geometry.surfaces)
            diff.apply(project)
            added_rooms = max(0, len(project.geometry.rooms) - before_rooms)
            added_surfs = max(0, len(project.geometry.surfaces) - before_surfs)
        except Exception as e:
            return ToolResult(ok=False, message=f"Geometry import failed: {e}")
        append_audit_event(
            project,
            action="agent.tools.import_geometry",
            plan="Import external geometry into project schema.",
            metadata={"file": file_path, "format": fmt or "AUTO", "rooms": added_rooms, "surfaces": added_surfs},
        )
        return ToolResult(ok=True, message="Geometry imported", data={"rooms_added": added_rooms, "surfaces_added": added_surfs, "warnings": []})

    def import_ifc(self, project, file_path: str, options: Optional[Dict[str, Any]] = None) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="IFC import requires an opened project path context")
        try:
            save_project_schema(project, self._current_project_path)
            diff = cmd_import_ifc(str(self._current_project_path), file_path, options=options or {})
            before_rooms = len(project.geometry.rooms)
            before_surfs = len(project.geometry.surfaces)
            before_openings = len(project.geometry.openings)
            diff.apply(project)
            added_rooms = max(0, len(project.geometry.rooms) - before_rooms)
            added_surfs = max(0, len(project.geometry.surfaces) - before_surfs)
            added_openings = max(0, len(project.geometry.openings) - before_openings)
        except Exception as e:
            return ToolResult(ok=False, message=f"IFC import failed: {e}")
        append_audit_event(
            project,
            action="agent.tools.import_ifc",
            plan="Import IFC geometry/spaces/openings into project schema.",
            metadata={"file": file_path, "rooms": added_rooms, "surfaces": added_surfs, "openings": added_openings, "options": options or {}},
        )
        return ToolResult(
            ok=True,
            message="IFC imported",
            data={"rooms_added": added_rooms, "surfaces_added": added_surfs, "openings_added": added_openings},
        )

    def clean_geometry(self, project, detect_rooms: bool = True) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Geometry clean requires an opened project path context")
        out = cmd_clean_geometry(str(self._current_project_path))
        cleaned = out.get("cleaned_surfaces", [])
        report = out.get("report", {})
        project.geometry.surfaces = list(cleaned)
        detected = 0
        if detect_rooms:
            save_project_schema(project, self._current_project_path)
            diff = cmd_detect_rooms(str(self._current_project_path))
            before = len(project.geometry.rooms)
            diff.apply(project)
            detected = max(0, len(project.geometry.rooms) - before)
        append_audit_event(
            project,
            action="agent.tools.clean_geometry",
            plan="Clean geometry topology and optionally detect rooms.",
            metadata={"report": report, "rooms_detected": detected},
            warnings=(report.get("warnings", []) if isinstance(report, dict) else []),
        )
        return ToolResult(ok=True, message="Geometry cleaned", data={"rooms_detected": detected, "report": report})

    def add_grid(self, project, name: str, width: float, height: float, elevation: float, nx: int, ny: int) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Add grid requires an opened project path context")
        if not project.geometry.rooms:
            return ToolResult(ok=False, message="Add grid requires at least one room")
        room = project.geometry.rooms[0]
        save_project_schema(project, self._current_project_path)
        spacing = max(width / max(nx - 1, 1), height / max(ny - 1, 1))
        diff = cmd_add_workplane_grid(str(self._current_project_path), room.id, height=max(0.0, elevation - room.origin[2]), spacing=spacing, margins=0.0)
        diff.apply(project)
        gid = diff.ops[0].id if diff.ops else f"grid_{len(project.grids)}"
        append_audit_event(project, action="agent.tools.add_grid", plan="Add calculation grid via tool API.", metadata={"grid_id": gid})
        return ToolResult(ok=True, message="Grid added", data={"grid_id": gid})

    def add_daylight_job(
        self,
        project,
        targets: List[str],
        mode: str = "df",
        sky: str = "CIE_overcast",
        e0: Optional[float] = 10000.0,
        vt: float = 0.70,
    ) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Add daylight job requires an opened project path context")
        save_project_schema(project, self._current_project_path)
        diff = cmd_add_daylight_job(str(self._current_project_path), targets=targets, mode=mode, sky=sky, e0=e0, vt=vt)
        diff.apply(project)
        jid = diff.ops[0].id if diff.ops else ""
        append_audit_event(
            project,
            action="agent.tools.add_daylight_job",
            plan="Add daylight job via command layer.",
            metadata={"job_id": jid, "targets": targets, "mode": mode, "sky": sky},
        )
        return ToolResult(ok=True, message="Daylight job added", data={"job_id": jid})

    def set_daylight_aperture(self, project, opening_id: str, vt: Optional[float] = None) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Set daylight aperture requires an opened project path context")
        save_project_schema(project, self._current_project_path)
        try:
            diff = cmd_mark_opening_as_aperture(str(self._current_project_path), opening_id=opening_id, vt=vt)
        except Exception as e:
            return ToolResult(ok=False, message=f"Set daylight aperture failed: {e}")
        diff.apply(project)
        append_audit_event(
            project,
            action="agent.tools.set_daylight_aperture",
            plan="Mark geometry opening as daylight aperture via command layer.",
            metadata={"opening_id": opening_id, "visible_transmittance": vt},
        )
        return ToolResult(ok=True, message="Daylight aperture updated", data={"opening_id": opening_id})

    def add_escape_route(
        self,
        project,
        route_id: str,
        polyline: List[tuple[float, float, float]],
        width_m: float = 1.0,
        spacing_m: float = 0.5,
        height_m: float = 0.0,
        end_margin_m: float = 0.0,
    ) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Add escape route requires an opened project path context")
        save_project_schema(project, self._current_project_path)
        diff = cmd_add_escape_route(
            str(self._current_project_path),
            route_id=route_id,
            polyline=polyline,
            width_m=width_m,
            spacing_m=spacing_m,
            height_m=height_m,
            end_margin_m=end_margin_m,
            name=route_id,
        )
        diff.apply(project)
        rid = diff.ops[0].id if diff.ops else route_id
        append_audit_event(
            project,
            action="agent.tools.add_escape_route",
            plan="Add emergency escape route via command layer.",
            metadata={"route_id": rid, "point_count": len(polyline), "width_m": width_m, "spacing_m": spacing_m},
        )
        return ToolResult(ok=True, message="Escape route added", data={"route_id": rid})

    def add_emergency_job(
        self,
        project,
        routes: List[str],
        open_area_targets: List[str],
        standard: str = "EN1838",
        route_min_lux: float = 1.0,
        route_u0_min: float = 0.1,
        open_area_min_lux: float = 0.5,
        open_area_u0_min: float = 0.1,
        emergency_factor: float = 1.0,
    ) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Add emergency job requires an opened project path context")
        save_project_schema(project, self._current_project_path)
        diff = cmd_add_emergency_job(
            str(self._current_project_path),
            routes=routes,
            open_area_targets=open_area_targets,
            standard=standard,
            route_min_lux=route_min_lux,
            route_u0_min=route_u0_min,
            open_area_min_lux=open_area_min_lux,
            open_area_u0_min=open_area_u0_min,
            emergency_factor=emergency_factor,
        )
        diff.apply(project)
        jid = diff.ops[0].id if diff.ops else ""
        append_audit_event(
            project,
            action="agent.tools.add_emergency_job",
            plan="Add emergency job via command layer.",
            metadata={"job_id": jid, "routes": routes, "open_area_targets": open_area_targets, "standard": standard},
        )
        return ToolResult(ok=True, message="Emergency job added", data={"job_id": jid})

    def add_variant(
        self,
        project,
        variant_id: str,
        name: str,
        description: str = "",
        diff_ops: Optional[List[Dict[str, Any]]] = None,
    ) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Add variant requires an opened project path context")
        save_project_schema(project, self._current_project_path)
        diff = cmd_add_variant(
            str(self._current_project_path),
            variant_id=variant_id,
            name=name,
            description=description,
            diff_ops=diff_ops or [],
        )
        diff.apply(project)
        vid = diff.ops[0].id if diff.ops else variant_id
        append_audit_event(
            project,
            action="agent.tools.add_variant",
            plan="Add project variant via command layer.",
            metadata={"variant_id": vid, "name": name, "ops": len(diff_ops or [])},
        )
        return ToolResult(ok=True, message="Variant added", data={"variant_id": vid})

    def compare_variants(self, project, job_id: str, variant_ids: List[str], baseline_variant_id: Optional[str] = None) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Variant compare requires an opened project path context")
        try:
            data = cmd_compare_variants(
                str(self._current_project_path),
                job_id=job_id,
                variant_ids=variant_ids,
                baseline_variant_id=baseline_variant_id,
            )
        except Exception as e:
            return ToolResult(ok=False, message=f"Variant compare failed: {e}")
        append_audit_event(
            project,
            action="agent.tools.compare_variants",
            plan="Run selected variants for a job and export comparison artifacts.",
            artifacts=[str(data.get("compare_json", "")), str(data.get("compare_csv", ""))],
            metadata={"job_id": job_id, "variant_ids": list(variant_ids), "baseline_variant_id": baseline_variant_id},
        )
        return ToolResult(ok=True, message="Variants compared", data=data if isinstance(data, dict) else {})

    def add_job(self, project, job_id: str, job_type: str = "direct", backend: str = "cpu", settings: Optional[Dict[str, Any]] = None) -> ToolResult:
        if any(j.id == job_id for j in project.jobs):
            return ToolResult(ok=False, message=f"Job already exists: {job_id}")
        job = JobSpec(id=job_id, type=job_type, backend=backend, settings=settings or {})
        project.jobs.append(job)
        append_audit_event(project, action="agent.tools.add_job", plan="Add job via tool API.", metadata={"job_id": job_id, "type": job_type, "backend": backend})
        return ToolResult(ok=True, message="Job added", data={"job_id": job_id})

    def summarize_results(self, project, job_id: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Result summary requires an opened project path context")
        try:
            data = cmd_summarize_results(str(self._current_project_path), job_id)
        except Exception as e:
            return ToolResult(ok=False, message=f"Result summary failed: {e}")
        return ToolResult(ok=True, message="Result summary", data=data)

    def render_heatmap(self, project, job_id: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="Heatmap render requires an opened project path context")
        ref = next((r for r in project.results if r.job_id == job_id), None)
        if ref is None:
            return ToolResult(ok=False, message=f"Result not found for job: {job_id}")
        try:
            data = cmd_render_heatmap(str(self._current_project_path), job_id)
        except Exception as e:
            return ToolResult(ok=False, message=f"Heatmap render failed: {e}")
        artifacts = data.get("artifacts", {}) if isinstance(data, dict) else {}
        append_audit_event(
            project,
            action="agent.tools.render_heatmap",
            plan="Render heatmap/isolux artifacts from existing result.",
            artifacts=[str(v) for v in artifacts.values()] if isinstance(artifacts, dict) else [],
            job_hashes=[ref.job_hash],
            metadata={"job_id": job_id},
        )
        return ToolResult(ok=True, message="Heatmap rendered", data=data if isinstance(data, dict) else {})

    def build_pdf(self, project, job_id: str, report_type: str, out_path: str) -> ToolResult:
        if self._current_project_path is None:
            return ToolResult(ok=False, message="PDF build requires an opened project path context")
        out = Path(out_path).expanduser().resolve()
        try:
            generated = cmd_export_report(str(self._current_project_path), job_id, report_type, out_path=str(out))
        except Exception as e:
            return ToolResult(ok=False, message=f"PDF build failed: {e}")
        ref = next((r for r in project.results if r.job_id == job_id), None)
        append_audit_event(
            project,
            action="agent.tools.build_pdf",
            plan="Build standards PDF report via tool API.",
            artifacts=[str(out)],
            job_hashes=[ref.job_hash] if ref is not None else [],
            metadata={"job_id": job_id, "report_type": report_type},
        )
        return ToolResult(ok=True, message="PDF report built", data={"path": str(generated), "report_type": report_type})

    # ----- M8 strict tools -----
    def summarize_project_context(self, project) -> ToolResult:
        ctx = summarize_project(project)
        return ToolResult(ok=True, message="Project summarized", data={"summary": ctx.to_dict()})

    def create_room(self, project, room_id: str, name: str, width: float, length: float, height: float, origin: tuple[float, float, float] = (0.0, 0.0, 0.0), approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="create_room requires explicit approval")
        if any(r.id == room_id for r in project.geometry.rooms):
            return ToolResult(ok=False, message=f"Room already exists: {room_id}")
        ctx = self._agent_ctx(approved=approved)
        room = create_room_op(project, room_id=room_id, name=name, width=width, length=length, height=height, origin=origin, ctx=ctx)
        extrude_room_to_surfaces(project, room.id, replace_existing=False, ctx=ctx)
        append_audit_event(project, action="agent.tools.create_room", plan="Create room and derive default room surfaces.", metadata={"room_id": room.id, "name": room.name})
        return ToolResult(ok=True, message="Room created", data={"room_id": room.id})

    def edit_room(self, project, room_id: str, updates: Dict[str, Any], approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="edit_room requires explicit approval")
        room = next((r for r in project.geometry.rooms if r.id == room_id), None)
        if room is None:
            return ToolResult(ok=False, message=f"Room not found: {room_id}")
        allowed = {"name", "width", "length", "height", "origin"}
        applied: Dict[str, Any] = {}
        for k, v in updates.items():
            if k not in allowed:
                continue
            setattr(room, k, v)
            applied[k] = v
        append_audit_event(project, action="agent.tools.edit_room", plan="Edit room dimensions/properties.", metadata={"room_id": room_id, "updates": applied})
        return ToolResult(ok=True, message="Room updated", data={"room_id": room_id, "updated_fields": sorted(applied.keys())})

    def assign_material(self, project, material_id: str, surface_ids: List[str], approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="assign_material requires explicit approval")
        try:
            count = assign_material_to_surface_set(project, surface_ids=surface_ids, material_id=material_id, ctx=self._agent_ctx(approved=approved))
        except Exception as e:
            return ToolResult(ok=False, message=f"Assign material failed: {e}")
        append_audit_event(project, action="agent.tools.assign_material", plan="Assign material to selected surfaces.", metadata={"material_id": material_id, "count": count})
        return ToolResult(ok=True, message="Material assigned", data={"material_id": material_id, "count": count})

    def place_luminaire(self, project, luminaire_id: str, name: str, asset_id: str, position: tuple[float, float, float], yaw_deg: float = 0.0, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="place_luminaire requires explicit approval")
        if any(l.id == luminaire_id for l in project.luminaires):
            return ToolResult(ok=False, message=f"Luminaire already exists: {luminaire_id}")
        if not any(a.id == asset_id for a in project.photometry_assets):
            return ToolResult(ok=False, message=f"Photometry asset not found: {asset_id}")
        tr = TransformSpec(position=position, rotation=RotationSpec(type="euler_zyx", euler_deg=(float(yaw_deg), 0.0, 0.0)))
        lum = LuminaireInstance(id=luminaire_id, name=name, photometry_asset_id=asset_id, transform=tr)
        project.luminaires.append(lum)
        append_audit_event(project, action="agent.tools.place_luminaire", plan="Place single luminaire instance.", metadata={"luminaire_id": luminaire_id, "asset_id": asset_id})
        return ToolResult(ok=True, message="Luminaire placed", data={"luminaire_id": luminaire_id})

    def array_luminaires(
        self,
        project,
        room_id: str,
        asset_id: str,
        rows: int,
        cols: int,
        margin_m: float = 0.5,
        mount_height_m: float = 2.8,
        approved: bool = False,
    ) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="array_luminaires requires explicit approval")
        room = next((r for r in project.geometry.rooms if r.id == room_id), None)
        if room is None:
            return ToolResult(ok=False, message=f"Room not found: {room_id}")
        arr = place_array_rect(
            room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
            nx=max(1, int(cols)),
            ny=max(1, int(rows)),
            margin_x=float(margin_m),
            margin_y=float(margin_m),
            z=float(room.origin[2] + mount_height_m),
            photometry_asset_id=asset_id,
        )
        project.luminaires = list(arr)
        append_audit_event(project, action="agent.tools.array_luminaires", plan="Place luminaire array inside room bounds.", metadata={"room_id": room_id, "rows": rows, "cols": cols, "count": len(arr)})
        return ToolResult(ok=True, message="Luminaire array placed", data={"count": len(arr)})

    def aim_luminaire(self, project, luminaire_id: str, yaw_deg: float, approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="aim_luminaire requires explicit approval")
        lum = next((l for l in project.luminaires if l.id == luminaire_id), None)
        if lum is None:
            return ToolResult(ok=False, message=f"Luminaire not found: {luminaire_id}")
        lum.transform.rotation = RotationSpec(type="euler_zyx", euler_deg=(float(yaw_deg), 0.0, 0.0))
        append_audit_event(project, action="agent.tools.aim_luminaire", plan="Update luminaire aim (yaw only).", metadata={"luminaire_id": luminaire_id, "yaw_deg": yaw_deg})
        return ToolResult(ok=True, message="Luminaire aimed", data={"luminaire_id": luminaire_id, "yaw_deg": float(yaw_deg)})

    def create_grid(
        self,
        project,
        grid_id: str,
        name: str,
        room_id: str,
        elevation_m: float = 0.8,
        spacing_m: float = 0.25,
        margin_m: float = 0.0,
        approved: bool = False,
    ) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="create_grid requires explicit approval")
        if any(g.id == grid_id for g in project.grids):
            return ToolResult(ok=False, message=f"Grid already exists: {grid_id}")
        grid = create_calc_grid_from_room(
            project,
            grid_id=grid_id,
            name=name,
            room_id=room_id,
            elevation=float(elevation_m),
            spacing=max(float(spacing_m), 0.05),
            margin=max(float(margin_m), 0.0),
            ctx=self._agent_ctx(approved=approved),
        )
        append_audit_event(project, action="agent.tools.create_grid", plan="Create room-aligned workplane grid.", metadata={"grid_id": grid.id, "room_id": room_id})
        return ToolResult(ok=True, message="Grid created", data={"grid_id": grid.id})

    def update_grid(self, project, grid_id: str, updates: Dict[str, Any], approved: bool = False) -> ToolResult:
        if not approved:
            return ToolResult(ok=False, requires_approval=True, message="update_grid requires explicit approval")
        grid = next((g for g in project.grids if g.id == grid_id), None)
        if grid is None:
            return ToolResult(ok=False, message=f"Grid not found: {grid_id}")
        for key, value in updates.items():
            if hasattr(grid, key):
                setattr(grid, key, value)
        append_audit_event(project, action="agent.tools.update_grid", plan="Update existing calc grid.", metadata={"grid_id": grid_id, "updates": updates})
        return ToolResult(ok=True, message="Grid updated", data={"grid_id": grid_id, "updated_fields": sorted(updates.keys())})

    def run_calc(self, project, job_id: str, approved: bool = False) -> ToolResult:
        return self.run_job(project, job_id=job_id, approved=approved)

    def generate_report(self, project, job_id: str, out_path: str, report_type: str = "auto") -> ToolResult:
        return self.build_pdf(project, job_id=job_id, report_type=report_type, out_path=out_path)

    def compare_to_target(self, project, job_id: str, thresholds: Optional[Dict[str, float]] = None) -> ToolResult:
        thresholds = dict(thresholds or {})
        summary = next((r.summary for r in project.results if r.job_id == job_id), None)
        if summary is None:
            return ToolResult(ok=False, message=f"No result summary for job: {job_id}")
        checks: Dict[str, Dict[str, Any]] = {}
        for key, threshold in thresholds.items():
            actual = summary.get(key)
            if isinstance(actual, (int, float)):
                checks[key] = {"actual": float(actual), "threshold": float(threshold), "pass": float(actual) >= float(threshold)}
        return ToolResult(ok=True, message="Compared result against targets", data={"job_id": job_id, "checks": checks})

    def propose_optimizations(self, project, job_id: str, constraints: Optional[Dict[str, Any]] = None, top_n: int = 5) -> ToolResult:
        result = self.optimize_layout_search(
            project,
            job_id=job_id,
            constraints=constraints or {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0},
            max_rows=6,
            max_cols=6,
            top_n=max(3, min(int(top_n), 5)),
        )
        if not result.ok:
            return result
        options = result.data.get("top", [])[: max(3, min(int(top_n), 5))]
        normalized: List[Dict[str, Any]] = []
        for idx, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            normalized.append(
                {
                    "index": idx,
                    "rows": int(option.get("rows", 1)),
                    "cols": int(option.get("cols", 1)),
                    "dimming": float(option.get("dimming", 1.0)),
                    "score": float(option.get("score", 0.0)),
                    "mean_lux": float(option.get("mean_lux", 0.0)),
                    "uniformity_ratio": float(option.get("uniformity_ratio", 0.0)),
                    "ugr_worst_case": option.get("ugr_worst_case"),
                }
            )
        return ToolResult(ok=True, message="Optimization options proposed", data={"job_id": job_id, "options": normalized, "preview": result.data.get("preview", {})})

    def optimization_option_diff(self, project, option: Dict[str, Any]) -> ToolResult:
        if not project.geometry.rooms:
            return ToolResult(ok=False, message="Option diff requires at least one room")
        if not project.photometry_assets:
            return ToolResult(ok=False, message="Option diff requires at least one photometry asset")
        room = project.geometry.rooms[0]
        asset_id = project.photometry_assets[0].id
        rows = max(1, int(option.get("rows", 1)))
        cols = max(1, int(option.get("cols", 1)))
        dimming = max(0.0, float(option.get("dimming", 1.0)))
        arr = place_array_rect(
            room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
            nx=cols,
            ny=rows,
            margin_x=room.width * 0.1,
            margin_y=room.length * 0.1,
            z=room.origin[2] + room.height * 0.9,
            photometry_asset_id=asset_id,
        )
        for lum in arr:
            lum.flux_multiplier = dimming
        ops: List[DiffOp] = [DiffOp(op="remove", kind="luminaire", id=l.id) for l in project.luminaires]
        ops.extend(DiffOp(op="add", kind="luminaire", id=l.id, payload=l) for l in arr)
        diff = ProjectDiff(ops=ops)
        preview = [{"op": op.op, "kind": op.kind, "id": op.id} for op in diff.ops]
        return ToolResult(ok=True, message="Option diff generated", data={"diff": diff, "preview": {"ops": preview, "count": len(preview)}})
