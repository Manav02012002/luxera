from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import List

from luxera.ai.assistant import propose_luminaire_layout
from luxera.design.placement import place_array_rect
from luxera.export.backend_comparison import render_backend_comparison_html
from luxera.export.client_bundle import export_client_bundle
from luxera.export.debug_bundle import export_debug_bundle
from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.export.en12464_report import build_en12464_report_model
from luxera.export.en13032_pdf import render_en13032_pdf
from luxera.export.pdf_report import build_project_pdf_report
from luxera.export.report_model import build_en13032_report_model
from luxera.export.roadway_report import render_roadway_report_html
from luxera.geometry.scene_prep import clean_scene_surfaces, detect_room_volumes_from_surfaces
from luxera.io.geometry_import import GeometryImportResult, import_geometry_file
from luxera.io.import_pipeline import run_import_pipeline
from luxera.project.diff import DiffOp, ProjectDiff
from luxera.project.io import load_project_schema
from luxera.project.schema import (
    DaylightSpec,
    EmergencyModeSpec,
    EmergencySpec,
    EscapeRouteSpec,
    JobResultRef,
    JobSpec,
    ProjectVariant,
)
from luxera.project.variants import run_job_for_variants
from luxera.results.grid_viz import write_grid_heatmap_and_isolux
from luxera.runner import run_job
import json
import numpy as np
from luxera.optim.search import run_deterministic_search
from luxera.optim.optimizer import run_optimizer
from luxera.ops.calc_ops import create_calc_grid_from_room


def _load(project_path: str):
    ppath = Path(project_path).expanduser().resolve()
    return load_project_schema(ppath), ppath


def _collection_for_kind(project, kind: str):
    if kind == "room":
        return project.geometry.rooms
    if kind == "surface":
        return project.geometry.surfaces
    if kind == "opening":
        return project.geometry.openings
    if kind == "obstruction":
        return project.geometry.obstructions
    if kind == "level":
        return project.geometry.levels
    if kind == "luminaire":
        return project.luminaires
    if kind == "grid":
        return project.grids
    if kind == "workplane":
        return project.workplanes
    if kind == "vertical_plane":
        return project.vertical_planes
    if kind == "arbitrary_plane":
        return project.arbitrary_planes
    if kind == "point_set":
        return project.point_sets
    if kind == "line_grid":
        return project.line_grids
    if kind == "roadway":
        return project.roadways
    if kind == "roadway_grid":
        return project.roadway_grids
    if kind == "escape_route":
        return project.escape_routes
    if kind == "job":
        return project.jobs
    if kind == "variant":
        return project.variants
    raise ValueError(f"Unsupported object kind: {kind}")


def _find_by_id(collection, object_id: str):
    for obj in collection:
        if getattr(obj, "id", None) == object_id:
            return obj
    return None


def _geometry_result_to_diff(project, res: GeometryImportResult) -> ProjectDiff:
    existing_room_ids = {r.id for r in project.geometry.rooms}
    existing_surf_ids = {s.id for s in project.geometry.surfaces}
    existing_opening_ids = {o.id for o in project.geometry.openings}
    existing_level_ids = {l.id for l in project.geometry.levels}
    existing_obstruction_ids = {o.id for o in project.geometry.obstructions}
    ops: List[DiffOp] = []
    for room in res.rooms:
        rid = room.id if room.id not in existing_room_ids else f"{room.id}_import"
        room.id = rid
        ops.append(DiffOp(op="add", kind="room", id=rid, payload=room))
    for surface in res.surfaces:
        sid = surface.id if surface.id not in existing_surf_ids else f"{surface.id}_import"
        surface.id = sid
        ops.append(DiffOp(op="add", kind="surface", id=sid, payload=surface))
    for opening in res.openings:
        oid = opening.id if opening.id not in existing_opening_ids else f"{opening.id}_import"
        opening.id = oid
        ops.append(DiffOp(op="add", kind="opening", id=oid, payload=opening))
    for lvl in res.levels:
        lid = lvl.id if lvl.id not in existing_level_ids else f"{lvl.id}_import"
        lvl.id = lid
        ops.append(DiffOp(op="add", kind="level", id=lid, payload=lvl))
    for obs in res.obstructions:
        oid = obs.id if obs.id not in existing_obstruction_ids else f"{obs.id}_import"
        obs.id = oid
        ops.append(DiffOp(op="add", kind="obstruction", id=oid, payload=obs))
    ops.append(
        DiffOp(
            op="update",
            kind="geometry_meta",
            id="geometry",
            payload={
                "length_unit": str(res.length_unit),
                "source_length_unit": str(getattr(res, "source_length_unit", res.length_unit)),
                "scale_to_meters": float(res.scale_to_meters),
                "axis_transform_applied": str(getattr(res, "axis_transform_applied", "Z_UP/RIGHT_HANDED->Z_UP/RIGHT_HANDED")),
            },
        )
    )
    return ProjectDiff(ops=ops)


