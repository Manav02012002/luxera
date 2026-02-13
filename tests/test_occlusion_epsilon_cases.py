from __future__ import annotations

import math

import numpy as np

from luxera.calculation.illuminance import DirectCalcSettings, Luminaire, _is_occluded, calculate_direct_illuminance
from luxera.core.transform import from_euler_zyx
from luxera.geometry.bvh import Triangle
from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry


def _constant_photometry(cd: float = 1000.0) -> Photometry:
    return Photometry(
        system="C",
        c_angles_deg=np.array([0.0, 180.0], dtype=float),
        gamma_angles_deg=np.array([0.0, 90.0], dtype=float),
        candela=np.array([[cd, cd], [cd, cd]], dtype=float),
        luminous_flux_lm=1000.0,
        symmetry="NONE",
        tilt=None,
    )


def test_point_on_surface_no_self_hit() -> None:
    tri = Triangle(
        a=Vector3(0.5, -1.0, 0.0),
        b=Vector3(0.5, 1.0, 0.0),
        c=Vector3(0.5, 0.0, 2.0),
        payload="blk",
    )
    lum = Vector3(0.0, 0.0, 1.0)
    point_on_surface = Vector3(0.5, 0.0, 1.0)
    assert _is_occluded(point_on_surface, lum, [tri], eps=1e-6) is False


def test_luminaire_near_surface_is_finite_and_stable() -> None:
    luminaire = Luminaire(
        photometry=_constant_photometry(),
        transform=from_euler_zyx(Vector3(0.0, 0.0, 1e-4), 0.0, 0.0, 0.0),
    )
    point = Vector3(0.0, 0.0, 0.0)
    n = Vector3(0.0, 0.0, 1.0)
    values = [
        calculate_direct_illuminance(
            point,
            n,
            luminaire,
            occluders=[],
            settings=DirectCalcSettings(use_occlusion=True, occlusion_epsilon=1e-6),
        )
        for _ in range(8)
    ]
    assert all(math.isfinite(v) and v >= 0.0 for v in values)
    assert max(values) - min(values) <= 1e-12


def test_grazing_ray_decision_stable_under_tiny_perturbation() -> None:
    tri = Triangle(
        a=Vector3(0.5, -1.0, 0.0),
        b=Vector3(0.5, 1.0, 0.0),
        c=Vector3(0.5, 0.0, 2.0),
        payload="blk",
    )
    lum = Vector3(0.0, 0.0, 1.0)
    decisions = []
    for dz in (0.0, 1e-9, -1e-9, 2e-9, -2e-9):
        point = Vector3(1.0, 0.0, 1.0 + dz)
        decisions.append(_is_occluded(point, lum, [tri], eps=1e-6))
    assert all(decisions)
