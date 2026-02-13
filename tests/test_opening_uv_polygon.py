from __future__ import annotations

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
