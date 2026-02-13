from __future__ import annotations

from luxera.geometry.spatial import (
    PickResult,
    SnapOptions,
    clip_points_to_polygon,
    constrain_fixed_length,
    constrain_orthogonal,
    constrain_parallel_perpendicular,
    pick_nearest,
    point_in_polygon,
    polygon_intersection,
    polygon_union,
    snap_polyline_to_segments,
    snap_point,
)


def test_point_clip_union_intersection() -> None:
    poly = [(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0)]
    assert point_in_polygon((1.0, 1.0), poly)
    clipped = clip_points_to_polygon([(1.0, 1.0), (5.0, 5.0)], poly)
    assert clipped == [(1.0, 1.0)]
    u = polygon_union([poly, [(2.0, 2.0), (4.0, 2.0), (4.0, 4.0), (2.0, 4.0)]])
    assert len(u) >= 4
    inter = polygon_intersection(poly, [(2.0, 2.0), (4.0, 2.0), (4.0, 4.0), (2.0, 4.0)])
    assert inter


def test_snap_constraints_and_pick() -> None:
    p = snap_point(
        (0.9, 0.1),
        endpoints=[(1.0, 0.0)],
        options=SnapOptions(grid=0.5, angle_deg=0.0),
        radius=0.3,
    )
    assert p == (1.0, 0.0)
    ortho = constrain_orthogonal((0.0, 0.0), (1.0, 0.2))
    assert ortho == (1.0, 0.0)
    fixed = constrain_fixed_length((0.0, 0.0), (2.0, 0.0), 1.0)
    assert fixed == (1.0, 0.0)
    par = constrain_parallel_perpendicular((0.0, 0.0), (1.0, 0.0), (0.0, 0.0), (0.3, 0.7), "parallel")
    assert abs(par[1]) < 1e-9
    per = constrain_parallel_perpendicular((0.0, 0.0), (1.0, 0.0), (0.0, 0.0), (0.3, 0.7), "perpendicular")
    assert abs(per[0]) < 1e-9

    pick = pick_nearest(
        (0.0, 0.0, 0.0),
        vertices=[("v1", (0.1, 0.0, 0.0))],
        radius=0.5,
    )
    assert isinstance(pick, PickResult)
    assert pick.kind == "vertex"
    assert pick.id == "v1"

    tn = snap_point(
        (2.0, 0.9),
        circles=[((1.0, 1.0), 1.0)],
        tangent_from=(3.0, 1.0),
        normal_from=(1.0, 3.0),
        options=SnapOptions(enabled=("tangent", "normal")),
        radius=5.0,
    )
    assert isinstance(tn[0], float)
    snapped_path = snap_polyline_to_segments([(0.2, 0.1), (1.7, 0.2)], [((0.0, 0.0), (2.0, 0.0))], radius=0.5)
    assert abs(snapped_path[0][1]) < 1e-6
