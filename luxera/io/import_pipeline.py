from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from luxera.core.coordinates import AxisConvention, apply_axis_conversion, describe_axis_conversion
from luxera.engine.direct_illuminance import build_direct_occluders
from luxera.geometry.bvh import build_bvh, triangulate_surfaces
from luxera.geometry.doctor import repair_mesh, scene_health_report
from luxera.geometry.polygon2d import make_polygon_valid, validate_polygon_with_holes
from luxera.io.dxf_import import DXFDocument, DXFInsert, load_dxf
from luxera.io.geometry_import import GeometryImportResult, import_geometry_file
from luxera.project.schema import Project
from luxera.scene.build import build_scene_graph_from_project


@dataclass(frozen=True)
class ImportStage:
    name: str
    status: str
    details: Dict[str, object] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportPipelineReport:
    source_file: str
    format: str
    stages: List[ImportStage] = field(default_factory=list)
    scene_health: Dict[str, object] = field(default_factory=dict)
    layer_map: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "source_file": self.source_file,
            "format": self.format,
            "stages": [
                {
                    "name": s.name,
                    "status": s.status,
                    "details": dict(s.details),
                    "errors": list(s.errors),
                    "warnings": list(s.warnings),
                }
                for s in self.stages
            ],
            "scene_health": dict(self.scene_health),
            "layer_map": dict(self.layer_map),
        }


@dataclass(frozen=True)
class ImportPipelineResult:
    geometry: Optional[GeometryImportResult]
    report: ImportPipelineReport


@dataclass(frozen=True)
class RepairPolicyDecision:
    severity: str
    action: str
    reasons: List[str] = field(default_factory=list)


def _detect_dxf_layer_map(doc: DXFDocument) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for layer in sorted(set(str(l).upper() for l in (doc.layers or []))):
        if "WALL" in layer:
            mapping[layer] = "wall"
        elif "DOOR" in layer:
            mapping[layer] = "door"
        elif "WINDOW" in layer:
            mapping[layer] = "window"
        elif "ROOM" in layer or "SPACE" in layer:
            mapping[layer] = "room"
        elif "GRID" in layer:
            mapping[layer] = "grid"
        else:
            mapping[layer] = "unmapped"
    return mapping


def _dxf_block_instances(doc: DXFDocument) -> List[DXFInsert]:
    return [e for e in doc.entities if isinstance(e, DXFInsert)]


def _classify_repair_policy(
    health: Dict[str, object],
    repair_errors: List[str],
    repair_warnings: List[str],
    *,
    semantic_count: int,
    triangle_count: int,
    has_raw_content: bool,
) -> RepairPolicyDecision:
    counts = health.get("counts", {}) if isinstance(health, dict) else {}
    deg = int(counts.get("degenerate_triangles", 0))
    non_manifold = int(counts.get("non_manifold_edges", 0))
    self_isect = int(counts.get("self_intersections_approx", 0))
    open_edges = int(counts.get("open_boundary_edges", 0))
    disconnected = int(counts.get("disconnected_components", 0))

    reasons: List[str] = []
    benign_errors = {"No vertices.", "No triangles."}
    severe_errors = [e for e in repair_errors if str(e) not in benign_errors]
    if severe_errors:
        reasons.append("repair_errors_present")
    if deg > 0:
        reasons.append(f"degenerate_triangles={deg}")
    if non_manifold > 0:
        reasons.append(f"non_manifold_edges={non_manifold}")
    if self_isect > 0:
        reasons.append(f"self_intersections_approx={self_isect}")
    if open_edges > 0:
        reasons.append(f"open_boundary_edges={open_edges}")
    if disconnected > 1:
        reasons.append(f"disconnected_components={disconnected}")

    # Extreme: clearly unsafe geometry for deterministic downstream calc.
    if severe_errors or non_manifold > 512 or deg > 4096:
        return RepairPolicyDecision(severity="extreme", action="block", reasons=reasons)
    if semantic_count <= 0 and triangle_count <= 0 and not has_raw_content:
        reasons.append("no_semantic_or_mesh_geometry")
        return RepairPolicyDecision(severity="extreme", action="block", reasons=reasons)

    # Medium: proceed, but report explicit warnings.
    if non_manifold > 0 or self_isect > 0 or deg > 0:
        return RepairPolicyDecision(severity="medium", action="warn_continue", reasons=reasons)

    # Low: auto-healed / soft quality issues.
    if open_edges > 0 or disconnected > 1 or repair_warnings:
        return RepairPolicyDecision(severity="low", action="auto_repair", reasons=reasons)

    return RepairPolicyDecision(severity="ok", action="none", reasons=[])


