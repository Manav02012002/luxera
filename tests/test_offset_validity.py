from __future__ import annotations

import pytest

from luxera.geometry.curves.offset import offset_polygon_v2
from luxera.geometry.primitives import Polygon2D


def test_offset_validity_first_returns_structured_failure_for_invalid_case() -> None:
    concave = Polygon2D(points=[(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)])
    res = offset_polygon_v2(concave, -2.0)
    assert res.ok is False
    assert res.failure is not None


def test_offset_validity_first_returns_valid_polygon_when_possible() -> None:
    poly = Polygon2D(points=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)])
    res = offset_polygon_v2(poly, 0.25)
    if not res.ok and res.failure is not None and res.failure.code == "backend_unavailable":
        pytest.skip("robust offset backend unavailable")
    assert res.ok is True
    assert res.polygon is not None
    assert len(res.polygon.points) >= 3
