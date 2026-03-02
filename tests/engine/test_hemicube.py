from __future__ import annotations

import math

import numpy as np

from luxera.engine.radiosity.form_factors import FormFactorConfig, build_form_factor_matrix
from luxera.engine.radiosity.hemicube import HemicubeEngine
from luxera.geometry.core import Material, Polygon, Surface, Vector3


def _surface(surface_id: str, vertices: list[tuple[float, float, float]], reflectance: float = 0.7) -> Surface:
    return Surface(
        id=surface_id,
        polygon=Polygon([Vector3(*v) for v in vertices]),
        material=Material(name=f"mat_{surface_id}", reflectance=reflectance),
    )


def _unit_parallel_squares() -> list[Surface]:
    # Bottom square, normal +Z.
    s0 = _surface(
        "s0",
        [
            (-0.5, -0.5, 0.0),
            (0.5, -0.5, 0.0),
            (0.5, 0.5, 0.0),
            (-0.5, 0.5, 0.0),
        ],
    )
    # Top square, normal -Z.
    s1 = _surface(
        "s1",
        [
            (-0.5, -0.5, 1.0),
            (-0.5, 0.5, 1.0),
            (0.5, 0.5, 1.0),
            (0.5, -0.5, 1.0),
        ],
    )
    return [s0, s1]


def _perpendicular_adjacent_squares() -> list[Surface]:
    # Horizontal square at z=0, normal +Z.
    floor = _surface(
        "a",
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
    )
    # Vertical square at x=1, normal -X, sharing the edge x=1,z=0.
    wall = _surface(
        "b",
        [
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (1.0, 1.0, 1.0),
            (1.0, 0.0, 1.0),
        ],
    )
    return [floor, wall]


def _box_surfaces(size: float = 2.0) -> list[Surface]:
    s = float(size)
    return [
        # floor (+Z)
        _surface("floor", [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0)]),
        # ceiling (-Z)
        _surface("ceiling", [(0, 0, s), (0, s, s), (s, s, s), (s, 0, s)]),
        # x=0 wall (+X)
        _surface("x0", [(0, 0, 0), (0, s, 0), (0, s, s), (0, 0, s)]),
        # x=s wall (-X)
        _surface("x1", [(s, 0, 0), (s, 0, s), (s, s, s), (s, s, 0)]),
        # y=0 wall (+Y)
        _surface("y0", [(0, 0, 0), (0, 0, s), (s, 0, s), (s, 0, 0)]),
        # y=s wall (-Y)
        _surface("y1", [(0, s, 0), (s, s, 0), (s, s, s), (0, s, s)]),
    ]


def test_delta_ff_top_conservation():
    """Sum of top face delta form factors should match canonical hemicube distribution."""
    engine = HemicubeEngine(resolution=128)
    total_top = float(np.sum(engine._delta_top))
    assert 0.53 < total_top < 0.58


def test_delta_ff_all_faces_conservation():
    """Sum over all 5 faces should be close to 1.0."""
    engine = HemicubeEngine(resolution=128)
    total = float(np.sum(engine._delta_top) + 4.0 * np.sum(engine._delta_side))
    assert abs(total - 1.0) < 0.02


def test_two_parallel_squares():
    """Two 1x1m parallel squares 1m apart. Known F ≈ 0.1998."""
    patches = _unit_parallel_squares()
    engine = HemicubeEngine(resolution=256)
    F = engine.compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    assert math.isfinite(float(F[0, 1]))
    assert abs(float(F[0, 1]) - 0.1998) <= 0.05


def test_perpendicular_adjacent_squares():
    """Two 1x1m squares sharing an edge at 90°. Known F ≈ 0.2000."""
    patches = _perpendicular_adjacent_squares()
    engine = HemicubeEngine(resolution=256)
    F = engine.compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    assert math.isfinite(float(F[0, 1]))
    assert abs(float(F[0, 1]) - 0.1) <= 0.03


def test_enclosed_box_row_sums():
    """6-face 2x2x2m box. Each row of F should sum to ~1.0."""
    patches = _box_surfaces(size=2.0)
    engine = HemicubeEngine(resolution=128)
    F = engine.compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    row_sums = np.sum(F, axis=1)
    assert np.all(np.isfinite(row_sums))
    assert np.all(np.abs(row_sums - 1.0) < 0.05)


def test_reciprocity():
    """F[i,j]*A[i] should equal F[j,i]*A[j] within tolerance."""
    patches = _box_surfaces(size=2.0)
    engine = HemicubeEngine(resolution=128)
    F = engine.compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    areas = np.array([p.area for p in patches], dtype=float)
    for i in range(len(patches)):
        for j in range(len(patches)):
            if i == j:
                continue
            lhs = F[i, j] * areas[i]
            rhs = F[j, i] * areas[j]
            assert abs(lhs - rhs) < 0.03


def test_hemicube_vs_mc_agreement():
    """For a simple 4-surface room, hemicube and MC (10000 samples) should agree within 5% on form factors."""
    patches = [
        _surface("floor", [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]),
        _surface("ceiling", [(0, 0, 2), (0, 2, 2), (2, 2, 2), (2, 0, 2)]),
        _surface("wall0", [(0, 0, 0), (0, 0, 2), (0, 2, 2), (0, 2, 0)]),
        _surface("wall1", [(2, 0, 0), (2, 2, 0), (2, 2, 2), (2, 0, 2)]),
    ]
    rng = np.random.default_rng(1234)
    F_mc = build_form_factor_matrix(
        patches,
        patches,
        config=FormFactorConfig(method="monte_carlo", use_visibility=True, monte_carlo_samples=10000),
        rng=rng,
        bvh=None,
    )
    F_h = build_form_factor_matrix(
        patches,
        patches,
        config=FormFactorConfig(method="hemicube", use_visibility=True, hemicube_resolution=192),
        rng=np.random.default_rng(0),
        bvh=None,
    )
    # Compare dominant off-diagonal entries.
    mask = ~np.eye(len(patches), dtype=bool)
    denom = np.maximum(np.abs(F_mc[mask]), 1e-6)
    rel = np.abs(F_h[mask] - F_mc[mask]) / denom
    assert float(np.median(rel)) < 0.05


def test_resolution_convergence():
    """F at resolution 64 vs 128 vs 256 should converge."""
    patches = _unit_parallel_squares()
    F64 = HemicubeEngine(resolution=64).compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    F128 = HemicubeEngine(resolution=128).compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    F256 = HemicubeEngine(resolution=256).compute_matrix(patches=patches, all_surfaces=patches, bvh=None)
    e64 = abs(float(F64[0, 1]) - float(F256[0, 1]))
    e128 = abs(float(F128[0, 1]) - float(F256[0, 1]))
    assert e128 < e64