def _apply_axis_to_geo(
    geo: GeometryImportResult,
    *,
    target_up_axis: str,
    target_handedness: str,
) -> Tuple[GeometryImportResult, str]:
    target = AxisConvention(
        up_axis=("Y_UP" if str(target_up_axis).upper() == "Y_UP" else "Z_UP"),  # type: ignore[arg-type]
        handedness=("LEFT_HANDED" if str(target_handedness).upper() == "LEFT_HANDED" else "RIGHT_HANDED"),  # type: ignore[arg-type]
    )
    report = describe_axis_conversion(AxisConvention(), target)
    if report.axis_transform_applied == "Z_UP/RIGHT_HANDED->Z_UP/RIGHT_HANDED":
        return geo, report.axis_transform_applied

    m4 = np.asarray(report.matrix, dtype=float)

    def _tx_points(points: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float]]:
        if not points:
            return []
        arr = np.asarray(points, dtype=float).reshape(-1, 3)
        out = apply_axis_conversion(arr, m4)
        return [(float(p[0]), float(p[1]), float(p[2])) for p in out.tolist()]

    rooms = []
    for r in geo.rooms:
        x0, y0, z0 = r.origin
        x1, y1, z1 = x0 + r.width, y0 + r.length, z0 + r.height
        corners = _tx_points(
            [
                (x0, y0, z0),
                (x1, y0, z0),
                (x1, y1, z0),
                (x0, y1, z0),
                (x0, y0, z1),
                (x1, y0, z1),
                (x1, y1, z1),
                (x0, y1, z1),
            ]
        )
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        zs = [p[2] for p in corners]
        rooms.append(
            type(r)(
                id=r.id,
                name=r.name,
                width=float(max(xs) - min(xs)),
                length=float(max(ys) - min(ys)),
                height=float(max(zs) - min(zs)),
                origin=(float(min(xs)), float(min(ys)), float(min(zs))),
                floor_reflectance=r.floor_reflectance,
                wall_reflectance=r.wall_reflectance,
                ceiling_reflectance=r.ceiling_reflectance,
                activity_type=r.activity_type,
                layer_id=r.layer_id,
                level_id=r.level_id,
                coordinate_system_id=r.coordinate_system_id,
                footprint=r.footprint,
            )
        )

    surfaces = []
    for s in geo.surfaces:
        surfaces.append(
            type(s)(
                id=s.id,
                name=s.name,
                kind=s.kind,
                vertices=_tx_points(list(s.vertices)),
                normal=s.normal,
                room_id=s.room_id,
                material_id=s.material_id,
                layer=s.layer,
                layer_id=s.layer_id,
                tags=list(s.tags),
                two_sided=s.two_sided,
                wall_room_side_a=s.wall_room_side_a,
                wall_room_side_b=s.wall_room_side_b,
                wall_material_side_a=s.wall_material_side_a,
                wall_material_side_b=s.wall_material_side_b,
            )
        )
    openings = []
    for o in geo.openings:
        openings.append(
            type(o)(
                id=o.id,
                name=o.name,
                opening_type=o.opening_type,
                kind=o.kind,
                layer_id=o.layer_id,
                host_surface_id=o.host_surface_id,
                vertices=_tx_points(list(o.vertices)),
                is_daylight_aperture=o.is_daylight_aperture,
                vt=o.vt,
                frame_fraction=o.frame_fraction,
                shade_factor=o.shade_factor,
                visible_transmittance=o.visible_transmittance,
                shading_factor=o.shading_factor,
            )
        )
    obstructions = []
    for ob in geo.obstructions:
        obstructions.append(
            type(ob)(
                id=ob.id,
                name=ob.name,
                kind=ob.kind,
                layer_id=ob.layer_id,
                vertices=_tx_points(list(ob.vertices)),
                height=ob.height,
            )
        )

    out = GeometryImportResult(
        source_file=geo.source_file,
        format=geo.format,
        length_unit=geo.length_unit,
        source_length_unit=geo.source_length_unit,
        scale_to_meters=geo.scale_to_meters,
        axis_transform_applied=f"{geo.axis_transform_applied}|post:{report.axis_transform_applied}",
        axis_matrix=[[float(v) for v in row] for row in m4.tolist()],
        rooms=rooms,
        surfaces=surfaces,
        openings=openings,
        obstructions=obstructions,
        levels=list(geo.levels),
        warnings=list(geo.warnings) + [f"post_import_axis_transform_applied={report.axis_transform_applied}"],
        stage_report=dict(geo.stage_report),
        scene_health_report=dict(geo.scene_health_report),
        layer_map=dict(geo.layer_map),
    )
    return out, report.axis_transform_applied


