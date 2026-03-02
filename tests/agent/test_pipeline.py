from __future__ import annotations

from pathlib import Path

import pytest

from luxera.agent.pipeline import CompliancePipeline


def test_parse_intent_basic(tmp_path: Path) -> None:
    p = CompliancePipeline(output_dir=tmp_path)
    got = p._parse_intent("500 lux office 12x8m EN 12464")
    assert got.target_illuminance == 500.0
    assert got.room_width == 12.0
    assert got.room_length == 8.0
    assert got.standard == "EN 12464-1"
    assert "OFFICE" in got.activity_type


def test_parse_intent_with_height(tmp_path: Path) -> None:
    p = CompliancePipeline(output_dir=tmp_path)
    got = p._parse_intent("300 lux classroom 10x8x3.5m")
    assert got.target_illuminance == 300.0
    assert got.room_width == 10.0
    assert got.room_length == 8.0
    assert got.room_height == 3.5


def test_initial_layout_plausible(tmp_path: Path) -> None:
    p = CompliancePipeline(output_dir=tmp_path)
    rows, cols, _, _ = p._compute_initial_layout(
        room_width=12.0,
        room_length=8.0,
        room_height=3.0,
        target_lux=500.0,
        luminaire_lumens=3600.0,
        beam_angle=90.0,
    )
    assert 2 <= rows <= 10
    assert 2 <= cols <= 10


def test_lumen_method_formula(tmp_path: Path) -> None:
    p = CompliancePipeline(output_dir=tmp_path)
    E = 500.0
    A = 96.0
    F = 3600.0
    UF = 0.55
    MF = 0.80
    expected = E * A / (F * UF * MF)
    got = p._required_luminaires(E=E, A=A, F=F, UF=UF, MF=MF)
    assert got == pytest.approx(expected, rel=1e-9)


def test_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    default_ies = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    pipeline = CompliancePipeline(output_dir=tmp_path / "out", default_ies_path=default_ies)
    result = pipeline.run("500 lux open plan office 12x8m EN 12464-1 generate report")
    assert result.project_path.exists()
    assert result.report_path.exists()
    assert isinstance(result.compliant, bool)
    assert result.luminaire_count > 0
