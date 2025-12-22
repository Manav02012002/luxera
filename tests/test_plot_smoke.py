from pathlib import Path

from luxera.parser.ies_parser import parse_ies_text
from luxera.plotting.plots import save_default_plots


def test_plot_smoke(tmp_path: Path):
    # H=2, V=3 => 6 candela values
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 2 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4 5
"""
    doc = parse_ies_text(text)
    paths = save_default_plots(doc, tmp_path, stem="smoke")
    assert paths.intensity_png.exists()
    assert paths.polar_png.exists()
    assert paths.intensity_png.stat().st_size > 0
    assert paths.polar_png.stat().st_size > 0
