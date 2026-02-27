from __future__ import annotations

import numba
import numpy as np


@numba.njit(cache=True)
def _find_bracket(val: float, arr: np.ndarray) -> tuple[int, int, float]:
    n = arr.shape[0]
    if n == 0:
        return 0, 0, 0.0
    if val <= arr[0]:
        return 0, 0, 0.0
    if val >= arr[n - 1]:
        return n - 1, n - 1, 0.0
    for i in range(n - 1):
        a0 = arr[i]
        a1 = arr[i + 1]
        if a0 <= val <= a1:
            d = a1 - a0
            t = (val - a0) / d if d != 0.0 else 0.0
            return i, i + 1, t
    return n - 1, n - 1, 0.0


@numba.njit(cache=True)
def _interp_candela(c_deg: float, g_deg: float, table: np.ndarray, h_angles: np.ndarray, v_angles: np.ndarray) -> float:
    h_lo, h_hi, h_t = _find_bracket(c_deg, h_angles)
    v_lo, v_hi, v_t = _find_bracket(g_deg, v_angles)

    c00 = table[h_lo, v_lo]
    c01 = table[h_lo, v_hi]
    c10 = table[h_hi, v_lo]
    c11 = table[h_hi, v_hi]
    c0 = c00 * (1.0 - v_t) + c01 * v_t
    c1 = c10 * (1.0 - v_t) + c11 * v_t
    return c0 * (1.0 - h_t) + c1 * h_t


@numba.njit(cache=True)
def _compute_direct_grid_jit(
    points: np.ndarray,  # float64[:, 3]
    luminaire_positions: np.ndarray,  # float64[:, 3]
    luminaire_rotations: np.ndarray,  # float64[:, 3, 3]
    candela_tables: np.ndarray,  # float64[:, :, :]
    v_angles: np.ndarray,  # float64[:]
    h_angles: np.ndarray,  # float64[:]
    grid_normal: np.ndarray,  # float64[3]
) -> np.ndarray:
    """
    Numba-accelerated direct illuminance kernel for no-occlusion Type-C luminaires.
    """
    n_points = points.shape[0]
    n_lum = luminaire_positions.shape[0]
    out = np.zeros(n_points, dtype=np.float64)

    h0 = h_angles[0]
    h1 = h_angles[h_angles.shape[0] - 1]
    v0 = v_angles[0]
    v1 = v_angles[v_angles.shape[0] - 1]
    signed_h_domain = h0 < 0.0 < h1

    for p in range(n_points):
        px = points[p, 0]
        py = points[p, 1]
        pz = points[p, 2]
        total_e = 0.0

        for l in range(n_lum):
            lx = luminaire_positions[l, 0]
            ly = luminaire_positions[l, 1]
            lz = luminaire_positions[l, 2]

            vx = px - lx
            vy = py - ly
            vz = pz - lz
            d2 = vx * vx + vy * vy + vz * vz
            if d2 < 1e-6:
                continue
            d = np.sqrt(d2)
            dx = vx / d
            dy = vy / d
            dz = vz / d

            # local_dir = R^T * dir
            r00 = luminaire_rotations[l, 0, 0]
            r01 = luminaire_rotations[l, 0, 1]
            r02 = luminaire_rotations[l, 0, 2]
            r10 = luminaire_rotations[l, 1, 0]
            r11 = luminaire_rotations[l, 1, 1]
            r12 = luminaire_rotations[l, 1, 2]
            r20 = luminaire_rotations[l, 2, 0]
            r21 = luminaire_rotations[l, 2, 1]
            r22 = luminaire_rotations[l, 2, 2]

            local_x = r00 * dx + r10 * dy + r20 * dz
            local_y = r01 * dx + r11 * dy + r21 * dz
            local_z = r02 * dx + r12 * dy + r22 * dz

            # Light only below luminaire (+Z up, nadir is -Z).
            if local_z >= 0.0:
                continue

            cos_gamma = -local_z
            if cos_gamma > 1.0:
                cos_gamma = 1.0
            elif cos_gamma < -1.0:
                cos_gamma = -1.0
            gamma_deg = np.degrees(np.arccos(cos_gamma))
            c_deg = np.degrees(np.arctan2(local_y, local_x))
            if c_deg < 0.0:
                c_deg += 360.0

            if signed_h_domain and c_deg > 180.0:
                c_deg -= 360.0

            if c_deg < h0:
                c_deg = h0
            elif c_deg > h1:
                c_deg = h1
            if gamma_deg < v0:
                gamma_deg = v0
            elif gamma_deg > v1:
                gamma_deg = v1

            intensity = _interp_candela(c_deg, gamma_deg, candela_tables[l], h_angles, v_angles)
            cos_incidence = -(dx * grid_normal[0] + dy * grid_normal[1] + dz * grid_normal[2])
            if cos_incidence <= 0.0:
                continue
            total_e += intensity * cos_incidence / d2

        out[p] = total_e if total_e > 0.0 else 0.0

    return out

