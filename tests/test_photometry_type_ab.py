import numpy as np
import pytest

from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry
from luxera.photometry.sample import sample_intensity_cd


def make_ab_photometry(system: str):
    c_angles = np.array([-90.0, 0.0, 90.0])
    g_angles = np.array([-90.0, 0.0, 90.0])
    candela = np.zeros((len(c_angles), len(g_angles)))
    for i, c in enumerate(c_angles):
        for j, g in enumerate(g_angles):
            candela[i][j] = c * 100 + g
    return Photometry(
        system=system,
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )


def test_type_a_axes_mapping():
    phot = make_ab_photometry("A")

    # +X (polar axis) should map to H=0, V=0
    val = sample_intensity_cd(phot, Vector3(1, 0, 0))
    assert val == pytest.approx(0.0)

    # -Z (down) should map to H=0, V=-90
    val = sample_intensity_cd(phot, Vector3(0, 0, -1))
    assert val == pytest.approx(-90.0)

    # +Y should map to H=-90, V=0 (clockwise convention)
    val = sample_intensity_cd(phot, Vector3(0, 1, 0))
    assert val == pytest.approx(-9000.0)


def test_type_b_axes_mapping():
    phot = make_ab_photometry("B")

    # +Y (polar axis) should map to H=0, V=0
    val = sample_intensity_cd(phot, Vector3(0, 1, 0))
    assert val == pytest.approx(0.0)

    # -Z (down) should map to H=0, V=-90
    val = sample_intensity_cd(phot, Vector3(0, 0, -1))
    assert val == pytest.approx(-90.0)

    # +X should map to H=90, V=0 (clockwise convention)
    val = sample_intensity_cd(phot, Vector3(1, 0, 0))
    assert val == pytest.approx(9000.0)
