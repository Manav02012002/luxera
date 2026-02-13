from __future__ import annotations

from luxera.geometry.views.hiddenline import depth_sort_primitives
from luxera.geometry.views.project import DrawingPrimitive


def test_hiddenline_depth_sort_back_to_front() -> None:
    a = DrawingPrimitive(type="polyline", points=[(0.0, 0.0), (1.0, 0.0)], layer="CUT", style="solid", depth=1.0)
    b = DrawingPrimitive(type="polyline", points=[(0.0, 1.0), (1.0, 1.0)], layer="CUT", style="solid", depth=5.0)
    out = depth_sort_primitives([a, b], back_to_front=True)
    assert out[0].depth == 5.0
    assert out[1].depth == 1.0
