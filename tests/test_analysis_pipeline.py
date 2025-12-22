from luxera.parser.pipeline import parse_and_analyse_ies


def test_parse_and_analyse_computes_peak_and_report():
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 2 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4 5
"""
    res = parse_and_analyse_ies(text)
    assert res.derived is not None
    assert res.report is not None

    # scaled values max = 10 at (h=180, v=90)
    assert res.derived.peak_candela == 10.0
    assert res.derived.peak_location == (180.0, 90.0)

    summ = res.report.summary
    assert summ["errors"] == 0
    assert summ["info"] >= 1  # multiplier not 1 + ranges info
