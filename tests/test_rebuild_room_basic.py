from __future__ import annotations

from luxera.geometry.param.identity import surface_id_for_wall_side
from luxera.geometry.param.model import FootprintParam, RoomParam, WallParam
from luxera.geometry.param.rebuild import rebuild_surfaces_for_room
from luxera.project.schema import Project


def _project_with_param_room() -> Project:
    p = Project(name="rebuild-room")
    p.param.footprints.append(FootprintParam(id="fp1", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]))
    p.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.0, name="Room 1"))
    p.param.walls.extend(
        [
            WallParam(id="w01", room_id="r1", edge_ref=(0, 1)),
            WallParam(id="w12", room_id="r1", edge_ref=(1, 2)),
            WallParam(id="w23", room_id="r1", edge_ref=(2, 3)),
            WallParam(id="w30", room_id="r1", edge_ref=(3, 0)),
        ]
    )
    return p


def test_rebuild_surfaces_for_room_generates_floor_ceiling_and_walls() -> None:
    p = _project_with_param_room()
    out = rebuild_surfaces_for_room("r1", p)
    assert out.room_id == "r1"
    assert len([s for s in p.geometry.surfaces if s.room_id == "r1" and s.kind == "floor"]) == 1
    assert len([s for s in p.geometry.surfaces if s.room_id == "r1" and s.kind == "ceiling"]) == 1
    assert len([s for s in p.geometry.surfaces if s.room_id == "r1" and s.kind == "wall"]) == 4


def test_rebuild_updates_wall_geometry_after_footprint_edit() -> None:
    p = _project_with_param_room()
    rebuild_surfaces_for_room("r1", p)
    wall_id = surface_id_for_wall_side("w01", "A")
    before = next(s for s in p.geometry.surfaces if s.id == wall_id)
    before_first = before.vertices[0]

    p.param.footprints[0].polygon2d[0] = (-1.0, 0.0)
    rebuild_surfaces_for_room("r1", p)
    after = next(s for s in p.geometry.surfaces if s.id == wall_id)
    after_first = after.vertices[0]
    assert before_first != after_first

