from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from luxera.geometry.tolerance import EPS_POS


Point3 = Tuple[float, float, float]
Basis = Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


@dataclass(frozen=True)
class PlanView:
    cut_z: float
    range_zmin: float
    range_zmax: float


@dataclass(frozen=True)
class SectionView:
    plane_origin: Point3
    plane_normal: Point3
    thickness: float


@dataclass(frozen=True)
class ElevationView:
    plane_origin: Point3
    plane_normal: Point3
    direction: Point3 | None = None
    depth: float = 0.0


def _normalize(v: np.ndarray) -> np.ndarray:
    lv = float(np.linalg.norm(v))
    if lv <= EPS_POS:
        raise ValueError("zero-length vector")
    return v / lv


def view_basis(view: PlanView | SectionView | ElevationView) -> Basis:
    """Return stable (origin, u, v, n) basis for a view."""
    if isinstance(view, PlanView):
        origin = np.array([0.0, 0.0, float(view.cut_z)], dtype=float)
        u = np.array([1.0, 0.0, 0.0], dtype=float)
        v = np.array([0.0, 1.0, 0.0], dtype=float)
        n = np.array([0.0, 0.0, 1.0], dtype=float)
        return origin, u, v, n

    origin = np.asarray(view.plane_origin, dtype=float)
    if isinstance(view, ElevationView) and view.direction is not None:
        n = _normalize(np.asarray(view.direction, dtype=float))
    else:
        n = _normalize(np.asarray(view.plane_normal, dtype=float))
    up = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(up, n))) >= (1.0 - EPS_POS):
        up = np.array([0.0, 1.0, 0.0], dtype=float)

    u = _normalize(np.cross(up, n))
    v = _normalize(np.cross(n, u))
    return origin, u, v, n
