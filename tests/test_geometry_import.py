from pathlib import Path

from luxera.io.geometry_import import import_geometry_file


def test_import_obj_surfaces(tmp_path: Path):
    obj = tmp_path / "box.obj"
    obj.write_text(
        """v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
""",
        encoding="utf-8",
    )
    res = import_geometry_file(str(obj))
    assert res.format == "OBJ"
    assert len(res.surfaces) == 1
    assert len(res.surfaces[0].vertices) == 4
