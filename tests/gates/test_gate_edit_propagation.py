from __future__ import annotations

import json
from pathlib import Path

from luxera.geometry.param.graph import ParamGraph
from luxera.geometry.param.identity import surface_id_for_wall_side
from luxera.geometry.param.model import FootprintParam, RoomParam, WallParam
from luxera.geometry.param.rebuild import rebuild_surfaces_for_room
from luxera.project.schema import Project


def _load_case() -> dict:
    p = Path("tests/assets/geometry_cases/edit_propagation_room.json").resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def test_gate_edit_propagation_graph_and_rebuild() -> None:
    case = _load_case()

    graph = ParamGraph()
    for node_id, kind in case["graph"]["nodes"]:
        graph.add_node(str(node_id), str(kind))
    for src, dst in case["graph"]["edges"]:
        graph.add_edge(str(src), str(dst))

    affected = graph.affected([str(x) for x in case["graph"]["start_ids"]])
    assert affected == set(str(x) for x in case["graph"]["expected_affected"])

    project = Project(name="gate-edit-prop")
    fp = FootprintParam(
        id=str(case["footprint_id"]),
        polygon2d=[(float(x), float(y)) for x, y in case["initial_footprint"]],
    )
    room = RoomParam(
        id=str(case["room_id"]),
        footprint_id=str(case["footprint_id"]),
        height=float(case["height"]),
    )
    walls = [
        WallParam(id=str(w["id"]), room_id=str(case["room_id"]), edge_ref=(int(w["edge_ref"][0]), int(w["edge_ref"][1])))
        for w in case["walls"]
    ]
    project.param.footprints.append(fp)
    project.param.rooms.append(room)
    project.param.walls.extend(walls)

    rebuild_surfaces_for_room(room.id, project)
    sid = surface_id_for_wall_side(str(case["walls"][0]["id"]), "A")
    before = next(s for s in project.geometry.surfaces if s.id == sid)
    before_first = before.vertices[0]

    x0, y0 = case["edited_first_vertex"]
    project.param.footprints[0].polygon2d[0] = (float(x0), float(y0))
    rebuild_surfaces_for_room(room.id, project)

    after = next(s for s in project.geometry.surfaces if s.id == sid)
    after_first = after.vertices[0]

    assert before_first != after_first
    assert sid == after.id
