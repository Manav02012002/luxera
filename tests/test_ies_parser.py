import pytest

from luxera.parser.ies_parser import ParseError, parse_ies_text


def test_parse_minimal_ies():
    text = """IESNA:LM-63-2002
[MANUFAC] Acme
[LUMCAT] XZ-400
TILT=NONE
"""
    doc = parse_ies_text(text)
    assert doc.standard_line == "IESNA:LM-63-2002"
    assert doc.keywords["MANUFAC"] == ["Acme"]
    assert doc.keywords["LUMCAT"] == ["XZ-400"]
    assert doc.tilt_line == "TILT=NONE"
    assert doc.photometry is None
    assert doc.angles is None
    assert doc.candela is None


def test_parse_photometry_header_only_requires_angles():
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 1 3 2 1 2 0.45 0.45 0.10
"""
    with pytest.raises(ParseError):
        parse_ies_text(text)


def test_parse_tilt_include():
    text = """IESNA:LM-63-2019
TILT=INCLUDE
3
0 15 30
1.0 0.9 0.8
1 1000 1 3 1 1 2 0.45 0.45 0.10
0 45 90
0
100 80 60
"""
    doc = parse_ies_text(text)
    assert doc.tilt_line == "TILT=INCLUDE"
    assert doc.tilt_data is not None
    angles, factors = doc.tilt_data
    assert angles == [0.0, 15.0, 30.0]
    assert factors == [1.0, 0.9, 0.8]


def test_parse_angles_after_photometry():
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 1 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 0 0  1 2 3
"""
    doc = parse_ies_text(text)
    assert doc.photometry is not None
    assert doc.angles is not None
    assert doc.angles.vertical_deg == [0.0, 45.0, 90.0]
    assert doc.angles.horizontal_deg == [0.0, 180.0]
    assert doc.candela is not None  # candela parsed too


def test_parse_candela_table_shape_and_scaling():
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 2 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4 5
"""
    doc = parse_ies_text(text)
    assert doc.photometry is not None
    assert doc.angles is not None
    assert doc.candela is not None

    # H=2 rows, V=3 cols
    assert doc.candela.values_cd == [
        [0.0, 1.0, 2.0],
        [3.0, 4.0, 5.0],
    ]
    # multiplier = 2
    assert doc.candela.values_cd_scaled == [
        [0.0, 2.0, 4.0],
        [6.0, 8.0, 10.0],
    ]
    assert doc.candela.min_cd == 0.0
    assert doc.candela.max_cd == 10.0
    assert doc.candela.has_negative is False
    assert doc.candela.has_nan_or_inf is False


def test_candela_count_mismatch_raises():
    # Needs H*V = 2*3 = 6 values, but provides only 5
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 1 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4
"""
    with pytest.raises(ParseError):
        parse_ies_text(text)


def test_photometry_header_rejects_bad_units_type():
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 1 32 9 1 99 0.45 0.45 0.10
"""
    with pytest.raises(ParseError):
        parse_ies_text(text)
