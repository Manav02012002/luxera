from __future__ import annotations

from pathlib import Path

from luxera.io.dxf_import import DXFDocument, DXFInsert
from luxera.io.geometry_import import GeometryImportResult
from luxera.io.import_pipeline import run_import_pipeline


def test_import_pipeline_detects_and_overrides_dxf_layers(monkeypatch, tmp_path: Path) -> None:
    dxf = tmp_path / "plan.dxf"
    dxf.write_text("0\nEOF\n", encoding="utf-8")

    doc = DXFDocument(layers=["A-WALL", "A-DOOR", "A-WINDOW", "A-ROOM"], entities=[DXFInsert(block_name="B1")], units="m")

    def _fake_load_dxf(_path):  # noqa: ANN001
        return doc

    def _fake_import_geometry_file(*args, **kwargs):  # noqa: ANN002, ANN003
        return GeometryImportResult(source_file=str(dxf), format="DXF")

    monkeypatch.setattr("luxera.io.import_pipeline.load_dxf", _fake_load_dxf)
    monkeypatch.setattr("luxera.io.import_pipeline.import_geometry_file", _fake_import_geometry_file)

    out = run_import_pipeline(
        str(dxf),
        fmt="DXF",
        layer_overrides={"A-WALL": "room"},
    )
    assert out.geometry is not None
    assert out.report.layer_map["A-WALL"] == "room"
    assert out.report.layer_map["A-DOOR"] == "door"
    assert any(s.name == "RawImport" for s in out.report.stages)

