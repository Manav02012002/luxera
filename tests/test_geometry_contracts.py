from __future__ import annotations

import pytest

from luxera.geometry.contracts import assert_orthonormal_basis, assert_surface, assert_valid_polygon
from luxera.geometry.primitives import Polygon2D
from luxera.project.schema import SurfaceSpec


def test_assert_valid_polygon_rejects_self_intersection() -> None:
    with pytest.raises(ValueError, match="Invalid polygon"):
        assert_valid_polygon(Polygon2D(points=[(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0)]))


def test_assert_orthonormal_basis_rejects_non_orthonormal_vectors() -> None:
    with pytest.raises(ValueError, match="orthogonal"):
        assert_orthonormal_basis((1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def test_assert_surface_rejects_non_planar_surface() -> None:
    s = SurfaceSpec(
        id="s1",
        name="Bad",
        kind="wall",
        vertices=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.01),
            (0.0, 1.0, 0.0),
        ],
    )
    with pytest.raises(ValueError, match="non-planar"):
        assert_surface(s)

