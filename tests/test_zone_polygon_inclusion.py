from __future__ import annotations

from luxera.derived.zone_metrics import point_in_polygon_inclusive


def test_point_in_polygon_inclusive_accepts_edge_and_vertex() -> None:
    poly = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    assert point_in_polygon_inclusive((2.0, 1.5), poly)
    assert point_in_polygon_inclusive((0.0, 1.5), poly)
    assert point_in_polygon_inclusive((4.0, 3.0), poly)


def test_point_in_polygon_inclusive_rejects_outside_points() -> None:
    poly = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    assert not point_in_polygon_inclusive((-0.01, 1.0), poly)
    assert not point_in_polygon_inclusive((2.0, 3.01), poly)
