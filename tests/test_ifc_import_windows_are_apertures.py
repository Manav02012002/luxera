from __future__ import annotations

from pathlib import Path

from luxera.io.ifc_import import IFCImportOptions, import_ifc


def test_ifc_windows_default_to_daylight_apertures() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc(fixture, IFCImportOptions(default_window_transmittance=0.61))
    assert out.openings
    op = out.openings[0]
    assert op.is_daylight_aperture is True
    assert op.opening_type == "window"
    assert abs(float(op.vt or 0.0) - 0.61) < 1e-9


def test_ifc_boundary_method_reported() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc(fixture, IFCImportOptions())
    assert out.ifc_space_boundary_method in {"relspaceboundary", "geometry", "bbox"}
