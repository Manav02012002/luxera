from __future__ import annotations

from pathlib import Path

from luxera.io.import_pipeline import run_import_pipeline


def test_import_pipeline_ifc_runs_all_stages_and_returns_health() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = run_import_pipeline(str(fixture), fmt="IFC")
    assert out.geometry is not None
    names = [s.name for s in out.report.stages]
    assert names == ["RawImport", "NormalizedGeometry", "SemanticExtraction", "Repair2D", "RepairHeal", "PolicyGate", "SceneBuild"]
    assert "degenerate_triangles" in out.report.scene_health.get("counts", {})


def test_import_pipeline_structured_error_for_missing_file() -> None:
    out = run_import_pipeline("tests/fixtures/ifc/does_not_exist.ifc", fmt="IFC")
    assert out.geometry is None
    assert out.report.stages
    assert out.report.stages[-1].status == "error"
    assert out.report.stages[-1].name == "NormalizedGeometry"


def test_import_pipeline_can_post_reorient_geometry_handoff() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = run_import_pipeline(str(fixture), fmt="IFC", target_up_axis="Y_UP", target_handedness="LEFT_HANDED")
    assert out.geometry is not None
    assert any(s.name == "PostAxisReorient" for s in out.report.stages)
    assert "post:" in str(out.geometry.axis_transform_applied)
