from __future__ import annotations

from luxera.geometry.param.model import FootprintParam, RoomParam, SharedWallParam
from luxera.geometry.topology.shared_walls import edit_shared_edge, reconcile_shared_walls


def test_edit_shared_edge_updates_both_room_footprints() -> None:
    fps = [
        FootprintParam(id="fa", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]),
        FootprintParam(id="fb", polygon2d=[(4.0, 0.0), (8.0, 0.0), (8.0, 3.0), (4.0, 3.0)]),
    ]
    rooms = [
        RoomParam(id="A", footprint_id="fa", height=3.0),
        RoomParam(id="B", footprint_id="fb", height=3.0),
    ]
    sw = [SharedWallParam(id="sw1", shared_edge_id="se1", edge_geom=((4.0, 0.0), (4.0, 3.0)), room_a="A", room_b="B")]

    edit_shared_edge(fps, rooms, sw, shared_wall_id="sw1", new_start=(4.2, 0.0), new_end=(4.2, 3.0))

    assert any(abs(x - 4.2) < 1e-9 for x, _y in fps[0].polygon2d)
    assert any(abs(x - 4.2) < 1e-9 for x, _y in fps[1].polygon2d)


def test_shared_wall_becomes_exterior_when_one_room_removed() -> None:
    fps = [
        FootprintParam(id="fa", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]),
        FootprintParam(id="fb", polygon2d=[(4.0, 0.0), (8.0, 0.0), (8.0, 3.0), (4.0, 3.0)]),
    ]
    rooms = [
        RoomParam(id="A", footprint_id="fa", height=3.0),
        RoomParam(id="B", footprint_id="fb", height=3.0),
    ]
    walls = [SharedWallParam(id="sw1", shared_edge_id="edge:ab", edge_geom=((4.0, 0.0), (4.0, 3.0)), room_a="A", room_b="B")]

    out0 = reconcile_shared_walls(rooms, fps, walls)
    assert any(w.room_b == "B" for w in out0)

    out1 = reconcile_shared_walls([rooms[0]], [fps[0]], out0)
    sw = next(w for w in out1 if w.id == "sw1")
    assert sw.room_a == "A"
    assert sw.room_b is None
