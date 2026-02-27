from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from luxera.geometry.core import Vector3
from luxera.photometry.canonical import CanonicalPhotometry
from luxera.photometry.sample import direction_to_photometric_angles


@dataclass(frozen=True)
class PhotometryLUT:
    content_hash: str
    system: str
    angles_h_deg: np.ndarray
    angles_v_deg: np.ndarray
    intensity_cd: np.ndarray
    symmetry: str = "UNKNOWN"


def build_interpolation_lut(canonical: CanonicalPhotometry) -> PhotometryLUT:
    return PhotometryLUT(
        content_hash=canonical.content_hash,
        system=str(canonical.system),
        angles_h_deg=np.asarray(canonical.angles_h_deg, dtype=float),
        angles_v_deg=np.asarray(canonical.angles_v_deg, dtype=float),
        intensity_cd=np.asarray(canonical.intensity_cd, dtype=float),
        symmetry=str(canonical.symmetry),
    )


def _find_bracket(val: float, arr: np.ndarray) -> Tuple[int, int, float]:
    n = len(arr)
    if n == 0:
        return 0, 0, 0.0
    if val <= arr[0]:
        return 0, 0, 0.0
    if val >= arr[-1]:
        return n - 1, n - 1, 0.0
    for i in range(n - 1):
        if arr[i] <= val <= arr[i + 1]:
            d = arr[i + 1] - arr[i]
            t = (val - arr[i]) / d if d != 0 else 0.0
            return i, i + 1, t
    return n - 1, n - 1, 0.0


def _find_cyclic_bracket(val: float, arr: np.ndarray, period: float = 360.0) -> Tuple[int, int, float]:
    n = len(arr)
    if n == 0:
        return 0, 0, 0.0
    if n == 1:
        return 0, 0, 0.0

    lo = float(arr[0])
    x = ((float(val) - lo) % period) + lo
    if x > float(arr[-1]):
        denom = (lo + period) - float(arr[-1])
        t = (x - float(arr[-1])) / denom if denom != 0.0 else 0.0
        return n - 1, 0, t
    for i in range(n - 1):
        a = float(arr[i])
        b = float(arr[i + 1])
        if a <= x <= b:
            d = b - a
            t = (x - a) / d if d != 0.0 else 0.0
            return i, i + 1, t
    return n - 1, 0, 0.0


def _apply_symmetry_from_domain(c_deg: float, c_angles: np.ndarray, symmetry: str) -> float:
    if len(c_angles) == 0:
        return c_deg
    c = c_deg % 360.0
    sym = str(symmetry or "UNKNOWN").upper()
    if sym == "FULL":
        return 0.0
    if sym == "QUADRANT":
        if c <= 90.0:
            return c
        if c <= 180.0:
            return 180.0 - c
        if c <= 270.0:
            return c - 180.0
        return 360.0 - c
    if sym == "BILATERAL":
        return c if c <= 180.0 else 360.0 - c
    if len(c_angles) == 1:
        return 0.0
    span = float(c_angles[-1] - c_angles[0])
    if span <= 90.0 + 1e-9:
        if c <= 90.0:
            return c
        if c <= 180.0:
            return 180.0 - c
        if c <= 270.0:
            return c - 180.0
        return 360.0 - c
    if span <= 180.0 + 1e-9:
        return c if c <= 180.0 else 360.0 - c
    return c


def sample_lut_intensity_cd(lut: PhotometryLUT, direction_luminaire_frame: Vector3) -> float:
    c_deg, g_deg = direction_to_photometric_angles(
        direction_luminaire_frame,
        lut.system,
        lut.angles_v_deg,
    )
    c_deg = _apply_symmetry_from_domain(c_deg, np.asarray(lut.angles_h_deg, dtype=float), str(getattr(lut, "symmetry", "UNKNOWN")))
    c = np.asarray(lut.angles_h_deg, dtype=float)
    g = np.asarray(lut.angles_v_deg, dtype=float)

    can_use_cyclic = (
        c.size >= 2
        and float(c[0]) >= -1e-9
        and float(c[-1]) <= 360.0 + 1e-9
        and (float(c[-1]) - float(c[0])) < 360.0 - 1e-9
    )
    if can_use_cyclic:
        c_lo, c_hi, c_t = _find_cyclic_bracket(c_deg, c, period=360.0)
    else:
        if c.size >= 2 and c[0] < 0 < c[-1] and c_deg > 180.0:
            c_deg -= 360.0
        c_deg = max(float(c[0]), min(float(c[-1]), c_deg))
        c_lo, c_hi, c_t = _find_bracket(c_deg, c)

    g_deg = max(float(g[0]), min(float(g[-1]), g_deg))
    g_lo, g_hi, g_t = _find_bracket(g_deg, g)
    c00 = lut.intensity_cd[c_lo][g_lo]
    c01 = lut.intensity_cd[c_lo][g_hi]
    c10 = lut.intensity_cd[c_hi][g_lo]
    c11 = lut.intensity_cd[c_hi][g_hi]
    v0 = c00 * (1.0 - g_t) + c01 * g_t
    v1 = c10 * (1.0 - g_t) + c11 * g_t
    return float(v0 * (1.0 - c_t) + v1 * c_t)
