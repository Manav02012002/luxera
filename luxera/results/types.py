from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

import numpy as np

from luxera.calculation.illuminance import IlluminanceResult


@dataclass(frozen=True)
class GridResult:
    points: np.ndarray  # shape (N,3)
    values: np.ndarray  # shape (N,)
    grid_meta: Dict[str, Any]

    @property
    def min_lux(self) -> float:
        return float(np.min(self.values)) if self.values.size else 0.0

    @property
    def max_lux(self) -> float:
        return float(np.max(self.values)) if self.values.size else 0.0

    @property
    def mean_lux(self) -> float:
        return float(np.mean(self.values)) if self.values.size else 0.0

    @property
    def uniformity_ratio(self) -> float:
        avg = self.mean_lux
        if avg <= 0:
            return 0.0
        return self.min_lux / avg


def grid_result_from_illuminance(result: IlluminanceResult) -> GridResult:
    grid = result.grid
    points = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
    values = result.values.reshape(-1).astype(float)
    meta = {
        "origin": grid.origin.to_tuple(),
        "width": grid.width,
        "height": grid.height,
        "elevation": grid.elevation,
        "nx": grid.nx,
        "ny": grid.ny,
        "normal": grid.normal.to_tuple(),
        "units": "lux",
    }
    return GridResult(points=points, values=values, grid_meta=meta)

