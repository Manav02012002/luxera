from __future__ import annotations

from pathlib import Path

from luxera.testing.compare import compare_golden_case
from luxera.testing.golden import discover_golden_cases, load_golden_case, run_golden_case


def test_golden_case_loader_reads_metadata() -> None:
    case = load_golden_case("box_room")
    assert case.case_id == "box_room"
    assert case.project_path.exists()
    assert case.scene_path.exists()
    assert case.expected_dir.exists()
    assert case.job_id == "j_direct"
    assert "max_abs_lux" in case.tolerances
    assert "engine_version" in case.metadata
    assert "tolerance_policy" in case.metadata


def test_golden_all_cases_regression_pack(tmp_path: Path) -> None:
    cases = discover_golden_cases()
    assert len(cases) >= 12
    for case in cases:
        produced = run_golden_case(case, run_root=tmp_path / "runs")
        out = compare_golden_case(case, produced)
        assert out.passed, f"Golden compare failed for {case.case_id}"
        assert out.report_path.exists()
        assert (produced / "diff_heatmap.png").exists()


def test_golden_includes_radiosity_cases() -> None:
    ids = {c.case_id for c in discover_golden_cases()}
    assert "box_room_radiosity" in ids
    assert "corridor_radiosity" in ids
