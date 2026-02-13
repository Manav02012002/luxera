from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set

from luxera.geometry.core import Vector3
from luxera.geometry.contracts import assert_surface
from luxera.geometry.id import derived_id
from luxera.geometry.tolerance import EPS_ANG, EPS_AREA, EPS_PLANE, EPS_POS, EPS_SNAP, EPS_WELD
from luxera.project.schema import RoomSpec, SurfaceSpec


def _to_v3(p: Tuple[float, float, float]) -> Vector3:
    return Vector3(float(p[0]), float(p[1]), float(p[2]))


def _to_tuple(v: Vector3) -> Tuple[float, float, float]:
    return (float(v.x), float(v.y), float(v.z))


def _newell_normal(vertices: List[Tuple[float, float, float]]) -> Vector3:
    if len(vertices) < 3:
        return Vector3(0.0, 0.0, 1.0)
    n = Vector3(0.0, 0.0, 0.0)
    pts = [_to_v3(v) for v in vertices]
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        n = n + Vector3(
            (a.y - b.y) * (a.z + b.z),
            (a.z - b.z) * (a.x + b.x),
            (a.x - b.x) * (a.y + b.y),
        )
    return n.normalize()


def _dedupe_vertices(vertices: List[Tuple[float, float, float]], tol: float = EPS_ANG) -> List[Tuple[float, float, float]]:
    if not vertices:
        return []
    out = [vertices[0]]
    for p in vertices[1:]:
        q = out[-1]
        if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol and abs(p[2] - q[2]) <= tol:
            continue
        out.append(p)
    if len(out) >= 2:
        a = out[0]
        b = out[-1]
        if abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol and abs(a[2] - b[2]) <= tol:
            out.pop()
    return out


def fix_surface_normals(surfaces: List[SurfaceSpec]) -> List[SurfaceSpec]:
    fixed: List[SurfaceSpec] = []
    for s in surfaces:
        verts = _dedupe_vertices(list(s.vertices))
        if len(verts) < 3:
            fixed.append(s)
            continue
        n = _newell_normal(verts)
        if s.normal is not None:
            wanted = _to_v3(s.normal).normalize()
            if n.dot(wanted) < 0:
                verts = list(reversed(verts))
                n = _newell_normal(verts)
        s.vertices = verts
        s.normal = _to_tuple(n)
        fixed.append(s)
    return fixed


def close_tiny_gaps(surfaces: List[SurfaceSpec], tolerance: float = EPS_SNAP) -> List[SurfaceSpec]:
    """
    Snap near-coincident vertices to a shared coordinate.
    """
    if tolerance <= 0:
        return surfaces

    buckets: Dict[Tuple[int, int, int], List[Vector3]] = {}
    inv = 1.0 / tolerance
    for s in surfaces:
        for v in s.vertices:
            p = _to_v3(v)
            key = (int(round(p.x * inv)), int(round(p.y * inv)), int(round(p.z * inv)))
            buckets.setdefault(key, []).append(p)

    centers: Dict[Tuple[int, int, int], Vector3] = {}
    for k, pts in buckets.items():
        cx = sum(p.x for p in pts) / len(pts)
        cy = sum(p.y for p in pts) / len(pts)
        cz = sum(p.z for p in pts) / len(pts)
        centers[k] = Vector3(cx, cy, cz)

    for s in surfaces:
        new_verts: List[Tuple[float, float, float]] = []
        for v in s.vertices:
            p = _to_v3(v)
            key = (int(round(p.x * inv)), int(round(p.y * inv)), int(round(p.z * inv)))
            c = centers[key]
            new_verts.append(_to_tuple(c))
        s.vertices = _dedupe_vertices(new_verts)
        s.normal = _to_tuple(_newell_normal(s.vertices)) if len(s.vertices) >= 3 else s.normal
    return surfaces


def _plane_key(surface: SurfaceSpec, angle_tol_deg: float, dist_tol: float) -> Tuple[int, int, int, int]:
    n = _newell_normal(surface.vertices)
    if n.length() < EPS_POS:
        n = Vector3(0, 0, 1)
    p0 = _to_v3(surface.vertices[0]) if surface.vertices else Vector3(0, 0, 0)
    d = -n.dot(p0)
    s = max(EPS_ANG, math.sin(math.radians(angle_tol_deg)))
    return (
        int(round(n.x / s)),
        int(round(n.y / s)),
        int(round(n.z / s)),
        int(round(d / max(dist_tol, EPS_ANG))),
    )


