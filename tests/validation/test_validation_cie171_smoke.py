from __future__ import annotations

from pathlib import Path

import pytest

from luxera.validation.harness import discover_cases, parse_target, run_cases, write_suite_report


@pytest.mark.validation_cie171_smoke
def test_cie171_smoke_case_direct_room_runs(tmp_path: Path) -> None:
    suites = discover_cases()
    cases = parse_target("cie171/case_direct_room", suites)
    out = tmp_path / "cie171_smoke_direct"
    results = run_cases(cases, out_root=out)
    assert len(results) == 1
    assert results[0].suite == "cie171"
    assert results[0].passed
    assert all(m.skipped for m in results[0].metrics)


@pytest.mark.validation_cie171_smoke
def test_cie171_smoke_case_roadway_runs_and_report(tmp_path: Path) -> None:
    suites = discover_cases()
    cases = parse_target("cie171/case_roadway_lane", suites)
    out = tmp_path / "cie171_smoke_roadway"
    results = run_cases(cases, out_root=out)
    assert len(results) == 1
    assert results[0].passed
    md, js = write_suite_report("cie171", results, out_root=out)
    assert md.exists()
    assert js.exists()
    assert (out / "cie171_summary.md").exists()
    assert (out / "cie171_summary.json").exists()
    text = md.read_text(encoding="utf-8")
    assert "SKIPPED" in text

