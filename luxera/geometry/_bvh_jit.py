from __future__ import annotations

import numba
import numpy as np


@numba.njit(cache=True)
def _aabb_hit(
    origin: np.ndarray,
    direction: np.ndarray,
    bounds: np.ndarray,
    t_min: float,
    t_max: float,
    epsilon: float,
) -> bool:
    lo = t_min
    hi = t_max
    for axis in range(3):
        o = origin[axis]
        d = direction[axis]
        mn = bounds[axis]
        mx = bounds[axis + 3]
        if abs(d) < epsilon:
            if o < mn or o > mx:
                return False
            continue
        inv_d = 1.0 / d
        t0 = (mn - o) * inv_d
        t1 = (mx - o) * inv_d
        if t0 > t1:
            tmp = t0
            t0 = t1
            t1 = tmp
        if t0 > lo:
            lo = t0
        if t1 < hi:
            hi = t1
        if hi < lo:
            return False
    return True


@numba.njit(cache=True)
def _ray_intersects_triangle_two_sided(
    origin: np.ndarray,
    direction: np.ndarray,
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    t_min: float,
    t_max: float,
    epsilon: float,
) -> bool:
    e1 = v1 - v0
    e2 = v2 - v0
    pvec = np.cross(direction, e2)
    det = e1[0] * pvec[0] + e1[1] * pvec[1] + e1[2] * pvec[2]
    if abs(det) < epsilon:
        return False

    inv_det = 1.0 / det
    tvec = origin - v0
    u = (tvec[0] * pvec[0] + tvec[1] * pvec[1] + tvec[2] * pvec[2]) * inv_det
    if u < 0.0 or u > 1.0:
        return False

    qvec = np.cross(tvec, e1)
    v = (direction[0] * qvec[0] + direction[1] * qvec[1] + direction[2] * qvec[2]) * inv_det
    if v < 0.0 or (u + v) > 1.0:
        return False

    t = (e2[0] * qvec[0] + e2[1] * qvec[1] + e2[2] * qvec[2]) * inv_det
    return t_min <= t <= t_max


@numba.njit(cache=True)
def any_hit_flat(
    origin: np.ndarray,
    direction: np.ndarray,
    max_t: float,
    node_bounds: np.ndarray,
    node_left: np.ndarray,
    node_right: np.ndarray,
    node_tri_start: np.ndarray,
    node_tri_count: np.ndarray,
    tri_v0: np.ndarray,
    tri_v1: np.ndarray,
    tri_v2: np.ndarray,
    epsilon: float,
) -> bool:
    n_nodes = node_bounds.shape[0]
    if n_nodes == 0:
        return False

    stack = np.empty(n_nodes, dtype=np.int32)
    top = 0
    stack[top] = 0
    top += 1

    while top > 0:
        top -= 1
        node_idx = stack[top]
        bounds = node_bounds[node_idx]
        if not _aabb_hit(origin, direction, bounds, epsilon, max_t, epsilon):
            continue

        tri_count = node_tri_count[node_idx]
        if tri_count > 0:
            tri_start = node_tri_start[node_idx]
            tri_end = tri_start + tri_count
            for ti in range(tri_start, tri_end):
                if _ray_intersects_triangle_two_sided(
                    origin, direction, tri_v0[ti], tri_v1[ti], tri_v2[ti], epsilon, max_t, epsilon
                ):
                    return True
            continue

        left = node_left[node_idx]
        right = node_right[node_idx]
        if left >= 0:
            stack[top] = left
            top += 1
        if right >= 0:
            stack[top] = right
            top += 1

    return False


@numba.njit(cache=True)
def batch_any_hit(
    origins: np.ndarray,
    directions: np.ndarray,
    max_ts: np.ndarray,
    node_bounds: np.ndarray,
    node_left: np.ndarray,
    node_right: np.ndarray,
    node_tri_start: np.ndarray,
    node_tri_count: np.ndarray,
    tri_v0: np.ndarray,
    tri_v1: np.ndarray,
    tri_v2: np.ndarray,
    epsilon: float,
) -> np.ndarray:
    n = origins.shape[0]
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        out[i] = any_hit_flat(
            origins[i],
            directions[i],
            max_ts[i],
            node_bounds,
            node_left,
            node_right,
            node_tri_start,
            node_tri_count,
            tri_v0,
            tri_v1,
            tri_v2,
            epsilon,
        )
    return out
