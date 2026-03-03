from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

from luxera.photometry.model import Photometry
from luxera.viz.falsecolour import FalseColourRenderer


matplotlib.use("Agg")


def _sample_photometry() -> Photometry:
    return Photometry(
        system="C",
        c_angles_deg=np.array([0.0, 90.0, 180.0, 270.0], dtype=float),
        gamma_angles_deg=np.array([0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0], dtype=float),
        candela=np.array(
            [
                [1200.0, 1150.0, 1000.0, 750.0, 400.0, 120.0, 0.0],
                [1000.0, 950.0, 820.0, 620.0, 360.0, 110.0, 0.0],
                [1200.0, 1150.0, 1000.0, 750.0, 400.0, 120.0, 0.0],
                [1000.0, 950.0, 820.0, 620.0, 360.0, 110.0, 0.0],
            ],
            dtype=float,
        ),
        luminous_flux_lm=3000.0,
        symmetry="NONE",
    )


def test_heatmap_creates_figure() -> None:
    vals = np.linspace(50.0, 500.0, 100, dtype=float).reshape(10, 10)
    r = FalseColourRenderer(colour_scale="viridis", vmin=0.0, vmax=600.0)
    fig = r.render_grid_heatmap(vals, (0.0, 0.0), 9.0, 9.0)
    assert fig is not None


def test_heatmap_save_png(tmp_path: Path) -> None:
    vals = np.linspace(10.0, 900.0, 100, dtype=float).reshape(10, 10)
    r = FalseColourRenderer(colour_scale="luxera", vmin=0.0, vmax=1000.0)
    fig = r.render_grid_heatmap(vals, (0.0, 0.0), 9.0, 9.0)
    out = tmp_path / "heatmap.png"
    r.save(fig, out)
    assert out.exists()
    assert out.stat().st_size > 5 * 1024


def test_isolux_with_levels() -> None:
    vals = np.linspace(100.0, 800.0, 100, dtype=float).reshape(10, 10)
    r = FalseColourRenderer(colour_scale="plasma", vmin=0.0, vmax=900.0)
    fig = r.render_isolux_contours(vals, (0.0, 0.0), 9.0, 9.0, levels=[150, 300, 450, 600, 750])
    assert fig is not None


def test_polar_plot_multiple_planes() -> None:
    r = FalseColourRenderer()
    fig = r.render_polar_candela(_sample_photometry(), planes=[0.0, 90.0, 180.0, 270.0])
    assert fig is not None


def test_room_3d_render() -> None:
    r = FalseColourRenderer(colour_scale="viridis", vmin=0.0, vmax=500.0)
    room_surfaces = [
        {"name": "floor", "illuminance": 320.0, "vertices": [(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)]},
        {"name": "ceiling", "illuminance": 120.0, "vertices": [(0, 0, 3), (0, 3, 3), (4, 3, 3), (4, 0, 3)]},
        {"name": "wall1", "illuminance": 220.0, "vertices": [(0, 0, 0), (0, 3, 0), (0, 3, 3), (0, 0, 3)]},
        {"name": "wall2", "illuminance": 200.0, "vertices": [(4, 0, 0), (4, 0, 3), (4, 3, 3), (4, 3, 0)]},
    ]
    lum_pos = [(1.0, 0.8, 2.9), (3.0, 0.8, 2.9), (1.0, 2.2, 2.9), (3.0, 2.2, 2.9)]
    fig = r.render_room_3d(room_surfaces, lum_pos)
    assert fig is not None


def test_custom_colourmap() -> None:
    cmap = FalseColourRenderer._custom_luxera_cmap()
    from matplotlib.colors import Colormap

    assert isinstance(cmap, Colormap)


def test_value_labels_on_small_grid() -> None:
    vals = np.arange(25, dtype=float).reshape(5, 5)
    r = FalseColourRenderer(colour_scale="viridis", vmin=0.0, vmax=25.0)
    fig = r.render_grid_heatmap(vals, (0.0, 0.0), 4.0, 4.0, show_values=True)
    assert fig is not None
