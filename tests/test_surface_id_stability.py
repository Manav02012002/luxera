from __future__ import annotations

from luxera.geometry.param.identity import surface_id_for_ceiling, surface_id_for_floor, surface_id_for_wall_side
from luxera.geometry.param.model import FootprintParam, RoomParam, WallParam
from luxera.geometry.param.rebuild import rebuild_surfaces_for_room
from luxera.project.schema import Project


def test_surface_ids_stable_across_rebuilds() -> None:
    p = Project(name="surface-id-stability")
    p.param.footprints.append(FootprintParam(id="fp1", polygon2d=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)]))
    p.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.2))
    p.param.walls.extend(
        [
            WallParam(id="w01", room_id="r1", edge_ref=(0, 1)),
            WallParam(id="w12", room_id="r1", edge_ref=(1, 2)),
            WallParam(id="w23", room_id="r1", edge_ref=(2, 3)),
            WallParam(id="w30", room_id="r1", edge_ref=(3, 0)),
        ]
    )

    rebuild_surfaces_for_room("r1", p)
    expected = {
        surface_id_for_floor("r1"),
        surface_id_for_ceiling("r1"),
        surface_id_for_wall_side("w01", "A"),
        surface_id_for_wall_side("w12", "A"),
        surface_id_for_wall_side("w23", "A"),
        surface_id_for_wall_side("w30", "A"),
    }
    got_before = {s.id for s in p.geometry.surfaces if s.room_id == "r1" and s.kind in {"floor", "ceiling", "wall"}}
    assert expected.issubset(got_before)

    p.param.footprints[0].polygon2d[1] = (6.0, 0.0)
    rebuild_surfaces_for_room("r1", p)
    got_after = {s.id for s in p.geometry.surfaces if s.room_id == "r1" and s.kind in {"floor", "ceiling", "wall"}}
    assert expected.issubset(got_after)

