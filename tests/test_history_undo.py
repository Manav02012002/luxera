from __future__ import annotations

from luxera.project.history import push_snapshot, redo, undo
from luxera.project.schema import CalcGrid, Project


def test_history_undo_redo_roundtrip() -> None:
    p = Project(name="hist")
    assert undo(p) is False
    assert redo(p) is False

    push_snapshot(p, label="before_grid")
    p.grids.append(
        CalcGrid(
            id="g1",
            name="grid",
            origin=(0.0, 0.0, 0.0),
            width=2.0,
            height=2.0,
            elevation=0.8,
            nx=3,
            ny=3,
        )
    )
    assert len(p.grids) == 1

    assert undo(p) is True
    assert len(p.grids) == 0
    assert len(p.assistant_redo_stack) == 1

    assert redo(p) is True
    assert len(p.grids) == 1
