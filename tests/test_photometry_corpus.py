from __future__ import annotations

import json
from pathlib import Path

import pytest

from luxera.parser.ies_parser import parse_ies_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory


CORPUS_DIR = Path(__file__).parent / "photometry" / "corpus"


def _expected() -> dict:
    return json.loads((CORPUS_DIR / "expected_metadata.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture",
    [
        "odd_angle_ordering.ies",
        "missing_keywords.ies",
        "tilt_include_variant.ies",
        "tilt_file_variant.ies",
        "tilt_file_missing.ies",
        "extreme_candela.ies",
        "type_b_beam_real.ies",
    ],
)
def test_photometry_corpus_cases_parse(fixture: str) -> None:
    p = CORPUS_DIR / fixture
    doc = parse_ies_text(p.read_text(encoding="utf-8"), source_path=p)
    assert doc.photometry is not None
    assert doc.angles is not None
    assert doc.candela is not None


def test_photometry_corpus_metadata_golden() -> None:
    expected = _expected()
    actual = {}
    for fixture in sorted(expected.keys()):
        p = CORPUS_DIR / fixture
        doc = parse_ies_text(p.read_text(encoding="utf-8"), source_path=p)
        actual[fixture] = {
            "metadata": {
                "luminous_width_m": doc.metadata.luminous_width_m,
                "luminous_length_m": doc.metadata.luminous_length_m,
                "luminous_height_m": doc.metadata.luminous_height_m,
                "luminous_dimensions_source_unit": doc.metadata.luminous_dimensions_source_unit,
                "lumens": doc.metadata.lumens,
                "cct_k": doc.metadata.cct_k,
                "cri": doc.metadata.cri,
                "distribution_type": doc.metadata.distribution_type,
                "coordinate_system": doc.metadata.coordinate_system,
            },
            "warning_codes": [w.code for w in doc.warnings],
        }
    assert actual == expected


def test_odd_angle_ordering_is_normalized_deterministically() -> None:
    p = CORPUS_DIR / "odd_angle_ordering.ies"
    doc = parse_ies_text(p.read_text(encoding="utf-8"), source_path=p)
    assert doc.angles is not None
    assert doc.angles.vertical_deg == [0.0, 45.0, 90.0]
    assert doc.angles.horizontal_deg == [0.0, 90.0]


def test_luminous_dimensions_in_feet_convert_to_meters() -> None:
    text = """IESNA:LM-63-2019
[MANUFAC] EdgeCo
[LUMCAT] FEET-CASE
TILT=NONE
1 1000 1 3 1 1 1 2 4 1
0 45 90
0
100 80 60
"""
    doc = parse_ies_text(text)
    phot = photometry_from_parsed_ies(doc)
    assert phot.luminous_width_m == pytest.approx(0.6096)
    assert phot.luminous_length_m == pytest.approx(1.2192)
    assert phot.luminous_height_m == pytest.approx(0.3048)


def test_structured_photometry_warnings_surface_in_result_json() -> None:
    project_path = Path(__file__).parent / "golden" / "projects" / "box_room" / "project.json"
    project = load_project_schema(project_path)
    project.root_dir = str(project_path.parent)
    project.photometry_assets[0].path = str(CORPUS_DIR / "odd_angle_ordering.ies")

    ref = run_job_in_memory(project, "j_direct")
    payload = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    warnings = payload.get("photometry_warnings", [])
    assert isinstance(warnings, list)
    codes = {w.get("code") for w in warnings if isinstance(w, dict) and w.get("asset_id") == "a1"}
    assert "vertical_angles_reordered" in codes
    assert "horizontal_angles_reordered" in codes
