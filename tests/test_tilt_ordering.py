from __future__ import annotations

import math

import numpy as np
import pytest

from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance
from luxera.core.transform import from_euler_zyx
from luxera.geometry.core import Transform, Vector3
from luxera.photometry.model import Photometry, TiltData
from luxera.photometry.sample import sample_intensity_cd_world


def _dir_from_gamma(gamma_deg: float) -> Vector3:
    g = math.radians(float(gamma_deg))
    return Vector3(math.sin(g), 0.0, -math.cos(g)).normalize()


def _make_constant_typec(*, with_tilt: bool) -> Photometry:
    c = np.array([0.0, 90.0, 180.0, 270.0], dtype=float)
    g = np.array([0.0, 30.0, 60.0, 90.0], dtype=float)
    candela = np.full((c.size, g.size), 100.0, dtype=float)
    tilt = None
    tilt_source = "NONE"
    if with_tilt:
        tilt = TiltData(type="INCLUDE", angles_deg=np.array([0.0, 30.0, 60.0]), factors=np.array([1.0, 0.5, 0.2]))
        tilt_source = "INCLUDE"
    return Photometry(
        system="C",
        c_angles_deg=c,
        gamma_angles_deg=g,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=tilt,
        tilt_source=tilt_source,  # type: ignore[arg-type]
    )


def test_tilt_changes_pattern_with_expected_gamma_deltas() -> None:
    base = _make_constant_typec(with_tilt=False)
    tilted = _make_constant_typec(with_tilt=True)
    tf = from_euler_zyx(Vector3(0.0, 0.0, 0.0), yaw_deg=37.0, pitch_deg=0.0, roll_deg=0.0)

    d0_world = tf.transform_direction(_dir_from_gamma(0.0))
    d60_world = tf.transform_direction(_dir_from_gamma(60.0))

    b0 = sample_intensity_cd_world(base, tf, d0_world)
    b60 = sample_intensity_cd_world(base, tf, d60_world)
    t0 = sample_intensity_cd_world(tilted, tf, d0_world, tilt_deg=0.0)
    t60 = sample_intensity_cd_world(tilted, tf, d60_world, tilt_deg=0.0)

    assert b0 == pytest.approx(100.0, rel=1e-10, abs=1e-10)
    assert b60 == pytest.approx(100.0, rel=1e-10, abs=1e-10)
    assert t0 / b0 == pytest.approx(1.0, rel=1e-10, abs=1e-10)
    assert t60 / b60 == pytest.approx(0.2, rel=1e-8, abs=1e-8)


def test_tilt_result_invariant_under_global_translation_and_rotation() -> None:
    phot = _make_constant_typec(with_tilt=True)
    base_tf = from_euler_zyx(Vector3(0.25, -0.4, 3.0), yaw_deg=20.0, pitch_deg=-12.0, roll_deg=5.0)
    base_lum = Luminaire(photometry=phot, transform=base_tf, flux_multiplier=1.0, tilt_deg=15.0)
    base_point = Vector3(1.8, 0.35, 0.0)
    base_normal = Vector3(0.0, 0.0, 1.0)
    e0 = calculate_direct_illuminance(base_point, base_normal, base_lum)

    global_rot = from_euler_zyx(Vector3(0.0, 0.0, 0.0), yaw_deg=90.0, pitch_deg=0.0, roll_deg=0.0)
    global_offset = Vector3(4.0, -2.5, 1.2)
    r_scene = global_rot.get_rotation_matrix()

    rotated_point = Vector3.from_array(r_scene @ base_point.to_array()) + global_offset
    rotated_normal = Vector3.from_array(r_scene @ base_normal.to_array()).normalize()
    rotated_pos = Vector3.from_array(r_scene @ base_tf.position.to_array()) + global_offset
    rotated_rot = r_scene @ base_tf.get_rotation_matrix()
    rotated_tf = Transform.from_rotation_matrix(position=rotated_pos, rotation_matrix=rotated_rot)
    rotated_lum = Luminaire(photometry=phot, transform=rotated_tf, flux_multiplier=1.0, tilt_deg=15.0)

    e1 = calculate_direct_illuminance(rotated_point, rotated_normal, rotated_lum)
    assert e1 == pytest.approx(e0, rel=1e-10, abs=1e-10)
