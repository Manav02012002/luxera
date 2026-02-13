from __future__ import annotations

from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.project.schema import NoGoZoneSpec, Project, RoomSpec


def test_grid_obstacle_mask_removes_points_in_keepout_polygon() -> None:
    p = Project(name="grid-mask")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=4.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.geometry.no_go_zones.append(
        NoGoZoneSpec(
            id="ng1",
            name="Core",
            room_id="r1",
            vertices=[(1.5, 1.5, 0.0), (2.5, 1.5, 0.0), (2.5, 2.5, 0.0), (1.5, 2.5, 0.0)],
        )
    )

    g = create_calc_grid_from_room(p, grid_id="g1", name="G1", room_id="r1", elevation=0.8, spacing=1.0)

    assert len(g.sample_mask) == g.nx * g.ny
    assert (2.0, 2.0, 0.8) not in g.sample_points
    assert len(g.sample_points) == sum(1 for m in g.sample_mask if m)
