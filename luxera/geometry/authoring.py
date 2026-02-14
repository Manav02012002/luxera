from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Literal, Sequence, Tuple, Union

from luxera.geometry.curves.arc import Arc
from luxera.geometry.curves.intersections import (
    Segment2D,
    arc_arc_intersections,
    nearest_intersection_to_point,
    segment_arc_intersections,
    segment_segment_intersections,
)
from luxera.geometry.curves.offset import OffsetResult, offset_polygon_v2
from luxera.geometry.primitives import Arc2D, Circle2D, Polygon2D, Polyline2D
from luxera.geometry.tolerance import EPS_ANG, EPS_PLANE, EPS_POS, EPS_WELD


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class Line2D:
    a: Point2
    b: Point2


Curve2D = Union[Line2D, Arc2D]


def add_vertex(polyline: Polyline2D, index: int, point: Point2) -> Polyline2D:
    pts = list(polyline.points)
    if index < 0 or index > len(pts):
        raise ValueError("index out of range")
    pts.insert(index, (float(point[0]), float(point[1])))
    return Polyline2D(points=pts)


def remove_vertex(polyline: Polyline2D, index: int, *, min_points: int = 2) -> Polyline2D:
    pts = list(polyline.points)
    if len(pts) <= min_points:
        raise ValueError("cannot remove vertex below minimum point count")
    if index < 0 or index >= len(pts):
        raise ValueError("index out of range")
    pts.pop(index)
    return Polyline2D(points=pts)


def drag_vertex(polyline: Polyline2D, index: int, point: Point2) -> Polyline2D:
    pts = list(polyline.points)
    if index < 0 or index >= len(pts):
        raise ValueError("index out of range")
    pts[index] = (float(point[0]), float(point[1]))
    return Polyline2D(points=pts)


