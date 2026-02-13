from __future__ import annotations

from pathlib import Path

from luxera.io.mesh_import import import_mesh_file


def test_mesh_cleaning_removes_degenerate_triangles(tmp_path: Path) -> None:
    obj = tmp_path / "deg.obj"
    obj.write_text(
        "\n".join(
            [
                "v 0 0 0",
                "v 1 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "f 1 2 3",  # degenerate
                "f 1 2 4",  # valid
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = import_mesh_file(str(obj), fmt="OBJ")
    assert len(out.triangles) == 1
