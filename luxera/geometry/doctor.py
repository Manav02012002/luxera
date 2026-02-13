from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

from luxera.geometry.cleaning import (
    detect_open_mesh_edges,
    fix_winding_consistent_normals,
    merge_vertices,
    remove_degenerate_triangles,
)
from luxera.geometry.tolerance import EPS_ANG, EPS_AREA, EPS_POS, EPS_SLIVER_RATIO, EPS_WELD

Point3 = Tuple[float, float, float]
TriangleIdx = Tuple[int, int, int]


@dataclass(frozen=True)
class SceneHealthReport:
    counts: Dict[str, int] = field(default_factory=dict)
    severities: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "counts": dict(self.counts),
            "severities": dict(self.severities),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class MeshRepairResult:
    vertices: List[Point3]
    triangles: List[TriangleIdx]
    normals: List[Point3]
    report: SceneHealthReport


def _tri_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return 0.5 * float(np.linalg.norm(np.cross(b - a, c - a)))


def _edge_incidence(tris: Sequence[TriangleIdx]) -> Dict[Tuple[int, int], int]:
    out: Dict[Tuple[int, int], int] = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            out[key] = out.get(key, 0) + 1
    return out


def _components(tris: Sequence[TriangleIdx]) -> int:
    if not tris:
        return 0
    adj: Dict[int, set[int]] = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
    seen: set[int] = set()
    comps = 0
    for n in adj:
        if n in seen:
            continue
        comps += 1
        stack = [n]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(list(adj.get(cur, ())))
    return comps


def split_connected_components(triangles: Sequence[TriangleIdx]) -> List[List[TriangleIdx]]:
    tris = list(triangles)
    if not tris:
        return []
    tri_edges: List[set[Tuple[int, int]]] = []
    edge_to_tris: Dict[Tuple[int, int], List[int]] = {}
    for i, (a, b, c) in enumerate(tris):
        edges = {(min(a, b), max(a, b)), (min(b, c), max(b, c)), (min(c, a), max(c, a))}
        tri_edges.append(edges)
        for e in edges:
            edge_to_tris.setdefault(e, []).append(i)

    visited: set[int] = set()
    out: List[List[TriangleIdx]] = []
    for i in range(len(tris)):
        if i in visited:
            continue
        stack = [i]
        comp_ids: List[int] = []
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp_ids.append(cur)
            for e in tri_edges[cur]:
                for other in edge_to_tris.get(e, ()):
                    if other not in visited:
                        stack.append(other)
        out.append([tris[j] for j in comp_ids])
    return out


def _boundary_loops(triangles: Sequence[TriangleIdx]) -> List[List[int]]:
    boundary = detect_open_mesh_edges(triangles)
    if not boundary:
        return []
    nbrs: Dict[int, List[int]] = {}
    for a, b in boundary:
        nbrs.setdefault(a, []).append(b)
        nbrs.setdefault(b, []).append(a)

    visited_edges: set[Tuple[int, int]] = set()
    loops: List[List[int]] = []
    for a, b in boundary:
        e = (min(a, b), max(a, b))
        if e in visited_edges:
            continue
        loop = [a, b]
        visited_edges.add(e)
        prev, cur = a, b
        while True:
            next_candidates = [n for n in nbrs.get(cur, []) if n != prev]
            if not next_candidates:
                break
            nxt = next_candidates[0]
            ee = (min(cur, nxt), max(cur, nxt))
            if ee in visited_edges:
                if nxt == loop[0]:
                    loops.append(loop)
                break
            loop.append(nxt)
            visited_edges.add(ee)
            prev, cur = cur, nxt
    return loops


def _fill_small_holes(triangles: Sequence[TriangleIdx], max_loop_len: int = 3) -> List[TriangleIdx]:
    out = list(triangles)
    for loop in _boundary_loops(triangles):
        if len(loop) <= max_loop_len and len(loop) >= 3:
            a, b, c = loop[0], loop[1], loop[2]
            out.append((a, b, c))
    return out


