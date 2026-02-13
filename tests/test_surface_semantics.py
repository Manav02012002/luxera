from __future__ import annotations

from luxera.ops.scene_ops import create_room, extrude_room_to_surfaces
from luxera.project.schema import Project


def test_room_surfaces_regenerate_from_footprint() -> None:
    project = Project(name="surf")
    room = create_room(project, room_id="r1", name="R", width=6.0, length=5.0, height=3.0)
    room.footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (2.0, 2.0), (2.0, 5.0), (0.0, 5.0)]
    s1 = extrude_room_to_surfaces(project, room.id, replace_existing=True)
    walls1 = [s for s in s1 if s.kind == "wall"]
    assert len(walls1) == len(room.footprint)

    room.footprint = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    s2 = extrude_room_to_surfaces(project, room.id, replace_existing=True)
    walls2 = [s for s in s2 if s.kind == "wall"]
    assert len(walls2) == 4

