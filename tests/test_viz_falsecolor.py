from __future__ import annotations

from pathlib import Path

import numpy as np

from luxera.viz.contours import compute_contour_levels
from luxera.viz.falsecolor import render_falsecolor_plane


def test_contour_levels_numeric() -> None:
    arr = np.array([[1.0, 2.0], [3.0, 4.0]])
    levels = compute_contour_levels(arr, n_levels=4)
    assert levels == [1.0, 2.0, 3.0, 4.0]


def test_falsecolor_image_non_empty(tmp_path: Path) -> None:
    values = np.arange(12, dtype=float)
    out = render_falsecolor_plane(values=values, nx=4, ny=3, out_path=tmp_path / "false.png", with_contours=True)
    assert out.exists()
    assert out.stat().st_size > 0

