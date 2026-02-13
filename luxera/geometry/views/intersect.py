from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

from luxera.geometry.mesh import TriMesh
from luxera.geometry.tolerance import EPS_PLANE, EPS_POS, EPS_WELD


Point3 = Tuple[float, float, float]
Segment3D = Tuple[Point3, Point3]


@dataclass(frozen=True)
class Plane:
    origin: Point3
    normal: Point3
    thickness: float = 0.0


@dataclass(frozen=True)
class Polyline3D:
    points: List[Point3] = field(default_factory=list)


def _norm(v: np.ndarray) -> np.ndarray:
    lv = float(np.linalg.norm(v))
    if lv <= EPS_POS:
        raise ValueError("invalid plane normal")
    return v / lv


def _intersect_edge_plane(a: np.ndarray, b: np.ndarray, da: float, db: float) -> np.ndarray | None:
    if abs(da) <= EPS_PLANE and abs(db) <= EPS_PLANE:
        return None
    if abs(da - db) <= EPS_POS:
        return None
    t = da / (da - db)
    if t < -EPS_PLANE or t > 1.0 + EPS_PLANE:
        return None
    t = min(1.0, max(0.0, float(t)))
    return a + (b - a) * t


def _quantize(p: Point3, eps: float = EPS_WELD) -> Tuple[int, int, int]:
    s = 1.0 / max(float(eps), EPS_POS)
    return (int(round(float(p[0]) * s)), int(round(float(p[1]) * s)), int(round(float(p[2]) * s)))


def intersect_trimesh_with_plane(mesh: TriMesh, plane: Plane) -> List[Segment3D]:
    n = _norm(np.asarray(plane.normal, dtype=float))
    o = np.asarray(plane.origin, dtype=float)
    segs: List[Segment3D] = []
    half_t = max(0.0, float(plane.thickness) * 0.5)

    for fa, fb, fc in mesh.faces:
        pts = [np.asarray(mesh.vertices[fa], dtype=float), np.asarray(mesh.vertices[fb], dtype=float), np.asarray(mesh.vertices[fc], dtype=float)]
        d = [float(np.dot(p - o, n)) for p in pts]

        if max(d) < -half_t - EPS_PLANE or min(d) > half_t + EPS_PLANE:
            continue

        # Use the center plane for slicing; thickness acts as slab inclusion gate.
        inter: List[np.ndarray] = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            p = _intersect_edge_plane(pts[i], pts[j], d[i], d[j])
            if p is not None:
                inter.append(p)
            elif abs(d[i]) <= EPS_PLANE and abs(d[j]) <= EPS_PLANE:
                inter.append(pts[i])
                inter.append(pts[j])

        # Deduplicate candidate points.
        unique: Dict[Tuple[int, int, int], np.ndarray] = {}
        for p in inter:
            key = _quantize((float(p[0]), float(p[1]), float(p[2])))
            unique[key] = p
        up = list(unique.values())
        if len(up) < 2:
            continue

        if len(up) == 2:
            a, b = up[0], up[1]
        else:
            # Deterministic farthest pair.
            best = (0, 1)
            best_d2 = -1.0
            for i in range(len(up)):
                for j in range(i + 1, len(up)):
                    dd = float(np.dot(up[i] - up[j], up[i] - up[j]))
                    if dd > best_d2:
                        best_d2 = dd
                        best = (i, j)
            a, b = up[best[0]], up[best[1]]

        if float(np.dot(a - b, a - b)) <= EPS_POS:
            continue
        segs.append(((float(a[0]), float(a[1]), float(a[2])), (float(b[0]), float(b[1]), float(b[2]))))

    return segs


def stitch_segments_to_polylines(segments: Sequence[Segment3D], eps: float = EPS_WELD) -> List[Polyline3D]:
    if not segments:
        return []

    rep: Dict[Tuple[int, int, int], Point3] = {}
    adj: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}

    def key(p: Point3) -> Tuple[int, int, int]:
        q = _quantize(p, eps=eps)
        rep.setdefault(q, p)
        return q

    for a, b in segments:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        adj.setdefault(ka, []).append(kb)
        adj.setdefault(kb, []).append(ka)

    used_edges: set[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = set()
    out: List[Polyline3D] = []

    def edge(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        return (a, b) if a <= b else (b, a)

    starts = sorted(adj.keys(), key=lambda x: (len(adj.get(x, [])), x))
    for start in starts:
        for nxt in sorted(adj.get(start, [])):
            e0 = edge(start, nxt)
            if e0 in used_edges:
                continue
            chain = [start, nxt]
            used_edges.add(e0)
            cur_prev = start
            cur = nxt
            while True:
                candidates = [x for x in adj.get(cur, []) if edge(cur, x) not in used_edges and x != cur_prev]
                if not candidates:
                    break
                candidates.sort()
                nn = candidates[0]
                used_edges.add(edge(cur, nn))
                chain.append(nn)
                cur_prev, cur = cur, nn
                if nn == chain[0]:
                    break
            out.append(Polyline3D(points=[rep[k] for k in chain]))

    out.sort(key=lambda pl: (len(pl.points), pl.points[0] if pl.points else (0.0, 0.0, 0.0)))
    return out
