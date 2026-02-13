from __future__ import annotations

from luxera.geometry.authoring import (
    Line2D,
    add_vertex,
    arc_from_bulge,
    drag_vertex,
    join_polylines,
    open_polyline_to_polygon,
    rectangle_tool,
    remove_vertex,
    split_segment,
    trim_line_to_intersection,
)
from luxera.geometry.primitives import Polyline2D


def test_polyline_vertex_editing_and_split() -> None:
    pl = Polyline2D(points=[(0.0, 0.0), (2.0, 0.0)])
    pl = add_vertex(pl, 1, (1.0, 0.0))
    assert len(pl.points) == 3
    pl = drag_vertex(pl, 1, (1.0, 1.0))
    assert pl.points[1] == (1.0, 1.0)
    pl = split_segment(pl, 0, 0.5)
    assert len(pl.points) == 4
    pl = remove_vertex(pl, 1)
    assert len(pl.points) == 3


def test_rectangle_join_polygon_and_arc() -> None:
    rect = rectangle_tool((0.0, 0.0), (2.0, 1.0))
    assert len(rect.points) == 4
    a = Polyline2D(points=[(0.0, 0.0), (1.0, 0.0)])
    b = Polyline2D(points=[(1.0, 0.0), (2.0, 0.0)])
    c = join_polylines(a, b)
    assert c.points[-1] == (2.0, 0.0)
    poly = open_polyline_to_polygon(Polyline2D(points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]))
    assert len(poly.points) == 3
    arc = arc_from_bulge((0.0, 0.0), (1.0, 0.0), bulge=0.5)
    assert arc.radius > 0.0


def test_trim_line_to_intersection() -> None:
    l1 = Line2D((0.0, 0.0), (2.0, 0.0))
    l2 = Line2D((1.0, -1.0), (1.0, 1.0))
    out = trim_line_to_intersection(l1, l2)
    assert out.b == (1.0, 0.0)

