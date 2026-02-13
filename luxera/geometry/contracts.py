from __future__ import annotations

import math
from typing import Iterable, Sequence, Tuple

from luxera.geometry.polygon2d import validate_polygon_with_holes
from luxera.geometry.primitives import Polygon2D
from luxera.geometry.tolerance import EPS_ANG, EPS_AREA, EPS_PLANE


Vec3 = Tuple[float, float, float]


def _dot(a: Vec3, b: Vec3) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        float(a[1] * b[2] - a[2] * b[1]),
        float(a[2] * b[0] - a[0] * b[2]),
        float(a[0] * b[1] - a[1] * b[0]),
    )


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (float(a[0] - b[0]), float(a[1] - b[1]), float(a[2] - b[2]))


def _norm(v: Vec3) -> float:
    return math.sqrt(_dot(v, v))


def _unit(v: Vec3) -> Vec3:
    n = _norm(v)
    if n <= EPS_ANG:
        raise ValueError("Zero-length basis vector is not allowed.")
    return (v[0] / n, v[1] / n, v[2] / n)


def assert_valid_polygon(p: Polygon2D) -> None:
    report = validate_polygon_with_holes(p.points, ())
    if not report.valid:
        raise ValueError(
            "Invalid polygon: "
            f"self_intersections={report.self_intersections}, "
            f"duplicates={report.duplicate_vertices}, "
            f"hole_outside_outer={report.hole_outside_outer}, "
            f"warnings={report.warnings}"
        )


def assert_orthonormal_basis(u: Vec3, v: Vec3, n: Vec3) -> None:
    uu = _unit(tuple(float(x) for x in u))
    vv = _unit(tuple(float(x) for x in v))
    nn = _unit(tuple(float(x) for x in n))
    uv = abs(_dot(uu, vv))
    un = abs(_dot(uu, nn))
    vn = abs(_dot(vv, nn))
    if uv > EPS_ANG or un > EPS_ANG or vn > EPS_ANG:
        raise ValueError(f"Basis vectors are not orthogonal within tolerance {EPS_ANG}.")
    handed = _dot(_cross(uu, vv), nn)
    if abs(handed) < 1.0 - EPS_PLANE:
        raise ValueError("Basis vectors are not mutually consistent (cross(u, v) !~= n).")


def _surface_points(surface: object) -> Sequence[Vec3]:
    points = getattr(surface, "vertices", None)
    if not isinstance(points, Iterable):
        raise ValueError("Surface must define a vertices sequence.")
    out: list[Vec3] = []
    for p in points:
        if not isinstance(p, (tuple, list)) or len(p) != 3:
            raise ValueError("Surface vertices must be 3D tuples.")
        out.append((float(p[0]), float(p[1]), float(p[2])))
    return out


def assert_surface(surface: object) -> None:
    pts = _surface_points(surface)
    if len(pts) < 3:
        raise ValueError("Surface must contain at least 3 vertices.")

    p0 = pts[0]
    normal: Vec3 | None = None
    for i in range(1, len(pts) - 1):
        n = _cross(_sub(pts[i], p0), _sub(pts[i + 1], p0))
        if _norm(n) > EPS_AREA:
            normal = n
            break
    if normal is None:
        raise ValueError("Surface vertices are degenerate/collinear.")
    normal_u = _unit(normal)

    for p in pts:
        d = abs(_dot(_sub(p, p0), normal_u))
        if d > EPS_PLANE:
            raise ValueError(f"Surface is non-planar (distance {d:.6g} exceeds EPS_PLANE={EPS_PLANE}).")
