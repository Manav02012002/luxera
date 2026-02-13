from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

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


def run_import_pipeline(
    path: str,
    *,
    fmt: Optional[str] = None,
    dxf_scale: float = 1.0,
    length_unit: Optional[str] = None,
    scale_to_meters: Optional[float] = None,
    ifc_options: Optional[dict] = None,
    layer_overrides: Optional[Dict[str, str]] = None,
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
    stages.append(
        ImportStage(
            name="SceneBuild",
            status="ok",
            details={"scene_nodes": len(graph.nodes), "rooms": len(graph.rooms), "bvh_triangles": len(tris)},
        )
    )

    report = ImportPipelineReport(source_file=str(p), format=fmt_used, stages=stages, scene_health=health, layer_map=layer_map)
    return ImportPipelineResult(geometry=geo, report=report)
