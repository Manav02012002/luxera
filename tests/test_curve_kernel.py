from __future__ import annotations

from luxera.geometry.curves.kernel import Arc2D, Line2D, PolyCurve2D, Spline2D


def test_curve_kernel_line_arc_polycurve_and_spline() -> None:
    l = Line2D((0.0, 0.0), (3.0, 0.0))
    assert l.length() == 3.0

    a = Arc2D.from_bulge((0.0, 0.0), (2.0, 0.0), bulge=0.5)
    assert a.radius > 0.0

    pc = PolyCurve2D(parts=[Line2D((0.0, 0.0), (1.0, 0.0)), Line2D((1.0, 0.0), (1.0, 1.0))])
    assert len(pc.parts) == 2
    assert len(pc.as_intersection_parts()) == 2

    sp = Spline2D(control_points=[(0.0, 0.0), (1.0, 1.0), (2.0, 0.0), (3.0, 1.0)])
    pts = sp.to_polyline(samples_per_span=8)
    assert len(pts) >= 8


def test_spline2d_exact_linear_and_rational_eval() -> None:
    s = Spline2D(
        control_points=[(0.0, 0.0), (2.0, 0.0)],
        degree=1,
        knots=[0.0, 0.0, 1.0, 1.0],
    )
    p = s.evaluate(0.25)
    assert abs(p[0] - 0.5) < 1e-9
    assert abs(p[1]) < 1e-9

    # Rational quadratic with middle control weighted pulls the curve upward.
    r = Spline2D(
        control_points=[(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)],
        degree=2,
        knots=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        weights=[1.0, 2.0, 1.0],
    )
    m = r.evaluate(0.5)
    assert m[1] > 0.5