def _q2(p: Tuple[float, float], tol: float) -> Tuple[int, int]:
    inv = 1.0 / max(tol, EPS_POS)
    return (int(round(p[0] * inv)), int(round(p[1] * inv)))


def _q3(p: Tuple[float, float, float], tol: float) -> Tuple[int, int, int]:
    inv = 1.0 / max(tol, EPS_POS)
    return (int(round(p[0] * inv)), int(round(p[1] * inv)), int(round(p[2] * inv)))


def _polygon_area_2d(loop: List[Tuple[float, float]]) -> float:
    if len(loop) < 3:
        return 0.0
    a = 0.0
    for i in range(len(loop)):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % len(loop)]
        a += x1 * y2 - x2 * y1
    return 0.5 * a


def _extract_boundary_loops_2d(polygons: List[List[Tuple[float, float]]], tol: float = EPS_WELD) -> Tuple[List[List[Tuple[float, float]]], List[str]]:
    warnings: List[str] = []
    rep: Dict[Tuple[int, int], Tuple[float, float]] = {}
    edge_count: Dict[Tuple[Tuple[int, int], Tuple[int, int]], int] = {}
    directed: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

    for poly in polygons:
        if len(poly) < 3:
            continue
        qpoly = [_q2(p, tol) for p in poly]
        for q, p in zip(qpoly, poly):
            rep.setdefault(q, p)
        for i in range(len(qpoly)):
            a = qpoly[i]
            b = qpoly[(i + 1) % len(qpoly)]
            if a == b:
                continue
            und = (a, b) if a < b else (b, a)
            edge_count[und] = edge_count.get(und, 0) + 1
            directed.append((a, b))

    boundary = [(a, b) for (a, b) in directed if edge_count.get((a, b) if a < b else (b, a), 0) == 1]
    outgoing: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for a, b in boundary:
        outgoing.setdefault(a, []).append(b)

    used: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    loops: List[List[Tuple[float, float]]] = []
    for a, bs in list(outgoing.items()):
        for b in bs:
            e0 = (a, b)
            if e0 in used:
                continue
            loopq: List[Tuple[int, int]] = [a]
            cur_a, cur_b = a, b
            used.add((cur_a, cur_b))
            safety = 0
            while safety < 10000:
                safety += 1
                loopq.append(cur_b)
                next_candidates = [n for n in outgoing.get(cur_b, []) if (cur_b, n) not in used]
                if not next_candidates:
                    break
                next_b = next_candidates[0]
                used.add((cur_b, next_b))
                cur_a, cur_b = cur_b, next_b
                if cur_b == loopq[0]:
                    break
            if len(loopq) >= 4 and loopq[0] == loopq[-1]:
                loop = [rep[q] for q in loopq[:-1]]
                loops.append(loop)

    if len(loops) > 1:
        warnings.append("Multiple boundary loops detected; potential openings/holes preserved as separate loops.")

    loops = [lp for lp in loops if abs(_polygon_area_2d(lp)) > EPS_AREA]
    return loops, warnings


def merge_coplanar_surfaces(
    surfaces: List[SurfaceSpec],
    angle_tol_deg: float = 1.0,
    dist_tol: float = EPS_SNAP,
) -> List[SurfaceSpec]:
    """
    Topology-aware coplanar merge by (room_id, material_id, plane).
    Uses boundary edge cancellation to preserve openings/holes as separate loops.
    """
    groups: Dict[Tuple[str, str, Tuple[int, int, int, int]], List[SurfaceSpec]] = {}
    for s in surfaces:
        if len(s.vertices) < 3:
            continue
        key = (s.room_id or "", s.material_id or "", _plane_key(s, angle_tol_deg, dist_tol))
        groups.setdefault(key, []).append(s)

    merged: List[SurfaceSpec] = []
    consumed = set()
    for _, grp in groups.items():
        if len(grp) == 1:
            merged.append(grp[0])
            consumed.add(grp[0].id)
            continue
        n = _newell_normal(grp[0].vertices).normalize()
        origin = _to_v3(grp[0].vertices[0])
        ref = Vector3(1, 0, 0) if abs(n.x) < 0.9 else Vector3(0, 1, 0)
        u = ref.cross(n).normalize()
        v = n.cross(u).normalize()
        polys_2d: List[List[Tuple[float, float]]] = []
        for s in grp:
            consumed.add(s.id)
            poly2d: List[Tuple[float, float]] = []
            for p in s.vertices:
                x = (_to_v3(p) - origin).dot(u)
                y = (_to_v3(p) - origin).dot(v)
                poly2d.append((x, y))
            if len(poly2d) >= 3:
                polys_2d.append(poly2d)
        loops, _ = _extract_boundary_loops_2d(polys_2d, tol=max(dist_tol * 0.5, EPS_WELD))
        if not loops:
            for s in grp:
                merged.append(s)
            continue
        first = grp[0]
        for li, loop in enumerate(loops):
            verts3 = [_to_tuple(origin + u * xy[0] + v * xy[1]) for xy in loop]
            sid = first.id if li == 0 else derived_id(
                first.id,
                "merged_loop",
                {
                    "loop_index": li,
                    "vertex_count": len(verts3),
                    "vertices": [tuple(float(v) for v in p) for p in verts3],
                },
            )
            sname = first.name if li == 0 else f"{first.name} (Loop {li+1})"
            merged.append(
                SurfaceSpec(
                    id=sid,
                    name=sname,
                    kind=first.kind,
                    vertices=verts3,
                    normal=_to_tuple(n),
                    room_id=first.room_id,
                    material_id=first.material_id,
                )
            )

    for s in surfaces:
        if s.id not in consumed:
            merged.append(s)
    return merged


