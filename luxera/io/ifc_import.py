from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

import numpy as np

from luxera.core.coordinates import AxisConvention, apply_axis_conversion, describe_axis_conversion
from luxera.core.units import unit_scale_to_m
from luxera.geometry.openings.opening_uv import opening_uv_polygon
from luxera.geometry.openings.project_uv import lift_uv_to_3d, project_points_to_uv, wall_basis
from luxera.geometry.openings.subtract import UVPolygon, subtract_openings
from luxera.geometry.openings.triangulate_wall import wall_mesh_from_uv
from luxera.project.schema import LevelSpec, ObstructionSpec, OpeningSpec, RoomSpec, SurfaceSpec


@dataclass(frozen=True)
class IFCImportOptions:
    length_unit_override: Optional[str] = None
    scale_to_meters_override: Optional[float] = None
    default_window_transmittance: float = 0.70
    fallback_room_size: Tuple[float, float, float] = (5.0, 5.0, 3.0)
    source_up_axis: str = "Z_UP"
    source_handedness: str = "RIGHT_HANDED"


@dataclass(frozen=True)
class ImportedIFC:
    source_file: str
    coordinate_system: Dict[str, object]
    levels: List[LevelSpec] = field(default_factory=list)
    rooms: List[RoomSpec] = field(default_factory=list)
    openings: List[OpeningSpec] = field(default_factory=list)
    surfaces: List[SurfaceSpec] = field(default_factory=list)
    obstructions: List[ObstructionSpec] = field(default_factory=list)
    ifc_space_boundary_method: str = "bbox"
    warnings: List[str] = field(default_factory=list)


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


def _extract_ifc_entities(text: str, name: str) -> List[str]:
    pat = re.compile(rf"#\d+\s*=\s*{name}\((.*?)\);", re.IGNORECASE | re.DOTALL)
    return [m.group(1).strip() for m in pat.finditer(text)]


def _extract_ifc_entities_with_ids(text: str, name: str) -> List[Tuple[int, str]]:
    pat = re.compile(rf"#(\d+)\s*=\s*{name}\((.*?)\);", re.IGNORECASE | re.DOTALL)
    out: List[Tuple[int, str]] = []
    for m in pat.finditer(text):
        out.append((int(m.group(1)), m.group(2).strip()))
    return out


def _extract_name(args_text: str, fallback: str) -> str:
    # IFC argument positions vary by schema; use first quoted token as human label.
    m = re.search(r"'([^']+)'", args_text)
    return m.group(1) if m else fallback


def _infer_unit_from_ifc_text(text: str) -> str:
    up = text.upper()
    if "IFCSIUNIT" not in up:
        return "m"
    if ".LENGTHUNIT." not in up:
        return "m"
    if ".MILLI." in up and ".METRE." in up:
        return "mm"
    if ".CENTI." in up and ".METRE." in up:
        return "cm"
    if ".FOOT." in up:
        return "ft"
    if ".INCH." in up:
        return "in"
    return "m"


