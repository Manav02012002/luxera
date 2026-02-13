from __future__ import annotations

from luxera.ops.calc_ops import create_line_grid
from luxera.project.schema import Project


def test_create_line_grid_with_snap_and_clip() -> None:
    p = Project(name="line")
    lg = create_line_grid(
        p,
        line_id="lg1",
        name="Route",
        polyline=[(0.1, 0.2, 0.0), (1.9, 0.2, 0.0), (3.9, 0.2, 0.0)],
        spacing=0.5,
        snap_segments_xy=[((0.0, 0.0), (4.0, 0.0))],
        clip_boundary_xy=[(0.0, -1.0), (4.0, -1.0), (4.0, 1.0), (0.0, 1.0)],
    )
    assert lg.id == "lg1"
    assert len(lg.polyline) >= 2
    assert all(abs(p[1]) < 1e-6 for p in lg.polyline)
