from __future__ import annotations

from pathlib import Path

import pytest

from luxera.geometry.core import Vector3
from luxera.parser.ies_parser import parse_ies_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.photometry.sample import sample_intensity_cd


def test_tilt_file_sampling_applies_gamma_factor() -> None:
    fixture = Path(__file__).parent / "fixtures" / "ies" / "tilt_file_simple.ies"
    doc = parse_ies_text(fixture.read_text(encoding="utf-8"), source_path=fixture)
    phot = photometry_from_parsed_ies(doc)
    assert phot.tilt_source == "FILE"
    assert phot.tilt is not None

    i0 = sample_intensity_cd(phot, Vector3(0.0, 0.0, -1.0))
    i60 = sample_intensity_cd(phot, Vector3(0.8660254038, 0.0, -0.5))
    assert i0 > 0.0
    assert i60 > 0.0
    assert i60 / i0 == pytest.approx(0.2, rel=1e-6)
