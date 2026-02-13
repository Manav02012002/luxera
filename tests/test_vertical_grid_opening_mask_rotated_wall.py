from __future__ import annotations

from luxera.calcs.geometry_ops import build_vertical_grid_on_wall
from luxera.project.schema import OpeningSpec, SurfaceSpec


def test_vertical_grid_opening_mask_on_rotated_wall() -> None:
    wall = SurfaceSpec(
        id="wall_diag",
        name="Diag Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (3.0, 2.0, 0.0), (3.0, 2.0, 3.0), (0.0, 0.0, 3.0)],
    )
    opening = OpeningSpec(
        id="op1",
        name="Window",
        opening_type="window",
        kind="window",
        host_surface_id="wall_diag",
        vertices=[(1.0, 0.6666666667, 1.0), (1.8, 1.2, 1.0), (1.8, 1.2, 2.0), (1.0, 0.6666666667, 2.0)],
    )

    g = build_vertical_grid_on_wall(wall, rows=9, cols=9, openings=[opening])
    assert any(m is False for m in g.mask)
    assert any(m is True for m in g.mask)
