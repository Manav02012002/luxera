from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from luxera.io.dxf_import import extract_rooms_from_dxf, load_dxf
from luxera.project.schema import LevelSpec, ObstructionSpec, OpeningSpec, RoomSpec, SurfaceSpec
from luxera.core.units import unit_scale_to_m
from luxera.io.ifc_import import IFCImportOptions, import_ifc
from luxera.geometry.ifc_cleaning import clean_ifc_surfaces
from luxera.io.mesh_import import import_mesh_file


@dataclass(frozen=True)
class GeometryImportResult:
    source_file: str
    format: str
    length_unit: str = "m"
    source_length_unit: str = "m"
    scale_to_meters: float = 1.0
    axis_transform_applied: str = "Z_UP/RIGHT_HANDED->Z_UP/RIGHT_HANDED"
    rooms: List[RoomSpec] = field(default_factory=list)
    surfaces: List[SurfaceSpec] = field(default_factory=list)
    openings: List[OpeningSpec] = field(default_factory=list)
    obstructions: List[ObstructionSpec] = field(default_factory=list)
    levels: List[LevelSpec] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stage_report: dict = field(default_factory=dict)
    scene_health_report: dict = field(default_factory=dict)
    layer_map: dict = field(default_factory=dict)


def _normalize_unit(unit: Optional[str]) -> str:
    u = str(unit or "m").lower()
    if u in {"m", "meter", "meters"}:
        return "m"
    if u in {"mm", "millimeter", "millimeters"}:
        return "mm"
    if u in {"cm", "centimeter", "centimeters"}:
        return "cm"
    if u in {"ft", "feet", "foot"}:
        return "ft"
    if u in {"in", "inch", "inches"}:
        return "in"
    return "m"


def _infer_format(path: Path, fmt: Optional[str]) -> str:
    if fmt:
        return fmt.upper()
    return path.suffix.replace(".", "").upper()


def _import_dxf(path: Path, scale: float = 1.0, length_unit: Optional[str] = None) -> GeometryImportResult:
    doc = load_dxf(path)
    inferred = _normalize_unit(length_unit or getattr(doc, "units", "m"))
    base_scale = float(unit_scale_to_m(inferred))
    combined_scale = float(scale) * base_scale
    rooms = extract_rooms_from_dxf(doc, scale=combined_scale)
    room_specs: List[RoomSpec] = []
    for i, room in enumerate(rooms):
        xs = [v.x for v in room.floor_vertices]
        ys = [v.y for v in room.floor_vertices]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        room_specs.append(
            RoomSpec(
                id=f"dxf_room_{i+1}",
                name=room.name,
                width=max_x - min_x,
                length=max_y - min_y,
                height=room.height,
                origin=(min_x, min_y, 0.0),
            )
        )
    return GeometryImportResult(
        source_file=str(path),
        format="DXF",
        length_unit=inferred,
        source_length_unit=inferred,
        scale_to_meters=combined_scale,
        rooms=room_specs,
    )


def _import_obj(path: Path, length_unit: Optional[str] = None, scale_to_meters: Optional[float] = None) -> GeometryImportResult:
    mesh = import_mesh_file(str(path), fmt="OBJ", length_unit=length_unit, scale_to_meters=scale_to_meters)
    surfaces: List[SurfaceSpec] = []
    for i, face in enumerate(mesh.faces):
        pts = [mesh.vertices[idx] for idx in face if 0 <= idx < len(mesh.vertices)]
        if len(pts) < 3:
            continue
        surfaces.append(
            SurfaceSpec(
                id=f"obj_surface_{i+1}",
                name=f"OBJ Surface {i+1}",
                kind="custom",
                vertices=pts,
            )
        )
    return GeometryImportResult(
        source_file=str(path),
        format="OBJ",
        length_unit=mesh.length_unit,
        source_length_unit=mesh.length_unit,
        scale_to_meters=mesh.scale_to_meters,
        surfaces=surfaces,
        warnings=list(mesh.warnings),
    )


def _import_gltf(path: Path, length_unit: Optional[str] = None, scale_to_meters: Optional[float] = None) -> GeometryImportResult:
    mesh = import_mesh_file(str(path), fmt="GLTF", length_unit=length_unit, scale_to_meters=scale_to_meters)
    surfaces: List[SurfaceSpec] = []
    for i, tri in enumerate(mesh.triangles):
        a, b, c = tri
        pts = [mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]]
        surfaces.append(
            SurfaceSpec(
                id=f"gltf_surface_{i+1}",
                name=f"GLTF Surface {i+1}",
                kind="custom",
                vertices=pts,
            )
        )
    if not surfaces:
        surfaces = []
    return GeometryImportResult(
        source_file=str(path),
        format="GLTF",
        length_unit=mesh.length_unit,
        source_length_unit=mesh.length_unit,
        scale_to_meters=mesh.scale_to_meters,
        surfaces=surfaces,
        warnings=list(mesh.warnings),
    )


