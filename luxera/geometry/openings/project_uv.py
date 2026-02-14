from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

from luxera.geometry.contracts import assert_orthonormal_basis, assert_surface
from luxera.geometry.tolerance import EPS_POS
from luxera.project.schema import SurfaceSpec


Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]


def wall_basis(surface: SurfaceSpec) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return a stable wall-local frame as (origin, u, v, n)."""
    assert_surface(surface)
    verts = np.asarray(surface.vertices, dtype=float)
    if verts.shape[0] < 3:
        raise ValueError("wall needs at least 3 vertices")

    origin = verts[0]
    # Fit a robust plane normal for noisy/imported/slanted walls.
    c = np.mean(verts, axis=0)
    centered = verts - c
    _u_svd, _s_svd, vh = np.linalg.svd(centered, full_matrices=False)
    n = vh[-1]
    ln = float(np.linalg.norm(n))
    if ln <= EPS_POS:
        raise ValueError("invalid wall normal for local frame")
    n = n / ln

    # Prefer the first edge as U; project it onto the fitted plane.
    u_raw = verts[1] - origin
    u = u_raw - n * float(np.dot(u_raw, n))
    lu = float(np.linalg.norm(u))
    if lu <= EPS_POS:
        # Fallback to principal in-plane axis from SVD.
        u = vh[0]
        u = u - n * float(np.dot(u, n))
        lu = float(np.linalg.norm(u))
        if lu <= EPS_POS:
            raise ValueError("invalid wall edge for local frame")
    u = u / lu

    v = np.cross(n, u)
    lv = float(np.linalg.norm(v))
    if lv <= EPS_POS:
        raise ValueError("invalid wall vertical axis for local frame")
    v = v / lv

    assert_orthonormal_basis(
        (float(u[0]), float(u[1]), float(u[2])),
        (float(v[0]), float(v[1]), float(v[2])),
        (float(n[0]), float(n[1]), float(n[2])),
    )
    return origin, u, v, n


def project_points_to_uv(points3d: Sequence[Point3], origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> List[Point2]:
    out: List[Point2] = []
    for p in points3d:
        d = np.asarray(p, dtype=float) - origin
        out.append((float(np.dot(d, u)), float(np.dot(d, v))))
    return out


def lift_uv_to_3d(points2d: Sequence[Point2], origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> List[Point3]:
    out: List[Point3] = []
    for uu, vv in points2d:
        p = origin + u * float(uu) + v * float(vv)
        out.append((float(p[0]), float(p[1]), float(p[2])))
    return out
