from __future__ import annotations

from pathlib import Path

import pytest

from luxera.parser.tilt_file import TiltFileError, load_tilt_file


def test_load_tilt_file_simple_fixture() -> None:
    path = Path(__file__).parent / "fixtures" / "ies" / "tilt.dat"
    tilt = load_tilt_file(path)
    assert tilt.angles_deg == [0.0, 30.0, 60.0]
    assert tilt.factors == [1.0, 0.5, 0.2]
    # Clamp behavior outside range.
    assert tilt.interpolate(-10.0) == pytest.approx(1.0)
    assert tilt.interpolate(80.0) == pytest.approx(0.2)


def test_load_tilt_file_rejects_non_monotonic_angles(tmp_path: Path) -> None:
    p = tmp_path / "bad_tilt.dat"
    p.write_text("1\n3\n0 20 10\n1.0 0.8 0.6\n", encoding="utf-8")
    with pytest.raises(TiltFileError):
        load_tilt_file(p)
