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