def cmd_import_geometry(
    project_path: str,
    file_path: str,
    fmt: str | None = None,
    options: dict | None = None,
) -> ProjectDiff:
    project, _ = _load(project_path)
    opts = dict(options or {})
    pipeline = run_import_pipeline(
        file_path,
        fmt=fmt,
        dxf_scale=float(opts.get("dxf_scale", 1.0)),
        length_unit=opts.get("length_unit"),
        scale_to_meters=opts.get("scale_to_meters"),
        ifc_options=opts.get("ifc_options"),
        layer_overrides=opts.get("layer_overrides"),
    )
    if pipeline.geometry is None:
        raise ValueError(f"Import failed: {pipeline.report.to_dict()}")
    res = pipeline.geometry
    res = GeometryImportResult(
        source_file=res.source_file,
        format=res.format,
        length_unit=res.length_unit,
        source_length_unit=res.source_length_unit,
        scale_to_meters=res.scale_to_meters,
        axis_transform_applied=res.axis_transform_applied,
        axis_matrix=[list(row) for row in getattr(res, "axis_matrix", [])],
        rooms=res.rooms,
        surfaces=res.surfaces,
        openings=res.openings,
        obstructions=res.obstructions,
        levels=res.levels,
        warnings=list(res.warnings) + [f"pipeline_stage_count={len(pipeline.report.stages)}"],
        stage_report=pipeline.report.to_dict(),
        scene_health_report=dict(pipeline.report.scene_health),
        layer_map=dict(pipeline.report.layer_map),
    )
    return _geometry_result_to_diff(project, res)


def cmd_import_ifc(project_path: str, ifc_path: str, options: dict | None = None) -> ProjectDiff:
    project, _ = _load(project_path)
    opts = dict(options or {})
    pipeline = run_import_pipeline(
        ifc_path,
        fmt="IFC",
        length_unit=opts.get("length_unit_override"),
        scale_to_meters=opts.get("scale_to_meters_override"),
        ifc_options={
            "default_window_transmittance": opts.get("default_window_transmittance", 0.70),
            "fallback_room_size": opts.get("fallback_room_size", (5.0, 5.0, 3.0)),
            "source_up_axis": opts.get("source_up_axis", "Z_UP"),
            "source_handedness": opts.get("source_handedness", "RIGHT_HANDED"),
        },
    )
    if pipeline.geometry is None:
        raise ValueError(f"IFC import failed: {pipeline.report.to_dict()}")
    g = pipeline.geometry
    res = GeometryImportResult(
        source_file=g.source_file,
        format=g.format,
        length_unit=g.length_unit,
        source_length_unit=g.source_length_unit,
        scale_to_meters=g.scale_to_meters,
        axis_transform_applied=g.axis_transform_applied,
        axis_matrix=[list(row) for row in getattr(g, "axis_matrix", [])],
        rooms=g.rooms,
        surfaces=g.surfaces,
        openings=g.openings,
        obstructions=g.obstructions,
        levels=g.levels,
        warnings=list(g.warnings) + [f"pipeline_stage_count={len(pipeline.report.stages)}"],
        stage_report=pipeline.report.to_dict(),
        scene_health_report=dict(pipeline.report.scene_health),
        layer_map=dict(pipeline.report.layer_map),
    )
    return _geometry_result_to_diff(project, res)


