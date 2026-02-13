from __future__ import annotations
"""Contract: docs/spec/emergency_contract.md, docs/spec/solver_contracts.md."""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from luxera.engine.direct_illuminance import OcclusionContext, run_direct_points
from luxera.calculation.illuminance import Luminaire
from luxera.geometry.core import Vector3
from luxera.project.schema import EscapeRouteSpec


@dataclass(frozen=True)
class EmergencyRouteResult:
    route_id: str
    points: np.ndarray
    values: np.ndarray
    summary: Dict[str, float]


def _route_samples(route: EscapeRouteSpec, length_scale: float = 1.0) -> np.ndarray:
    poly = [np.asarray([float(x) * length_scale, float(y) * length_scale, float(z) * length_scale], dtype=float) for (x, y, z) in route.polyline]
    if len(poly) < 2:
        return np.zeros((0, 3), dtype=float)
    spacing = max(float(route.spacing_m) * length_scale, 1e-3)
    half_w = max(float(route.width_m) * 0.5 * length_scale, 0.0)
    margins = max(float(route.end_margin_m) * length_scale, 0.0)
    samples: List[np.ndarray] = []
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        d = b - a
        seg_len = float(np.linalg.norm(d))
        if seg_len <= 1e-9:
            continue
        u = d / seg_len
        lateral = np.array([-u[1], u[0], 0.0], dtype=float)
        start = margins if i == 0 else 0.0
        end = max(start, seg_len - (margins if i == len(poly) - 2 else 0.0))
        s = start
        while s <= end + 1e-9:
            c = a + u * s
            for off in (-half_w, 0.0, half_w):
                p = c + lateral * off
                p[2] = float(route.height_m) * length_scale
                samples.append(p.copy())
            s += spacing
    if not samples:
        return np.zeros((0, 3), dtype=float)
    return np.asarray(samples, dtype=float)


def run_escape_routes(
    routes: List[EscapeRouteSpec],
    luminaires: List[Luminaire],
    *,
    emergency_factor: float = 1.0,
    occlusion: OcclusionContext | None = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
    length_scale: float = 1.0,
) -> List[EmergencyRouteResult]:
    if not routes:
        return []
    ef = max(0.0, float(emergency_factor))
    scaled_lums = [Luminaire(photometry=l.photometry, transform=l.transform, flux_multiplier=l.flux_multiplier * ef, tilt_deg=l.tilt_deg) for l in luminaires]
    out: List[EmergencyRouteResult] = []
    for route in routes:
        points = _route_samples(route, length_scale=length_scale)
        if points.size == 0:
            values = np.zeros((0,), dtype=float)
        else:
            r = run_direct_points(
                points=points,
                surface_normal=Vector3.up(),
                luminaires=scaled_lums,
                occlusion=occlusion,
                use_occlusion=use_occlusion,
                occlusion_epsilon=occlusion_epsilon,
            )
            values = r.values
        mean_v = float(np.mean(values)) if values.size else 0.0
        min_v = float(np.min(values)) if values.size else 0.0
        max_v = float(np.max(values)) if values.size else 0.0
        out.append(
            EmergencyRouteResult(
                route_id=route.id,
                points=points,
                values=values,
                summary={
                    "min_lux": min_v,
                    "mean_lux": mean_v,
                    "max_lux": max_v,
                    "u0": (min_v / mean_v) if mean_v > 1e-9 else 0.0,
                },
            )
        )
    return out