def run_import_pipeline(
    path: str,
    *,
    fmt: Optional[str] = None,
    dxf_scale: float = 1.0,
    length_unit: Optional[str] = None,
    scale_to_meters: Optional[float] = None,
    ifc_options: Optional[dict] = None,
    layer_overrides: Optional[Dict[str, str]] = None,
    force_extreme: bool = False,
    target_up_axis: str = "Z_UP",
    target_handedness: str = "RIGHT_HANDED",
) -> ImportPipelineResult:
    p = Path(path).expanduser().resolve()
    fmt_used = (fmt.upper() if fmt else p.suffix.replace(".", "").upper())
    stages: List[ImportStage] = []
    layer_map: Dict[str, str] = {}

    # Raw import stage
    raw_errors: List[str] = []
    raw_warnings: List[str] = []
    raw_details: Dict[str, object] = {"path": str(p), "format": fmt_used}
    if fmt_used == "DXF":
        try:
            doc = load_dxf(p)
            layer_map = _detect_dxf_layer_map(doc)
            if layer_overrides:
                for k, v in layer_overrides.items():
                    layer_map[str(k).upper()] = str(v)
            inserts = _dxf_block_instances(doc)
            raw_details["layers"] = sorted(list(layer_map.keys()))
            raw_details["block_instances"] = len(inserts)
            raw_details["units"] = getattr(doc, "units", "m")
        except Exception as exc:
            raw_errors.append(str(exc))
    stages.append(ImportStage(name="RawImport", status=("error" if raw_errors else "ok"), details=raw_details, errors=raw_errors, warnings=raw_warnings))
    if raw_errors:
        report = ImportPipelineReport(source_file=str(p), format=fmt_used, stages=stages, layer_map=layer_map)
        return ImportPipelineResult(geometry=None, report=report)

    # Normalized geometry + semantic extraction (current importer already does both).
    try:
        geo = import_geometry_file(
            str(p),
            fmt=fmt_used,
            dxf_scale=dxf_scale,
            length_unit=length_unit,
            scale_to_meters=scale_to_meters,
            ifc_options=ifc_options,
        )
    except Exception as exc:
        stages.append(ImportStage(name="NormalizedGeometry", status="error", errors=[str(exc)]))
        report = ImportPipelineReport(source_file=str(p), format=fmt_used, stages=stages, layer_map=layer_map)
        return ImportPipelineResult(geometry=None, report=report)

    stages.append(
        ImportStage(
            name="NormalizedGeometry",
            status="ok",
            details={
                "length_unit": geo.length_unit,
                "source_length_unit": geo.source_length_unit,
                "scale_to_meters": geo.scale_to_meters,
                "axis_transform_applied": geo.axis_transform_applied,
                "axis_matrix": list(getattr(geo, "axis_matrix", [])),
            },
            warnings=list(geo.warnings),
        )
    )
    stages.append(
        ImportStage(
            name="SemanticExtraction",
            status="ok",
            details={
                "rooms": len(geo.rooms),
                "surfaces": len(geo.surfaces),
                "openings": len(geo.openings),
                "levels": len(geo.levels),
                "obstructions": len(geo.obstructions),
            },
        )
    )

    # 2D polygon doctor for room footprints.
    poly_warn: List[str] = []
    for room in geo.rooms:
        if room.footprint:
            fixed = make_polygon_valid(list(room.footprint))
            rep = validate_polygon_with_holes(fixed, ())
            room.footprint = fixed
            if not rep.valid:
                poly_warn.append(f"room:{room.id} footprint repaired via hull fallback")
    stages.append(ImportStage(name="Repair2D", status="ok", warnings=poly_warn))

    # Scene build + mesh diagnostics.
    project = Project(name=p.stem)
    project.geometry.rooms = list(geo.rooms)
    project.geometry.surfaces = list(geo.surfaces)
    project.geometry.openings = list(geo.openings)
    project.geometry.obstructions = list(geo.obstructions)
    project.geometry.levels = list(geo.levels)
    project.geometry.length_unit = geo.length_unit  # type: ignore[assignment]
    project.geometry.source_length_unit = geo.source_length_unit
    project.geometry.scale_to_meters = float(geo.scale_to_meters)
    project.geometry.axis_transform_applied = geo.axis_transform_applied

    graph = build_scene_graph_from_project(project)
    occluders = build_direct_occluders(project, include_room_shell=False)
    tris = triangulate_surfaces(occluders)
    verts = [t.a.to_tuple() for t in tris] + [t.b.to_tuple() for t in tris] + [t.c.to_tuple() for t in tris]
    tri_idx = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(tris))]
    health = scene_health_report(verts, tri_idx).to_dict()
    repaired = repair_mesh(verts, tri_idx)
    _ = build_bvh(tris) if tris else None
    stages.append(
        ImportStage(
            name="RepairHeal",
            status="ok",
            details={"triangles_before": len(tri_idx), "triangles_after": len(repaired.triangles)},
            warnings=list(repaired.report.warnings),
            errors=list(repaired.report.errors),
        )
    )
    semantic_count = len(geo.rooms) + len(geo.surfaces) + len(geo.openings) + len(geo.obstructions)
    has_raw_content = bool(layer_map) or int(raw_details.get("block_instances", 0) if isinstance(raw_details, dict) else 0) > 0
    decision = _classify_repair_policy(
        health,
        list(repaired.report.errors),
        list(repaired.report.warnings),
        semantic_count=semantic_count,
        triangle_count=len(tri_idx),
        has_raw_content=has_raw_content,
    )
    policy_stage_status = "ok"
    policy_warnings: List[str] = []
    policy_errors: List[str] = []
    if decision.severity == "low":
        policy_warnings.append("Low-severity defects auto-repaired.")
    elif decision.severity == "medium":
        policy_warnings.append("Medium-severity defects detected; import continued with warnings.")
    elif decision.severity == "extreme":
        if force_extreme:
            policy_warnings.append("Extreme defects detected; import forced to continue.")
        else:
            policy_stage_status = "error"
            policy_errors.append("Extreme geometry defects detected; import blocked unless force_extreme=True.")

    stages.append(
        ImportStage(
            name="PolicyGate",
            status=policy_stage_status,
            details={"severity": decision.severity, "action": decision.action, "reasons": list(decision.reasons)},
            warnings=policy_warnings,
            errors=policy_errors,
        )
    )
    if policy_stage_status == "error":
        report = ImportPipelineReport(source_file=str(p), format=fmt_used, stages=stages, scene_health=health, layer_map=layer_map)
        return ImportPipelineResult(geometry=None, report=report)

    geo, post_axis = _apply_axis_to_geo(
        geo,
        target_up_axis=target_up_axis,
        target_handedness=target_handedness,
    )
    if post_axis != "Z_UP/RIGHT_HANDED->Z_UP/RIGHT_HANDED":
        stages.append(
            ImportStage(
                name="PostAxisReorient",
                status="ok",
                details={"post_axis_transform_applied": post_axis},
                warnings=["Geometry reoriented for app handoff."],
            )
        )
    stages.append(
        ImportStage(
            name="SceneBuild",
            status="ok",
            details={"scene_nodes": len(graph.nodes), "rooms": len(graph.rooms), "bvh_triangles": len(tris)},
        )
    )

    report = ImportPipelineReport(source_file=str(p), format=fmt_used, stages=stages, scene_health=health, layer_map=layer_map)
    return ImportPipelineResult(geometry=geo, report=report)