def cmd_detect_rooms(project_path: str) -> ProjectDiff:
    project, _ = _load(project_path)
    cleaned, _ = clean_scene_surfaces(project.geometry.surfaces)
    detected = detect_room_volumes_from_surfaces(cleaned)
    existing = {r.id for r in project.geometry.rooms}
    ops: List[DiffOp] = []
    for room in detected:
        if room.id in existing:
            continue
        ops.append(DiffOp(op="add", kind="room", id=room.id, payload=room))
    return ProjectDiff(ops=ops)


def cmd_clean_geometry(project_path: str) -> dict:
    project, _ = _load(project_path)
    cleaned, report = clean_scene_surfaces(project.geometry.surfaces)
    return {
        "cleaned_surfaces": cleaned,
        "report": report.to_dict() if hasattr(report, "to_dict") else report.__dict__,
    }


def cmd_propose_layout(project_path: str, target_lux: float, constraints: dict | None = None) -> ProjectDiff:
    project, _ = _load(project_path)
    return propose_luminaire_layout(project, target_lux, constraints=constraints or {})


def cmd_add_daylight_job(
    project_path: str,
    targets: list[str],
    mode: str = "df",
    sky: str = "CIE_overcast",
    e0: float | None = 10000.0,
    vt: float = 0.70,
) -> ProjectDiff:
    project, _ = _load(project_path)
    job_id = "daylight_1"
    existing = {j.id for j in project.jobs}
    i = 1
    while job_id in existing:
        i += 1
        job_id = f"daylight_{i}"
    daylight = DaylightSpec(
        mode=("radiance" if str(mode).lower() == "radiance" else "df"),
        sky=str(sky),
        external_horizontal_illuminance_lux=float(e0) if e0 is not None else None,
        glass_visible_transmittance_default=float(vt),
    )
    backend = "radiance" if daylight.mode == "radiance" else "df"
    job = JobSpec(
        id=job_id,
        type="daylight",
        backend=backend,  # type: ignore[arg-type]
        settings={"mode": "daylight_factor"},
        daylight=daylight,
        targets=[str(t) for t in targets],
        seed=int(daylight.random_seed),
    )
    return ProjectDiff(ops=[DiffOp(op="add", kind="job", id=job.id, payload=job)])


def cmd_mark_opening_as_aperture(project_path: str, opening_id: str, vt: float | None = None) -> ProjectDiff:
    project, _ = _load(project_path)
    op = next((o for o in project.geometry.openings if o.id == opening_id), None)
    if op is None:
        raise ValueError(f"Opening not found: {opening_id}")
    payload = {"is_daylight_aperture": True}
    if vt is not None:
        payload["visible_transmittance"] = float(vt)
    return ProjectDiff(ops=[DiffOp(op="update", kind="opening", id=opening_id, payload=payload)])


def cmd_add_escape_route(
    project_path: str,
    route_id: str,
    polyline: list[tuple[float, float, float]],
    *,
    width_m: float = 1.0,
    spacing_m: float = 0.5,
    height_m: float = 0.0,
    end_margin_m: float = 0.0,
    name: str | None = None,
) -> ProjectDiff:
    project, _ = _load(project_path)
    rid = route_id
    existing = {r.id for r in project.escape_routes}
    if rid in existing:
        i = 2
        while f"{route_id}_{i}" in existing:
            i += 1
        rid = f"{route_id}_{i}"
    route = EscapeRouteSpec(
        id=rid,
        name=name or rid,
        polyline=[(float(a), float(b), float(c)) for a, b, c in polyline],
        width_m=float(width_m),
        spacing_m=float(spacing_m),
        height_m=float(height_m),
        end_margin_m=float(end_margin_m),
    )
    return ProjectDiff(ops=[DiffOp(op="add", kind="escape_route", id=route.id, payload=route)])


