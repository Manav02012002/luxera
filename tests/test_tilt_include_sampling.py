from __future__ import annotations

from pathlib import Path

import pytest
from luxera.geometry.core import Vector3
from luxera.parser.ies_parser import parse_ies_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.photometry.sample import sample_intensity_cd


def test_tilt_include_gamma_ratio() -> None:
    fixture = Path(__file__).parent / "fixtures" / "ies" / "tilt_include_simple.ies"
    doc = parse_ies_text(fixture.read_text(encoding="utf-8"))
    phot = photometry_from_parsed_ies(doc)

    # gamma 0
    i0 = sample_intensity_cd(phot, Vector3(0.0, 0.0, -1.0))
    # gamma 60
    i60 = sample_intensity_cd(phot, Vector3(0.8660254038, 0.0, -0.5))
    assert i0 > 0.0
    assert i60 > 0.0
    assert i60 / i0 == pytest.approx(0.2, rel=1e-6)
