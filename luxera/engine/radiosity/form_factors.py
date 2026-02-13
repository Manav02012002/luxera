from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

import numpy as np

from luxera.calculation.radiosity import (
    BVHNode,
    compute_form_factor_analytic,
    compute_form_factor_monte_carlo,
)
from luxera.geometry.core import Surface


@dataclass(frozen=True)
class FormFactorConfig:
    method: Literal["analytic", "monte_carlo"] = "monte_carlo"
    use_visibility: bool = True
    monte_carlo_samples: int = 16


def build_form_factor_matrix(
    patches: List[Surface],
    all_surfaces: List[Surface],
    *,
    config: FormFactorConfig,
    rng: np.random.Generator,
    bvh: Optional[BVHNode] = None,
) -> np.ndarray:
    n = len(patches)
    F = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if config.method == "analytic" or not config.use_visibility:
                F[i, j] = compute_form_factor_analytic(patches[i], patches[j])
            else:
                F[i, j] = compute_form_factor_monte_carlo(
                    patches[i],
                    patches[j],
                    all_surfaces,
                    num_samples=max(1, int(config.monte_carlo_samples)),
                    rng=rng,
                    bvh=bvh,
                )

    # Enforce basic energy conservation in transfer matrix.
    row_sums = np.sum(F, axis=1)
    for i, s in enumerate(row_sums):
        if s > 1.0 and s > 1e-12:
            F[i, :] = F[i, :] / s
    return F

