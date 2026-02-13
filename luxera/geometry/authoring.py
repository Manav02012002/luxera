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
    hit2 = nearest_intersection_to_point(pts2, arc.end_point)
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
    # Minimal viable: for arcs use trim logic against target intersections near end.
    return trim_curve_to_intersection(curve, target)


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
    res = offset_polygon_v2(polygon, distance)
    if not res.ok or res.polygon is None:
        raise ValueError(res.failure.message if res.failure is not None else "offset failed")
    return res.polygon


def offset(polygon: Polygon2D, distance: float) -> OffsetResult:
    return offset_polygon_v2(polygon, distance)


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
