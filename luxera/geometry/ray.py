from __future__ import annotations

from luxera.geometry.ray_config import RAY_ORIGIN_EPS, RAY_TMIN, scaled_ray_policy

RAY_EPS = RAY_TMIN
ORIGIN_OFFSET = RAY_ORIGIN_EPS


def scaled_ray_epsilon(scene_scale: float = 1.0) -> float:
    return scaled_ray_policy(scene_scale=scene_scale).t_min


def scaled_origin_offset(scene_scale: float = 1.0) -> float:
    return scaled_ray_policy(scene_scale=scene_scale).origin_eps
