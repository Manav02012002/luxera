import numpy as np
import pytest

from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry, TiltData
from luxera.photometry.sample import sample_intensity_cd


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
    phot = make_photometry()
    tilt = TiltData(type="INCLUDE", angles_deg=np.array([0.0, 30.0]), factors=np.array([1.0, 0.5]))
    phot = Photometry(
        system=phot.system,
        c_angles_deg=phot.c_angles_deg,
        gamma_angles_deg=phot.gamma_angles_deg,
        candela=phot.candela,
        luminous_flux_lm=None,
        symmetry=phot.symmetry,
        tilt=tilt,
    )

    # gamma=0, c=0 base is 0; set a non-zero direction for meaningful scaling
    base = sample_intensity_cd(phot, Vector3(1, 0, -1).normalize(), tilt_deg=0.0)
    scaled = sample_intensity_cd(phot, Vector3(1, 0, -1).normalize(), tilt_deg=30.0)
    assert scaled == pytest.approx(base * 0.5, rel=1e-6)
