from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from luxera.geometry.tolerance import EPS_POS, EPS_WELD


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class PolygonValidityReport:
    valid: bool
    self_intersections: int = 0
    winding: str = "CCW"
    hole_outside_outer: int = 0
    duplicate_vertices: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": bool(self.valid),
            "self_intersections": int(self.self_intersections),
            "winding": str(self.winding),
            "hole_outside_outer": int(self.hole_outside_outer),
            "duplicate_vertices": int(self.duplicate_vertices),
            "warnings": list(self.warnings),
        }


def _signed_area(poly: Sequence[Point2]) -> float:
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def _orient(a: Point2, b: Point2, c: Point2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    return (o1 * o2 < 0.0) and (o3 * o4 < 0.0)


def _point_in_polygon(pt: Point2, poly: Sequence[Point2]) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside


def validate_polygon_with_holes(outer: Sequence[Point2], holes: Sequence[Sequence[Point2]] = ()) -> PolygonValidityReport:
    warnings: List[str] = []
    if len(outer) < 3:
        return PolygonValidityReport(valid=False, warnings=["Outer polygon has fewer than 3 points."])

    # duplicate vertices
    dup = 0
    seen = set()
    for p in outer:
        key = (round(float(p[0]), 9), round(float(p[1]), 9))
        if key in seen:
            dup += 1
        seen.add(key)

    # self-intersections
    si = 0
    for i in range(len(outer)):
        a, b = outer[i], outer[(i + 1) % len(outer)]
        for j in range(i + 2, len(outer)):
            if i == 0 and j == len(outer) - 1:
                continue
            c, d = outer[j], outer[(j + 1) % len(outer)]
            if _segments_intersect(a, b, c, d):
                si += 1

    winding = "CCW" if _signed_area(outer) > 0.0 else "CW"

    hole_out = 0
    for hole in holes:
        if len(hole) < 3:
            warnings.append("Hole has fewer than 3 points.")
            hole_out += 1
            continue
        cx = sum(p[0] for p in hole) / len(hole)
        cy = sum(p[1] for p in hole) / len(hole)
        if not _point_in_polygon((cx, cy), outer):
            hole_out += 1

    valid = (si == 0) and (hole_out == 0) and (len(outer) >= 3)
    return PolygonValidityReport(
        valid=valid,
        self_intersections=si,
        winding=winding,
        hole_outside_outer=hole_out,
        duplicate_vertices=dup,
        warnings=warnings,
    )


def make_polygon_valid(points: Sequence[Point2], *, snap_eps: float = EPS_WELD) -> List[Point2]:
    # snap nearly coincident vertices + remove consecutive duplicates
    out: List[Point2] = []
    inv = 1.0 / max(float(snap_eps), EPS_POS)
    for x, y in points:
        p = (round(float(x) * inv) / inv, round(float(y) * inv) / inv)
        if out and abs(out[-1][0] - p[0]) <= snap_eps and abs(out[-1][1] - p[1]) <= snap_eps:
            continue
        out.append(p)
    if len(out) >= 2 and abs(out[0][0] - out[-1][0]) <= snap_eps and abs(out[0][1] - out[-1][1]) <= snap_eps:
        out.pop()

    report = validate_polygon_with_holes(out, ())
    if report.valid:
        # enforce CCW winding
        if _signed_area(out) < 0.0:
            out = list(reversed(out))
        return out

    # Optional robust cleanup when available.
    try:
        from shapely.geometry import Polygon  # type: ignore

        poly = Polygon(out)
        cleaned = poly.buffer(0)
        if not cleaned.is_empty:
            ext = [(float(x), float(y)) for x, y in list(cleaned.exterior.coords)[:-1]]
            if len(ext) >= 3:
                if _signed_area(ext) < 0.0:
                    ext = list(reversed(ext))
                return ext
    except Exception:
        pass

    # Fallback cleanup: convex hull (monotonic chain)
    pts = sorted(set((float(x), float(y)) for x, y in out))
    if len(pts) < 3:
        return pts

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
    hull = lower[:-1] + upper[:-1]
    return hull


def make_polygon_with_holes_valid(
    outer: Sequence[Point2],
    holes: Sequence[Sequence[Point2]],
    *,
    snap_eps: float = EPS_WELD,
) -> tuple[List[Point2], List[List[Point2]], PolygonValidityReport]:
    fixed_outer = make_polygon_valid(outer, snap_eps=snap_eps)
    fixed_holes: List[List[Point2]] = []
    for hole in holes:
        h = make_polygon_valid(hole, snap_eps=snap_eps)
        if len(h) < 3:
            continue
        if _signed_area(h) > 0.0:
            h = list(reversed(h))  # holes clockwise
        cx = sum(p[0] for p in h) / len(h)
        cy = sum(p[1] for p in h) / len(h)
        if _point_in_polygon((cx, cy), fixed_outer):
            fixed_holes.append(h)
    report = validate_polygon_with_holes(fixed_outer, fixed_holes)
    return fixed_outer, fixed_holes, report
