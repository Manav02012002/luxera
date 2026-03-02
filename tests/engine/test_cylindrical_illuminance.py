from __future__ import annotations

import math

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.core.transform import from_euler_zyx
from luxera.engine.cylindrical_illuminance import (
    CylindricalIlluminanceEngine,
    compute_cylindrical_illuminance,
    compute_semicylindrical_illuminance,
)
from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry
from luxera.project.schema import CalcGrid, Project


def _isotropic_photometry(flux_lm: float) -> Photometry:
    gamma = np.linspace(0.0, 180.0, 361, dtype=float)
    cd = np.full_like(gamma, float(flux_lm) / (4.0 * np.pi), dtype=float)
    return Photometry(
        system="C",
        c_angles_deg=np.array([0.0], dtype=float),
        gamma_angles_deg=gamma,
        candela=cd.reshape(1, -1),
        luminous_flux_lm=float(flux_lm),
        symmetry="FULL",
    )


def test_single_source_directly_above():
    e = compute_cylindrical_illuminance(
        np.array([0.0, 0.0, 0.0], dtype=float),
        np.array([0.0, 0.0, 3.0], dtype=float),
        intensity_cd=100.0,
    )
    assert e == 0.0


def test_single_source_horizontal():
    d = 3.0
    i = 120.0
    e = compute_cylindrical_illuminance(
        np.array([0.0, 0.0, 1.5], dtype=float),
        np.array([3.0, 0.0, 1.5], dtype=float),
        intensity_cd=i,
    )
    expected = i / (math.pi * d * d)
    assert abs(e - expected) < 1e-9


def test_single_source_at_45deg():
    point = np.array([0.0, 0.0, 1.5], dtype=float)
    source = np.array([2.0, 0.0, 3.5], dtype=float)
    i = 200.0
    e = compute_cylindrical_illuminance(point, source, i)
    vec = source - point
    d = float(np.linalg.norm(vec))
    cos_alpha = float(np.hypot(vec[0], vec[1]) / d)
    expected = i * cos_alpha / (math.pi * d * d)
    assert abs(e - expected) < 1e-9


def test_semicylindrical_facing_source():
    e = compute_semicylindrical_illuminance(
        np.array([0.0, 0.0, 1.5], dtype=float),
        np.array([3.0, 0.0, 1.5], dtype=float),
        intensity_cd=100.0,
        facing_direction=np.array([1.0, 0.0], dtype=float),
    )
    assert e > 0.0


def test_semicylindrical_facing_away():
    e = compute_semicylindrical_illuminance(
        np.array([0.0, 0.0, 1.5], dtype=float),
        np.array([3.0, 0.0, 1.5], dtype=float),
        intensity_cd=100.0,
        facing_direction=np.array([-1.0, 0.0], dtype=float),
    )
    assert e == 0.0


def test_cylindrical_matches_manual_grid():
    phot = _isotropic_photometry(1000.0)
    lum = Luminaire(
        photometry=phot,
        transform=from_euler_zyx(Vector3(2.0, 2.0, 3.0), 0.0, 0.0, 0.0),
        flux_multiplier=1.0,
    )
    grid = CalcGrid(
        id="g1",
        name="Grid",
        origin=(0.0, 0.0, 1.5),
        width=4.0,
        height=4.0,
        elevation=1.5,
        nx=3,
        ny=3,
        illuminance_metric="cylindrical",
    )
    result = CylindricalIlluminanceEngine().compute_grid(
        project=Project(name="demo"),
        grid_spec=grid,
        luminaires=[lum],
        metric="cylindrical",
    )

    intensity = 1000.0 / (4.0 * math.pi)
    manual_points = [
        np.array([0.0, 0.0, 1.5], dtype=float),
        np.array([2.0, 2.0, 1.5], dtype=float),
        np.array([4.0, 4.0, 1.5], dtype=float),
    ]
    expected = [
        compute_cylindrical_illuminance(p, np.array([2.0, 2.0, 3.0], dtype=float), intensity) for p in manual_points
    ]
    # Flattened order is row-major over Y then X: (0,0)->idx0, (2,2)->idx4, (4,4)->idx8.
    assert abs(result.values[0] - expected[0]) < 1e-6
    assert abs(result.values[4] - expected[1]) < 1e-6
    assert abs(result.values[8] - expected[2]) < 1e-6

