from __future__ import annotations
"""Contract: docs/spec/photometry_contracts.md, docs/spec/coordinate_conventions.md."""

import math
from typing import Tuple

import numpy as np

from luxera.core.types import Transform
from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry, TiltData


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
            denom = arr[i + 1] - arr[i]
            t = (val - arr[i]) / denom if denom != 0 else 0.0
            return i, i + 1, t
    return n - 1, n - 1, 0.0


def _find_cyclic_bracket(val: float, arr: np.ndarray, period: float = 360.0) -> Tuple[int, int, float]:
    """
    Find interpolation bracket on a cyclic axis.

    Supports seam interpolation between the last tabulated plane and the first plane
    shifted by +period (Type C horizontal wrap behavior).
    """
    n = len(arr)
    if n == 0:
        return 0, 0, 0.0
    if n == 1:
        return 0, 0, 0.0

    lo = float(arr[0])
    span = float(arr[-1] - arr[0])
    x = ((float(val) - lo) % period) + lo
    if x > float(arr[-1]):
        # Seam segment [arr[-1], arr[0] + period]
        denom = (lo + period) - float(arr[-1])
        t = (x - float(arr[-1])) / denom if denom != 0.0 else 0.0
        return n - 1, 0, t

    for i in range(n - 1):
        a = float(arr[i])
        b = float(arr[i + 1])
        if a <= x <= b:
            denom = b - a
            t = (x - a) / denom if denom != 0.0 else 0.0
            return i, i + 1, t
    if span <= 0.0:
        return 0, 0, 0.0
    return n - 1, 0, 0.0


def _apply_symmetry(c_deg: float, phot: Photometry) -> float:
    c = c_deg % 360.0
    if phot.symmetry == "FULL":
        return 0.0
    if phot.symmetry == "QUADRANT":
        if c <= 90:
            return c
        if c <= 180:
            return 180 - c
        if c <= 270:
            return c - 180
        return 360 - c
    if phot.symmetry == "BILATERAL":
        if c <= 180:
            return c
        return 360 - c
    return c


def _angles_from_direction_type_c(direction: Vector3) -> Tuple[float, float]:
    # Local frame convention: +Z up, nadir is -Z
    d = direction.normalize()
    cos_gamma = -d.z
    cos_gamma = max(-1.0, min(1.0, cos_gamma))
    gamma_deg = math.degrees(math.acos(cos_gamma))
    c_deg = (math.degrees(math.atan2(d.y, d.x)) + 360.0) % 360.0
    return c_deg, gamma_deg


def _rotate_about_axis(v: Vector3, axis: Vector3, angle_rad: float) -> Vector3:
    # Rodrigues' rotation formula
    a = axis.normalize()
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    term1 = v * cos_a
    term2 = a.cross(v) * sin_a
    term3 = a * (a.dot(v) * (1.0 - cos_a))
    return term1 + term2 + term3


def _angles_from_direction_type_ab(
    direction: Vector3,
    system: str,
    vertical_angles: np.ndarray,
) -> Tuple[float, float]:
    # Contract: docs/spec/photometry_typeb.md
    p = Vector3(1, 0, 0) if system == "A" else Vector3(0, 1, 0)
    d = direction.normalize()
    e0 = Vector3(0, 0, -1)  # projection of -Z onto plane normal to p in canonical local frame
    e90 = p.cross(e0)
    if e90.length() < 1e-12:
        e90 = Vector3(1, 0, 0)
    e90 = e90.normalize()

    d_perp = d - p * p.dot(d)
    if d_perp.length() < 1e-12:
        h_deg = 0.0
    else:
        u = d_perp.normalize()
        ccw = math.degrees(math.atan2(u.dot(e90), u.dot(e0)))
        h_deg = (-ccw + 360.0) % 360.0

    # Determine vertical-angle convention from data range
    vmin = float(np.min(vertical_angles)) if len(vertical_angles) else 0.0
    vmax = float(np.max(vertical_angles)) if len(vertical_angles) else 0.0
    use_elevation = vmin < 0.0 or vmax <= 90.0

    # Compute vertical angle
    if use_elevation:
        # Elevation from global horizontal plane (legacy A/B behavior).
        horiz = math.sqrt(d.x * d.x + d.y * d.y)
        v_deg = math.degrees(math.atan2(d.z, horiz))
    else:
        # Polar from +p axis.
        v_deg = math.degrees(math.acos(max(-1.0, min(1.0, d.dot(p)))))

    return h_deg, v_deg