def rectangle_tool(p0: Point2, p1: Point2) -> Polygon2D:
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    return Polygon2D(points=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def circle_tool(center: Point2, radius: float) -> Circle2D:
    if radius <= 0.0:
        raise ValueError("radius must be > 0")
    return Circle2D(center=(float(center[0]), float(center[1])), radius=float(radius))


def arc_from_bulge(start: Point2, end: Point2, bulge: float) -> Arc2D:
    arc = Arc.from_bulge(start, end, bulge)
    start_deg = math.degrees(arc.start_rad)
    sweep_deg = math.degrees(arc.sweep())
    end_deg = start_deg + (sweep_deg if arc.ccw else -sweep_deg)
    return Arc2D(center=(float(arc.center[0]), float(arc.center[1])), radius=float(arc.radius), start_deg=float(start_deg), end_deg=float(end_deg))


def _arc2d_to_arc(arc: Arc2D) -> Arc:
    a0 = math.radians(float(arc.start_deg))
    a1 = math.radians(float(arc.end_deg))
    return Arc(center=(float(arc.center[0]), float(arc.center[1])), radius=float(arc.radius), start_rad=a0, end_rad=a1, ccw=(float(arc.end_deg) >= float(arc.start_deg)))


def _line_line_intersection_inf(a: Line2D, b: Line2D) -> Point2 | None:
    p, r = a.a, (a.b[0] - a.a[0], a.b[1] - a.a[1])
    q, s = b.a, (b.b[0] - b.a[0], b.b[1] - b.a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) <= EPS_POS:
        return None
    qp = (q[0] - p[0], q[1] - p[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    return (float(p[0] + t * r[0]), float(p[1] + t * r[1]))


def _unit(v: Point2) -> Point2:
    ln = math.hypot(float(v[0]), float(v[1]))
    if ln <= EPS_POS:
        return (0.0, 0.0)
    return (float(v[0]) / ln, float(v[1]) / ln)


def _project_point_to_line(p: Point2, l: Line2D) -> Point2:
    ax, ay = float(l.a[0]), float(l.a[1])
    bx, by = float(l.b[0]), float(l.b[1])
    vx, vy = bx - ax, by - ay
    vv = vx * vx + vy * vy
    if vv <= EPS_POS:
        return (ax, ay)
    t = ((float(p[0]) - ax) * vx + (float(p[1]) - ay) * vy) / vv
    return (ax + t * vx, ay + t * vy)


def _circle_line_intersections(center: Point2, radius: float, a: Point2, b: Point2) -> List[Point2]:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cx, cy = float(center[0]), float(center[1])
    dx, dy = bx - ax, by - ay
    fx, fy = ax - cx, ay - cy
    A = dx * dx + dy * dy
    if A <= EPS_POS:
        return []
    B = 2.0 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - float(radius) * float(radius)
    disc = B * B - 4.0 * A * C
    if disc < -EPS_POS:
        return []
    disc = max(0.0, disc)
    s = math.sqrt(disc)
    t0 = (-B - s) / (2.0 * A)
    t1 = (-B + s) / (2.0 * A)
    return [(ax + dx * t0, ay + dy * t0), (ax + dx * t1, ay + dy * t1)]


def _circle_circle_intersections(c0: Point2, r0: float, c1: Point2, r1: float) -> List[Point2]:
    x0, y0 = float(c0[0]), float(c0[1])
    x1, y1 = float(c1[0]), float(c1[1])
    rr0, rr1 = float(r0), float(r1)
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy)
    if d <= EPS_POS:
        return []
    if d > rr0 + rr1 + EPS_POS:
        return []
    if d < abs(rr0 - rr1) - EPS_POS:
        return []
    a = (rr0 * rr0 - rr1 * rr1 + d * d) / (2.0 * d)
    h2 = rr0 * rr0 - a * a
    if h2 < -EPS_POS:
        return []
    h = math.sqrt(max(0.0, h2))
    xm = x0 + a * dx / d
    ym = y0 + a * dy / d
    rx = -dy * (h / d)
    ry = dx * (h / d)
    return [(xm + rx, ym + ry), (xm - rx, ym - ry)]


def trim_line_to_intersection(line: Line2D, cutter: Line2D) -> Line2D:
    p, r = line.a, (line.b[0] - line.a[0], line.b[1] - line.a[1])
    q, s = cutter.a, (cutter.b[0] - cutter.a[0], cutter.b[1] - cutter.a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) <= EPS_POS:
        return line
    qp = (q[0] - p[0], q[1] - p[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    if t < 0.0 or t > 1.0:
        return line
    x = p[0] + t * r[0]
    y = p[1] + t * r[1]
    return Line2D(a=line.a, b=(x, y))


def extend_line_to_intersection(line: Line2D, target: Line2D) -> Line2D:
    p, r = line.a, (line.b[0] - line.a[0], line.b[1] - line.a[1])
    q, s = target.a, (target.b[0] - target.a[0], target.b[1] - target.a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) <= EPS_POS:
        return line
    qp = (q[0] - p[0], q[1] - p[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    x = p[0] + t * r[0]
    y = p[1] + t * r[1]
    return Line2D(a=line.a, b=(x, y))


def trim_curve_to_intersection(curve: Curve2D, cutter: Curve2D) -> Curve2D:
    if isinstance(curve, Line2D) and isinstance(cutter, Line2D):
        return trim_line_to_intersection(curve, cutter)

    if isinstance(curve, Line2D):
        seg = Segment2D(curve.a, curve.b)
        pts: List[Point2] = []
        if isinstance(cutter, Arc2D):
            pts = segment_arc_intersections(seg, _arc2d_to_arc(cutter))
        hit = nearest_intersection_to_point(pts, curve.b)
        if hit is None:
            return curve
        return Line2D(a=curve.a, b=hit)

    arc = _arc2d_to_arc(curve)
    pts2: List[Point2] = []
    if isinstance(cutter, Line2D):
        pts2 = arc.intersections_with_line_segment(cutter.a, cutter.b)
    else:
        pts2 = arc_arc_intersections(arc, _arc2d_to_arc(cutter))
    cands = []
    for p in pts2:
        a = math.atan2(p[1] - arc.center[1], p[0] - arc.center[0])
        if arc.contains_angle(a):
            cands.append(p)
    hit2 = nearest_intersection_to_point(cands, arc.end_point)
    if hit2 is None:
        return curve
    hit_ang = math.atan2(hit2[1] - arc.center[1], hit2[0] - arc.center[0])
    trimmed = Arc(center=arc.center, radius=arc.radius, start_rad=arc.start_rad, end_rad=hit_ang, ccw=arc.ccw)
    start_deg = math.degrees(trimmed.start_rad)
    sweep_deg = math.degrees(trimmed.sweep())
    end_deg = start_deg + (sweep_deg if trimmed.ccw else -sweep_deg)
    return Arc2D(center=trimmed.center, radius=trimmed.radius, start_deg=start_deg, end_deg=end_deg)


def extend_curve_to_intersection(curve: Curve2D, target: Curve2D) -> Curve2D:
    if isinstance(curve, Line2D) and isinstance(target, Line2D):
        return extend_line_to_intersection(curve, target)
    if isinstance(curve, Arc2D):
        arc = _arc2d_to_arc(curve)
        pts: List[Point2] = []
        if isinstance(target, Line2D):
            # Intersect with infinite target line by using a long segment in target direction.
            tx = float(target.b[0]) - float(target.a[0])
            ty = float(target.b[1]) - float(target.a[1])
            tl = max(math.hypot(tx, ty), 1.0)
            ux, uy = tx / tl, ty / tl
            p0 = (float(target.a[0]) - ux * 1.0e6, float(target.a[1]) - uy * 1.0e6)
            p1 = (float(target.a[0]) + ux * 1.0e6, float(target.a[1]) + uy * 1.0e6)
            pts = arc.intersections_with_line_segment(p0, p1)
        else:
            pts = arc_arc_intersections(arc, _arc2d_to_arc(target))
        if not pts:
            return curve
        end_ang = arc.end_rad
        best: Point2 | None = None
        best_delta = float("inf")
        for p in pts:
            a = math.atan2(p[1] - arc.center[1], p[0] - arc.center[0])
            if arc.contains_angle(a):
                continue
            delta = (a - end_ang) % (2.0 * math.pi) if arc.ccw else (end_ang - a) % (2.0 * math.pi)
            if delta < best_delta:
                best_delta = delta
                best = p
        if best is None:
            return curve
        hit_ang = math.atan2(best[1] - arc.center[1], best[0] - arc.center[0])
        ext = Arc(center=arc.center, radius=arc.radius, start_rad=arc.start_rad, end_rad=hit_ang, ccw=arc.ccw)
        sdeg = math.degrees(ext.start_rad)
        edeg = math.degrees(ext.end_rad)
        return Arc2D(center=ext.center, radius=ext.radius, start_deg=sdeg, end_deg=edeg)
    return trim_curve_to_intersection(curve, target)


def fillet_between_curves(curve_a: Curve2D, curve_b: Curve2D, radius: float) -> Arc2D | None:
    r = float(radius)
    if r <= EPS_POS:
        raise ValueError("radius must be > 0")
    if isinstance(curve_a, Line2D) and isinstance(curve_b, Line2D):
        ip = _line_line_intersection_inf(curve_a, curve_b)
        if ip is None:
            return None
        d1a = math.hypot(curve_a.a[0] - ip[0], curve_a.a[1] - ip[1])
        d1b = math.hypot(curve_a.b[0] - ip[0], curve_a.b[1] - ip[1])
        d2a = math.hypot(curve_b.a[0] - ip[0], curve_b.a[1] - ip[1])
        d2b = math.hypot(curve_b.b[0] - ip[0], curve_b.b[1] - ip[1])
        u1 = _unit((curve_a.a[0] - ip[0], curve_a.a[1] - ip[1])) if d1a >= d1b else _unit((curve_a.b[0] - ip[0], curve_a.b[1] - ip[1]))
        u2 = _unit((curve_b.a[0] - ip[0], curve_b.a[1] - ip[1])) if d2a >= d2b else _unit((curve_b.b[0] - ip[0], curve_b.b[1] - ip[1]))
        dotv = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        phi = math.acos(dotv)
        if phi <= EPS_ANG or abs(phi - math.pi) <= EPS_ANG:
            return None
        t = r / math.tan(phi * 0.5)
        p1 = (ip[0] + u1[0] * t, ip[1] + u1[1] * t)
        p2 = (ip[0] + u2[0] * t, ip[1] + u2[1] * t)
        bis = _unit((u1[0] + u2[0], u1[1] + u2[1]))
        if math.hypot(bis[0], bis[1]) <= EPS_POS:
            return None
        cdist = r / max(math.sin(phi * 0.5), EPS_POS)
        c = (ip[0] + bis[0] * cdist, ip[1] + bis[1] * cdist)
        a0 = math.degrees(math.atan2(p1[1] - c[1], p1[0] - c[0]))
        a1 = math.degrees(math.atan2(p2[1] - c[1], p2[0] - c[0]))
        ccw = ((p1[0] - c[0]) * (p2[1] - c[1]) - (p1[1] - c[1]) * (p2[0] - c[0])) > 0.0
        return Arc2D(center=(float(c[0]), float(c[1])), radius=r, start_deg=float(a0), end_deg=float(a1 if ccw else a1),)
    if isinstance(curve_a, Line2D) and isinstance(curve_b, Arc2D):
        return _fillet_line_arc(curve_a, curve_b, r)
    if isinstance(curve_a, Arc2D) and isinstance(curve_b, Line2D):
        return _fillet_line_arc(curve_b, curve_a, r)
    if isinstance(curve_a, Arc2D) and isinstance(curve_b, Arc2D):
        return _fillet_arc_arc(curve_a, curve_b, r)
    return None


def _fillet_line_arc(line: Line2D, arc2d: Arc2D, r: float) -> Arc2D | None:
    arc = _arc2d_to_arc(arc2d)
    ax, ay = float(line.a[0]), float(line.a[1])
    bx, by = float(line.b[0]), float(line.b[1])
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy)
    if ln <= EPS_POS:
        return None
    ux, uy = dx / ln, dy / ln
    nx, ny = -uy, ux
    best: Arc2D | None = None
    best_score = float("inf")
    for side in (-1.0, 1.0):
        la = (ax + nx * side * r, ay + ny * side * r)
        lb = (bx + nx * side * r, by + ny * side * r)
        for s in (-1.0, 1.0):
            ro = arc.radius + s * r
            if ro <= EPS_POS:
                continue
            centers = _circle_line_intersections(arc.center, ro, (la[0] - ux * 1.0e6, la[1] - uy * 1.0e6), (lb[0] + ux * 1.0e6, lb[1] + uy * 1.0e6))
            for c in centers:
                tp_line = _project_point_to_line(c, line)
                vc = _unit((c[0] - arc.center[0], c[1] - arc.center[1]))
                tp_arc = (arc.center[0] + vc[0] * arc.radius, arc.center[1] + vc[1] * arc.radius)
                ang_arc = math.atan2(tp_arc[1] - arc.center[1], tp_arc[0] - arc.center[0])
                if not arc.contains_angle(ang_arc):
                    continue
                a0 = math.degrees(math.atan2(tp_line[1] - c[1], tp_line[0] - c[0]))
                a1 = math.degrees(math.atan2(tp_arc[1] - c[1], tp_arc[0] - c[0]))
                cand = Arc2D(center=(float(c[0]), float(c[1])), radius=r, start_deg=a0, end_deg=a1)
                score = math.hypot(tp_line[0] - tp_arc[0], tp_line[1] - tp_arc[1])
                if score < best_score:
                    best_score = score
                    best = cand
    return best


def _fillet_arc_arc(a2d: Arc2D, b2d: Arc2D, r: float) -> Arc2D | None:
    a = _arc2d_to_arc(a2d)
    b = _arc2d_to_arc(b2d)
    best: Arc2D | None = None
    best_score = float("inf")
    for sa in (-1.0, 1.0):
        ra = a.radius + sa * r
        if ra <= EPS_POS:
            continue
        for sb in (-1.0, 1.0):
            rb = b.radius + sb * r
            if rb <= EPS_POS:
                continue
            centers = _circle_circle_intersections(a.center, ra, b.center, rb)
            for c in centers:
                va = _unit((c[0] - a.center[0], c[1] - a.center[1]))
                vb = _unit((c[0] - b.center[0], c[1] - b.center[1]))
                ta = (a.center[0] + va[0] * a.radius, a.center[1] + va[1] * a.radius)
                tb = (b.center[0] + vb[0] * b.radius, b.center[1] + vb[1] * b.radius)
                if not a.contains_angle(math.atan2(ta[1] - a.center[1], ta[0] - a.center[0])):
                    continue
                if not b.contains_angle(math.atan2(tb[1] - b.center[1], tb[0] - b.center[0])):
                    continue
                a0 = math.degrees(math.atan2(ta[1] - c[1], ta[0] - c[0]))
                a1 = math.degrees(math.atan2(tb[1] - c[1], tb[0] - c[0]))
                cand = Arc2D(center=(float(c[0]), float(c[1])), radius=r, start_deg=a0, end_deg=a1)
                score = math.hypot(ta[0] - tb[0], ta[1] - tb[1])
                if score < best_score:
                    best_score = score
                    best = cand
    return best


def chamfer_between_curves(curve_a: Curve2D, curve_b: Curve2D, distance: float) -> Line2D | None:
    d = float(distance)
    if d <= EPS_POS:
        raise ValueError("distance must be > 0")
    if isinstance(curve_a, Line2D) and isinstance(curve_b, Line2D):
        ip = _line_line_intersection_inf(curve_a, curve_b)
        if ip is None:
            return None
        u1 = _unit((curve_a.a[0] - ip[0], curve_a.a[1] - ip[1])) if math.hypot(curve_a.a[0] - ip[0], curve_a.a[1] - ip[1]) >= math.hypot(curve_a.b[0] - ip[0], curve_a.b[1] - ip[1]) else _unit((curve_a.b[0] - ip[0], curve_a.b[1] - ip[1]))
        u2 = _unit((curve_b.a[0] - ip[0], curve_b.a[1] - ip[1])) if math.hypot(curve_b.a[0] - ip[0], curve_b.a[1] - ip[1]) >= math.hypot(curve_b.b[0] - ip[0], curve_b.b[1] - ip[1]) else _unit((curve_b.b[0] - ip[0], curve_b.b[1] - ip[1]))
        p1 = (ip[0] + u1[0] * d, ip[1] + u1[1] * d)
        p2 = (ip[0] + u2[0] * d, ip[1] + u2[1] * d)
        return Line2D(a=p1, b=p2)
    fil = fillet_between_curves(curve_a, curve_b, d)
    if fil is None:
        return None
    ac = _arc2d_to_arc(fil)
    return Line2D(a=ac.start_point, b=ac.end_point)


def fillet_corner(polyline: Polyline2D, index: int, radius: float) -> Polyline2D:
    if radius <= 0.0:
        raise ValueError("radius must be > 0")
    pts = list(polyline.points)
    if len(pts) < 3:
        return polyline
    i0 = max(0, index - 1)
    i1 = index
    i2 = min(len(pts) - 1, index + 1)
    p0, p1, p2 = pts[i0], pts[i1], pts[i2]
    v1 = (p0[0] - p1[0], p0[1] - p1[1])
    v2 = (p2[0] - p1[0], p2[1] - p1[1])
    l1 = math.hypot(v1[0], v1[1])
    l2 = math.hypot(v2[0], v2[1])
    if l1 <= EPS_ANG or l2 <= EPS_ANG:
        return polyline
    u1 = (v1[0] / l1, v1[1] / l1)
    u2 = (v2[0] / l2, v2[1] / l2)
    d = min(radius, 0.45 * min(l1, l2))
    a = (p1[0] + u1[0] * d, p1[1] + u1[1] * d)
    b = (p1[0] + u2[0] * d, p1[1] + u2[1] * d)
    pts[i1:i1 + 1] = [a, b]
    return Polyline2D(points=pts)


def chamfer_corner(polyline: Polyline2D, index: int, distance: float) -> Polyline2D:
    return fillet_corner(polyline, index, distance)


def offset_polygon(polygon: Polygon2D, distance: float) -> Polygon2D:
    res = offset_polygon_v2(polygon, distance, join_style="miter")
    if not res.ok or res.polygon is None:
        raise ValueError(res.failure.message if res.failure is not None else "offset failed")
    return res.polygon


def offset(polygon: Polygon2D, distance: float) -> OffsetResult:
    return offset_polygon_v2(polygon, distance, join_style="miter")


def join_polylines(a: Polyline2D, b: Polyline2D, eps: float = EPS_WELD) -> Polyline2D:
    ap, bp = list(a.points), list(b.points)
    if not ap:
        return b
    if not bp:
        return a
    if math.hypot(ap[-1][0] - bp[0][0], ap[-1][1] - bp[0][1]) <= eps:
        return Polyline2D(points=ap + bp[1:])
    if math.hypot(ap[-1][0] - bp[-1][0], ap[-1][1] - bp[-1][1]) <= eps:
        return Polyline2D(points=ap + list(reversed(bp[:-1])))
    raise ValueError("polylines are not joinable at endpoints")


def split_segment(polyline: Polyline2D, segment_index: int, t: float) -> Polyline2D:
    pts = list(polyline.points)
    if segment_index < 0 or segment_index >= len(pts) - 1:
        raise ValueError("segment index out of range")
    t = max(0.0, min(1.0, float(t)))
    a, b = pts[segment_index], pts[segment_index + 1]
    p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    pts.insert(segment_index + 1, p)
    return Polyline2D(points=pts)


def open_polyline_to_polygon(polyline: Polyline2D) -> Polygon2D:
    pts = list(polyline.points)
    if len(pts) < 3:
        raise ValueError("polyline needs at least 3 points")
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    return Polygon2D(points=pts)


def create_arc_segment(start: Point2, end: Point2, *, mode: Literal["bulge"] = "bulge", bulge: float = 0.0) -> Arc2D:
    if mode != "bulge":
        raise ValueError("unsupported arc mode")
    return arc_from_bulge(start, end, bulge)
