from pathlib import Path

from luxera.cli import main


def test_cli_demo_writes_file(tmp_path: Path):
    out = tmp_path / "demo.ies"
    rc = main(["demo", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    assert out.stat().st_size > 0
