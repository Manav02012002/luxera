from __future__ import annotations

import pytest

from luxera.geometry.openings.opening_uv import opening_uv_polygon
from luxera.geometry.param.model import OpeningParam
from luxera.project.schema import OpeningSpec, SurfaceSpec


def test_opening_uv_polygon_from_param_on_rotated_wall() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (3.0, 2.0, 0.0), (3.0, 2.0, 3.0), (0.0, 0.0, 3.0)],
    )
    op = OpeningParam(id="o1", wall_id="w1", anchor=0.5, width=1.2, height=1.4, sill=0.8)
    uv = opening_uv_polygon(op, wall)
    us = [p[0] for p in uv]
    vs = [p[1] for p in uv]
    assert abs((max(us) - min(us)) - 1.2) < 1e-9
    assert abs((max(vs) - min(vs)) - 1.4) < 1e-9


def test_opening_uv_polygon_from_openingspec() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (3.0, 2.0, 0.0), (3.0, 2.0, 3.0), (0.0, 0.0, 3.0)],
    )
    opening = OpeningSpec(
        id="o1",
        name="W",
        opening_type="window",
        kind="window",
        host_surface_id="w1",
        vertices=[(0.8, 0.5333333333, 1.0), (1.6, 1.0666666667, 1.0), (1.6, 1.0666666667, 2.0), (0.8, 0.5333333333, 2.0)],
    )
    uv = opening_uv_polygon(opening, wall)
    assert len(uv) == 4
    assert max(p[0] for p in uv) > min(p[0] for p in uv)
    assert max(p[1] for p in uv) > min(p[1] for p in uv)


def test_opening_uv_polygon_nearest_gridline_center() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (3.0, 2.0, 0.0), (3.0, 2.0, 3.0), (0.0, 0.0, 3.0)],
    )
    op = OpeningParam(
        id="o1",
        wall_id="w1",
        anchor=0.31,
        width=1.0,
        height=1.2,
        sill=0.8,
        anchor_mode="nearest_gridline_center",
        gridline_spacing=0.5,
    )
    uv = opening_uv_polygon(op, wall)
    uc = 0.5 * (uv[0][0] + uv[1][0])
    assert abs(uc - 1.0) < 1e-9


def test_opening_uv_polygon_equal_spacing_group() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
    )
    group = [
        OpeningParam(id="o1", wall_id="w1", width=0.6, height=1.2, sill=0.8, anchor_mode="equal_spacing", spacing_group_id="g1"),
        OpeningParam(id="o2", wall_id="w1", width=0.6, height=1.2, sill=0.8, anchor_mode="equal_spacing", spacing_group_id="g1"),
        OpeningParam(id="o3", wall_id="w1", width=0.6, height=1.2, sill=0.8, anchor_mode="equal_spacing", spacing_group_id="g1"),
    ]
    centers = []
    for op in group:
        uv = opening_uv_polygon(op, wall, peer_openings=group)
        centers.append(0.5 * (uv[0][0] + uv[1][0]))
    assert abs(centers[0] - 1.0) < 1e-9
    assert abs(centers[1] - 2.0) < 1e-9
    assert abs(centers[2] - 3.0) < 1e-9


def test_opening_uv_polygon_clamps_on_anchor_shift() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
    )
    op = OpeningParam(
        id="o1",
        wall_id="w1",
        anchor_mode="from_start_distance",
        from_start_distance=1.8,
        width=0.8,
        height=1.2,
        sill=0.8,
    )
    uv = opening_uv_polygon(op, wall)
    assert len(uv) == 4
    assert abs(0.5 * (uv[0][0] + uv[1][0]) - 1.6) < 1e-9


def test_opening_uv_polygon_warns_when_impossible() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (0.6, 0.0, 0.0), (0.6, 0.0, 3.0), (0.0, 0.0, 3.0)],
    )
    op = OpeningParam(id="o1", wall_id="w1", width=1.0, height=1.2, sill=0.8)
    with pytest.warns(RuntimeWarning, match="does not fit host wall"):
        with pytest.raises(ValueError, match="does not fit host wall length"):
            opening_uv_polygon(op, wall)