def angles_to_direction_type_ab(
    h_deg: float,
    v_deg: float,
    system: str,
    vertical_angles: np.ndarray | None = None,
) -> Vector3:
    """
    Convert Type A/B photometric angles back to a luminaire-local direction.

    This is the inverse companion to `_angles_from_direction_type_ab` for
    deterministic transform/parity tests.
    """
    sys = str(system).upper()
    if sys not in {"A", "B"}:
        raise ValueError(f"angles_to_direction_type_ab requires system 'A' or 'B', got: {system!r}")

    p = Vector3(1, 0, 0) if sys == "A" else Vector3(0, 1, 0)
    e0 = Vector3(0, 0, -1)
    e90 = p.cross(e0)
    if e90.length() < 1e-12:
        e90 = Vector3(1, 0, 0)
    e90 = e90.normalize()

    ccw = math.radians((-float(h_deg)) % 360.0)
    radial = (e0 * math.cos(ccw) + e90 * math.sin(ccw)).normalize()

    va = vertical_angles if vertical_angles is not None else np.array([0.0, 90.0, 180.0], dtype=float)
    vmin = float(np.min(va)) if len(va) else 0.0
    vmax = float(np.max(va)) if len(va) else 0.0
    use_elevation = vmin < 0.0 or vmax <= 90.0

    if use_elevation:
        # Elevation from horizontal plane orthogonal to p.
        elev = math.radians(float(v_deg))
        d = p * math.sin(elev) + radial * math.cos(elev)
        return d.normalize()

    # Polar from +p axis.
    beta = math.radians(float(v_deg))
    d = p * math.cos(beta) + radial * math.sin(beta)
    return d.normalize()


def world_to_luminaire_local_direction(transform: Transform, world_dir: Vector3) -> Vector3:
    """
    Convert a world-space direction to luminaire-local direction.

    Convention reference: docs/spec/coordinate_conventions.md
    """
    R = transform.get_rotation_matrix()
    return Vector3.from_array(R.T @ world_dir.normalize().to_array())


def _axis_from_token(token: str) -> Vector3:
    t = str(token).strip().upper()
    axes = {
        "+X": Vector3(1.0, 0.0, 0.0),
        "-X": Vector3(-1.0, 0.0, 0.0),
        "+Y": Vector3(0.0, 1.0, 0.0),
        "-Y": Vector3(0.0, -1.0, 0.0),
        "+Z": Vector3(0.0, 0.0, 1.0),
        "-Z": Vector3(0.0, 0.0, -1.0),
    }
    return axes.get(t, Vector3(0.0, 0.0, 1.0))


def _apply_orientation(local_dir: Vector3, orientation: dict[str, str] | None) -> Vector3:
    if not orientation:
        return local_dir
    up = _axis_from_token(orientation.get("luminaire_up_axis", "+Z")).normalize()
    forward = _axis_from_token(orientation.get("photometric_forward_axis", "+X")).normalize()
    side = up.cross(forward)
    if side.length() < 1e-9:
        return local_dir
    side = side.normalize()
    d = local_dir.normalize()
    return Vector3(d.dot(forward), d.dot(side), d.dot(up))


def world_dir_to_photometric_angles(
    world_dir: Vector3,
    luminaire_transform: Transform,
    orientation: dict[str, str] | None,
    system: str,
    vertical_angles: np.ndarray | None = None,
) -> Tuple[float, float]:
    local_dir = world_to_luminaire_local_direction(luminaire_transform, world_dir)
    oriented = _apply_orientation(local_dir, orientation)
    return direction_to_photometric_angles(oriented, system, vertical_angles)


def direction_to_photometric_angles(
    direction_luminaire_frame: Vector3,
    system: str,
    vertical_angles: np.ndarray | None = None,
) -> Tuple[float, float]:
    """
    Convert luminaire-local direction to photometric angles for the given system.
    Returns (C_or_H_deg, gamma_or_V_deg).

    Convention reference: docs/spec/coordinate_conventions.md
    """
    if system == "C":
        return _angles_from_direction_type_c(direction_luminaire_frame)
    if system in ("A", "B"):
        va = vertical_angles if vertical_angles is not None else np.array([0.0, 90.0, 180.0], dtype=float)
        return _angles_from_direction_type_ab(direction_luminaire_frame, system, va)
    raise NotImplementedError(f"Photometric system {system} not yet supported")


