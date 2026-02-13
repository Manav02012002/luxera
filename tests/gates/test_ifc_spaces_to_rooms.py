from __future__ import annotations

from pathlib import Path

from luxera.io.ifc_import import IFCImportOptions, import_ifc


def test_ifc_spaces_to_rooms() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc(fixture, IFCImportOptions())
    assert len(out.rooms) >= 1