def _segment_intersects_triangle(p0: np.ndarray, p1: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> bool:
    d = p1 - p0
    e1 = b - a
    e2 = c - a
    pvec = np.cross(d, e2)
    det = float(np.dot(e1, pvec))
    if abs(det) < EPS_POS:
        return False
    inv_det = 1.0 / det
    tvec = p0 - a
    u = float(np.dot(tvec, pvec) * inv_det)
    if u < 0.0 or u > 1.0:
        return False
    qvec = np.cross(tvec, e1)
    v = float(np.dot(d, qvec) * inv_det)
    if v < 0.0 or (u + v) > 1.0:
        return False
    t = float(np.dot(e2, qvec) * inv_det)
    return 0.0 <= t <= 1.0


def _self_intersections_approx(vertices: np.ndarray, triangles: Sequence[TriangleIdx]) -> int:
    tris = list(triangles)
    if len(tris) < 2:
        return 0
    boxes: List[Tuple[np.ndarray, np.ndarray]] = []
    for a, b, c in tris:
        pts = np.vstack((vertices[a], vertices[b], vertices[c]))
        boxes.append((pts.min(axis=0), pts.max(axis=0)))
    hits = 0
    for i in range(len(tris)):
        ai, bi, ci = tris[i]
        v1 = (vertices[ai], vertices[bi], vertices[ci])
        set_i = {ai, bi, ci}
        for j in range(i + 1, len(tris)):
            aj, bj, cj = tris[j]
            if set_i.intersection({aj, bj, cj}):
                continue
            mn_i, mx_i = boxes[i]
            mn_j, mx_j = boxes[j]
            if np.any(mx_i < mn_j) or np.any(mx_j < mn_i):
                continue
            v2 = (vertices[aj], vertices[bj], vertices[cj])
            edges1 = ((v1[0], v1[1]), (v1[1], v1[2]), (v1[2], v1[0]))
            edges2 = ((v2[0], v2[1]), (v2[1], v2[2]), (v2[2], v2[0]))
            if any(_segment_intersects_triangle(e0, e1, v2[0], v2[1], v2[2]) for e0, e1 in edges1):
                hits += 1
                continue
            if any(_segment_intersects_triangle(e0, e1, v1[0], v1[1], v1[2]) for e0, e1 in edges2):
                hits += 1
    return hits


def scene_health_report(vertices: Sequence[Point3], triangles: Sequence[TriangleIdx]) -> SceneHealthReport:
    verts = np.asarray(vertices, dtype=float)
    tris = list((int(a), int(b), int(c)) for a, b, c in triangles)
    counts: Dict[str, int] = {}
    severities: Dict[str, str] = {}
    warnings: List[str] = []
    errors: List[str] = []

    if verts.size == 0:
        errors.append("No vertices.")
    if not tris:
        errors.append("No triangles.")

    # Degenerate triangles.
    deg = 0
    sliver = 0
    dup_faces = 0
    seen_faces: set[Tuple[int, int, int]] = set()
    inverted = 0
    for a, b, c in tris:
        key = tuple(sorted((a, b, c)))
        if key in seen_faces:
            dup_faces += 1
        seen_faces.add(key)
        if a == b or b == c or a == c:
            deg += 1
            continue
        va, vb, vc = verts[a], verts[b], verts[c]
        area = _tri_area(va, vb, vc)
        if area <= EPS_AREA:
            deg += 1
            continue
        edges = sorted(
            [
                float(np.linalg.norm(vb - va)),
                float(np.linalg.norm(vc - vb)),
                float(np.linalg.norm(va - vc)),
            ]
        )
        if edges[-1] > 0 and edges[0] / edges[-1] < EPS_SLIVER_RATIO:
            sliver += 1
        n = np.cross(vb - va, vc - va)
        cent = (va + vb + vc) / 3.0
        if float(np.dot(n, cent)) < 0.0:
            inverted += 1
    counts["degenerate_triangles"] = deg
    counts["duplicate_faces"] = dup_faces
    counts["sliver_triangles"] = sliver
    counts["inverted_winding_triangles"] = inverted
    severities["degenerate_triangles"] = "error" if deg > 0 else "ok"
    severities["duplicate_faces"] = "warn" if dup_faces > 0 else "ok"
    severities["sliver_triangles"] = "warn" if sliver > 0 else "ok"
    severities["inverted_winding_triangles"] = "warn" if inverted > 0 else "ok"

    # Non-manifold / open boundaries.
    edge_inc = _edge_incidence(tris)
    non_manifold = sum(1 for _e, n in edge_inc.items() if n > 2)
    open_edges = len(detect_open_mesh_edges(tris))
    counts["non_manifold_edges"] = int(non_manifold)
    counts["open_boundary_edges"] = int(open_edges)
    severities["non_manifold_edges"] = "error" if non_manifold > 0 else "ok"
    severities["open_boundary_edges"] = "warn" if open_edges > 0 else "ok"

    # Duplicate vertices.
    merged, _remap = merge_vertices(vertices, eps=EPS_ANG)
    dup_v = max(0, len(vertices) - len(merged))
    counts["duplicate_vertices"] = int(dup_v)
    severities["duplicate_vertices"] = "warn" if dup_v > 0 else "ok"

    # Components and coordinate magnitudes.
    counts["disconnected_components"] = int(_components(tris))
    severities["disconnected_components"] = "warn" if counts["disconnected_components"] > 1 else "ok"
    huge = int(np.sum(np.abs(verts) > 1e6)) if verts.size else 0
    counts["huge_coordinate_values"] = huge
    severities["huge_coordinate_values"] = "warn" if huge > 0 else "ok"

    # Approximate self-intersection checks using edge/triangle tests.
    si = _self_intersections_approx(verts, tris) if verts.size and tris else 0
    counts["self_intersections_approx"] = int(si)
    severities["self_intersections_approx"] = "warn" if si > 0 else "ok"

    return SceneHealthReport(counts=counts, severities=severities, warnings=warnings, errors=errors)


def _face_normals(vertices: Sequence[Point3], triangles: Sequence[TriangleIdx]) -> List[Point3]:
    verts = np.asarray(vertices, dtype=float)
    out: List[Point3] = []
    for a, b, c in triangles:
        n = np.cross(verts[b] - verts[a], verts[c] - verts[a])
        ln = float(np.linalg.norm(n))
        if ln <= EPS_POS:
            out.append((0.0, 0.0, 1.0))
        else:
            n = n / ln
            out.append((float(n[0]), float(n[1]), float(n[2])))
    return out


def repair_mesh(
    vertices: Sequence[Point3],
    triangles: Sequence[TriangleIdx],
    *,
    weld_epsilon: float = EPS_WELD * 0.01,
    make_two_sided: bool = False,
    fill_holes: bool = True,
    split_components: bool = False,
    simplify_ratio: float | None = None,
) -> MeshRepairResult:
    merged, remap = merge_vertices(vertices, eps=weld_epsilon)
    tris = [(remap[a], remap[b], remap[c]) for a, b, c in triangles]
    tris = remove_degenerate_triangles(tris, merged, area_eps=EPS_AREA)
    tris = fix_winding_consistent_normals(tris, merged)
    if fill_holes:
        tris = _fill_small_holes(tris, max_loop_len=3)
    if simplify_ratio is not None and 0.0 < float(simplify_ratio) < 1.0 and len(tris) > 8:
        step = max(2, int(round(1.0 / float(simplify_ratio))))
        tris = [t for i, t in enumerate(tris) if (i % step == 0)]
    if split_components:
        comps = split_connected_components(tris)
        # Deterministic: keep all components but sorted by size for stable downstream processing.
        tris = [t for comp in sorted(comps, key=len, reverse=True) for t in comp]
    if make_two_sided:
        tris = list(tris) + [(a, c, b) for a, b, c in tris]
    normals = _face_normals(merged, tris)
    report = scene_health_report(merged, tris)
    return MeshRepairResult(vertices=merged, triangles=tris, normals=normals, report=report)
