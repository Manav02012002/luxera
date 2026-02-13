from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional, Sequence, Tuple

from luxera.geometry.tolerance import EPS_POS


Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]


def point_in_polygon(point: Point2, polygon: Sequence[Point2]) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / max(y2 - y1, EPS_POS) + x1):
            inside = not inside
    return inside


def clip_points_to_polygon(points: Sequence[Point2], polygon: Sequence[Point2]) -> List[Point2]:
    return [p for p in points if point_in_polygon(p, polygon)]


def polygon_union(polygons: Sequence[Sequence[Point2]]) -> List[Point2]:
    if not polygons:
        return []
    try:
        from shapely.geometry import Polygon  # type: ignore
        from shapely.ops import unary_union  # type: ignore

        u = unary_union([Polygon(list(p)) for p in polygons if len(p) >= 3])
        if u.is_empty:
            return []
        geom = u.geoms[0] if hasattr(u, "geoms") else u
        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]
    except Exception:
        # Convex hull fallback.
        pts = [tuple(map(float, p)) for poly in polygons for p in poly]
        if len(pts) < 3:
            return pts
        pts = sorted(set(pts))
        def cross(o: Point2, a: Point2, b: Point2) -> float:
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lower: List[Point2] = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper: List[Point2] = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]


def polygon_intersection(a: Sequence[Point2], b: Sequence[Point2]) -> List[Point2]:
    try:
        from shapely.geometry import Polygon  # type: ignore

        inter = Polygon(list(a)).intersection(Polygon(list(b)))
        if inter.is_empty:
            return []
        geom = inter.geoms[0] if hasattr(inter, "geoms") else inter
        return [(float(x), float(y)) for x, y in list(geom.exterior.coords)[:-1]]
    except Exception:
        return [p for p in a if point_in_polygon(p, b)]


def clip_polyline_to_polygon(polyline: Sequence[Point2], polygon: Sequence[Point2]) -> List[Point2]:
    out: List[Point2] = []
    for p in polyline:
        if point_in_polygon(p, polygon):
            out.append((float(p[0]), float(p[1])))
    return out


@dataclass(frozen=True)
class SnapOptions:
    grid: float = 0.0
    angle_deg: float = 0.0
    enabled: Tuple[str, ...] = ("endpoint", "midpoint", "segment", "intersection", "grid")


def _dist2(a: Point2, b: Point2) -> float:
    dx, dy = a[0] - b[0], a[1] - b[1]
    return dx * dx + dy * dy


def snap_point(
    point: Point2,
    *,
    endpoints: Sequence[Point2] = (),
    segments: Sequence[Tuple[Point2, Point2]] = (),
    intersections: Sequence[Point2] = (),
    circles: Sequence[Tuple[Point2, float]] = (),
    tangent_from: Optional[Point2] = None,
    normal_from: Optional[Point2] = None,
    origin: Point2 = (0.0, 0.0),
    options: SnapOptions = SnapOptions(),
    radius: float = 0.25,
) -> Point2:
    p = (float(point[0]), float(point[1]))
    best = p
    best_d2 = radius * radius
    enabled = set(options.enabled)

    if "endpoint" in enabled:
        for e in endpoints:
            d2 = _dist2(p, e)
            if d2 < best_d2:
                best, best_d2 = (float(e[0]), float(e[1])), d2
    if "midpoint" in enabled:
        for a, b in segments:
            m = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            d2 = _dist2(p, m)
            if d2 < best_d2:
                best, best_d2 = m, d2
    if "intersection" in enabled:
        for ip in intersections:
            d2 = _dist2(p, ip)
            if d2 < best_d2:
                best, best_d2 = (float(ip[0]), float(ip[1])), d2
    if "segment" in enabled:
        for a, b in segments:
            ab = (b[0] - a[0], b[1] - a[1])
            ab2 = ab[0] * ab[0] + ab[1] * ab[1]
            if ab2 <= EPS_POS:
                continue
            t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ab2
            t = max(0.0, min(1.0, t))
            q = (a[0] + ab[0] * t, a[1] + ab[1] * t)
            d2 = _dist2(p, q)
            if d2 < best_d2:
                best, best_d2 = q, d2
    if "normal" in enabled and circles:
        ref = normal_from if normal_from is not None else p
        for c, r in circles:
            cx, cy = float(c[0]), float(c[1])
            rv = (ref[0] - cx, ref[1] - cy)
            ln = math.hypot(rv[0], rv[1])
            if ln <= EPS_POS:
                continue
            q = (cx + rv[0] * float(r) / ln, cy + rv[1] * float(r) / ln)
            d2 = _dist2(p, q)
            if d2 < best_d2:
                best, best_d2 = q, d2
    if "tangent" in enabled and circles and tangent_from is not None:
        tx, ty = float(tangent_from[0]), float(tangent_from[1])
        for c, r in circles:
            cx, cy = float(c[0]), float(c[1])
            dx, dy = tx - cx, ty - cy
            d = math.hypot(dx, dy)
            rr = float(r)
            if d <= rr + EPS_POS:
                continue
            a = math.atan2(dy, dx)
            b = math.acos(rr / d)
            for ang in (a + b, a - b):
                q = (cx + rr * math.cos(ang), cy + rr * math.sin(ang))
                d2 = _dist2(p, q)
                if d2 < best_d2:
                    best, best_d2 = q, d2
    if "grid" in enabled and options.grid > 0.0:
        g = float(options.grid)
        gx = round((p[0] - origin[0]) / g) * g + origin[0]
        gy = round((p[1] - origin[1]) / g) * g + origin[1]
        q = (gx, gy)
        d2 = _dist2(p, q)
        if d2 < best_d2:
            best, best_d2 = q, d2

    if options.angle_deg > 0.0:
        a = math.radians(float(options.angle_deg))
        r = math.hypot(best[0] - origin[0], best[1] - origin[1])
        if r > EPS_POS:
            ang = math.atan2(best[1] - origin[1], best[0] - origin[0])
            ang = round(ang / a) * a
            best = (origin[0] + r * math.cos(ang), origin[1] + r * math.sin(ang))
    return best