def _tilt_factor_for_gamma(tilt: TiltData, gamma_deg: float) -> float:
    series = tilt.to_series()
    if series is None:
        return 1.0
    return float(series.interpolate(float(gamma_deg)))


def _sample_from_angles_and_table(
    *,
    c_deg: float,
    gamma_deg: float,
    c_angles: np.ndarray,
    g_angles: np.ndarray,
    candela: np.ndarray,
) -> float:
    # Type C seam interpolation (cyclic) when the horizontal domain is partial [0, <360).
    can_use_cyclic = (
        len(c_angles) >= 2
        and float(c_angles[0]) >= -1e-9
        and float(c_angles[-1]) <= 360.0 + 1e-9
        and (float(c_angles[-1]) - float(c_angles[0])) < 360.0 - 1e-9
    )

    if can_use_cyclic:
        c_lo, c_hi, c_t = _find_cyclic_bracket(c_deg, c_angles, period=360.0)
    else:
        # Backward-compatible non-cyclic clamp for non-Type-C or explicit signed domains.
        if len(c_angles) >= 2 and c_angles[0] < 0 < c_angles[-1] and c_deg > 180:
            c_deg -= 360
        c_deg = max(float(c_angles[0]), min(float(c_angles[-1]), float(c_deg)))
        c_lo, c_hi, c_t = _find_bracket(c_deg, c_angles)

    gamma_deg = max(float(g_angles[0]), min(float(g_angles[-1]), float(gamma_deg)))
    g_lo, g_hi, g_t = _find_bracket(gamma_deg, g_angles)

    c00 = candela[c_lo][g_lo]
    c01 = candela[c_lo][g_hi]
    c10 = candela[c_hi][g_lo]
    c11 = candela[c_hi][g_hi]
    c0 = c00 * (1 - g_t) + c01 * g_t
    c1 = c10 * (1 - g_t) + c11 * g_t
    return float(c0 * (1 - c_t) + c1 * c_t)


def sample_intensity_cd(
    phot: Photometry,
    direction_luminaire_frame: Vector3,
    tilt_deg: float | None = None,
) -> float:
    c_deg, gamma_deg = direction_to_photometric_angles(
        direction_luminaire_frame,
        phot.system,
        phot.gamma_angles_deg,
    )
    c_deg = _apply_symmetry(c_deg, phot)

    c_angles = phot.c_angles_deg
    g_angles = phot.gamma_angles_deg
    value = _sample_from_angles_and_table(
        c_deg=c_deg,
        gamma_deg=gamma_deg,
        c_angles=c_angles,
        g_angles=g_angles,
        candela=phot.candela,
    )
    # TILT factor policy: apply interpolation against gamma (vertical) angle.
    if phot.tilt is not None and (phot.tilt_source in {"INCLUDE", "FILE"} or phot.tilt.type in {"INCLUDE", "FILE"}):
        value *= _tilt_factor_for_gamma(phot.tilt, gamma_deg)
    return value


def sample_intensity_cd_world(
    phot: Photometry,
    transform: Transform,
    direction_world: Vector3,
    tilt_deg: float | None = None,
) -> float:
    """
    Authoritative world-space sampling API.
    Pipeline: world direction -> luminaire local frame -> photometric angles -> symmetry/wrap/interpolation.

    Convention reference: docs/spec/coordinate_conventions.md
    """
    c_deg, gamma_deg = world_dir_to_photometric_angles(
        direction_world,
        transform,
        {"luminaire_up_axis": "+Z", "photometric_forward_axis": "+X"},
        phot.system,
        phot.gamma_angles_deg,
    )
    c_deg = _apply_symmetry(c_deg, phot)
    value = _sample_from_angles_and_table(
        c_deg=c_deg,
        gamma_deg=gamma_deg,
        c_angles=phot.c_angles_deg,
        g_angles=phot.gamma_angles_deg,
        candela=phot.candela,
    )
    if phot.tilt is not None and (phot.tilt_source in {"INCLUDE", "FILE"} or phot.tilt.type in {"INCLUDE", "FILE"}):
        value *= _tilt_factor_for_gamma(phot.tilt, gamma_deg)
    return value