def cmd_add_emergency_job(
    project_path: str,
    *,
    routes: list[str],
    open_area_targets: list[str],
    standard: str = "EN1838",
    route_min_lux: float = 1.0,
    route_u0_min: float = 0.1,
    open_area_min_lux: float = 0.5,
    open_area_u0_min: float = 0.1,
    emergency_factor: float = 1.0,
    include_luminaires: list[str] | None = None,
    exclude_luminaires: list[str] | None = None,
) -> ProjectDiff:
    project, _ = _load(project_path)
    job_id = "emergency_1"
    existing = {j.id for j in project.jobs}
    i = 1
    while job_id in existing:
        i += 1
        job_id = f"emergency_{i}"
    em_spec = EmergencySpec(
        standard=str(standard),  # type: ignore[arg-type]
        route_min_lux=float(route_min_lux),
        route_u0_min=float(route_u0_min),
        open_area_min_lux=float(open_area_min_lux),
        open_area_u0_min=float(open_area_u0_min),
    )
    mode = EmergencyModeSpec(
        emergency_factor=float(emergency_factor),
        include_luminaires=[str(x) for x in (include_luminaires or [])],
        exclude_luminaires=[str(x) for x in (exclude_luminaires or [])],
    )
    job = JobSpec(
        id=job_id,
        type="emergency",
        backend="cpu",
        settings={"mode": "escape_route"},
        emergency=em_spec,
        mode=mode,
        routes=[str(x) for x in routes],
        open_area_targets=[str(x) for x in open_area_targets],
    )
    return ProjectDiff(ops=[DiffOp(op="add", kind="job", id=job.id, payload=job)])


def cmd_add_variant(
    project_path: str,
    variant_id: str,
    name: str,
    *,
    description: str = "",
    diff_ops: list[dict] | None = None,
) -> ProjectDiff:
    project, _ = _load(project_path)
    vid = variant_id
    existing = {v.id for v in project.variants}
    if vid in existing:
        i = 2
        while f"{variant_id}_{i}" in existing:
            i += 1
        vid = f"{variant_id}_{i}"
    variant = ProjectVariant(
        id=vid,
        name=str(name),
        description=str(description),
        diff_ops=[dict(x) for x in (diff_ops or []) if isinstance(x, dict)],
    )
    return ProjectDiff(ops=[DiffOp(op="add", kind="variant", id=variant.id, payload=variant)])


def cmd_compare_variants(project_path: str, job_id: str, variant_ids: list[str], baseline_variant_id: str | None = None) -> dict:
    res = run_job_for_variants(project_path, job_id, variant_ids, baseline_variant_id=baseline_variant_id)
    return {
        "out_dir": res.out_dir,
        "compare_json": res.compare_json,
        "compare_csv": res.compare_csv,
        "rows": res.rows,
    }


def cmd_add_workplane_grid(
    project_path: str,
    room_id: str,
    height: float,
    spacing: float,
    margins: float,
) -> ProjectDiff:
    project, _ = _load(project_path)
    room = next((r for r in project.geometry.rooms if r.id == room_id), None)
    if room is None:
        raise ValueError(f"Room not found: {room_id}")
    grid = create_calc_grid_from_room(
        project,
        grid_id=f"grid_{room_id}_{int(height * 1000)}",
        name=f"Workplane {room.name}",
        room_id=room_id,
        elevation=float(height),
        spacing=max(float(spacing), 0.1),
        margin=float(margins),
    )
    # Command returns diff only; caller decides apply/persist.
    project.grids = [g for g in project.grids if g.id != grid.id]
    return ProjectDiff(ops=[DiffOp(op="add", kind="grid", id=grid.id, payload=grid)])


