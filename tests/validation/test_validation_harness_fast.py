from __future__ import annotations

from pathlib import Path

import pytest

from luxera.validation.harness import (
    discover_cases,
    parse_target,
    run_cases,
    write_suite_report,
)


@pytest.mark.validation_fast
def test_validation_harness_toy_suite_runs(tmp_path: Path) -> None:
    suites = discover_cases()
    assert "toy" in suites

    toy_cases = parse_target("toy", suites)
    assert {c.case_id for c in toy_cases} >= {"indoor_direct", "roadway_basic"}

    out = tmp_path / "validation_out"
    results = run_cases(toy_cases, out_root=out)
    assert len(results) >= 2
    assert all(r.passed for r in results)


@pytest.mark.validation_fast
def test_validation_harness_report_artifacts(tmp_path: Path) -> None:
    suites = discover_cases()
    toy_cases = parse_target("toy", suites)
    out = tmp_path / "validation_report"
    results = run_cases(toy_cases, out_root=out)

    md, js = write_suite_report("toy", results, out_root=out)
    assert md.exists()
    assert js.exists()
    text = md.read_text(encoding="utf-8")
    assert "Validation Summary: toy" in text


@pytest.mark.validation_fast
def test_validation_harness_supports_skipped_metrics(tmp_path: Path) -> None:
    suites = discover_cases()
    assert "cie171" in suites
    cases = parse_target("cie171/case_direct_room", suites)
    out = tmp_path / "validation_skip"
    results = run_cases(cases, out_root=out)
    assert len(results) == 1
    assert results[0].passed
    assert results[0].metrics
    assert all(m.skipped for m in results[0].metrics)
    assert all(bool(m.details.get("reason")) for m in results[0].metrics)
