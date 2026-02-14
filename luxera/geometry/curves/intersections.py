from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from luxera.geometry.curves.arc import Arc
from luxera.geometry.tolerance import EPS_POS, EPS_WELD


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class Segment2D:
    a: Point2
    b: Point2


def segment_segment_intersections(s1: Segment2D, s2: Segment2D, eps: float = EPS_WELD) -> List[Point2]:
    p = s1.a
    r = (s1.b[0] - s1.a[0], s1.b[1] - s1.a[1])
    q = s2.a
    s = (s2.b[0] - s2.a[0], s2.b[1] - s2.a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) <= EPS_POS:
        return []
    qp = (q[0] - p[0], q[1] - p[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    u = (qp[0] * r[1] - qp[1] * r[0]) / den
    if -eps <= t <= 1.0 + eps and -eps <= u <= 1.0 + eps:
        x = p[0] + t * r[0]
        y = p[1] + t * r[1]
        return [(float(x), float(y))]
    return []


def segment_arc_intersections(seg: Segment2D, arc: Arc, eps: float = EPS_WELD) -> List[Point2]:
    return arc.intersections_with_line_segment(seg.a, seg.b, eps=eps)


def arc_arc_intersections(a: Arc, b: Arc, eps: float = EPS_WELD) -> List[Point2]:
    return a.intersections_with_arc(b, eps=eps)


def nearest_intersection_to_point(points: List[Point2], ref: Point2) -> Point2 | None:
    if not points:
        return None
    rx, ry = float(ref[0]), float(ref[1])
    return min(points, key=lambda p: math.hypot(p[0] - rx, p[1] - ry))


def cluster_points(points: Sequence[Point2], eps: float = EPS_WELD) -> List[Point2]:
    out: List[Point2] = []
    for p in points:
        px, py = float(p[0]), float(p[1])
        merged = False
        for i, q in enumerate(out):
            if math.hypot(px - q[0], py - q[1]) <= eps:
                out[i] = ((q[0] + px) * 0.5, (q[1] + py) * 0.5)
                merged = True
                break
        if not merged:
            out.append((px, py))
    return out


def polycurve_intersections(
    parts_a: Iterable[Segment2D | Arc],
    parts_b: Iterable[Segment2D | Arc],
    *,
    eps: float = EPS_WELD,
) -> List[Point2]:
    raw: List[Point2] = []
    for a in parts_a:
        for b in parts_b:
            if isinstance(a, Segment2D) and isinstance(b, Segment2D):
                raw.extend(segment_segment_intersections(a, b, eps=eps))
            elif isinstance(a, Segment2D) and isinstance(b, Arc):
                raw.extend(segment_arc_intersections(a, b, eps=eps))
            elif isinstance(a, Arc) and isinstance(b, Segment2D):
                raw.extend(segment_arc_intersections(b, a, eps=eps))
            else:
                raw.extend(arc_arc_intersections(a, b, eps=eps))  # type: ignore[arg-type]
    return cluster_points(raw, eps=eps)