def _room_box_surfaces(room: RoomSpec) -> List[SurfaceSpec]:
    x0, y0, z0 = room.origin
    x1 = x0 + float(room.width)
    y1 = y0 + float(room.length)
    z1 = z0 + float(room.height)
    rid = room.id
    return [
        SurfaceSpec(
            id=f"{rid}_floor",
            name=f"{room.name} Floor",
            kind="floor",
            room_id=rid,
            vertices=[(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
        ),
        SurfaceSpec(
            id=f"{rid}_ceiling",
            name=f"{room.name} Ceiling",
            kind="ceiling",
            room_id=rid,
            vertices=[(x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)],
        ),
        SurfaceSpec(
            id=f"{rid}_wall_south",
            name=f"{room.name} South Wall",
            kind="wall",
            room_id=rid,
            vertices=[(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
        ),
        SurfaceSpec(
            id=f"{rid}_wall_north",
            name=f"{room.name} North Wall",
            kind="wall",
            room_id=rid,
            vertices=[(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
        ),
        SurfaceSpec(
            id=f"{rid}_wall_west",
            name=f"{room.name} West Wall",
            kind="wall",
            room_id=rid,
            vertices=[(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
        ),
        SurfaceSpec(
            id=f"{rid}_wall_east",
            name=f"{room.name} East Wall",
            kind="wall",
            room_id=rid,
            vertices=[(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
        ),
    ]


def _apply_axis_to_points(points: List[Tuple[float, float, float]], m4: np.ndarray) -> List[Tuple[float, float, float]]:
    if not points:
        return []
    arr = np.array(points, dtype=float).reshape(-1, 3)
    out = apply_axis_conversion(arr, m4)
    return [tuple(float(v) for v in row) for row in out.tolist()]


def _apply_axis_to_room(room: RoomSpec, m4: np.ndarray) -> RoomSpec:
    x0, y0, z0 = room.origin
    x1, y1, z1 = x0 + room.width, y0 + room.length, z0 + room.height
    corners = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    tr = _apply_axis_to_points(corners, m4)
    xs = [p[0] for p in tr]
    ys = [p[1] for p in tr]
    zs = [p[2] for p in tr]
    return RoomSpec(
        id=room.id,
        name=room.name,
        width=float(max(xs) - min(xs)),
        length=float(max(ys) - min(ys)),
        height=float(max(zs) - min(zs)),
        origin=(float(min(xs)), float(min(ys)), float(min(zs))),
        floor_reflectance=room.floor_reflectance,
        wall_reflectance=room.wall_reflectance,
        ceiling_reflectance=room.ceiling_reflectance,
        activity_type=room.activity_type,
        level_id=room.level_id,
        coordinate_system_id=room.coordinate_system_id,
        footprint=room.footprint,
    )


def _default_window_host_surface(room_id: str) -> str:
    return f"{room_id}_wall_south"


def _extract_ifc_refs(args_text: str) -> List[int]:
    return [int(x) for x in re.findall(r"#(\d+)", args_text)]


def _room_rank(room_id: Optional[str]) -> int:
    if not room_id:
        return 1_000_000_000
    m = re.search(r"(\d+)$", str(room_id))
    if m:
        return int(m.group(1))
    return 1_000_000_000


def _pick_preferred_room(existing_room_id: Optional[str], candidate_room_id: Optional[str]) -> Optional[str]:
    if existing_room_id is None:
        return candidate_room_id
    if candidate_room_id is None:
        return existing_room_id
    return candidate_room_id if _room_rank(candidate_room_id) < _room_rank(existing_room_id) else existing_room_id


def _build_boundary_room_map_from_rows(
    boundary_rows: List[Tuple[int, str]],
    room_by_space_step_id: Dict[int, RoomSpec],
    target_element_ids: Optional[set[int]] = None,
) -> Tuple[Dict[int, str], int]:
    mapping: Dict[int, str] = {}
    conflicts = 0
    for _, args in boundary_rows:
        refs = _extract_ifc_refs(args)
        if len(refs) < 2:
            continue
        sid = next((r for r in refs if r in room_by_space_step_id), None)
        if sid is None:
            continue
        room_id = room_by_space_step_id[sid].id
        candidates = [r for r in refs if r != sid and (target_element_ids is None or r in target_element_ids)]
        if not candidates:
            continue
        eid = candidates[0]
        prev = mapping.get(eid)
        picked = _pick_preferred_room(prev, room_id)
        if prev is not None and prev != picked:
            conflicts += 1
        if picked is not None:
            mapping[eid] = picked
    return mapping, conflicts


def _fallback_surface_for_linear_element(
    *,
    prefix: str,
    index: int,
    name: str,
    room_id: Optional[str],
    scale: float,
    kind: str = "custom",
) -> SurfaceSpec:
    x0 = 0.2 + float(index) * 0.4
    y0 = 0.2
    y1 = 1.8
    z0 = 0.0
    z1 = 0.2
    if kind == "wall":
        z1 = 2.6
    return SurfaceSpec(
        id=f"{prefix}_{index+1}",
        name=name,
        kind=kind,  # type: ignore[arg-type]
        room_id=room_id,
        vertices=[
            (x0 * scale, y0 * scale, z0 * scale),
            (x0 * scale, y1 * scale, z0 * scale),
            (x0 * scale, y1 * scale, z1 * scale),
            (x0 * scale, y0 * scale, z1 * scale),
        ],
    )


def _span(values: List[float]) -> float:
    return float(max(values) - min(values)) if values else 0.0


def _wall_axis(surface: SurfaceSpec, eps: float = 1e-6) -> Optional[str]:
    xs = [float(v[0]) for v in surface.vertices]
    ys = [float(v[1]) for v in surface.vertices]
    if _span(xs) <= eps and _span(ys) > eps:
        return "X_CONST"
    if _span(ys) <= eps and _span(xs) > eps:
        return "Y_CONST"
    return None


def _surface_rect_uv(surface: SurfaceSpec, axis: str) -> Tuple[float, float, float, float]:
    xs = [float(v[0]) for v in surface.vertices]
    ys = [float(v[1]) for v in surface.vertices]
    zs = [float(v[2]) for v in surface.vertices]
    if axis == "X_CONST":
        us = ys
    else:
        us = xs
    return (float(min(us)), float(max(us)), float(min(zs)), float(max(zs)))


def _opening_rect_uv(opening: OpeningSpec, axis: str) -> Tuple[float, float, float, float]:
    xs = [float(v[0]) for v in opening.vertices]
    ys = [float(v[1]) for v in opening.vertices]
    zs = [float(v[2]) for v in opening.vertices]
    if axis == "X_CONST":
        us = ys
    else:
        us = xs
    return (float(min(us)), float(max(us)), float(min(zs)), float(max(zs)))


def _uv_rect_to_surface(surface: SurfaceSpec, axis: str, u0: float, u1: float, z0: float, z1: float, *, sid: str) -> SurfaceSpec:
    if axis == "X_CONST":
        x = float(surface.vertices[0][0])
        verts = [(x, u0, z0), (x, u1, z0), (x, u1, z1), (x, u0, z1)]
    else:
        y = float(surface.vertices[0][1])
        verts = [(u0, y, z0), (u1, y, z0), (u1, y, z1), (u0, y, z1)]
    return SurfaceSpec(
        id=sid,
        name=surface.name,
        kind=surface.kind,
        vertices=verts,
        normal=surface.normal,
        room_id=surface.room_id,
        material_id=surface.material_id,
    )


def _subtract_opening_from_rect_surface(surface: SurfaceSpec, opening: OpeningSpec, eps: float = 1e-6) -> Optional[List[SurfaceSpec]]:
    axis = _wall_axis(surface, eps=eps)
    if axis is None:
        return None
    su0, su1, sz0, sz1 = _surface_rect_uv(surface, axis)
    ou0, ou1, oz0, oz1 = _opening_rect_uv(opening, axis)
    iu0, iu1 = max(su0, ou0), min(su1, ou1)
    iz0, iz1 = max(sz0, oz0), min(sz1, oz1)
    if (iu1 - iu0) <= eps or (iz1 - iz0) <= eps:
        return None

    out: List[SurfaceSpec] = []
    # Left strip
    if (iu0 - su0) > eps:
        out.append(_uv_rect_to_surface(surface, axis, su0, iu0, sz0, sz1, sid=surface.id))
    # Right strip
    if (su1 - iu1) > eps:
        sid = f"{surface.id}:right" if out else surface.id
        out.append(_uv_rect_to_surface(surface, axis, iu1, su1, sz0, sz1, sid=sid))
    # Bottom strip
    if (iz0 - sz0) > eps:
        sid = f"{surface.id}:bottom" if out else surface.id
        out.append(_uv_rect_to_surface(surface, axis, iu0, iu1, sz0, iz0, sid=sid))
    # Top strip
    if (sz1 - iz1) > eps:
        sid = f"{surface.id}:top" if out else surface.id
        out.append(_uv_rect_to_surface(surface, axis, iu0, iu1, iz1, sz1, sid=sid))
    return out if out else None


def _apply_opening_subtractions(
    surfaces: List[SurfaceSpec],
    openings: List[OpeningSpec],
) -> Tuple[List[SurfaceSpec], List[str]]:
    warnings: List[str] = []
    by_host: Dict[str, List[OpeningSpec]] = {}
    for o in openings:
        if o.host_surface_id:
            by_host.setdefault(o.host_surface_id, []).append(o)
    if not by_host:
        return surfaces, warnings

    out: List[SurfaceSpec] = []
    for s in surfaces:
        host_openings = by_host.get(s.id, [])
        if not host_openings:
            out.append(s)
            continue

        try:
            origin, u, v, _n = wall_basis(s)
            wall_uv = project_points_to_uv(s.vertices, origin, u, v)
            opening_uvs = [opening_uv_polygon(op, s) for op in host_openings]
            cut = subtract_openings(UVPolygon(outer=wall_uv), opening_uvs)
            polygons = [cut] if isinstance(cut, UVPolygon) else list(cut.polygons)
            if not polygons:
                warnings.append(f"Opening subtraction removed entire host wall {s.id}; host surface retained unchanged.")
                out.append(s)
                continue

            k = 0
            for poly in polygons:
                if poly.holes:
                    mesh = wall_mesh_from_uv(poly, origin, u, v)
                    for a, b, c in mesh.faces:
                        sid = s.id if k == 0 else f"{s.id}:tri{k}"
                        out.append(
                            SurfaceSpec(
                                id=sid,
                                name=s.name,
                                kind=s.kind,
                                vertices=[mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]],
                                normal=s.normal,
                                room_id=s.room_id,
                                material_id=s.material_id,
                            )
                        )
                        k += 1
                    continue
                sid = s.id if k == 0 else f"{s.id}:part{k}"
                out.append(
                    SurfaceSpec(
                        id=sid,
                        name=s.name,
                        kind=s.kind,
                        vertices=lift_uv_to_3d(poly.outer, origin, u, v),
                        normal=s.normal,
                        room_id=s.room_id,
                        material_id=s.material_id,
                    )
                )
                k += 1
        except Exception:
            warnings.append(f"Opening tagged but not subtracted from host {s.id} (unsupported host geometry).")
            out.append(s)
    return out, warnings


def _derive_rooms_from_wall_surfaces(
    surfaces: List[SurfaceSpec],
    *,
    min_xy_span: float = 0.25,
    min_z_span: float = 1.8,
) -> Tuple[List[RoomSpec], List[str]]:
    walls = [s for s in surfaces if str(s.kind).lower() == "wall" and len(s.vertices) >= 3]
    if not walls:
        return [], []

    wall_boxes: List[Tuple[float, float, float, float, float, float]] = []
    for s in walls:
        xs = [float(v[0]) for v in s.vertices]
        ys = [float(v[1]) for v in s.vertices]
        zs = [float(v[2]) for v in s.vertices]
        wall_boxes.append((min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)))

    # Build connected components from XY bbox proximity/overlap.
    tol = 0.5
    n = len(wall_boxes)
    adj: Dict[int, set[int]] = {i: set() for i in range(n)}
    for i in range(n):
        ax0, ay0, _az0, ax1, ay1, _az1 = wall_boxes[i]
        for j in range(i + 1, n):
            bx0, by0, _bz0, bx1, by1, _bz1 = wall_boxes[j]
            overlap_x = min(ax1, bx1) - max(ax0, bx0)
            overlap_y = min(ay1, by1) - max(ay0, by0)
            close_x = max(0.0, max(ax0 - bx1, bx0 - ax1))
            close_y = max(0.0, max(ay0 - by1, by0 - ay1))
            if overlap_x >= -tol and overlap_y >= -tol:
                adj[i].add(j)
                adj[j].add(i)
                continue
            if close_x <= tol and close_y <= tol:
                adj[i].add(j)
                adj[j].add(i)

    comps: List[List[int]] = []
    seen: set[int] = set()
    for i in range(n):
        if i in seen:
            continue
        stack = [i]
        comp: List[int] = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(list(adj.get(cur, ())))
        comps.append(comp)

    rooms: List[RoomSpec] = []
    warnings: List[str] = []
    for ri, comp in enumerate(comps):
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = []
        for wi in comp:
            x0, y0, z0, x1, y1, z1 = wall_boxes[wi]
            xs.extend([x0, x1])
            ys.extend([y0, y1])
            zs.extend([z0, z1])
        if not xs or not ys or not zs:
            continue
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        w = max_x - min_x
        l = max_y - min_y
        h = max_z - min_z
        if w < min_xy_span or l < min_xy_span or h < min_z_span:
            continue
        rid = f"ifc_derived_room_{ri+1}"
        rooms.append(
            RoomSpec(
                id=rid,
                name=f"Derived Room {ri+1}",
                width=float(w),
                length=float(l),
                height=float(h),
                origin=(float(min_x), float(min_y), float(min_z)),
                footprint=[(float(min_x), float(min_y)), (float(max_x), float(min_y)), (float(max_x), float(max_y)), (float(min_x), float(max_y))],
            )
        )

    if rooms:
        warnings.append(
            "IfcSpace missing: derived room envelopes from wall surfaces (gap/overlap healing via tolerance-based enclosure)."
        )
    return rooms, warnings


def _ensure_floor_ceiling_for_rooms(rooms: List[RoomSpec], surfaces: List[SurfaceSpec]) -> List[SurfaceSpec]:
    out = list(surfaces)
    by_room_and_kind: set[Tuple[str, str]] = set()
    for s in surfaces:
        if s.room_id and s.kind in {"floor", "ceiling"}:
            by_room_and_kind.add((s.room_id, s.kind))
    for room in rooms:
        x0, y0, z0 = room.origin
        x1 = x0 + float(room.width)
        y1 = y0 + float(room.length)
        z1 = z0 + float(room.height)
        if (room.id, "floor") not in by_room_and_kind:
            out.append(
                SurfaceSpec(
                    id=f"{room.id}_floor",
                    name=f"{room.name} Floor",
                    kind="floor",
                    room_id=room.id,
                    vertices=[(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
                )
            )
        if (room.id, "ceiling") not in by_room_and_kind:
            out.append(
                SurfaceSpec(
                    id=f"{room.id}_ceiling",
                    name=f"{room.name} Ceiling",
                    kind="ceiling",
                    room_id=room.id,
                    vertices=[(x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)],
                )
            )
    return out


def _extract_ifcgeom_surfaces(
    model,
    ifcgeom,
    scale: float,
    element_room_id_map: Optional[Dict[int, str]] = None,
) -> List[SurfaceSpec]:
    surfaces: List[SurfaceSpec] = []
    room_map = element_room_id_map or {}
    try:
        settings = ifcgeom.settings()
    except Exception:
        return surfaces
    idx = 0
    for entity_name in ("IfcWall", "IfcSlab", "IfcRoof", "IfcCovering", "IfcPlate"):
        try:
            entities = list(model.by_type(entity_name))
        except Exception:
            entities = []
        for ent in entities:
            try:
                shape = ifcgeom.create_shape(settings, ent)
                verts = getattr(shape.geometry, "verts", None)
                faces = getattr(shape.geometry, "faces", None)
                if not verts or not faces:
                    continue
                pts = [(float(verts[i]) * scale, float(verts[i + 1]) * scale, float(verts[i + 2]) * scale) for i in range(0, len(verts), 3)]
                for j in range(0, len(faces), 3):
                    a, b, c = int(faces[j]), int(faces[j + 1]), int(faces[j + 2])
                    if min(a, b, c) < 0 or max(a, b, c) >= len(pts):
                        continue
                    idx += 1
                    surfaces.append(
                        SurfaceSpec(
                            id=f"ifc_geom_surface_{idx}",
                            name=f"{entity_name} Face {idx}",
                            kind="wall" if entity_name == "IfcWall" else "floor" if entity_name == "IfcSlab" else "custom",
                            room_id=room_map.get(int(ent.id())),
                            vertices=[pts[a], pts[b], pts[c]],
                        )
                    )
            except Exception:
                continue
    return surfaces


def import_ifc(path: Path, options: IFCImportOptions | None = None) -> ImportedIFC:
    options = options or IFCImportOptions()
    text = path.read_text(encoding="utf-8", errors="replace")
    inferred_unit = _normalize_unit(options.length_unit_override or _infer_unit_from_ifc_text(text))
    scale = float(options.scale_to_meters_override if options.scale_to_meters_override is not None else unit_scale_to_m(inferred_unit))

    warnings: List[str] = []
    boundary_method = "bbox"
    levels: List[LevelSpec] = []
    rooms: List[RoomSpec] = []
    openings: List[OpeningSpec] = []
    surfaces: List[SurfaceSpec] = []
    obstructions: List[ObstructionSpec] = []

    # Prefer ifcopenshell when available; fallback parser keeps smoke functionality.
    model = None
    ifcgeom = None
    try:
        import ifcopenshell  # type: ignore

        model = ifcopenshell.open(str(path))
        try:
            import ifcopenshell.geom as ifcgeom  # type: ignore
        except Exception:
            ifcgeom = None
    except Exception:
        warnings.append("IFC parsed via fallback text parser (ifcopenshell unavailable).")

    if model is not None:
        # Units from IfcUnitAssignment when no override provided.
        if options.length_unit_override is None and options.scale_to_meters_override is None:
            try:
                ua = model.by_type("IfcUnitAssignment")
                if ua:
                    for uu in getattr(ua[0], "Units", []) or []:
                        if str(getattr(uu, "UnitType", "")).upper() != "LENGTHUNIT":
                            continue
                        name = str(getattr(uu, "Name", "")).upper()
                        prefix = str(getattr(uu, "Prefix", "")).upper()
                        if "METRE" in name:
                            inferred_unit = "mm" if prefix == "MILLI" else "cm" if prefix == "CENTI" else "m"
                        elif "FOOT" in name:
                            inferred_unit = "ft"
                        elif "INCH" in name:
                            inferred_unit = "in"
                        scale = float(options.scale_to_meters_override if options.scale_to_meters_override is not None else unit_scale_to_m(inferred_unit))
                        break
            except Exception:
                warnings.append("Failed reading IfcUnitAssignment; using inferred/default units.")

        for i, lvl in enumerate(model.by_type("IfcBuildingStorey")):
            name = getattr(lvl, "Name", None) or f"Level {i+1}"
            elev = float(getattr(lvl, "Elevation", 0.0) or 0.0) * scale
            levels.append(LevelSpec(id=f"ifc_level_{i+1}", name=str(name), elevation=elev))

        spaces = model.by_type("IfcSpace")
        room_by_space_step_id: Dict[int, RoomSpec] = {}
        for i, sp in enumerate(spaces):
            name = getattr(sp, "LongName", None) or getattr(sp, "Name", None) or f"IFC Space {i+1}"
            rid = f"ifc_space_{i+1}"
            # Conservative bbox fallback dimensions.
            w, l, h = options.fallback_room_size
            rooms.append(
                RoomSpec(
                    id=rid,
                    name=str(name),
                    width=float(w) * scale,
                    length=float(l) * scale,
                    height=float(h) * scale,
                    origin=(float(i) * float(w) * scale, 0.0, 0.0),
                )
            )
            try:
                room_by_space_step_id[int(sp.id())] = rooms[-1]
            except Exception:
                pass

        boundary_element_to_room: Dict[int, str] = {}
        boundary_conflicts = 0
        try:
            for rel in model.by_type("IfcRelSpaceBoundary"):
                space = getattr(rel, "RelatingSpace", None)
                elem = getattr(rel, "RelatedBuildingElement", None)
                if space is None or elem is None:
                    continue
                room = room_by_space_step_id.get(int(space.id()))
                if room is None:
                    continue
                eid = int(elem.id())
                prev = boundary_element_to_room.get(eid)
                picked = _pick_preferred_room(prev, room.id)
                if prev is not None and prev != picked:
                    boundary_conflicts += 1
                if picked is not None:
                    boundary_element_to_room[eid] = picked
        except Exception:
            warnings.append("Failed reading IfcRelSpaceBoundary relationships for surface ownership.")
        if boundary_element_to_room:
            boundary_method = "relspaceboundary"
        if boundary_conflicts > 0:
            warnings.append(
                f"IfcRelSpaceBoundary ownership conflicts resolved deterministically for {boundary_conflicts} elements."
            )

        if ifcgeom is not None:
            geom_surfaces = _extract_ifcgeom_surfaces(model, ifcgeom, scale, element_room_id_map=boundary_element_to_room)
            if geom_surfaces:
                surfaces.extend(geom_surfaces)
                if boundary_method != "relspaceboundary":
                    boundary_method = "geometry"
            else:
                warnings.append("ifcopenshell.geom returned no surface faces; using fallback room boxes.")
        if not surfaces:
            for room in rooms:
                surfaces.extend(_room_box_surfaces(room))

        opening_by_window_step_id: Dict[int, OpeningSpec] = {}
        for i, win in enumerate(model.by_type("IfcWindow")):
            name = getattr(win, "Name", None) or f"Window {i+1}"
            oid = f"ifc_window_{i+1}"
            room = rooms[i % len(rooms)] if rooms else None
            if room is None:
                x0 = float(i) * 2.0 * scale
                y0 = 0.0
                z_base = 1.0 * scale
                z_top = 2.5 * scale
                host_surface_id = None
            else:
                x0, y0, z0 = room.origin
                z_base = z0 + min(room.height * 0.35, 1.0 * scale)
                z_top = min(z0 + room.height * 0.85, z0 + room.height - 0.05)
                x0 = x0 + min(room.width * 0.25, room.width - 0.2)
                host_surface_id = _default_window_host_surface(room.id)
                # Place on south wall plane of room box.
            verts = [(x0, 0.0, 1.0 * scale), (x0 + 1.5 * scale, 0.0, 1.0 * scale), (x0 + 1.5 * scale, 0.0, 2.5 * scale), (x0, 0.0, 2.5 * scale)]
            openings.append(
                OpeningSpec(
                    id=oid,
                    name=str(name),
                    opening_type="window",
                    kind="window",
                    host_surface_id=host_surface_id,
                    vertices=[(verts[0][0], y0, z_base), (verts[1][0], y0, z_base), (verts[1][0], y0, z_top), (verts[0][0], y0, z_top)],
                    is_daylight_aperture=True,
                    vt=float(options.default_window_transmittance),
                    visible_transmittance=float(options.default_window_transmittance),
                )
            )
            try:
                opening_by_window_step_id[int(win.id())] = openings[-1]
            except Exception:
                pass

        # Prefer IFC boundary relationships when present for opening host assignment.
        opening_window_room: Dict[int, str] = {}
        opening_boundary_conflicts = 0
        try:
            for rel in model.by_type("IfcRelSpaceBoundary"):
                space = getattr(rel, "RelatingSpace", None)
                elem = getattr(rel, "RelatedBuildingElement", None)
                if space is None or elem is None:
                    continue
                if str(getattr(elem, "is_a", lambda: "")()).lower() != "ifcwindow":
                    continue
                room = room_by_space_step_id.get(int(space.id()))
                opening = opening_by_window_step_id.get(int(elem.id()))
                if room is None or opening is None:
                    continue
                wid = int(elem.id())
                prev = opening_window_room.get(wid)
                picked = _pick_preferred_room(prev, room.id)
                if prev is not None and prev != picked:
                    opening_boundary_conflicts += 1
                if picked is not None:
                    opening_window_room[wid] = picked
            for wid, room_id in opening_window_room.items():
                opening = opening_by_window_step_id.get(wid)
                if opening is not None:
                    opening.host_surface_id = _default_window_host_surface(room_id)
        except Exception:
            warnings.append("Failed reading IfcRelSpaceBoundary relationships for opening mapping.")
        if opening_boundary_conflicts > 0:
            warnings.append(
                f"IfcRelSpaceBoundary opening conflicts resolved deterministically for {opening_boundary_conflicts} windows."
            )

        if ifcgeom is None:
            warnings.append("ifcopenshell.geom unavailable; imported metadata + fallback room/opening geometry.")
    else:
        # Fallback line-based extraction for tests and minimal ingestion.
        for i, args in enumerate(_extract_ifc_entities(text, "IFCBUILDINGSTOREY")):
            levels.append(LevelSpec(id=f"ifc_level_{i+1}", name=_extract_name(args, f"Level {i+1}"), elevation=0.0))
        spaces = _extract_ifc_entities_with_ids(text, "IFCSPACE")
        room_by_space_step_id: Dict[int, RoomSpec] = {}
        for i, (sid, args) in enumerate(spaces):
            w, l, h = options.fallback_room_size
            rooms.append(
                RoomSpec(
                    id=f"ifc_space_{i+1}",
                    name=_extract_name(args, f"IFC Space {i+1}"),
                    width=float(w) * scale,
                    length=float(l) * scale,
                    height=float(h) * scale,
                    origin=(float(i) * float(w) * scale, 0.0, 0.0),
                )
            )
            room_by_space_step_id[int(sid)] = rooms[-1]
        for room in rooms:
            surfaces.extend(_room_box_surfaces(room))
        boundary_rows = _extract_ifc_entities_with_ids(text, "IFCRELSPACEBOUNDARY")
        walls = _extract_ifc_entities_with_ids(text, "IFCWALL")
        wall_ids = {wid for wid, _ in walls}
        wall_room_map, wall_conflicts = _build_boundary_room_map_from_rows(boundary_rows, room_by_space_step_id, target_element_ids=wall_ids)
        if wall_room_map:
            boundary_method = "relspaceboundary"
        for i, (wid, args) in enumerate(walls):
            name = _extract_name(args, f"Wall {i+1}")
            surfaces.append(
                _fallback_surface_for_linear_element(
                    prefix="ifc_wall",
                    index=i,
                    name=name,
                    room_id=wall_room_map.get(wid),
                    scale=scale,
                    kind="wall",
                )
            )
        if wall_conflicts > 0:
            warnings.append(
                f"Fallback IFCRELSPACEBOUNDARY ownership conflicts resolved deterministically for {wall_conflicts} elements."
            )
        extra_element_specs = [
            ("IFCSLAB", "ifc_slab", "floor"),
            ("IFCCOVERING", "ifc_covering", "custom"),
            ("IFCROOF", "ifc_roof", "ceiling"),
            ("IFCPLATE", "ifc_plate", "custom"),
        ]
        for entity_name, prefix, kind in extra_element_specs:
            elems = _extract_ifc_entities_with_ids(text, entity_name)
            if not elems:
                continue
            elem_ids = {eid for eid, _ in elems}
            elem_room_map, elem_conflicts = _build_boundary_room_map_from_rows(
                boundary_rows,
                room_by_space_step_id,
                target_element_ids=elem_ids,
            )
            for i, (eid, args) in enumerate(elems):
                name = _extract_name(args, f"{entity_name.title()} {i+1}")
                surfaces.append(
                    _fallback_surface_for_linear_element(
                        prefix=prefix,
                        index=i,
                        name=name,
                        room_id=elem_room_map.get(eid),
                        scale=scale,
                        kind=kind,
                    )
                )
            if elem_conflicts > 0:
                warnings.append(
                    f"Fallback IFCRELSPACEBOUNDARY ownership conflicts resolved deterministically for {elem_conflicts} {entity_name} elements."
                )
        windows = _extract_ifc_entities_with_ids(text, "IFCWINDOW")
        opening_by_window_step_id: Dict[int, OpeningSpec] = {}
        for i, (wid, args) in enumerate(windows):
            name = _extract_name(args, f"Window {i+1}")
            room = rooms[i % len(rooms)] if rooms else None
            if room is None:
                x0 = float(i) * 2.0 * scale
                y0 = 0.0
                z_base = 1.0 * scale
                z_top = 2.5 * scale
                host_surface_id = None
            else:
                x0, y0, z0 = room.origin
                z_base = z0 + min(room.height * 0.35, 1.0 * scale)
                z_top = min(z0 + room.height * 0.85, z0 + room.height - 0.05)
                x0 = x0 + min(room.width * 0.25, room.width - 0.2)
                host_surface_id = _default_window_host_surface(room.id)
            opening = OpeningSpec(
                id=f"ifc_window_{i+1}",
                name=name,
                opening_type="window",
                kind="window",
                host_surface_id=host_surface_id,
                vertices=[(x0, y0, z_base), (x0 + 1.5 * scale, y0, z_base), (x0 + 1.5 * scale, y0, z_top), (x0, y0, z_top)],
                is_daylight_aperture=True,
                vt=float(options.default_window_transmittance),
                visible_transmittance=float(options.default_window_transmittance),
            )
            openings.append(opening)
            opening_by_window_step_id[int(wid)] = opening

        # Parse fallback space boundary relations and remap window host surfaces.
        opening_window_room, boundary_conflicts = _build_boundary_room_map_from_rows(
            boundary_rows,
            room_by_space_step_id,
            target_element_ids=set(opening_by_window_step_id.keys()),
        )
        for wid, room_id in opening_window_room.items():
            opening_by_window_step_id[wid].host_surface_id = _default_window_host_surface(room_id)
        if boundary_conflicts > 0:
            warnings.append(
                f"Fallback IFCRELSPACEBOUNDARY conflicts resolved deterministically for {boundary_conflicts} windows."
            )

    if not rooms:
        warnings.append("No IfcSpace entities found.")
        derived_rooms, derive_warnings = _derive_rooms_from_wall_surfaces(surfaces)
        rooms.extend(derived_rooms)
        warnings.extend(derive_warnings)
        if rooms:
            surfaces = _ensure_floor_ceiling_for_rooms(rooms, surfaces)

    source_conv = AxisConvention(
        up_axis=("Y_UP" if str(options.source_up_axis).upper() == "Y_UP" else "Z_UP"),  # type: ignore[arg-type]
        handedness=("LEFT_HANDED" if str(options.source_handedness).upper() == "LEFT_HANDED" else "RIGHT_HANDED"),  # type: ignore[arg-type]
    )
    axis_report = describe_axis_conversion(source_conv, AxisConvention())
    m4 = np.array(axis_report.matrix, dtype=float)
    if axis_report.axis_transform_applied != "Z_UP/RIGHT_HANDED->Z_UP/RIGHT_HANDED":
        rooms = [_apply_axis_to_room(r, m4) for r in rooms]
        surfaces = [
            SurfaceSpec(
                id=s.id,
                name=s.name,
                kind=s.kind,
                vertices=_apply_axis_to_points(list(s.vertices), m4),
                normal=s.normal,
                room_id=s.room_id,
                material_id=s.material_id,
            )
            for s in surfaces
        ]
        openings = [
            OpeningSpec(
                id=o.id,
                name=o.name,
                opening_type=o.opening_type,
                kind=o.kind,
                host_surface_id=o.host_surface_id,
                vertices=_apply_axis_to_points(list(o.vertices), m4),
                is_daylight_aperture=o.is_daylight_aperture,
                vt=o.vt,
                frame_fraction=o.frame_fraction,
                shade_factor=o.shade_factor,
                visible_transmittance=o.visible_transmittance,
                shading_factor=o.shading_factor,
            )
            for o in openings
        ]
        obstructions = [
            ObstructionSpec(
                id=o.id,
                name=o.name,
                kind=o.kind,
                vertices=_apply_axis_to_points(list(o.vertices), m4),
                height=o.height,
            )
            for o in obstructions
        ]
        warnings.append(f"axis_transform_applied={axis_report.axis_transform_applied}")

    surfaces, subtract_warnings = _apply_opening_subtractions(surfaces, openings)
    warnings.extend(subtract_warnings)

    return ImportedIFC(
        source_file=str(path),
        coordinate_system={
            "length_unit": inferred_unit,
            "source_length_unit": inferred_unit,
            "scale_to_meters": scale,
            "axis_transform_applied": axis_report.axis_transform_applied,
            "axis_matrix": axis_report.matrix,
        },
        levels=levels,
        rooms=rooms,
        openings=openings,
        surfaces=surfaces,
        obstructions=obstructions,
        ifc_space_boundary_method=boundary_method,
        warnings=warnings,
    )