def cmd_place_rect_array(
    project_path: str,
    room_id: str,
    asset_id: str,
    nx: int,
    ny: int,
    margins: float,
    mount_height: float,
) -> ProjectDiff:
    project, _ = _load(project_path)
    room = next((r for r in project.geometry.rooms if r.id == room_id), None)
    if room is None:
        raise ValueError(f"Room not found: {room_id}")
    no_go_polys = []
    for ng in project.geometry.no_go_zones:
        if ng.room_id and ng.room_id != room_id:
            continue
        poly2d = [(float(v[0]), float(v[1])) for v in ng.vertices]
        if len(poly2d) >= 3:
            no_go_polys.append(poly2d)
    arr = place_array_rect(
        room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
        nx=nx,
        ny=ny,
        margin_x=margins,
        margin_y=margins,
        z=room.origin[2] + mount_height,
        photometry_asset_id=asset_id,
        no_go_polygons=no_go_polys,
    )
    ops: List[DiffOp] = [DiffOp(op="remove", kind="luminaire", id=l.id) for l in project.luminaires]
    ops.extend(DiffOp(op="add", kind="luminaire", id=l.id, payload=l) for l in arr)
    return ProjectDiff(ops=ops)


def cmd_run_job(project_path: str, job_id: str) -> JobResultRef:
    return run_job(project_path, job_id)


def cmd_export_report(project_path: str, job_id: str, template: str, out_path: str | None = None) -> Path:
    project, ppath = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    if template.lower() == "en12464":
        out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_en12464.pdf")
        model = build_en12464_report_model(project, ref)
        return render_en12464_pdf(model, out)
    if template.lower() == "en13032":
        out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_en13032.pdf")
        model = build_en13032_report_model(project, ref)
        return render_en13032_pdf(model, out)
    if template.lower() in {"auto", "daylight", "emergency", "roadway"}:
        out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_report.pdf")
        return build_project_pdf_report(project, ref, out)
    raise ValueError(f"Unsupported report template: {template}")


def cmd_export_audit_bundle(project_path: str, job_id: str, out_path: str | None = None) -> Path:
    project, ppath = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_audit_bundle.zip")
    return export_debug_bundle(project, ref, out)


def cmd_export_client_bundle(project_path: str, job_id: str, out_path: str | None = None) -> Path:
    project, ppath = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_client_bundle.zip")
    return export_client_bundle(project, ref, out)


def cmd_export_backend_compare(project_path: str, job_id: str, out_path: str | None = None) -> Path:
    project, ppath = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_backend_compare.html")
    return render_backend_comparison_html(Path(ref.result_dir), out)


def cmd_export_roadway_report(project_path: str, job_id: str, out_path: str | None = None) -> Path:
    project, ppath = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    out = Path(out_path).expanduser().resolve() if out_path else (ppath.parent / f"{project.name}_{job_id}_roadway_report.html")
    return render_roadway_report_html(Path(ref.result_dir), out)


def cmd_apply_diff(project_path: str, diff: ProjectDiff) -> ProjectDiff:
    project, ppath = _load(project_path)
    diff.apply(project)
    from luxera.project.io import save_project_schema

    save_project_schema(project, ppath)
    return diff


def cmd_update_object(project_path: str, kind: str, object_id: str, payload: dict) -> dict:
    project, ppath = _load(project_path)
    coll = _collection_for_kind(project, kind)
    obj = _find_by_id(coll, object_id)
    if obj is None:
        raise ValueError(f"{kind} not found: {object_id}")
    for key, value in payload.items():
        setattr(obj, key, value)
    from luxera.project.io import save_project_schema

    save_project_schema(project, ppath)
    return {"kind": kind, "id": object_id, "updated_fields": sorted(payload.keys())}


def cmd_delete_object(project_path: str, kind: str, object_id: str) -> dict:
    project, ppath = _load(project_path)
    coll = _collection_for_kind(project, kind)
    idx = next((i for i, x in enumerate(coll) if getattr(x, "id", None) == object_id), None)
    if idx is None:
        raise ValueError(f"{kind} not found: {object_id}")
    coll.pop(idx)
    from luxera.project.io import save_project_schema

    save_project_schema(project, ppath)
    return {"kind": kind, "id": object_id, "deleted": True}


