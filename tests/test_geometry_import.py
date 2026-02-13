from pathlib import Path

import pytest

from luxera.io.geometry_import import import_geometry_file
from luxera.io.mesh_import import MeshImportResult


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


def test_import_obj_with_unit_override_scales_geometry(tmp_path: Path):
    obj = tmp_path / "line.obj"
    obj.write_text(
        """v 0 0 0
v 1 0 0
v 1 1 0
f 1 2 3
""",
        encoding="utf-8",
    )
    res = import_geometry_file(str(obj), length_unit="ft")
    assert res.scale_to_meters == 0.3048
    assert res.length_unit == "ft"
    pts = res.surfaces[0].vertices
    assert pts[1][0] == 0.3048


def test_import_dwg_returns_actionable_error(tmp_path: Path) -> None:
    dwg = tmp_path / "x.dwg"
    dwg.write_bytes(b"dummy")
    with pytest.raises(ValueError, match="DWG import requires external conversion"):
        import_geometry_file(str(dwg))


def test_import_fbx_via_mesh_import_adapter(monkeypatch, tmp_path: Path) -> None:
    fbx = tmp_path / "mesh.fbx"
    fbx.write_bytes(b"dummy")

    def _fake_import_mesh_file(*args, **kwargs):  # noqa: ANN002, ANN003
        return MeshImportResult(
            source_file=str(fbx),
            format="FBX",
            vertices=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            faces=[(0, 1, 2)],
            triangles=[(0, 1, 2)],
            length_unit="m",
            scale_to_meters=1.0,
            warnings=[],
        )

    monkeypatch.setattr("luxera.io.geometry_import.import_mesh_file", _fake_import_mesh_file)
    res = import_geometry_file(str(fbx), fmt="FBX")
    assert res.format == "FBX"
    assert len(res.surfaces) == 1


def test_import_skp_via_mesh_import_adapter(monkeypatch, tmp_path: Path) -> None:
    skp = tmp_path / "mesh.skp"
    skp.write_bytes(b"dummy")

    def _fake_import_mesh_file(*args, **kwargs):  # noqa: ANN002, ANN003
        return MeshImportResult(
            source_file=str(skp),
            format="SKP",
            vertices=[(0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 2.0)],
            faces=[(0, 1, 2)],
            triangles=[(0, 1, 2)],
            length_unit="m",
            scale_to_meters=1.0,
            warnings=[],
        )

    monkeypatch.setattr("luxera.io.geometry_import.import_mesh_file", _fake_import_mesh_file)
    res = import_geometry_file(str(skp), fmt="SKP")
    assert res.format == "SKP"
    assert len(res.surfaces) == 1
