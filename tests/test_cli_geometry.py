import json
from pathlib import Path

from luxera.cli import main


def test_cli_geometry_import_obj(tmp_path: Path):
    project = tmp_path / "p.json"
    rc = main(["init", str(project), "--name", "Geom"])
    assert rc == 0

    obj = tmp_path / "plane.obj"
    obj.write_text(
        """v 0 0 0
v 1 0 0
v 1 1 0
f 1 2 3
""",
        encoding="utf-8",
    )

    rc = main(["geometry", "import", str(project), str(obj)])
    assert rc == 0
    data = json.loads(project.read_text(encoding="utf-8"))
    assert data["geometry"]["surfaces"]
    assert data["geometry"]["length_unit"] == "m"
    assert data["geometry"]["scale_to_meters"] == 1.0


def test_cli_geometry_import_ifc_options(tmp_path: Path):
    project = tmp_path / "p_ifc.json"
    rc = main(["init", str(project), "--name", "GeomIFC"])
    assert rc == 0

    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    rc = main(
        [
            "geometry",
            "import",
            str(project),
            str(fixture),
            "--format",
            "IFC",
            "--length-unit",
            "ft",
            "--ifc-window-vt",
            "0.61",
            "--ifc-room-width",
            "7",
            "--ifc-room-length",
            "9",
            "--ifc-room-height",
            "4",
        ]
    )
    assert rc == 0
    data = json.loads(project.read_text(encoding="utf-8"))
    openings = data["geometry"]["openings"]
    rooms = data["geometry"]["rooms"]
    assert openings and rooms
    assert abs(float(openings[0]["visible_transmittance"]) - 0.61) < 1e-9
    assert abs(float(rooms[0]["width"]) - (7.0 * 0.3048)) < 1e-9
