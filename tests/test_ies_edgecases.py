from __future__ import annotations

from pathlib import Path

import pytest

from luxera.parser.ies_parser import ParseError, parse_ies_text


def _edge(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / "ies" / "lm63_edgecases" / name


@pytest.mark.parametrize(
    "fixture,expected_v,expected_h",
    [
        ("ok_whitespace.ies", 3, 2),
        ("ok_wrapped_with_comments.ies", 4, 2),
    ],
)
def test_ies_edgecases_parse_ok(fixture: str, expected_v: int, expected_h: int) -> None:
    p = _edge(fixture)
    doc = parse_ies_text(p.read_text(encoding="utf-8"), source_path=p)
    assert doc.photometry is not None
    assert doc.angles is not None
    assert doc.candela is not None
    assert doc.photometry.num_vertical_angles == expected_v
    assert doc.photometry.num_horizontal_angles == expected_h


@pytest.mark.parametrize(
    "fixture,expected_substring",
    [
        ("fail_bad_counts.ies", "Expected 6 numeric values"),
        ("fail_symmetry_inconsistent.ies", "Horizontal angle series must start at 0"),
    ],
)
def test_ies_edgecases_parse_fail_actionable(fixture: str, expected_substring: str) -> None:
    p = _edge(fixture)
    with pytest.raises(ParseError) as exc:
        parse_ies_text(p.read_text(encoding="utf-8"), source_path=p)
    msg = str(exc.value)
    assert p.name in msg
    assert expected_substring in msg
