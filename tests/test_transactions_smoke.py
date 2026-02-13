from __future__ import annotations

import pytest

from luxera.ops.base import execute_op
from luxera.ops.transactions import get_transaction_manager
from luxera.project.schema import Project, RoomSpec


def test_transaction_begin_commit_rollback_smoke() -> None:
    p = Project(name="tx-smoke")
    tx = get_transaction_manager(p)

    tx.begin("manual")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=4.0, length=4.0, height=3.0))
    rec = tx.commit()
    assert tx.undo_depth == 1
    assert len(rec.delta.created) == 1

    assert tx.undo() is True
    assert len(p.geometry.rooms) == 0
    assert tx.redo() is True
    assert len(p.geometry.rooms) == 1


def test_execute_op_rolls_back_on_exception() -> None:
    p = Project(name="tx-rollback")

    def _mutate() -> None:
        p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=4.0, length=4.0, height=3.0))
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        execute_op(p, op_name="fail_op", args={}, ctx=None, validate=None, mutate=_mutate)

    assert len(p.geometry.rooms) == 0
