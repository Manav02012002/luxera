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
    # Local axes: +X length (major), +Y width (minor), +Z up
    # Type A polar axis: +X (major), Type B polar axis: +Y (minor)
    p = Vector3(1, 0, 0) if system == "A" else Vector3(0, 1, 0)
    d = direction.normalize()
    r = Vector3(0, 0, -1)  # photometric zero (down)

    # Horizontal angle: rotation about polar axis from reference plane (p + r)
    r_proj = r - p * p.dot(r)
    if r_proj.length() < 1e-12:
        r_proj = Vector3(0, 0, -1)
    r_proj = r_proj.normalize()
    u = d - p * p.dot(d)
    if u.length() < 1e-12:
        h_deg = 0.0
        v_dir = r_proj
    else:
        v = u.normalize()
        # CCW about +p using right-hand rule, then convert to clockwise per LM-63 for A/B
        ccw = math.degrees(math.atan2(p.dot(r_proj.cross(v)), r_proj.dot(v)))
        h_deg = (-ccw + 360.0) % 360.0
        v_dir = _rotate_about_axis(r_proj, p, math.radians(ccw))

    # Determine vertical-angle convention from data range
    vmin = float(np.min(vertical_angles)) if len(vertical_angles) else 0.0
    vmax = float(np.max(vertical_angles)) if len(vertical_angles) else 0.0
    use_elevation = vmin < 0.0 or vmax <= 90.0

    # Compute vertical angle
    if use_elevation:
        # Elevation from horizontal plane: 0 at horizontal, +90 up, -90 down
        horiz = math.sqrt(d.x * d.x + d.y * d.y)
        v_deg = math.degrees(math.atan2(d.z, horiz))
    else:
        # 0 at down (v_dir), 180 at up (-v_dir) in the plane spanned by p and v_dir
        n = p.cross(v_dir)
        if n.length() < 1e-12:
            n = p.cross(Vector3(0, 0, 1))
        n = n.normalize()
        d_plane = d - n * n.dot(d)
        if d_plane.length() < 1e-12:
            v_deg = 0.0
        else:
            d_plane = d_plane.normalize()
            cos_v = max(-1.0, min(1.0, d_plane.dot(v_dir)))
            v_deg = math.degrees(math.acos(cos_v))

    return h_deg, v_deg


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

    # normalize C angle to match dataset domain
    if len(c_angles) >= 2 and c_angles[0] < 0 < c_angles[-1]:
        if c_deg > 180:
            c_deg -= 360
    c_deg = max(c_angles[0], min(c_angles[-1], c_deg))
    gamma_deg = max(g_angles[0], min(g_angles[-1], gamma_deg))

    c_lo, c_hi, c_t = _find_bracket(c_deg, c_angles)
    g_lo, g_hi, g_t = _find_bracket(gamma_deg, g_angles)

    c00 = phot.candela[c_lo][g_lo]
    c01 = phot.candela[c_lo][g_hi]
    c10 = phot.candela[c_hi][g_lo]
    c11 = phot.candela[c_hi][g_hi]

    c0 = c00 * (1 - g_t) + c01 * g_t
    c1 = c10 * (1 - g_t) + c11 * g_t
    value = c0 * (1 - c_t) + c1 * c_t
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
    c_angles = phot.c_angles_deg
    g_angles = phot.gamma_angles_deg
    if len(c_angles) >= 2 and c_angles[0] < 0 < c_angles[-1]:
        if c_deg > 180:
            c_deg -= 360
    c_deg = max(c_angles[0], min(c_angles[-1], c_deg))
    gamma_deg = max(g_angles[0], min(g_angles[-1], gamma_deg))
    c_lo, c_hi, c_t = _find_bracket(c_deg, c_angles)
    g_lo, g_hi, g_t = _find_bracket(gamma_deg, g_angles)
    c00 = phot.candela[c_lo][g_lo]
    c01 = phot.candela[c_lo][g_hi]
    c10 = phot.candela[c_hi][g_lo]
    c11 = phot.candela[c_hi][g_hi]
    c0 = c00 * (1 - g_t) + c01 * g_t
    c1 = c10 * (1 - g_t) + c11 * g_t
    value = c0 * (1 - c_t) + c1 * c_t
    if phot.tilt is not None and (phot.tilt_source in {"INCLUDE", "FILE"} or phot.tilt.type in {"INCLUDE", "FILE"}):
        value *= _tilt_factor_for_gamma(phot.tilt, gamma_deg)
    return value