@dataclass(frozen=True)
class PickResult:
    kind: Literal["vertex", "edge", "surface", "grid", "luminaire", "none"]
    id: Optional[str]
    distance: float


def pick_nearest(
    click: Point3,
    *,
    vertices: Sequence[Tuple[str, Point3]] = (),
    edges: Sequence[Tuple[str, Point3, Point3]] = (),
    surfaces: Sequence[Tuple[str, Sequence[Point3]]] = (),
    grids: Sequence[Tuple[str, Point3]] = (),
    luminaires: Sequence[Tuple[str, Point3]] = (),
    radius: float = 0.5,
) -> PickResult:
    cx, cy, cz = click
    best = PickResult(kind="none", id=None, distance=float("inf"))
    r2 = float(radius) * float(radius)

    def d2(p: Point3) -> float:
        return (p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2

    for vid, p in vertices:
        dd = d2(p)
        if dd < r2 and dd < best.distance * best.distance:
            best = PickResult("vertex", vid, math.sqrt(dd))
    for gid, p in grids:
        dd = d2(p)
        if dd < r2 and dd < best.distance * best.distance:
            best = PickResult("grid", gid, math.sqrt(dd))
    for lid, p in luminaires:
        dd = d2(p)
        if dd < r2 and dd < best.distance * best.distance:
            best = PickResult("luminaire", lid, math.sqrt(dd))
    for eid, a, b in edges:
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ab2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2]
        if ab2 <= EPS_POS:
            continue
        t = ((cx - a[0]) * ab[0] + (cy - a[1]) * ab[1] + (cz - a[2]) * ab[2]) / ab2
        t = max(0.0, min(1.0, t))
        q = (a[0] + t * ab[0], a[1] + t * ab[1], a[2] + t * ab[2])
        dd = d2(q)
        if dd < r2 and dd < best.distance * best.distance:
            best = PickResult("edge", eid, math.sqrt(dd))
    for sid, verts3 in surfaces:
        if not verts3:
            continue
        c = (
            sum(v[0] for v in verts3) / len(verts3),
            sum(v[1] for v in verts3) / len(verts3),
            sum(v[2] for v in verts3) / len(verts3),
        )
        dd = d2(c)
        if dd < r2 and dd < best.distance * best.distance:
            best = PickResult("surface", sid, math.sqrt(dd))
    return best


def constrain_orthogonal(start: Point2, current: Point2) -> Point2:
    dx = current[0] - start[0]
    dy = current[1] - start[1]
    return (current[0], start[1]) if abs(dx) >= abs(dy) else (start[0], current[1])


def constrain_fixed_length(start: Point2, current: Point2, length: float) -> Point2:
    dx = current[0] - start[0]
    dy = current[1] - start[1]
    d = math.hypot(dx, dy)
    if d <= EPS_POS:
        return (start[0] + float(length), start[1])
    s = float(length) / d
    return (start[0] + dx * s, start[1] + dy * s)


def constrain_parallel_perpendicular(
    ref_a: Point2,
    ref_b: Point2,
    start: Point2,
    current: Point2,
    mode: Literal["parallel", "perpendicular"],
) -> Point2:
    vx, vy = ref_b[0] - ref_a[0], ref_b[1] - ref_a[1]
    ln = math.hypot(vx, vy)
    if ln <= EPS_POS:
        return current
    ux, uy = vx / ln, vy / ln
    if mode == "perpendicular":
        ux, uy = -uy, ux
    wx, wy = current[0] - start[0], current[1] - start[1]
    t = wx * ux + wy * uy
    return (start[0] + t * ux, start[1] + t * uy)


def snap_polyline_to_segments(polyline: Sequence[Point2], segments: Sequence[Tuple[Point2, Point2]], radius: float = 0.25) -> List[Point2]:
    out: List[Point2] = []
    for p in polyline:
        sp = snap_point(
            p,
            segments=segments,
            options=SnapOptions(enabled=("segment", "endpoint")),
            radius=radius,
        )
        out.append((float(sp[0]), float(sp[1])))
    return out
