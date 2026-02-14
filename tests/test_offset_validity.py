from __future__ import annotations

import pytest

from luxera.geometry.curves.kernel import Arc2D
from luxera.geometry.curves.offset import offset_arc2d, offset_polygon_v2
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


def test_offset_join_styles_and_arc_radius_offset() -> None:
    poly = Polygon2D(points=[(0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)])
    for js in ("miter", "round", "bevel"):
        res = offset_polygon_v2(poly, 0.2, join_style=js)
        if not res.ok and res.failure is not None and res.failure.code == "backend_unavailable":
            pytest.skip("robust offset backend unavailable")
        assert res.ok
    arc = Arc2D(center=(0.0, 0.0), radius=2.0, start_deg=0.0, end_deg=90.0, ccw=True)
    out = offset_arc2d(arc, 0.5)
    assert isinstance(out, Arc2D)
    assert out.radius == 2.5
