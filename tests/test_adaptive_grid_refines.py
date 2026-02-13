from __future__ import annotations

from luxera.calcs.adaptive_grid import refine_rect_grid


def test_adaptive_grid_refines_high_gradient_cells() -> None:
    nx, ny = 3, 3
    values = [
        0.0,
        0.0,
        0.0,
        0.0,
        100.0,
        100.0,
        0.0,
        100.0,
        100.0,
    ]
    pts = refine_rect_grid(origin=(0.0, 0.0), width=2.0, height=2.0, nx=nx, ny=ny, values=values, gradient_threshold=10.0)

    assert len(pts) > nx * ny
    assert (0.5, 0.5) in pts
    assert (1.5, 0.5) in pts
    assert all(0.0 <= x <= 2.0 and 0.0 <= y <= 2.0 for x, y in pts)
