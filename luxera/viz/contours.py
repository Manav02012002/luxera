from __future__ import annotations

from typing import List

import numpy as np


def compute_contour_levels(values: np.ndarray, n_levels: int = 8) -> List[float]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return [0.0]
    vmin = float(np.min(arr))
    vmax = float(np.max(arr))
    if vmax <= vmin + 1e-12:
        return [vmin]
    n = max(2, int(n_levels))
    return [float(x) for x in np.linspace(vmin, vmax, n)]

