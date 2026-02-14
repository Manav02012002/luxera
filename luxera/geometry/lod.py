from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from luxera.geometry.mesh import TriMesh


@dataclass(frozen=True)
class LODMesh:
    full: TriMesh
    simplified: TriMesh


@dataclass(frozen=True)
class LODChunk:
    chunk_id: str
    storey_id: str
    viewport: TriMesh
    calc: TriMesh


def mesh_bounds(mesh: TriMesh) -> Tuple[np.ndarray, np.ndarray]:
    v = np.asarray(mesh.vertices, dtype=float)
    return v.min(axis=0), v.max(axis=0)


def simplify_mesh(mesh: TriMesh, ratio: float = 0.5) -> TriMesh:
    """Deterministic face decimation for viewport LOD."""
    if not mesh.faces:
        return TriMesh(vertices=list(mesh.vertices), faces=[])
    r = max(0.05, min(1.0, float(ratio)))
    keep_n = max(1, int(round(len(mesh.faces) * r)))

    # Deterministic sampling in input face order.
    step = max(1, int(round(len(mesh.faces) / keep_n)))
    selected_faces = [mesh.faces[i] for i in range(0, len(mesh.faces), step)][:keep_n]

    used = sorted({idx for f in selected_faces for idx in f})
    remap = {old: new for new, old in enumerate(used)}
    new_vertices = [mesh.vertices[i] for i in used]
    new_faces = [(remap[a], remap[b], remap[c]) for a, b, c in selected_faces]

    # Preserve full-mesh bounds for viewer fit by appending bbox corner verts.
    mn, mx = mesh_bounds(mesh)
    corners = [
        (float(mn[0]), float(mn[1]), float(mn[2])),
        (float(mx[0]), float(mn[1]), float(mn[2])),
        (float(mx[0]), float(mx[1]), float(mn[2])),
        (float(mn[0]), float(mx[1]), float(mn[2])),
        (float(mn[0]), float(mn[1]), float(mx[2])),
        (float(mx[0]), float(mn[1]), float(mx[2])),
        (float(mx[0]), float(mx[1]), float(mx[2])),
        (float(mn[0]), float(mx[1]), float(mx[2])),
    ]
    new_vertices.extend(corners)

    out = TriMesh(vertices=new_vertices, faces=new_faces)
    out.validate()
    return out


def build_lod(full_mesh: TriMesh, viewport_ratio: float = 0.4) -> LODMesh:
    return LODMesh(full=full_mesh, simplified=simplify_mesh(full_mesh, ratio=viewport_ratio))


def infer_storey_id(mesh: TriMesh, floor_height: float = 3.5) -> str:
    mn, mx = mesh_bounds(mesh)
    z = 0.5 * (float(mn[2]) + float(mx[2]))
    idx = int(np.floor(z / max(float(floor_height), 0.5)))
    return f"storey_{idx}"


def build_lod_chunks(
    meshes: List[TriMesh],
    *,
    viewport_ratio: float = 0.4,
    storey_ids: Optional[List[str]] = None,
    floor_height: float = 3.5,
) -> List[LODChunk]:
    chunks: List[LODChunk] = []
    for i, mesh in enumerate(meshes):
        lod = build_lod(mesh, viewport_ratio=viewport_ratio)
        sid = storey_ids[i] if storey_ids and i < len(storey_ids) else infer_storey_id(mesh, floor_height=floor_height)
        chunks.append(LODChunk(chunk_id=f"chunk_{i}", storey_id=sid, viewport=lod.simplified, calc=lod.full))
    return chunks
