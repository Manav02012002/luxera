from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from luxera.core.units import unit_scale_to_m
from luxera.geometry.cleaning import (
    detect_open_mesh_edges,
    fix_winding_consistent_normals,
    merge_vertices as clean_merge_vertices,
    remove_degenerate_triangles,
)
from luxera.geometry.heal import heal_mesh
from luxera.geometry.triangulate import TriangulationConfig, canonicalize_mesh


Point3 = Tuple[float, float, float]


@dataclass(frozen=True)
class MeshImportResult:
    source_file: str
    format: str
    vertices: List[Point3]
    faces: List[Tuple[int, ...]]
    triangles: List[Tuple[int, int, int]]
    length_unit: str = "m"
    scale_to_meters: float = 1.0
    warnings: List[str] = field(default_factory=list)
    geometry_heal_report: dict = field(default_factory=dict)


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


def _parse_obj(path: Path) -> Tuple[List[Point3], List[Tuple[int, ...]]]:
    vertices: List[Point3] = []
    faces: List[Tuple[int, ...]] = []
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
            for p in s.split()[1:]:
                tok = p.split("/")[0]
                if not tok:
                    continue
                idx = int(tok)
                if idx < 0:
                    idx = len(vertices) + idx + 1
                idxs.append(idx - 1)
            if len(idxs) >= 3:
                faces.append(tuple(idxs))
    return vertices, faces


def _load_gltf_fallback(path: Path) -> Tuple[List[Point3], List[Tuple[int, ...]], List[str]]:
    """Fallback parser for JSON .gltf with embedded arrays only."""
    warnings: List[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))
    vertices_raw = data.get("extras", {}).get("vertices")
    faces_raw = data.get("extras", {}).get("faces")
    if not isinstance(vertices_raw, list) or not isinstance(faces_raw, list):
        raise ValueError("GLTF fallback expects extras.vertices and extras.faces arrays")
    vertices = [(float(v[0]), float(v[1]), float(v[2])) for v in vertices_raw]
    faces = [tuple(int(i) for i in f) for f in faces_raw if len(f) >= 3]
    warnings.append("Loaded GLTF using extras fallback parser.")
    return vertices, faces, warnings


def _parse_trimesh_scene(path: Path) -> Tuple[List[Point3], List[Tuple[int, ...]], List[str]]:
    warnings: List[str] = []
    try:
        import trimesh  # type: ignore
    except Exception as exc:
        raise RuntimeError("trimesh is required for this mesh format") from exc

    try:
        loaded = trimesh.load(str(path), force="scene")
    except Exception as exc:
        raise RuntimeError(f"Failed to load mesh via trimesh: {exc}") from exc
    vertices: List[Point3] = []
    faces: List[Tuple[int, ...]] = []
    v_offset = 0
    geometries = loaded.geometry
    for name in sorted(geometries.keys()):
        mesh = geometries[name]
        if not hasattr(mesh, "faces") or not hasattr(mesh, "vertices"):
            continue
        for v in mesh.vertices:
            vertices.append((float(v[0]), float(v[1]), float(v[2])))
        for face in mesh.faces:
            faces.append((int(face[0]) + v_offset, int(face[1]) + v_offset, int(face[2]) + v_offset))
        v_offset += len(mesh.vertices)
    if not faces:
        warnings.append("No mesh faces found in GLTF scene.")
    return vertices, faces, warnings


def _parse_gltf(path: Path) -> Tuple[List[Point3], List[Tuple[int, ...]], List[str]]:
    try:
        return _parse_trimesh_scene(path)
    except Exception:
        return _load_gltf_fallback(path)


def _parse_fbx(path: Path) -> Tuple[List[Point3], List[Tuple[int, ...]], List[str]]:
    vertices, faces, warnings = _parse_trimesh_scene(path)
    if not faces:
        warnings.append("No mesh faces found in FBX scene.")
    return vertices, faces, warnings


def _parse_skp(path: Path) -> Tuple[List[Point3], List[Tuple[int, ...]], List[str]]:
    vertices, faces, warnings = _parse_trimesh_scene(path)
    if not faces:
        warnings.append("No mesh faces found in SKP scene.")
    return vertices, faces, warnings


def import_mesh_file(
    path: str,
    fmt: Optional[str] = None,
    length_unit: Optional[str] = None,
    scale_to_meters: Optional[float] = None,
    triangulation: TriangulationConfig | None = None,
) -> MeshImportResult:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Mesh file not found: {p}")

    format_used = (fmt.upper() if fmt else p.suffix.replace(".", "").upper())
    unit = _normalize_unit(length_unit)
    scale = float(scale_to_meters if scale_to_meters is not None else unit_scale_to_m(unit))

    if format_used == "OBJ":
        vertices, faces = _parse_obj(p)
        warnings: List[str] = []
    elif format_used in {"GLTF", "GLB"}:
        vertices, faces, warnings = _parse_gltf(p)
    elif format_used == "FBX":
        vertices, faces, warnings = _parse_fbx(p)
    elif format_used == "SKP":
        vertices, faces, warnings = _parse_skp(p)
    else:
        raise ValueError(f"Unsupported mesh format: {format_used}")

    scaled_vertices = [(vx * scale, vy * scale, vz * scale) for (vx, vy, vz) in vertices]
    merged_vertices, normalized_faces, triangles = canonicalize_mesh(scaled_vertices, faces, config=triangulation)
    healed = heal_mesh(merged_vertices, triangles, deduplicate_coplanar_faces=False)
    merged_vertices = list(healed.vertices)
    triangles = list(healed.triangles)
    cleaned_vertices, remap = clean_merge_vertices(
        merged_vertices,
        eps=(triangulation.merge_epsilon if triangulation is not None else 1e-9),
    )
    remapped_triangles = [(remap[a], remap[b], remap[c]) for (a, b, c) in triangles]
    no_degenerate = remove_degenerate_triangles(remapped_triangles, cleaned_vertices, area_eps=1e-12)
    consistent = fix_winding_consistent_normals(no_degenerate, cleaned_vertices)
    open_edges = detect_open_mesh_edges(consistent)
    if open_edges:
        warnings.append(f"Mesh has {len(open_edges)} open boundary edges after cleaning.")

    return MeshImportResult(
        source_file=str(p),
        format=format_used,
        vertices=cleaned_vertices,
        faces=normalized_faces,
        triangles=consistent,
        length_unit=unit,
        scale_to_meters=scale,
        warnings=warnings,
        geometry_heal_report=healed.report.to_dict(),
    )
