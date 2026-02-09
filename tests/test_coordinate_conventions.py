import numpy as np
import pytest

from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance
from luxera.core.transform import from_euler_zyx
from luxera.geometry.core import Transform, Vector3
from luxera.photometry.model import Photometry


def test_yaw_only_rotates_about_world_z_axis():
    t = from_euler_zyx(Vector3(0, 0, 0), yaw_deg=90, pitch_deg=0, roll_deg=0)
    d = t.transform_direction(Vector3(1, 0, 0))
    assert d.x == pytest.approx(0.0, abs=1e-9)
    assert d.y == pytest.approx(1.0, abs=1e-9)
    assert d.z == pytest.approx(0.0, abs=1e-9)


def test_pitch_only_rotates_about_world_y_axis():
    t = from_euler_zyx(Vector3(0, 0, 0), yaw_deg=0, pitch_deg=90, roll_deg=0)
    d = t.transform_direction(Vector3(1, 0, 0))
    assert d.x == pytest.approx(0.0, abs=1e-9)
    assert d.y == pytest.approx(0.0, abs=1e-9)
    assert d.z == pytest.approx(-1.0, abs=1e-9)


def test_roll_only_rotates_about_world_x_axis():
    t = from_euler_zyx(Vector3(0, 0, 0), yaw_deg=0, pitch_deg=0, roll_deg=90)
    d = t.transform_direction(Vector3(0, 1, 0))
    assert d.x == pytest.approx(0.0, abs=1e-9)
    assert d.y == pytest.approx(0.0, abs=1e-9)
    assert d.z == pytest.approx(1.0, abs=1e-9)


def test_luminaire_yaw_rotates_illuminance_field():
    phot = Photometry(
        system="C",
        c_angles_deg=np.array([0.0, 90.0, 180.0, 270.0], dtype=float),
        gamma_angles_deg=np.array([90.0], dtype=float),
        candela=np.array([[100.0], [400.0], [100.0], [400.0]], dtype=float),
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )

    point_x = Vector3(2.0, 0.0, 0.0)
    point_y = Vector3(0.0, 2.0, 0.0)
    normal = Vector3(0.0, 0.0, 1.0)

    lum_0 = Luminaire(photometry=phot, transform=Transform(position=Vector3(0.0, 0.0, 3.0)))
    e0_x = calculate_direct_illuminance(point_x, normal, lum_0)
    e0_y = calculate_direct_illuminance(point_y, normal, lum_0)
    assert e0_y > e0_x

    lum_90 = Luminaire(
        photometry=phot,
        transform=from_euler_zyx(Vector3(0.0, 0.0, 3.0), yaw_deg=90.0, pitch_deg=0.0, roll_deg=0.0),
    )
    e90_x = calculate_direct_illuminance(point_x, normal, lum_90)
    e90_y = calculate_direct_illuminance(point_y, normal, lum_90)

    assert e90_x > e90_y
    assert e90_x == pytest.approx(e0_y, rel=1e-6)
    assert e90_y == pytest.approx(e0_x, rel=1e-6)
