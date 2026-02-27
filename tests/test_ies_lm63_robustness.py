from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from luxera.core.transform import from_euler_zyx
from luxera.geometry.core import Vector3
from luxera.parser.ies_parser import ParseError, parse_ies_file, parse_ies_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.photometry.sample import sample_intensity_cd, sample_intensity_cd_world


def _ies_text(vertical: list[float], horizontal: list[float], rows: list[list[float]], photometric_type: int = 1) -> str:
    v = " ".join(f"{x:g}" for x in vertical)
    h = " ".join(f"{x:g}" for x in horizontal)
    cd = "\n".join(" ".join(f"{x:g}" for x in row) for row in rows)
    return (
        "IESNA:LM-63-2019\n"
        "[MANUFAC] Robust\n"
        "[LUMCAT] ROBUST-01\n"
        "TILT=NONE\n"
        f"1 1000 1 {len(vertical)} {len(horizontal)} {photometric_type} 2 0.2 0.2 0.1\n"
        f"{v}\n"
        f"{h}\n"
        f"{cd}\n"
    )


def _dir_from_c_gamma(c_deg: float, g_deg: float) -> Vector3:
    c = math.radians(float(c_deg))
    g = math.radians(float(g_deg))
    return Vector3(math.sin(g) * math.cos(c), math.sin(g) * math.sin(c), -math.cos(g)).normalize()


def test_unsorted_duplicate_angles_are_normalized_deterministically() -> None:
    text = _ies_text(
        vertical=[90.0, 0.0, 45.0, 45.0],
        horizontal=[360.0, 90.0, 0.0, 270.0],
        rows=[
            [9.0, 1.0, 5.0, 5.0],
            [10.0, 2.0, 6.0, 6.0],
            [11.0, 3.0, 7.0, 7.0],
            [12.0, 4.0, 8.0, 8.0],
        ],
        photometric_type=1,
    )
    doc = parse_ies_text(text)
    assert doc.angles is not None
    assert doc.candela is not None
    assert doc.angles.vertical_deg == [0.0, 45.0, 90.0]
    assert doc.angles.horizontal_deg == [0.0, 90.0, 270.0]
    assert len(doc.candela.values_cd_scaled) == 3
    assert len(doc.candela.values_cd_scaled[0]) == 3
    codes = {w.code for w in doc.warnings}
    assert "vertical_angles_reordered" in codes
    assert "vertical_angles_deduplicated" in codes
    assert "horizontal_angles_reordered" in codes
    assert "horizontal_angles_deduplicated" in codes


def test_symmetry_expansion_matches_full_plane_equivalent() -> None:
    # Quadrant-only C-planes with irregular spacing.
    partial = _ies_text(
        vertical=[0.0, 30.0, 60.0, 90.0],
        horizontal=[0.0, 25.0, 60.0, 90.0],
        rows=[
            [100.0, 90.0, 70.0, 50.0],
            [120.0, 108.0, 84.0, 60.0],
            [150.0, 135.0, 105.0, 75.0],
            [180.0, 162.0, 126.0, 90.0],
        ],
        photometric_type=1,
    )
    full = _ies_text(
        vertical=[0.0, 30.0, 60.0, 90.0],
        horizontal=[0.0, 25.0, 60.0, 90.0, 120.0, 155.0, 180.0, 205.0, 240.0, 270.0, 300.0, 335.0],
        rows=[
            [100.0, 90.0, 70.0, 50.0],   # 0
            [120.0, 108.0, 84.0, 60.0],  # 25
            [150.0, 135.0, 105.0, 75.0],  # 60
            [180.0, 162.0, 126.0, 90.0],  # 90
            [150.0, 135.0, 105.0, 75.0],  # 120 = 180-60
            [120.0, 108.0, 84.0, 60.0],  # 155 = 180-25
            [100.0, 90.0, 70.0, 50.0],   # 180 = 180-0
            [120.0, 108.0, 84.0, 60.0],  # 205 = 25
            [150.0, 135.0, 105.0, 75.0],  # 240 = 60
            [180.0, 162.0, 126.0, 90.0],  # 270 = 90
            [150.0, 135.0, 105.0, 75.0],  # 300 = 360-60
            [120.0, 108.0, 84.0, 60.0],  # 335 = 360-25
        ],
        photometric_type=1,
    )
    p_partial = photometry_from_parsed_ies(parse_ies_text(partial))
    p_full = photometry_from_parsed_ies(parse_ies_text(full))

    gammas = np.linspace(0.0, 90.0, 13)
    c_angles = np.linspace(0.0, 359.0, 37)
    for c in c_angles.tolist():
        for g in gammas.tolist():
            d = _dir_from_c_gamma(c, g)
            a = sample_intensity_cd(p_partial, d)
            b = sample_intensity_cd(p_full, d)
            assert a == pytest.approx(b, rel=1e-8, abs=1e-8)


def test_rotation_360_degree_invariance_property() -> None:
    text = _ies_text(
        vertical=[0.0, 45.0, 90.0, 135.0, 180.0],
        horizontal=[0.0, 120.0, 240.0],
        rows=[
            [200.0, 180.0, 100.0, 35.0, 10.0],
            [120.0, 160.0, 140.0, 50.0, 15.0],
            [220.0, 150.0, 90.0, 20.0, 8.0],
        ],
        photometric_type=1,
    )
    phot = photometry_from_parsed_ies(parse_ies_text(text))
    t0 = from_euler_zyx(Vector3(0.0, 0.0, 0.0), yaw_deg=0.0, pitch_deg=0.0, roll_deg=0.0)
    t360 = from_euler_zyx(Vector3(0.0, 0.0, 0.0), yaw_deg=360.0, pitch_deg=0.0, roll_deg=0.0)

    rng = np.random.default_rng(12345)
    for _ in range(250):
        v = rng.normal(size=3)
        d = Vector3(float(v[0]), float(v[1]), float(v[2])).normalize()
        a = sample_intensity_cd_world(phot, t0, d)
        b = sample_intensity_cd_world(phot, t360, d)
        assert a == pytest.approx(b, rel=1e-10, abs=1e-10)


def test_parse_ies_file_uses_fallback_encoding_and_reports_warning(tmp_path: Path) -> None:
    text = _ies_text(
        vertical=[0.0, 45.0, 90.0],
        horizontal=[0.0],
        rows=[[100.0, 80.0, 50.0]],
        photometric_type=1,
    ).replace("Robust", "Robust-é")
    p = tmp_path / "encoding_case.ies"
    p.write_bytes(text.encode("cp1252"))
    doc = parse_ies_file(p)
    codes = {w.code for w in doc.warnings}
    assert "encoding_fallback" in codes


def test_parse_ies_file_invalid_data_has_actionable_path_and_reason(tmp_path: Path) -> None:
    bad = (
        "IESNA:LM-63-2019\n"
        "TILT=NONE\n"
        "1 1000 1 3 2 1 2 0.2 0.2 0.1\n"
        "0 45 90\n"
        "10 20\n"  # invalid: missing horizontal 0 plane
        "100 80 60 20 10 5\n"
    )
    p = tmp_path / "broken.ies"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ParseError) as exc:
        parse_ies_file(p)
    msg = str(exc.value)
    assert str(p) in msg
    assert "Horizontal angle series must include 0 degrees" in msg
