from __future__ import annotations

from luxera.calcs.geometry_ops import (
    Viewpoint,
    build_point_set,
    build_vertical_grid_on_wall,
    build_workplane_grid,
    luminaire_points_in_view,
    sample_line_grid,
)
from luxera.project.schema import OpeningSpec, SurfaceSpec


def test_build_workplane_grid_with_polygon_mask_and_hole() -> None:
    g = build_workplane_grid(
        origin=(0.0, 0.0, 0.8),
        axis_u=(1.0, 0.0, 0.0),
        axis_v=(0.0, 1.0, 0.0),
        width=4.0,
        height=4.0,
        rows=5,
        cols=5,
        clip_polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        holes=[[(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5)]],
    )
    assert len(g.points_xyz) == 25
    assert any(m is False for m in g.mask)
    assert g.connectivity


def test_vertical_grid_masks_opening_void() -> None:
    wall = SurfaceSpec(
        id="wall1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
    )
    opening = OpeningSpec(
        id="op1",
        name="Window",
        opening_type="window",
        kind="window",
        host_surface_id="wall1",
        vertices=[(1.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.0), (1.0, 0.0, 2.0)],
    )
    g = build_vertical_grid_on_wall(wall, rows=7, cols=7, openings=[opening])
    assert any(m is False for m in g.mask)


def test_point_line_and_view_geometry_helpers() -> None:
    pts = build_point_set([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
    assert len(pts) == 2
    line = sample_line_grid([(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)], spacing=0.5)
    assert len(line) >= 4
    v = Viewpoint(position=(0.0, 0.0, 1.2), look_dir=(1.0, 0.0, 0.0), up_dir=(0.0, 0.0, 1.0), fov_deg=90.0)
    vis = luminaire_points_in_view(v, [(2.0, 0.0, 1.2), (-2.0, 0.0, 1.2)])
    assert (2.0, 0.0, 1.2) in vis
    assert (-2.0, 0.0, 1.2) not in vis

