from __future__ import annotations

import math

from luxera.geometry.core import Material, Polygon, Surface, Vector3
from luxera.engine.radiosity.solver import RadiosityConfig, solve_radiosity


def _single_patch(reflectance: float) -> list[Surface]:
    return [
        Surface(
            id="s1",
            polygon=Polygon(
                [
                    Vector3(0.0, 0.0, 0.0),
                    Vector3(1.0, 0.0, 0.0),
                    Vector3(1.0, 1.0, 0.0),
                    Vector3(0.0, 1.0, 0.0),
                ]
            ),
            material=Material(name="m", reflectance=reflectance),
        )
    ]


def test_radiosity_zero_reflectance_has_no_secondary_light() -> None:
    surfaces = _single_patch(reflectance=0.0)
    r = solve_radiosity(
        surfaces,
        {"s1": 100.0},
        config=RadiosityConfig(max_iters=20, tol=1e-8, damping=1.0, use_visibility=False, form_factor_method="analytic"),
    )
    assert r.energy.total_emitted == 0.0
    assert r.energy.total_reflected == 0.0
    assert r.energy.total_exitance == 0.0


def test_radiosity_reflectance_one_with_damping_stays_finite() -> None:
    surfaces = _single_patch(reflectance=1.0)
    r = solve_radiosity(
        surfaces,
        {"s1": 100.0},
        config=RadiosityConfig(max_iters=30, tol=1e-9, damping=0.5, use_visibility=False, form_factor_method="analytic"),
    )
    assert math.isfinite(r.energy.total_exitance)
    assert math.isfinite(r.status.residual)
    assert r.status.iterations <= 30

