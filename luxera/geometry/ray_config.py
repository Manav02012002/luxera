from __future__ import annotations

from dataclasses import dataclass

from luxera.geometry.tolerance import EPS_POS, EPS_RAY_ORIGIN, EPS_WELD

# Global ray policy for geometric occlusion checks.
RAY_ORIGIN_EPS = EPS_RAY_ORIGIN
RAY_TMIN = EPS_RAY_ORIGIN * 0.1


@dataclass(frozen=True)
class RayPolicy:
    origin_eps: float
    t_min: float


def scaled_ray_policy(scene_scale: float = 1.0, user_eps: float | None = None) -> RayPolicy:
    s = max(float(scene_scale), EPS_POS)
    base_origin = max(RAY_ORIGIN_EPS * s, EPS_RAY_ORIGIN * EPS_WELD)
    base_tmin = max(RAY_TMIN * s, EPS_POS)
    if user_eps is not None:
        u = max(float(user_eps), EPS_POS)
        base_origin = max(base_origin, u)
        base_tmin = max(base_tmin, u * 0.1)
    return RayPolicy(origin_eps=base_origin, t_min=base_tmin)
