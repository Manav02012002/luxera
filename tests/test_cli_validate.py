from __future__ import annotations

from pathlib import Path

from luxera.cli import main


def test_cli_validate_list() -> None:
    rc = main(["validate", "list"])
    assert rc == 0


def test_cli_validate_run_single_case(tmp_path: Path) -> None:
    out = tmp_path / "out"
    rc = main(["validate", "run", "toy/indoor_direct", "--out", str(out)])
    assert rc == 0
    assert (out / "toy" / "indoor_direct" / "comparison.json").exists()


def test_cli_validate_report_suite(tmp_path: Path) -> None:
    out = tmp_path / "report"
    rc = main(["validate", "report", "toy", "--out", str(out)])
    assert rc == 0
    assert (out / "toy_summary.json").exists()
    assert (out / "toy_summary.md").exists()
    assert (out / "validation_toy_summary.json").exists()
    assert (out / "validation_toy_summary.md").exists()


def test_cli_validate_cie171_run_and_report(tmp_path: Path) -> None:
    out = tmp_path / "cie171_report"
    rc_run = main(["validate", "run", "cie171", "--out", str(out)])
    assert rc_run == 0
    rc_report = main(["validate", "report", "cie171", "--out", str(out)])
    assert rc_report == 0
    assert (out / "cie171_summary.json").exists()
    assert (out / "cie171_summary.md").exists()
