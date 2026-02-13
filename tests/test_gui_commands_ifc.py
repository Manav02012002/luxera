from __future__ import annotations

from pathlib import Path

from luxera.gui.commands import cmd_import_ifc
from luxera.project.io import save_project_schema
from luxera.project.schema import Project

def test_cmd_import_ifc_applies_unit_override_in_diff(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    p = Project(name="IFC Cmd", root_dir=str(tmp_path))
    project_path = tmp_path / "p.json"
    save_project_schema(p, project_path)

    diff = cmd_import_ifc(
        str(project_path),
        str(fixture),
        options={"length_unit_override": "ft", "default_window_transmittance": 0.55},
    )
    rooms = [op.payload for op in diff.ops if op.kind == "room" and op.op == "add"]
    openings = [op.payload for op in diff.ops if op.kind == "opening" and op.op == "add"]
    assert rooms
    assert openings
    # fallback room width of 5.0 ft should be converted to meters.
    assert abs(float(rooms[0].width) - (5.0 * 0.3048)) < 1e-9
    assert abs(float(openings[0].visible_transmittance) - 0.55) < 1e-9