@dataclass(frozen=True)
class ScenePrepReport:
    input_surfaces: int
    output_surfaces: int
    fixed_normals: int
    merged_surfaces: int
    snapped_vertices: int
    non_manifold_edges: int
    warnings: List[str] = field(default_factory=list)


def detect_non_manifold_edges(
    surfaces: List[SurfaceSpec],
    tolerance: float = EPS_WELD,
) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float], int]]:
    """
    Return edges used by more than two surface faces.
    """
    rep: Dict[Tuple[int, int, int], Tuple[float, float, float]] = {}
    counts: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], int] = {}
    for s in surfaces:
        verts = s.vertices
        if len(verts) < 2:
            continue
        for i in range(len(verts)):
            a = _q3(verts[i], tolerance)
            b = _q3(verts[(i + 1) % len(verts)], tolerance)
            rep.setdefault(a, verts[i])
            rep.setdefault(b, verts[(i + 1) % len(verts)])
            und = (a, b) if a < b else (b, a)
            counts[und] = counts.get(und, 0) + 1
    out: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], int]] = []
    for (a, b), c in counts.items():
        if c > 2:
            out.append((rep[a], rep[b], c))
    return out


def clean_scene_surfaces(
    surfaces: List[SurfaceSpec],
    snap_tolerance: float = EPS_SNAP,
    merge_coplanar: bool = True,
) -> Tuple[List[SurfaceSpec], ScenePrepReport]:
    for s in surfaces:
        assert_surface(s)
    before = len(surfaces)
    fixed = fix_surface_normals(list(surfaces))
    pre_vertices = sum(len(s.vertices) for s in fixed)
    snapped = close_tiny_gaps(fixed, tolerance=snap_tolerance)
    post_vertices = sum(len(s.vertices) for s in snapped)
    out = merge_coplanar_surfaces(snapped) if merge_coplanar else snapped
    for s in out:
        assert_surface(s)
    non_manifold = detect_non_manifold_edges(out)
    warnings: List[str] = []
    if non_manifold:
        warnings.append(f"Detected {len(non_manifold)} non-manifold edge(s) (edge valence > 2).")
    report = ScenePrepReport(
        input_surfaces=before,
        output_surfaces=len(out),
        fixed_normals=before,
        merged_surfaces=max(0, before - len(out)),
        snapped_vertices=max(0, pre_vertices - post_vertices),
        non_manifold_edges=len(non_manifold),
        warnings=warnings,
    )
    return out, report


def detect_room_volumes_from_surfaces(surfaces: List[SurfaceSpec]) -> List[RoomSpec]:
    """
    Detect simple axis-aligned room boxes from surface sets grouped by room_id.
    """
    by_room: Dict[str, List[SurfaceSpec]] = {}
    for s in surfaces:
        if s.room_id:
            by_room.setdefault(s.room_id, []).append(s)

    rooms: List[RoomSpec] = []
    for room_id, grp in by_room.items():
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = []
        for s in grp:
            for p in s.vertices:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
                zs.append(float(p[2]))
        if not xs:
            continue
        mnx, mxx = min(xs), max(xs)
        mny, mxy = min(ys), max(ys)
        mnz, mxz = min(zs), max(zs)
        w = mxx - mnx
        l = mxy - mny
        h = mxz - mnz
        if w <= EPS_PLANE or l <= EPS_PLANE or h <= EPS_PLANE:
            continue
        rooms.append(
            RoomSpec(
                id=room_id,
                name=room_id,
                width=w,
                length=l,
                height=h,
                origin=(mnx, mny, mnz),
            )
        )
    return rooms
