from __future__ import annotations

from luxera.geometry.param.identity import surface_id_for_shared_wall
from luxera.geometry.param.model import FootprintParam, RoomParam, SharedWallParam
from luxera.geometry.param.rebuild import rebuild_surfaces_for_room
from luxera.project.schema import Project


def test_two_rooms_share_one_wall_entity_and_one_wall_surface_mesh() -> None:
    p = Project(name="shared-wall-single-mesh")
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
    p.param.shared_walls.append(
        SharedWallParam(
            id="sw1",
            edge_geom=((4.0, 0.0), (4.0, 3.0)),
            room_a="A",
            room_b="B",
            thickness=0.2,
        )
    )

    rebuild_surfaces_for_room("A", p)
    rebuild_surfaces_for_room("B", p)
    sid = surface_id_for_shared_wall("sw1")
    shared_wall_surfaces = [s for s in p.geometry.surfaces if s.id == sid]
    assert len(shared_wall_surfaces) == 1
    assert shared_wall_surfaces[0].kind == "wall"
    assert shared_wall_surfaces[0].layer == "shared_wall"