def cmd_duplicate_object(project_path: str, kind: str, object_id: str) -> dict:
    project, ppath = _load(project_path)
    coll = _collection_for_kind(project, kind)
    obj = _find_by_id(coll, object_id)
    if obj is None:
        raise ValueError(f"{kind} not found: {object_id}")
    dup = copy.deepcopy(obj)
    new_id = f"{object_id}_{uuid.uuid4().hex[:8]}"
    setattr(dup, "id", new_id)
    if hasattr(dup, "name"):
        name = str(getattr(dup, "name") or kind)
        setattr(dup, "name", f"{name} Copy")
    coll.append(dup)
    from luxera.project.io import save_project_schema

    save_project_schema(project, ppath)
    return {"kind": kind, "source_id": object_id, "id": new_id}


def cmd_summarize_results(project_path: str, job_id: str) -> dict:
    project, _ = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    return {"job_id": ref.job_id, "job_hash": ref.job_hash, "summary": ref.summary}


def cmd_render_heatmap(project_path: str, job_id: str) -> dict:
    project, _ = _load(project_path)
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        raise ValueError(f"Result not found for job: {job_id}")
    result_dir = Path(ref.result_dir)
    csv_path = result_dir / "grid.csv"
    meta_path = result_dir / "result.json"
    if not csv_path.exists():
        raise ValueError("Result has no grid.csv for heatmap rendering")
    rows = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if rows.ndim == 1:
        rows = rows.reshape(1, -1)
    points = rows[:, 0:3]
    values = rows[:, 3]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    nx = int(meta.get("job", {}).get("settings", {}).get("grid_nx", 0))
    ny = int(meta.get("job", {}).get("settings", {}).get("grid_ny", 0))
    if nx <= 0 or ny <= 0:
        grid = next((g for g in project.grids), None)
        if grid is not None:
            nx, ny = int(grid.nx), int(grid.ny)
    if nx <= 0 or ny <= 0:
        raise ValueError("Cannot determine grid resolution (nx, ny)")
    out = write_grid_heatmap_and_isolux(result_dir, points, values, nx=nx, ny=ny)
    return {"artifacts": {k: str(v) for k, v in out.items()}}


def cmd_optimize_search(
    project_path: str,
    job_id: str,
    constraints: dict | None = None,
    max_rows: int = 6,
    max_cols: int = 6,
    top_n: int = 8,
) -> dict:
    res = run_deterministic_search(
        project_path,
        job_id,
        max_rows=max_rows,
        max_cols=max_cols,
        constraints={str(k): float(v) for k, v in (constraints or {}).items()} if constraints else None,
        top_n=top_n,
    )
    return {
        "best": {
            "rows": res.best.rows,
            "cols": res.best.cols,
            "dimming": res.best.dimming,
            "score": res.best.score,
            "mean_lux": res.best.mean_lux,
            "uniformity_ratio": res.best.uniformity_ratio,
            "ugr_worst_case": res.best.ugr_worst_case,
        },
        "top": [x.__dict__ for x in res.top],
        "artifact_json": res.artifact_json,
        "best_layout": res.best_layout,
    }


def cmd_optimize_candidates(
    project_path: str,
    job_id: str,
    candidate_limit: int = 12,
    constraints: dict | None = None,
) -> dict:
    artifacts = run_optimizer(
        project_path,
        job_id=job_id,
        candidate_limit=max(1, int(candidate_limit)),
        constraints={str(k): float(v) for k, v in (constraints or {}).items()} if constraints else None,
    )
    return {
        "candidates_csv": artifacts.candidates_csv,
        "topk_csv": artifacts.topk_csv,
        "best_diff_json": artifacts.best_diff_json,
        "optimizer_manifest_json": artifacts.optimizer_manifest_json,
    }
