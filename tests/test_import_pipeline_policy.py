from __future__ import annotations

from pathlib import Path

from luxera.io.import_pipeline import run_import_pipeline


def test_import_pipeline_blocks_extreme_geometry_by_default(tmp_path: Path) -> None:
    # Empty IFC yields no usable triangles -> extreme severity gate.
    fixture = tmp_path / "empty.ifc"
    fixture.write_text("ISO-10303-21;ENDSEC;END-ISO-10303-21;", encoding="utf-8")

    out = run_import_pipeline(str(fixture), fmt="IFC")
    assert out.geometry is None
    gate = next(s for s in out.report.stages if s.name == "PolicyGate")
    assert gate.status == "error"
    assert gate.details.get("severity") == "extreme"


def test_import_pipeline_force_extreme_allows_continue(tmp_path: Path) -> None:
    fixture = tmp_path / "empty.ifc"
    fixture.write_text("ISO-10303-21;ENDSEC;END-ISO-10303-21;", encoding="utf-8")

    out = run_import_pipeline(str(fixture), fmt="IFC", force_extreme=True)
    assert out.geometry is not None
    gate = next(s for s in out.report.stages if s.name == "PolicyGate")
    assert gate.status == "ok"
    assert gate.details.get("severity") == "extreme"
