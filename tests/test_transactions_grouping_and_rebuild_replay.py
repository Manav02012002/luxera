from __future__ import annotations

from luxera.geometry.param.identity import surface_id_for_wall_side
from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, WallParam
from luxera.geometry.param.rebuild import rebuild
from luxera.ops.base import execute_op, project_hash
from luxera.ops.diff import diff_project
from luxera.ops.delta import apply_delta
from luxera.ops.scene_ops import create_room_from_footprint, create_walls_from_footprint, edit_wall_and_propagate_adjacency
from luxera.ops.transactions import get_transaction_manager
from luxera.project.io import _project_from_dict  # type: ignore[attr-defined]
from luxera.project.schema import Project


def _state(p: Project) -> dict:
    return {
        "rooms": sorted(r.id for r in p.geometry.rooms),
        "surfaces": sorted(s.id for s in p.geometry.surfaces),
        "openings": sorted(o.id for o in p.geometry.openings),
    }


def test_transaction_grouping_merges_multiple_ops_into_one_undo_step() -> None:
    p = Project(name="tx-group")
    tx = get_transaction_manager(p)
    tx.begin_group("drag_session", args={"tool": "vertex_drag"})
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)], height=3.0)
    create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    rec = tx.end_group(before_hash="", after_hash=project_hash(p))
    assert rec is not None
    assert rec.group_id == "drag_session"
    assert len(rec.grouped_ops) == 2
    assert tx.undo_depth == 1
    assert tx.undo() is True
    assert not p.geometry.rooms
    assert not p.geometry.surfaces
    assert tx.redo() is True
    assert p.geometry.rooms
    assert p.geometry.surfaces


def test_delta_param_changes_and_apply_delta_replays_rebuild() -> None:
    p = Project(name="tx-param-replay")
    p.param.footprints.append(FootprintParam(id="fp1", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]))
    p.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.0))
    p.param.walls.append(WallParam(id="w01", room_id="r1", edge_ref=(0, 1)))
    p.param.openings.append(OpeningParam(id="o1", wall_id="w01", anchor=0.5, width=0.8, height=1.0, sill=0.8))
    rebuild(["footprint:fp1"], p)
    sid = surface_id_for_wall_side("w01", "A")

    before = p.to_dict()

    def _mutate() -> object:
        p.param.openings[0].width = 1.2
        return rebuild(["opening:o1"], p)

    execute_op(p, op_name="param_edit_opening", args={"opening_id": "o1", "width": 1.2}, ctx=None, validate=None, mutate=_mutate)
    after = p.to_dict()

    d = diff_project(before, after)
    assert "o1" in d.param_changes.get("updated", [])

    q = _project_from_dict(before)
    apply_delta(q, d)
    assert _state(q) == _state(p)
    assert any(s.id == sid or s.id.startswith(f"{sid}:") for s in q.geometry.surfaces)


def test_undo_redo_50_steps_keeps_state_valid() -> None:
    p = Project(name="tx-50")
    tx = get_transaction_manager(p)
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)], height=3.0)
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    wall = walls[0]

    for i in range(50):
        edit_wall_and_propagate_adjacency(
            p,
            wall_id=wall.id,
            new_start=(0.0, 0.0, 0.0),
            new_end=(6.0 + (i + 1) * 0.02, 0.0, 0.0),
        )
    after = _state(p)
    d0 = tx.undo_depth
    assert d0 >= 52  # room + walls + 50 edits

    for _ in range(50):
        assert tx.undo() is True
    assert p.geometry.rooms and p.geometry.surfaces

    for _ in range(50):
        assert tx.redo() is True
    assert _state(p) == after
