from __future__ import annotations
"""Contract: docs/spec/emergency_contract.md, docs/spec/solver_contracts.md."""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.engine.direct_illuminance import (
    OcclusionContext,
    run_direct_grid,
)
from luxera.project.schema import CalcGrid


@dataclass(frozen=True)
class EmergencyOpenAreaResult:
    target_id: str
    points: np.ndarray
    values: np.ndarray
    nx: int
    ny: int
    summary: Dict[str, float]


def run_open_area(
    grids: List[CalcGrid],
    luminaires: List[Luminaire],
    *,
    emergency_factor: float = 1.0,
    occlusion: OcclusionContext | None = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
) -> List[EmergencyOpenAreaResult]:
    if not grids:
        return []
    ef = max(0.0, float(emergency_factor))
    scaled_lums = [Luminaire(photometry=l.photometry, transform=l.transform, flux_multiplier=l.flux_multiplier * ef, tilt_deg=l.tilt_deg) for l in luminaires]
    out: List[EmergencyOpenAreaResult] = []
    for g in grids:
        r = run_direct_grid(
            g,
            scaled_lums,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )
        vals = r.values.reshape(-1)
        mean_v = float(np.mean(vals)) if vals.size else 0.0
        min_v = float(np.min(vals)) if vals.size else 0.0
        max_v = float(np.max(vals)) if vals.size else 0.0
        out.append(
            EmergencyOpenAreaResult(
                target_id=g.id,
                points=r.points,
                values=vals,
                nx=r.nx,
                ny=r.ny,
                summary={
                    "min_lux": min_v,
                    "mean_lux": mean_v,
                    "max_lux": max_v,
                    "u0": (min_v / mean_v) if mean_v > 1e-9 else 0.0,
                },
            )
        )
    return out
