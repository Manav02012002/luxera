from __future__ import annotations

import pytest

from luxera.ops.base import OpContext
from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.ops.scene_ops import create_room
from luxera.project.schema import Project


def test_ops_require_agent_approval() -> None:
    project = Project(name="ops")
    with pytest.raises(PermissionError):
        create_room(
            project,
            room_id="r1",
            name="R",
            width=4.0,
            length=5.0,
            height=3.0,
            ctx=OpContext(source="agent", user="agent", require_approval=True, approved=False),
        )


def test_ops_append_audit_with_hashes() -> None:
    project = Project(name="ops")
    room = create_room(
        project,
        room_id="r1",
        name="R",
        width=4.0,
        length=5.0,
        height=3.0,
        ctx=OpContext(source="gui", user="tester"),
    )
    _ = create_calc_grid_from_room(
        project,
        grid_id="g1",
        name="G",
        room_id=room.id,
        elevation=0.8,
        spacing=0.5,
        ctx=OpContext(source="gui", user="tester"),
    )
    assert len(project.agent_history) >= 2
    evt = project.agent_history[-1]
    assert evt["action"] == "ops.create_calc_grid_from_room"
    assert isinstance(evt.get("before_hash"), str) and len(evt["before_hash"]) == 64
    assert isinstance(evt.get("after_hash"), str) and len(evt["after_hash"]) == 64
    assert evt["before_hash"] != evt["after_hash"]

