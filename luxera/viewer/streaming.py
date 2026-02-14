from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from luxera.geometry.lod import build_lod
from luxera.geometry.mesh import TriMesh
from luxera.geometry.triangulate import triangulate_polygon_vertices
from luxera.project.schema import Project, SurfaceSpec
from luxera.viewer.mesh import Mesh, mesh_from_trimesh


@dataclass(frozen=True)
class StoreyChunk:
    chunk_id: str
    storey_id: str
    surface_ids: Tuple[str, ...]
    calc_mesh: TriMesh
    viewport_mesh: Mesh


def _surface_to_trimesh(surface: SurfaceSpec) -> Optional[TriMesh]:
    verts = list(surface.vertices)
    if len(verts) < 3:
        return None

    tri_verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    for a, b, c in triangulate_polygon_vertices(verts):
        ia = len(tri_verts)
        tri_verts.extend([(float(a[0]), float(a[1]), float(a[2])), (float(b[0]), float(b[1]), float(b[2])), (float(c[0]), float(c[1]), float(c[2]))])
        faces.append((ia, ia + 1, ia + 2))

    if not faces:
        return None

    mesh = TriMesh(vertices=tri_verts, faces=faces)
    mesh.validate()
    return mesh


def _combine_meshes(meshes: Sequence[TriMesh]) -> Optional[TriMesh]:
    if not meshes:
        return None
    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    base = 0
    for m in meshes:
        vertices.extend((float(x), float(y), float(z)) for x, y, z in m.vertices)
        faces.extend((a + base, b + base, c + base) for a, b, c in m.faces)
        base += len(m.vertices)
    if not faces:
        return None
    out = TriMesh(vertices=vertices, faces=faces)
    out.validate()
    return out


def _infer_storey_id(surface: SurfaceSpec, room_level_by_id: Mapping[str, str]) -> str:
    if surface.room_id and surface.room_id in room_level_by_id:
        return room_level_by_id[surface.room_id]
    if not surface.vertices:
        return "storey_0"
    z_avg = sum(float(v[2]) for v in surface.vertices) / float(len(surface.vertices))
    idx = int(z_avg // 3.5)
    return f"storey_{idx}"


def build_storey_chunks(
    project: Project,
    *,
    viewport_ratio: float = 0.4,
    include_kinds: Optional[Iterable[str]] = None,
) -> List[StoreyChunk]:
    kinds = set(include_kinds) if include_kinds is not None else {"wall", "floor", "ceiling", "custom"}
    room_level_by_id: Dict[str, str] = {r.id: r.level_id for r in project.geometry.rooms if r.level_id}

    surfaces_by_storey: Dict[str, List[SurfaceSpec]] = {}
    for s in project.geometry.surfaces:
        if kinds and s.kind not in kinds:
            continue
        sid = _infer_storey_id(s, room_level_by_id)
        surfaces_by_storey.setdefault(sid, []).append(s)

    chunks: List[StoreyChunk] = []
    for storey_id in sorted(surfaces_by_storey):
        meshes = [m for m in (_surface_to_trimesh(s) for s in surfaces_by_storey[storey_id]) if m is not None]
        merged = _combine_meshes(meshes)
        if merged is None:
            continue
        lod = build_lod(merged, viewport_ratio=viewport_ratio)
        viewport = mesh_from_trimesh(lod.simplified, use_lod=False)
        chunks.append(
            StoreyChunk(
                chunk_id=f"chunk:{storey_id}",
                storey_id=storey_id,
                surface_ids=tuple(s.id for s in surfaces_by_storey[storey_id]),
                calc_mesh=lod.full,
                viewport_mesh=viewport,
            )
        )
    return chunks


def filter_chunks_for_storeys(chunks: Sequence[StoreyChunk], visible_storeys: Optional[Set[str]]) -> List[StoreyChunk]:
    if not visible_storeys:
        return list(chunks)
    return [c for c in chunks if c.storey_id in visible_storeys]
