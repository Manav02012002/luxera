from __future__ import annotations

from luxera.design.placement import snap_to_ceiling, snap_to_grid_intersections
from luxera.project.schema import CalcGrid, SurfaceSpec


def test_snap_to_ceiling_height_and_orientation() -> None:
    surface = SurfaceSpec(
        id="c1",
        name="Ceiling",
        kind="ceiling",
        vertices=[(0.0, 0.0, 3.0), (4.0, 0.0, 3.0), (4.0, 4.0, 3.0), (0.0, 4.0, 3.0)],
        normal=(0.0, 0.0, -1.0),
    )
    tr = snap_to_ceiling("c1", mount_offset=0.2, surfaces=[surface])
    assert abs(tr.position[2] - 3.2) < 1e-9
    assert tr.rotation.type == "aim_up"
    assert tr.rotation.aim == (0.0, 0.0, -1.0)


def test_snap_to_grid_intersections_count_and_positions() -> None:
    grid = CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=2.0, height=1.0, elevation=0.8, nx=3, ny=2)
    trs = snap_to_grid_intersections("g1", [grid], z=2.5)
    assert len(trs) == 6
    assert trs[0].position == (0.0, 0.0, 2.5)
    assert trs[-1].position == (2.0, 1.0, 2.5)
