from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from luxera.io.dxf_import import extract_rooms_from_dxf, load_dxf
from luxera.project.schema import RoomSpec, SurfaceSpec


@dataclass(frozen=True)
class GeometryImportResult:
    source_file: str
    format: str
    rooms: List[RoomSpec] = field(default_factory=list)
    surfaces: List[SurfaceSpec] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _infer_format(path: Path, fmt: Optional[str]) -> str:
    if fmt:
        return fmt.upper()
    return path.suffix.replace(".", "").upper()


def _import_dxf(path: Path, scale: float = 1.0) -> GeometryImportResult:
    doc = load_dxf(path)
    rooms = extract_rooms_from_dxf(doc, scale=scale)
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
    return GeometryImportResult(source_file=str(path), format="DXF", rooms=room_specs)


def _parse_obj(path: Path) -> Tuple[List[Tuple[float, float, float]], List[List[int]]]:
    vertices: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("v "):
            parts = s.split()
            if len(parts) >= 4:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif s.startswith("f "):
            idxs: List[int] = []
            parts = s.split()[1:]
            for p in parts:
                tok = p.split("/")[0]
                if not tok:
                    continue
                idx = int(tok)
                if idx < 0:
                    idx = len(vertices) + idx + 1
                idxs.append(idx - 1)
            if len(idxs) >= 3:
                faces.append(idxs)
    return vertices, faces


def _import_obj(path: Path) -> GeometryImportResult:
    vertices, faces = _parse_obj(path)
    surfaces: List[SurfaceSpec] = []
    for i, face in enumerate(faces):
        pts = [vertices[idx] for idx in face if 0 <= idx < len(vertices)]
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
    return GeometryImportResult(source_file=str(path), format="OBJ", surfaces=surfaces)


def _import_gltf(path: Path) -> GeometryImportResult:
    warnings: List[str] = []
    surfaces: List[SurfaceSpec] = []
    try:
        import trimesh  # type: ignore
    except Exception:
        return GeometryImportResult(
            source_file=str(path),
            format="GLTF",
            warnings=["GLTF import requires trimesh to be installed."],
        )

    scene = trimesh.load(str(path), force="scene")
    mesh_index = 0
    for _, geom in scene.geometry.items():
        mesh = geom
        if not hasattr(mesh, "faces"):
            continue
        verts = mesh.vertices
        faces = mesh.faces
        for f in faces:
            mesh_index += 1
            pts = [
                (float(verts[f[0]][0]), float(verts[f[0]][1]), float(verts[f[0]][2])),
                (float(verts[f[1]][0]), float(verts[f[1]][1]), float(verts[f[1]][2])),
                (float(verts[f[2]][0]), float(verts[f[2]][1]), float(verts[f[2]][2])),
            ]
            surfaces.append(
                SurfaceSpec(
                    id=f"gltf_surface_{mesh_index}",
                    name=f"GLTF Surface {mesh_index}",
                    kind="custom",
                    vertices=pts,
                )
            )
    if not surfaces:
        warnings.append("No mesh surfaces found in GLTF.")
    return GeometryImportResult(source_file=str(path), format="GLTF", surfaces=surfaces, warnings=warnings)


def _import_ifc(path: Path) -> GeometryImportResult:
    warnings: List[str] = []
    rooms: List[RoomSpec] = []
    surfaces: List[SurfaceSpec] = []
    try:
        import ifcopenshell  # type: ignore
    except Exception:
        return GeometryImportResult(
            source_file=str(path),
            format="IFC",
            warnings=["IFC import requires ifcopenshell to be installed."],
        )

    model = ifcopenshell.open(str(path))
    spaces = model.by_type("IfcSpace")
    shape_mod = None
    settings = None
    try:
        import ifcopenshell.geom as ifcgeom  # type: ignore
        shape_mod = ifcgeom
        settings = ifcgeom.settings()
        try:
            settings.set(settings.USE_WORLD_COORDS, True)
        except Exception:
            pass
    except Exception:
        warnings.append("IFC geometry kernel unavailable; falling back to metadata extraction.")

    def _mesh_from_space(space_obj) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
        if shape_mod is None or settings is None:
            return [], []
        try:
            shape = shape_mod.create_shape(settings, space_obj)
            g = shape.geometry
            vflat = list(getattr(g, "verts", []) or [])
            fflat = list(getattr(g, "faces", []) or [])
            verts: List[Tuple[float, float, float]] = []
            tris: List[Tuple[int, int, int]] = []
            for i in range(0, len(vflat), 3):
                verts.append((float(vflat[i]), float(vflat[i + 1]), float(vflat[i + 2])))
            for i in range(0, len(fflat), 3):
                a = int(fflat[i])
                b = int(fflat[i + 1])
                c = int(fflat[i + 2])
                if a >= 0 and b >= 0 and c >= 0 and a < len(verts) and b < len(verts) and c < len(verts):
                    tris.append((a, b, c))
            return verts, tris
        except Exception:
            return [], []

    def _bbox_room(room_id: str, room_name: str, verts: List[Tuple[float, float, float]]) -> Optional[RoomSpec]:
        if not verts:
            return None
        xs = [p[0] for p in verts]
        ys = [p[1] for p in verts]
        zs = [p[2] for p in verts]
        mnx, mxx = min(xs), max(xs)
        mny, mxy = min(ys), max(ys)
        mnz, mxz = min(zs), max(zs)
        w, l, h = (mxx - mnx), (mxy - mny), (mxz - mnz)
        if w <= 1e-6 or l <= 1e-6 or h <= 1e-6:
            return None
        return RoomSpec(id=room_id, name=room_name, width=w, length=l, height=h, origin=(mnx, mny, mnz))

    for i, sp in enumerate(spaces):
        name = getattr(sp, "LongName", None) or getattr(sp, "Name", None) or f"IFC Space {i+1}"
        room_id = f"ifc_space_{i+1}"
        verts, tris = _mesh_from_space(sp)
        room_spec = _bbox_room(room_id, str(name), verts)
        if room_spec is not None:
            rooms.append(room_spec)
            for ti, tri in enumerate(tris):
                pts = [verts[tri[0]], verts[tri[1]], verts[tri[2]]]
                surfaces.append(
                    SurfaceSpec(
                        id=f"{room_id}_surface_{ti+1}",
                        name=f"{name} Surface {ti+1}",
                        kind="custom",
                        vertices=pts,
                        room_id=room_id,
                    )
                )
        else:
            # Conservative fallback dimensions if geometry extraction is unavailable.
            rooms.append(
                RoomSpec(
                    id=room_id,
                    name=str(name),
                    width=5.0,
                    length=5.0,
                    height=3.0,
                )
            )
            warnings.append(f"IFC space '{name}' imported without mesh geometry; using placeholder dimensions.")
    if not rooms:
        warnings.append("No IfcSpace entities found.")
    return GeometryImportResult(source_file=str(path), format="IFC", rooms=rooms, surfaces=surfaces, warnings=warnings)


def import_geometry_file(path: str, fmt: Optional[str] = None, dxf_scale: float = 1.0) -> GeometryImportResult:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Geometry file not found: {p}")

    format_used = _infer_format(p, fmt)
    if format_used == "DXF":
        return _import_dxf(p, scale=dxf_scale)
    if format_used == "OBJ":
        return _import_obj(p)
    if format_used in {"GLTF", "GLB"}:
        return _import_gltf(p)
    if format_used == "IFC":
        return _import_ifc(p)
    raise ValueError(f"Unsupported geometry format: {format_used}")
