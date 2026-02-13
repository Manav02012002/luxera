from __future__ import annotations

from luxera.geometry.param.graph import ParamGraph


def test_param_graph_affected_transitive_closure() -> None:
    g = ParamGraph()
    g.add_node("fp:room1", "footprint")
    g.add_node("room:r1", "room")
    g.add_node("wall:w1", "wall")
    g.add_node("opening:o1", "opening")
    g.add_node("grid:g1", "grid")

    g.add_edge("fp:room1", "room:r1")
    g.add_edge("room:r1", "wall:w1")
    g.add_edge("wall:w1", "opening:o1")
    g.add_edge("room:r1", "grid:g1")

    affected = g.affected(["fp:room1"])
    assert affected == {"fp:room1", "room:r1", "wall:w1", "opening:o1", "grid:g1"}

