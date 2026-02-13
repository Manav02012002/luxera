from __future__ import annotations

from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.project.schema import Project, RoomSpec, ZoneSpec


def test_multi_zone_clipping_uses_independent_zone_footprints() -> None:
    p = Project(name="multi-zone")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=10.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.geometry.zones.extend(
        [
            ZoneSpec(id="z_left", name="Left", room_ids=["r1"], polygon2d=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)]),
            ZoneSpec(id="z_right", name="Right", room_ids=["r1"], polygon2d=[(5.0, 0.0), (10.0, 0.0), (10.0, 4.0), (5.0, 4.0)]),
        ]
    )

    g_left = create_calc_grid_from_room(p, grid_id="g_left", name="Left", room_id="r1", zone_id="z_left", elevation=0.8, spacing=2.0)
    g_right = create_calc_grid_from_room(p, grid_id="g_right", name="Right", room_id="r1", zone_id="z_right", elevation=0.8, spacing=2.0)

    assert g_left.zone_id == "z_left"
    assert g_right.zone_id == "z_right"
    assert g_left.sample_points
    assert g_right.sample_points
    assert all(pt[0] <= 5.0 for pt in g_left.sample_points)
    assert all(pt[0] >= 5.0 for pt in g_right.sample_points)
