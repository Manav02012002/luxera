from __future__ import annotations

from luxera.project.history import push_snapshot, redo, undo
from luxera.project.schema import CalcGrid, Project


def _grid(grid_id: str, elevation: float) -> CalcGrid:
    return CalcGrid(
        id=grid_id,
        name=grid_id,
        origin=(0.0, 0.0, 0.0),
        width=2.0,
        height=2.0,
        elevation=elevation,
        nx=3,
        ny=3,
    )


def test_history_undo_redo_multiple_snapshots() -> None:
    p = Project(name="hist-multi")
    push_snapshot(p, label="before_g1")
    p.grids.append(_grid("g1", 0.8))

    push_snapshot(p, label="before_g2")
    p.grids.append(_grid("g2", 1.0))
    assert [g.id for g in p.grids] == ["g1", "g2"]

    assert undo(p) is True
    assert [g.id for g in p.grids] == ["g1"]
    assert undo(p) is True
    assert [g.id for g in p.grids] == []
    assert len(p.assistant_redo_stack) == 2

    assert redo(p) is True
    assert [g.id for g in p.grids] == ["g1"]
    assert redo(p) is True
    assert [g.id for g in p.grids] == ["g1", "g2"]


def test_history_new_change_clears_redo_stack() -> None:
    p = Project(name="hist-clear-redo")
    push_snapshot(p, label="before_g1")
    p.grids.append(_grid("g1", 0.8))
    assert undo(p) is True
    assert len(p.assistant_redo_stack) == 1

    push_snapshot(p, label="before_g3")
    p.grids.append(_grid("g3", 1.2))
    assert p.assistant_redo_stack == []
    assert redo(p) is False
