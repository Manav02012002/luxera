from __future__ import annotations

from pathlib import Path

from luxera.io.ifc_import import IFCImportOptions, import_ifc


def test_ifc_import_records_axis_transform_metadata() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc(fixture, IFCImportOptions(source_up_axis="Y_UP", source_handedness="LEFT_HANDED"))
    cs = out.coordinate_system
    assert "axis_transform_applied" in cs
    assert "axis_matrix" in cs
    assert str(cs["axis_transform_applied"]).endswith("->Z_UP/RIGHT_HANDED")

