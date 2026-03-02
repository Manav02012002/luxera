from __future__ import annotations

from pathlib import Path

from luxera.validation.cie171_cases import CIE171_CASES
from luxera.validation.cie171_runner import CIE171ValidationRunner


def _case(case_id: str):
    return next(c for c in CIE171_CASES if c.id == case_id)


def test_case1_isotropic_direct():
    runner = CIE171ValidationRunner(cases=[_case("case1")])
    result = runner.run_all()[0]
    assert result.deviation_pct < 0.5
    assert result.passed


def test_case2_cosine_direct():
    runner = CIE171ValidationRunner(cases=[_case("case2")])
    result = runner.run_all()[0]
    assert result.deviation_pct < 0.5
    assert result.passed


def test_case3_grid_of_6():
    runner = CIE171ValidationRunner(cases=[_case("case3")])
    result = runner.run_all()[0]
    assert result.deviation_pct < 0.5
    assert result.passed


def test_case6_corridor():
    runner = CIE171ValidationRunner(cases=[_case("case6")])
    result = runner.run_all()[0]
    assert result.deviation_pct < 0.5
    assert result.passed


def test_case8_near_field():
    runner = CIE171ValidationRunner(cases=[_case("case8")])
    result = runner.run_all()[0]
    assert result.deviation_pct < 1.0
    assert result.passed


def test_all_analytical_pass():
    case_ids = {"case1", "case2", "case3", "case6", "case7", "case8"}
    runner = CIE171ValidationRunner(cases=[c for c in CIE171_CASES if c.id in case_ids])
    results = runner.run_all()
    assert len(results) == 6
    assert all(r.passed for r in results)


def test_report_generation(tmp_path: Path):
    case_ids = {"case1", "case2", "case3", "case6", "case7", "case8"}
    runner = CIE171ValidationRunner(cases=[c for c in CIE171_CASES if c.id in case_ids])
    results = runner.run_all()
    ascii_report = runner.generate_report(results)
    assert "Case ID" in ascii_report
    assert "Summary:" in ascii_report
    out = tmp_path / "cie171_validation.html"
    runner.generate_html_report(results, out)
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip() != ""

