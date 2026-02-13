from __future__ import annotations

from luxera.ops import OpContext, create_room, create_wall_polygon, replay_agent_history_to_scene_graph
from luxera.project.schema import Project
from luxera.scene.build import build_scene_graph_from_project


def test_build_scene_graph_from_project_has_hierarchy() -> None:
    p = Project(name="hier")
    room = create_room(p, room_id="r1", name="Room", width=4.0, length=5.0, height=3.0)
    _ = create_wall_polygon(
        p,
        surface_id="s1",
        name="Wall",
        vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
        room_id=room.id,
    )
    g = build_scene_graph_from_project(p)
    room_node = g.get_node("room:r1")
    surf_node = g.get_node("surface:s1")
    assert room_node.parent in {"group:rooms", None}
    assert surf_node.parent == "room:r1"


def test_replay_agent_history_to_scene_graph_applies_ops_events() -> None:
    p = Project(name="replay")
    _ = create_room(
        p,
        room_id="r1",
        name="Room",
        width=4.0,
        length=5.0,
        height=3.0,
        ctx=OpContext(source="gui", user="tester"),
    )
    _ = create_wall_polygon(
        p,
        surface_id="s1",
        name="Wall",
        vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
        room_id="r1",
        ctx=OpContext(source="gui", user="tester"),
    )
    rr = replay_agent_history_to_scene_graph(p, strict_hash_chain=True)
    assert rr.applied_events >= 2
    assert rr.hash_chain_ok is True
    assert rr.scene_graph.get_node("room:r1").id == "room:r1"
    assert rr.scene_graph.get_node("surface:s1").id == "surface:s1"

