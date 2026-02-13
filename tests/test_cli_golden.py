from __future__ import annotations

from pathlib import Path

from luxera.cli import main


def test_cli_golden_update_requires_yes() -> None:
    rc = main(["golden", "update", "box_room"])
    assert rc == 2


def test_cli_golden_run_and_compare(tmp_path: Path) -> None:
    out = tmp_path / "runs"
    rc_run = main(["golden", "run", "box_room", "--out", str(out)])
    assert rc_run == 0
    rc_cmp = main(["golden", "compare", "box_room", "--out", str(out)])
    assert rc_cmp == 0
    assert (out / "box_room" / "diff_report.json").exists()
