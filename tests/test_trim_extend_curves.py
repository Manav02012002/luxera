from __future__ import annotations

from luxera.geometry.authoring import Arc2D, Line2D, extend_curve_to_intersection, trim_curve_to_intersection


def test_trim_line_against_arc() -> None:
    line = Line2D((0.0, 0.0), (3.0, 0.0))
    arc = Arc2D(center=(1.5, 0.0), radius=1.0, start_deg=0.0, end_deg=180.0)
    out = trim_curve_to_intersection(line, arc)
    assert isinstance(out, Line2D)
    assert out.b[0] <= 2.5


def test_trim_arc_against_line() -> None:
    arc = Arc2D(center=(0.0, 0.0), radius=2.0, start_deg=0.0, end_deg=180.0)
    cutter = Line2D((0.0, -3.0), (0.0, 3.0))
    out = trim_curve_to_intersection(arc, cutter)
    assert isinstance(out, Arc2D)
    assert out.end_deg != arc.end_deg


def test_extend_curve_for_arc_uses_curve_intersection_logic() -> None:
    arc = Arc2D(center=(0.0, 0.0), radius=2.0, start_deg=0.0, end_deg=90.0)
    cutter = Line2D((-3.0, 0.0), (3.0, 0.0))
    out = extend_curve_to_intersection(arc, cutter)
    assert isinstance(out, Arc2D)
