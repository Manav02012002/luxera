from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from luxera.geometry.core import Surface, Vector3
from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance


@dataclass(frozen=True)
class SurfaceGrid:
    surface_id: str
    points: np.ndarray  # (N,3)
    values: np.ndarray  # (N,)
    resolution: int


def _surface_bounds(surface: Surface) -> tuple[Vector3, Vector3]:
    xs = [v.x for v in surface.polygon.vertices]
    ys = [v.y for v in surface.polygon.vertices]
    zs = [v.z for v in surface.polygon.vertices]
    return Vector3(min(xs), min(ys), min(zs)), Vector3(max(xs), max(ys), max(zs))


def compute_surface_grid(
    surface: Surface,
    luminaires: List[Luminaire],
    resolution: int = 10,
) -> SurfaceGrid:
    bb_min, bb_max = _surface_bounds(surface)
    xs = np.linspace(bb_min.x, bb_max.x, resolution)
    ys = np.linspace(bb_min.y, bb_max.y, resolution)
    points = []
    values = []

    for x in xs:
        for y in ys:
            p = Vector3(x, y, bb_min.z)
            points.append(p.to_tuple())
            total = 0.0
            for lum in luminaires:
                total += calculate_direct_illuminance(p, surface.normal, lum)
            values.append(total)

    return SurfaceGrid(
        surface_id=surface.id,
        points=np.array(points, dtype=float),
        values=np.array(values, dtype=float),
        resolution=resolution,
    )


def compute_surface_grids(
    surfaces: List[Surface],
    luminaires: List[Luminaire],
    resolution: int = 10,
) -> Dict[str, SurfaceGrid]:
    grids: Dict[str, SurfaceGrid] = {}
    for s in surfaces:
        grids[s.id] = compute_surface_grid(s, luminaires, resolution)
    return grids
