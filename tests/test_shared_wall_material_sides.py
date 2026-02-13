from __future__ import annotations

from luxera.geometry.param.identity import surface_id_for_shared_wall
from luxera.geometry.param.model import FootprintParam, RoomParam, SharedWallParam
from luxera.geometry.param.rebuild import rebuild_surfaces_for_room
from luxera.project.schema import Project


def _tag_value(tags: list[str], key: str) -> str:
    for t in tags:
        if t.startswith(f"{key}="):
            return t.split("=", 1)[1]
    return ""


def test_shared_wall_per_side_materials_are_independent() -> None:
    p = Project(name="shared-wall-material-sides")
    p.param.footprints.extend(
        [
            FootprintParam(id="fa", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]),
            FootprintParam(id="fb", polygon2d=[(4.0, 0.0), (8.0, 0.0), (8.0, 3.0), (4.0, 3.0)]),
        ]
    )
    p.param.rooms.extend(
        [
            RoomParam(id="A", footprint_id="fa", height=3.0),
            RoomParam(id="B", footprint_id="fb", height=3.0),
        ]
    )
    sw = SharedWallParam(
        id="sw1",
        edge_geom=((4.0, 0.0), (4.0, 3.0)),
        room_a="A",
        room_b="B",
        wall_material_side_a="mat_room_a",
        wall_material_side_b="mat_room_b",
    )
    p.param.shared_walls.append(sw)

    rebuild_surfaces_for_room("A", p)
    sid = surface_id_for_shared_wall("sw1")
    s0 = next(s for s in p.geometry.surfaces if s.id == sid)
    b0 = _tag_value(s0.tags, "wall_material_side_b")
    assert b0 == "mat_room_b"

    sw.wall_material_side_a = "mat_room_a_changed"
    rebuild_surfaces_for_room("A", p)
    s1 = next(s for s in p.geometry.surfaces if s.id == sid)
    assert _tag_value(s1.tags, "wall_material_side_a") == "mat_room_a_changed"
    assert _tag_value(s1.tags, "wall_material_side_b") == "mat_room_b"

