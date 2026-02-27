import numpy as np
import pytest

from luxera.geometry.core import Vector3
from luxera.core.transform import from_euler_zyx
from luxera.photometry.model import Photometry, TiltData
from luxera.photometry.sample import sample_intensity_cd, sample_intensity_cd_world


def make_photometry(symmetry="NONE"):
    c_angles = np.array([0.0, 90.0, 180.0, 270.0])
    g_angles = np.array([0.0, 90.0])
    candela = np.zeros((len(c_angles), len(g_angles)))
    for i, c in enumerate(c_angles):
        for j, g in enumerate(g_angles):
            candela[i][j] = c + g
    return Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry=symmetry,
        tilt=None,
    )


def test_sample_exact_angles():
    phot = make_photometry()

    # gamma=0, c=0 -> candela = 0
    val = sample_intensity_cd(phot, Vector3(0, 0, -1))
    assert abs(val - 0.0) < 1e-9

    # gamma=90, c=90 -> candela = 180
    val = sample_intensity_cd(phot, Vector3(0, 1, 0))
    assert abs(val - 180.0) < 1e-9


def test_sample_symmetry_quadrant():
    phot = make_photometry(symmetry="QUADRANT")

    # c=270 should map to 90 under quadrant symmetry
    val = sample_intensity_cd(phot, Vector3(0, -1, 0))
    assert abs(val - 180.0) < 1e-9


def test_tilt_include_multiplier():
    base_phot = make_photometry()
    tilt = TiltData(type="INCLUDE", angles_deg=np.array([0.0, 30.0]), factors=np.array([1.0, 0.5]))
    phot = Photometry(
        system=base_phot.system,
        c_angles_deg=base_phot.c_angles_deg,
        gamma_angles_deg=base_phot.gamma_angles_deg,
        candela=base_phot.candela,
        luminous_flux_lm=None,
        symmetry=base_phot.symmetry,
        tilt=tilt,
    )

    # Tilt policy is gamma-based; compare same direction with/without tilt.
    d30 = Vector3(0.5, 0, -np.sqrt(3.0) / 2.0).normalize()
    raw = sample_intensity_cd(base_phot, d30)
    tilted = sample_intensity_cd(phot, d30)
    assert tilted == pytest.approx(raw * 0.5, rel=1e-6)


def test_sample_bilinear_interpolation_midpoint():
    c_angles = np.array([0.0, 90.0])
    g_angles = np.array([0.0, 90.0])
    candela = np.array([[0.0, 100.0], [200.0, 300.0]])
    phot = Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )

    # c=45, gamma=45
    direction = Vector3(0.5, 0.5, -np.sqrt(0.5)).normalize()
    val = sample_intensity_cd(phot, direction)
    assert val == pytest.approx(150.0, rel=1e-6)


def test_sample_world_rotation_invariance():
    c_angles = np.array([0.0, 90.0])
    g_angles = np.array([90.0])
    candela = np.array([[100.0], [500.0]])
    phot = Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )

    # Yaw +90 means world +Y maps to local +X
    t = from_euler_zyx(Vector3(0, 0, 0), yaw_deg=90, pitch_deg=0, roll_deg=0)
    world_val = sample_intensity_cd_world(phot, t, Vector3(0, 1, 0))
    local_val = sample_intensity_cd(phot, Vector3(1, 0, 0))
    assert world_val == pytest.approx(local_val, rel=1e-6)


def test_sample_type_c_seam_interpolates_cyclically() -> None:
    # Horizontal planes do not include 360 explicitly; seam should interpolate
    # between C=270 and wrapped C=0 instead of clamping to C=270.
    c_angles = np.array([0.0, 90.0, 180.0, 270.0], dtype=float)
    g_angles = np.array([90.0], dtype=float)
    # Encode strong seam contrast to expose interpolation behavior.
    candela = np.array([[1000.0], [200.0], [200.0], [0.0]], dtype=float)
    phot = Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )
    # Direction at C=315, gamma=90.
    d = Vector3(np.sqrt(0.5), -np.sqrt(0.5), 0.0).normalize()
    got = sample_intensity_cd(phot, d)
    # Midway between C=270(0) and C=360/0(1000) -> 500.
    assert got == pytest.approx(500.0, rel=1e-6, abs=1e-6)
