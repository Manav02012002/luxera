from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from luxera.geometry.polygon2d import make_polygon_with_holes_valid
from luxera.geometry.tolerance import EPS_PLANE


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class UVPolygon:
    outer: List[Point2]
    holes: List[List[Point2]] = field(default_factory=list)


@dataclass(frozen=True)
class MultiPolygon2D:
    polygons: List[UVPolygon]


def _is_rect(poly: Sequence[Point2], eps: float = EPS_PLANE) -> Tuple[bool, Tuple[float, float, float, float]]:
    if len(poly) < 4:
        return False, (0.0, 0.0, 0.0, 0.0)
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    ok = True
    for x, y in poly:
        on_x = abs(float(x) - x0) <= eps or abs(float(x) - x1) <= eps
        on_y = abs(float(y) - y0) <= eps or abs(float(y) - y1) <= eps
        if not (on_x and on_y):
            ok = False
            break
    return ok, (x0, x1, y0, y1)


def _rect_poly(x0: float, x1: float, y0: float, y1: float) -> UVPolygon:
    return UVPolygon(outer=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _poly_area(poly: Sequence[Point2]) -> float:
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def _clip_halfplane(poly: Sequence[Point2], *, axis: str, k: float, keep_ge: bool, eps: float) -> List[Point2]:
    if not poly:
        return []

    def inside(p: Point2) -> bool:
        v = p[0] if axis == "x" else p[1]
        return v >= (k - eps) if keep_ge else v <= (k + eps)

    def intersect(a: Point2, b: Point2) -> Point2:
        av = a[0] if axis == "x" else a[1]
        bv = b[0] if axis == "x" else b[1]
        dv = bv - av
        if abs(dv) <= eps:
            return a
        t = (k - av) / dv
        t = max(0.0, min(1.0, t))
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    out: List[Point2] = []
    prev = poly[-1]
    prev_in = inside(prev)
    for cur in poly:
        cur_in = inside(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect(prev, cur))
            out.append((float(cur[0]), float(cur[1])))
        elif prev_in:
            out.append(intersect(prev, cur))
        prev, prev_in = cur, cur_in
    return out


def _subtract_axis_aligned_rect_from_poly(
    poly: Sequence[Point2],
    rect: Tuple[float, float, float, float],
    eps: float,
) -> List[UVPolygon]:
    x0, x1, y0, y1 = rect
    if len(poly) < 3:
        return []

    # Partition P\\R into disjoint regions clipped from P.
    left = _clip_halfplane(poly, axis="x", k=x0, keep_ge=False, eps=eps)
    right = _clip_halfplane(poly, axis="x", k=x1, keep_ge=True, eps=eps)
    mid = _clip_halfplane(_clip_halfplane(poly, axis="x", k=x0, keep_ge=True, eps=eps), axis="x", k=x1, keep_ge=False, eps=eps)
    bottom = _clip_halfplane(mid, axis="y", k=y0, keep_ge=False, eps=eps)
    top = _clip_halfplane(mid, axis="y", k=y1, keep_ge=True, eps=eps)

    parts: List[UVPolygon] = []
    for p in (left, right, bottom, top):
        if len(p) < 3:
            continue
        if abs(_poly_area(p)) <= eps:
            continue
        parts.append(UVPolygon(outer=[(float(a), float(b)) for a, b in p]))
    return parts


def _subtract_rect(rect: Tuple[float, float, float, float], cut: Tuple[float, float, float, float], eps: float = EPS_PLANE) -> List[UVPolygon]:
    x0, x1, y0, y1 = rect
    cx0, cx1, cy0, cy1 = cut
    ix0, ix1 = max(x0, cx0), min(x1, cx1)
    iy0, iy1 = max(y0, cy0), min(y1, cy1)
    if (ix1 - ix0) <= eps or (iy1 - iy0) <= eps:
        return [_rect_poly(x0, x1, y0, y1)]

    out: List[UVPolygon] = []
    if (ix0 - x0) > eps:
        out.append(_rect_poly(x0, ix0, y0, y1))
    if (x1 - ix1) > eps:
        out.append(_rect_poly(ix1, x1, y0, y1))
    if (iy0 - y0) > eps:
        out.append(_rect_poly(ix0, ix1, y0, iy0))
    if (y1 - iy1) > eps:
        out.append(_rect_poly(ix0, ix1, iy1, y1))
    return out


def _shapely_subtract(wall_poly_uv: UVPolygon, opening_polys_uv: Sequence[Sequence[Point2]]) -> UVPolygon | MultiPolygon2D:
    from shapely.geometry import Polygon  # type: ignore

    geom = Polygon(wall_poly_uv.outer, holes=wall_poly_uv.holes)
    for op in opening_polys_uv:
        if len(op) < 3:
            continue
        geom = geom.difference(Polygon(list(op)))
    geom = geom.buffer(0)
    if geom.is_empty:
        return MultiPolygon2D(polygons=[])

    geoms = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    polys: List[UVPolygon] = []
    for g in geoms:
        outer = [(float(x), float(y)) for x, y in list(g.exterior.coords)[:-1]]
        holes = [[(float(x), float(y)) for x, y in list(r.coords)[:-1]] for r in list(g.interiors)]
        outer_v, holes_v, _ = make_polygon_with_holes_valid(outer, holes)
        polys.append(UVPolygon(outer=outer_v, holes=holes_v))
    if len(polys) == 1:
        return polys[0]
    return MultiPolygon2D(polygons=polys)


def subtract_openings(
    wall_poly_uv: UVPolygon,
    opening_polys_uv: Sequence[Sequence[Point2]],
    *,
    eps: float = EPS_PLANE,
) -> UVPolygon | MultiPolygon2D:
    """Subtract opening polygons from wall polygon in UV space."""
    if not opening_polys_uv:
        return wall_poly_uv

    is_rect_wall, wall_rect = _is_rect(wall_poly_uv.outer, eps=eps)
    rect_cuts: List[Tuple[float, float, float, float]] = []
    if is_rect_wall and not wall_poly_uv.holes:
        all_rect = True
        for op in opening_polys_uv:
            ok, rr = _is_rect(op, eps=eps)
            if not ok:
                all_rect = False
                break
            rect_cuts.append(rr)
        if all_rect:
            parts: List[UVPolygon] = [_rect_poly(*wall_rect)]
            for cut in rect_cuts:
                next_parts: List[UVPolygon] = []
                for part in parts:
                    _, rr = _is_rect(part.outer, eps=eps)
                    next_parts.extend(_subtract_rect(rr, cut, eps=eps))
                parts = next_parts
            if len(parts) == 1:
                return parts[0]
            return MultiPolygon2D(polygons=parts)
    # Native fallback without shapely: arbitrary wall polygon minus axis-aligned rectangular openings.
    if not wall_poly_uv.holes:
        rect_cuts_native: List[Tuple[float, float, float, float]] = []
        all_rect_openings = True
        for op in opening_polys_uv:
            ok, rr = _is_rect(op, eps=eps)
            if not ok:
                all_rect_openings = False
                break
            rect_cuts_native.append(rr)
        if all_rect_openings:
            polys: List[UVPolygon] = [UVPolygon(outer=list(wall_poly_uv.outer))]
            for cut in rect_cuts_native:
                nxt: List[UVPolygon] = []
                for p in polys:
                    nxt.extend(_subtract_axis_aligned_rect_from_poly(p.outer, cut, eps=eps))
                polys = nxt if nxt else polys
            if len(polys) == 1:
                return polys[0]
            return MultiPolygon2D(polygons=polys)

    try:
        return _shapely_subtract(wall_poly_uv, opening_polys_uv)
    except Exception:
        # Conservative fallback: keep wall if robust subtraction backend is unavailable.
        return wall_poly_uv
