from __future__ import annotations

import numpy as np

from luxera.engine.radiosity.form_factors import FormFactorConfig, build_form_factor_matrix
from luxera.engine.radiosity.solver import RadiosityConfig, solve_radiosity
from luxera.engine.radiosity.spectral import (
    CCTConverter,
    SPECTRAL_MATERIAL_LIBRARY,
    SpectralMaterial,
    SpectralRadiositySolver,
    estimate_cct_from_xy,
)
from luxera.geometry.core import Material, Polygon, Surface, Vector3


def _surface(surface_id: str, verts: list[tuple[float, float, float]], reflectance: float, color: tuple[float, float, float]) -> Surface:
    return Surface(
        id=surface_id,
        polygon=Polygon([Vector3(*v) for v in verts]),
        material=Material(name=f"mat_{surface_id}", reflectance=reflectance, color=color),
    )


def _box_surfaces() -> list[Surface]:
    s = 2.0
    return [
        _surface("floor", [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0)], 0.2, (0.2, 0.2, 0.2)),
        _surface("ceiling", [(0, 0, s), (0, s, s), (s, s, s), (s, 0, s)], 0.7, (0.7, 0.7, 0.7)),
        _surface("x0", [(0, 0, 0), (0, s, 0), (0, s, s), (0, 0, s)], 0.5, (0.5, 0.5, 0.5)),
        _surface("x1", [(s, 0, 0), (s, 0, s), (s, s, s), (s, s, 0)], 0.5, (0.5, 0.5, 0.5)),
        _surface("y0", [(0, 0, 0), (0, 0, s), (s, 0, s), (s, 0, 0)], 0.5, (0.5, 0.5, 0.5)),
        _surface("y1", [(0, s, 0), (s, s, 0), (s, s, s), (0, s, s)], 0.5, (0.5, 0.5, 0.5)),
    ]


def test_cct_to_rgb_3000K():
    r, g, b = CCTConverter.cct_to_rgb(3000.0)
    assert r > g > b
    assert r > 0 and g > 0 and b > 0


def test_cct_to_rgb_6500K():
    r, g, b = CCTConverter.cct_to_rgb(6500.0)
    arr = np.array([r, g, b], dtype=float)
    rel = np.abs(arr - np.mean(arr)) / np.mean(arr)
    assert np.all(rel < 0.15)


def test_cct_to_xy_d65():
    x, y = CCTConverter.cct_to_xy(6504.0)
    assert abs(x - 0.3127) < 0.02
    assert abs(y - 0.3290) < 0.02


def test_neutral_room_matches_scalar():
    surfaces = _box_surfaces()
    direct_scalar = {s.id: 300.0 for s in surfaces}
    r_scalar = solve_radiosity(
        surfaces,
        direct_scalar,
        config=RadiosityConfig(
            use_visibility=False,
            form_factor_method="analytic",
            max_iters=60,
            tol=1e-6,
            damping=1.0,
            spectral=False,
        ),
    )
    r_spectral = solve_radiosity(
        surfaces,
        direct_scalar,
        config=RadiosityConfig(
            use_visibility=False,
            form_factor_method="analytic",
            max_iters=60,
            tol=1e-6,
            damping=1.0,
            spectral=True,
        ),
    )
    mean_scalar = float(np.mean(r_scalar.irradiance))
    mean_spectral = float(np.mean(r_spectral.irradiance))
    assert mean_scalar > 1e-9
    assert abs(mean_scalar - mean_spectral) / mean_scalar < 0.02


def test_coloured_wall_shifts_chromaticity():
    surfaces = _box_surfaces()
    red = SpectralMaterial.from_scalar("redish", 0.5, tint="red_brick")
    surfaces[2].material.color = red.reflectance_rgb
    surfaces[2].material.reflectance = float(np.mean(red.reflectance_rgb))

    patches = surfaces
    F = build_form_factor_matrix(
        patches,
        surfaces,
        config=FormFactorConfig(method="analytic", use_visibility=False),
        rng=np.random.default_rng(1),
    )
    reflectance_rgb = np.array([np.array(s.material.color, dtype=float) for s in patches], dtype=float)
    direct_rgb = {s.id: tuple(300.0 * np.array(CCTConverter.cct_to_rgb(4000.0), dtype=float)) for s in surfaces}
    out = SpectralRadiositySolver().solve(
        patches=patches,
        form_factors=F,
        direct_illuminance_rgb=direct_rgb,
        reflectance_rgb=reflectance_rgb,
        max_iters=80,
        tol=1e-6,
    )
    assert np.max(out.chromaticity_xy[:, 0]) > 0.4


def test_mccamy_d65():
    xy = np.array([[0.3127, 0.3290]], dtype=float)
    cct = estimate_cct_from_xy(xy)[0]
    assert 6400.0 <= float(cct) <= 6600.0


def test_material_library_has_25_entries():
    assert len(SPECTRAL_MATERIAL_LIBRARY) >= 25


def test_spectral_convergence():
    surfaces = _box_surfaces()
    r = solve_radiosity(
        surfaces,
        {s.id: 250.0 for s in surfaces},
        config=RadiosityConfig(
            use_visibility=False,
            form_factor_method="analytic",
            max_iters=80,
            tol=1e-5,
            damping=1.0,
            spectral=True,
        ),
    )
    assert bool(r.status.converged)
    assert float(r.status.residual) <= 1e-3


def test_spectral_energy_conservation():
    surfaces = _box_surfaces()
    patches = surfaces
    F = build_form_factor_matrix(
        patches,
        surfaces,
        config=FormFactorConfig(method="analytic", use_visibility=False),
        rng=np.random.default_rng(7),
    )
    reflectance_rgb = np.array([np.array(s.material.color, dtype=float) for s in patches], dtype=float)
    scale = np.array(CCTConverter.cct_to_photopic_rgb_scale(4000.0), dtype=float)
    direct_rgb = {s.id: tuple(200.0 * scale) for s in surfaces}
    out = SpectralRadiositySolver().solve(
        patches=patches,
        form_factors=F,
        direct_illuminance_rgb=direct_rgb,
        reflectance_rgb=reflectance_rgb,
        max_iters=100,
        tol=1e-6,
        damping=1.0,
    )
    areas = np.array([p.area for p in patches], dtype=float)
    refl = reflectance_rgb
    emission = np.array([refl[i] * np.array(direct_rgb[p.id], dtype=float) for i, p in enumerate(patches)], dtype=float)
    residual = out.radiosity_rgb - (emission + refl * out.irradiance_rgb)
    den = max(float(np.sum(emission * areas[:, None])), 1e-9)
    err = float(np.sum(np.abs(residual) * areas[:, None]) / den)
    assert err < 0.10
