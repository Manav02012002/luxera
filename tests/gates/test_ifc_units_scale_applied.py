from __future__ import annotations

from pathlib import Path

from luxera.io.ifc_import import IFCImportOptions, import_ifc


def test_ifc_units_scale_applied_override() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc(fixture, IFCImportOptions(length_unit_override="ft"))
    assert abs(float(out.coordinate_system["scale_to_meters"]) - 0.3048) < 1e-9
