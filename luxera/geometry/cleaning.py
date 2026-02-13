from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import numpy as np

from luxera.geometry.tolerance import EPS_AREA, EPS_POS, EPS_WELD


Point3 = Tuple[float, float, float]
TriangleIdx = Tuple[int, int, int]


def merge_vertices(vertices: Sequence[Point3], eps: float = EPS_WELD) -> tuple[List[Point3], List[int]]:
    inv = 1.0 / max(eps, EPS_POS)
    out: List[Point3] = []
    remap: List[int] = []
    bucket_to_idx: dict[tuple[int, int, int], int] = {}
    for x, y, z in vertices:
        b = (int(round(float(x) * inv)), int(round(float(y) * inv)), int(round(float(z) * inv)))
        idx = bucket_to_idx.get(b)
        if idx is None:
            idx = len(out)
            bucket_to_idx[b] = idx
            out.append((float(x), float(y), float(z)))
        remap.append(idx)
    return out, remap


def remove_degenerate_triangles(
    triangles: Iterable[TriangleIdx],
    vertices: Sequence[Point3],
    area_eps: float = EPS_AREA,
) -> List[TriangleIdx]:
    verts = np.asarray(vertices, dtype=float)
    out: List[TriangleIdx] = []
    for a, b, c in triangles:
        if a == b or b == c or a == c:
            continue
        va, vb, vc = verts[int(a)], verts[int(b)], verts[int(c)]
        area = 0.5 * np.linalg.norm(np.cross(vb - va, vc - va))
        if float(area) <= float(area_eps):
            continue
        out.append((int(a), int(b), int(c)))
    return out


def fix_winding_consistent_normals(triangles: Sequence[TriangleIdx], vertices: Sequence[Point3]) -> List[TriangleIdx]:
    if not triangles:
        return []
    verts = np.asarray(vertices, dtype=float)
    # Deterministic global reference by centroid-to-normal orientation.
    tris: List[TriangleIdx] = []
    for a, b, c in triangles:
        va, vb, vc = verts[a], verts[b], verts[c]
        n = np.cross(vb - va, vc - va)
        centroid = (va + vb + vc) / 3.0
        if float(np.dot(n, centroid)) < 0.0:
            tris.append((a, c, b))
        else:
            tris.append((a, b, c))
    return tris


def detect_open_mesh_edges(triangles: Sequence[TriangleIdx]) -> List[Tuple[int, int]]:
    edge_count: dict[tuple[int, int], int] = {}
    for a, b, c in triangles:
        for u, v in ((a, b), (b, c), (c, a)):
            key = (min(u, v), max(u, v))
            edge_count[key] = edge_count.get(key, 0) + 1
    return [e for e, n in edge_count.items() if n == 1]
