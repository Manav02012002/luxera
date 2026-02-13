from __future__ import annotations

from pathlib import Path

from luxera.gui.commands.core import cmd_add_workplane_grid
from luxera.project.io import save_project_schema
from luxera.project.schema import Project, RoomSpec


def test_gui_workplane_grid_uses_calc_ops(monkeypatch, tmp_path: Path) -> None:
    project = Project(name="gui-ops", root_dir=str(tmp_path))
    project.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=5.0, height=3.0))
    p = tmp_path / "p.json"
    save_project_schema(project, p)

    called = {"ok": False}

    def _fake_create(*args, **kwargs):  # noqa: ANN001
        called["ok"] = True
        from luxera.project.schema import CalcGrid

        return CalcGrid(
            id="g1",
            name="G1",
            origin=(0.0, 0.0, 0.0),
            width=1.0,
            height=1.0,
            elevation=0.8,
            nx=2,
            ny=2,
            room_id="r1",
        )

    monkeypatch.setattr("luxera.gui.commands.core.create_calc_grid_from_room", _fake_create)
    diff = cmd_add_workplane_grid(str(p), "r1", height=0.8, spacing=0.5, margins=0.2)
    assert called["ok"] is True
    assert diff.ops and diff.ops[0].kind == "grid"

