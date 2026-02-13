from pathlib import Path

from luxera.parser.ies_parser import parse_ies_text
from luxera.plotting.plots import _resolve_polar_plane_pairs, save_default_plots


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


def test_plot_smoke_with_horizontal_plane_selector(tmp_path: Path):
    text = """IESNA:LM-63-2002
TILT=NONE
1 16000 2 3 4 1 2 0.45 0.45 0.10
0 45 90
0 90 180 270
0 1 2
3 4 5
6 7 8
9 10 11
"""
    doc = parse_ies_text(text)
    paths = save_default_plots(doc, tmp_path, stem="plane", horizontal_plane_deg=90.0)
    assert paths.intensity_png.exists()
    assert paths.polar_png.exists()
    assert paths.intensity_png.stat().st_size > 0
    assert paths.polar_png.stat().st_size > 0


def test_polar_plane_pair_resolves_to_nearest_opposite():
    h = [10.0, 80.0, 190.0, 260.0]
    pairs = _resolve_polar_plane_pairs(h, horizontal_plane_deg=90.0)
    assert pairs == [(80.0, 260.0)]


def test_polar_plane_pair_defaults_to_standard_axes_when_present():
    h = [0.0, 90.0, 180.0, 270.0]
    pairs = _resolve_polar_plane_pairs(h, horizontal_plane_deg=None)
    assert pairs == [(0.0, 180.0), (90.0, 270.0)]
