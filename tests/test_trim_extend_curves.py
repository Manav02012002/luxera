from __future__ import annotations

from luxera.geometry.authoring import Arc2D, Line2D, chamfer_between_curves, extend_curve_to_intersection, fillet_between_curves, trim_curve_to_intersection


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


def test_fillet_and_chamfer_between_lines() -> None:
    a = Line2D((0.0, 0.0), (2.0, 0.0))
    b = Line2D((0.0, 0.0), (0.0, 2.0))
    fil = fillet_between_curves(a, b, 0.25)
    assert isinstance(fil, Arc2D)
    ch = chamfer_between_curves(a, b, 0.2)
    assert isinstance(ch, Line2D)


def test_fillet_between_line_and_arc() -> None:
    l = Line2D((0.0, 0.0), (3.0, 0.0))
    a = Arc2D(center=(3.0, 1.0), radius=1.0, start_deg=180.0, end_deg=360.0)
    fil = fillet_between_curves(l, a, 0.15)
    assert isinstance(fil, Arc2D)