def _import_fbx(path: Path, length_unit: Optional[str] = None, scale_to_meters: Optional[float] = None) -> GeometryImportResult:
    mesh = import_mesh_file(str(path), fmt="FBX", length_unit=length_unit, scale_to_meters=scale_to_meters)
    surfaces: List[SurfaceSpec] = []
    for i, tri in enumerate(mesh.triangles):
        a, b, c = tri
        pts = [mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]]
        surfaces.append(
            SurfaceSpec(
                id=f"fbx_surface_{i+1}",
                name=f"FBX Surface {i+1}",
                kind="custom",
                vertices=pts,
            )
        )
    return GeometryImportResult(
        source_file=str(path),
        format="FBX",
        length_unit=mesh.length_unit,
        source_length_unit=mesh.length_unit,
        scale_to_meters=mesh.scale_to_meters,
        surfaces=surfaces,
        warnings=list(mesh.warnings),
    )


def _import_skp(path: Path, length_unit: Optional[str] = None, scale_to_meters: Optional[float] = None) -> GeometryImportResult:
    mesh = import_mesh_file(str(path), fmt="SKP", length_unit=length_unit, scale_to_meters=scale_to_meters)
    surfaces: List[SurfaceSpec] = []
    for i, tri in enumerate(mesh.triangles):
        a, b, c = tri
        pts = [mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]]
        surfaces.append(
            SurfaceSpec(
                id=f"skp_surface_{i+1}",
                name=f"SKP Surface {i+1}",
                kind="custom",
                vertices=pts,
            )
        )
    return GeometryImportResult(
        source_file=str(path),
        format="SKP",
        length_unit=mesh.length_unit,
        source_length_unit=mesh.length_unit,
        scale_to_meters=mesh.scale_to_meters,
        surfaces=surfaces,
        warnings=list(mesh.warnings),
    )


def _import_dwg(path: Path, length_unit: Optional[str] = None, scale_to_meters: Optional[float] = None) -> GeometryImportResult:
    # Professional workflows commonly convert DWG to IFC/DXF/OBJ in a pre-step.
    # We return a clear structured error instead of silently producing wrong geometry.
    raise ValueError(
        "DWG import requires external conversion. Convert to DXF/IFC/OBJ first, "
        "or provide a DWG backend integration."
    )


def _import_ifc(path: Path, length_unit: Optional[str] = None, scale_to_meters: Optional[float] = None) -> GeometryImportResult:
    return _import_ifc_with_options(path, length_unit=length_unit, scale_to_meters=scale_to_meters, ifc_options=None)


def _import_ifc_with_options(
    path: Path,
    length_unit: Optional[str] = None,
    scale_to_meters: Optional[float] = None,
    ifc_options: Optional[dict] = None,
) -> GeometryImportResult:
    opts = dict(ifc_options or {})
    fallback_room_size = opts.get("fallback_room_size")
    if fallback_room_size is not None:
        fallback_room_size = tuple(float(v) for v in fallback_room_size)
    imported = import_ifc(
        path,
        IFCImportOptions(
            length_unit_override=length_unit,
            scale_to_meters_override=scale_to_meters,
            default_window_transmittance=float(opts.get("default_window_transmittance", 0.70)),
            fallback_room_size=fallback_room_size if fallback_room_size is not None else (5.0, 5.0, 3.0),
        ),
    )
    cleaned_surfaces, cleaning_report = clean_ifc_surfaces(imported.surfaces)
    warnings = list(imported.warnings)
    warnings.append(f"ifc_space_boundary_method={imported.ifc_space_boundary_method}")
    if cleaning_report:
        warnings.append(f"IFC cleaning: {cleaning_report}")
    return GeometryImportResult(
        source_file=str(path),
        format="IFC",
        length_unit=str(imported.coordinate_system.get("length_unit", "m")),
        source_length_unit=str(imported.coordinate_system.get("source_length_unit", imported.coordinate_system.get("length_unit", "m"))),
        scale_to_meters=float(imported.coordinate_system.get("scale_to_meters", 1.0)),
        axis_transform_applied=str(imported.coordinate_system.get("axis_transform_applied", "Z_UP/RIGHT_HANDED->Z_UP/RIGHT_HANDED")),
        rooms=imported.rooms,
        surfaces=cleaned_surfaces,
        openings=imported.openings,
        obstructions=imported.obstructions,
        levels=imported.levels,
        warnings=warnings,
    )


def import_geometry_file(
    path: str,
    fmt: Optional[str] = None,
    dxf_scale: float = 1.0,
    length_unit: Optional[str] = None,
    scale_to_meters: Optional[float] = None,
    ifc_options: Optional[dict] = None,
) -> GeometryImportResult:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Geometry file not found: {p}")

    format_used = _infer_format(p, fmt)
    if format_used == "DXF":
        return _import_dxf(p, scale=dxf_scale, length_unit=length_unit)
    if format_used == "OBJ":
        return _import_obj(p, length_unit=length_unit, scale_to_meters=scale_to_meters)
    if format_used in {"GLTF", "GLB"}:
        return _import_gltf(p, length_unit=length_unit, scale_to_meters=scale_to_meters)
    if format_used == "FBX":
        return _import_fbx(p, length_unit=length_unit, scale_to_meters=scale_to_meters)
    if format_used == "SKP":
        return _import_skp(p, length_unit=length_unit, scale_to_meters=scale_to_meters)
    if format_used == "DWG":
        return _import_dwg(p, length_unit=length_unit, scale_to_meters=scale_to_meters)
    if format_used == "IFC":
        return _import_ifc_with_options(p, length_unit=length_unit, scale_to_meters=scale_to_meters, ifc_options=ifc_options)
    raise ValueError(f"Unsupported geometry format: {format_used}")
