from __future__ import annotations

from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.ops.scene_ops import create_room
from luxera.project.schema import Project


def _point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside


def test_grid_points_are_clipped_to_room_footprint() -> None:
    project = Project(name="clip")
    room = create_room(project, room_id="r1", name="Room", width=6.0, length=6.0, height=3.0)
    room.footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (2.0, 2.0), (2.0, 6.0), (0.0, 6.0)]
    grid = create_calc_grid_from_room(project, grid_id="g1", name="G", room_id="r1", elevation=0.8, spacing=1.0)
    assert grid.sample_mask
    assert any(not m for m in grid.sample_mask)
    assert grid.sample_points
    for x, y, _z in grid.sample_points:
        assert _point_in_polygon(float(x), float(y), list(room.footprint))

