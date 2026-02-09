from pathlib import Path

from luxera.parser.pipeline import parse_and_analyse_ies


def test_smoke_pipeline_parses_fixture():
    fixture = Path(__file__).parent / "fixtures" / "photometry" / "synthetic_basic.ies"
    text = fixture.read_text(encoding="utf-8")
    res = parse_and_analyse_ies(text)

    assert res.doc.photometry is not None
    assert res.doc.angles is not None
    assert res.doc.candela is not None

    assert res.doc.photometry.num_vertical_angles == 3
    assert res.doc.photometry.num_horizontal_angles == 2
    assert len(res.doc.angles.vertical_deg) == 3
    assert len(res.doc.angles.horizontal_deg) == 2

    values = res.doc.candela.values_cd_scaled
    assert len(values) == 2
    assert len(values[0]) == 3
