from __future__ import annotations

from luxera.geometry.curves.arc import Arc
from luxera.geometry.curves.intersections import Segment2D, arc_arc_intersections, segment_arc_intersections, segment_segment_intersections
from luxera.geometry.curves.polycurve import PolyCurve


def test_segment_segment_arc_and_arc_arc_intersections() -> None:
    s1 = Segment2D((0.0, 0.0), (2.0, 0.0))
    s2 = Segment2D((1.0, -1.0), (1.0, 1.0))
    hits_ss = segment_segment_intersections(s1, s2)
    assert hits_ss == [(1.0, 0.0)]

    arc = Arc.from_bulge((0.0, 0.0), (2.0, 0.0), bulge=1.0)
    hits_sa = segment_arc_intersections(s2, arc)
    assert hits_sa

    a2 = Arc(center=(1.0, 0.0), radius=2.0, start_rad=3.141592653589793, end_rad=0.0, ccw=False)
    hits_aa = arc_arc_intersections(Arc(center=(0.0, 0.0), radius=2.0, start_rad=0.0, end_rad=3.141592653589793, ccw=True), a2)
    assert hits_aa


def test_polycurve_intersections_mixed_parts() -> None:
    p1 = PolyCurve(parts=[Segment2D((0.0, 0.0), (2.0, 0.0)), Arc.from_bulge((2.0, 0.0), (4.0, 0.0), bulge=0.5)])
    p2 = PolyCurve(parts=[Segment2D((1.0, -1.0), (1.0, 1.0))])
    hits = p1.intersections(p2)
    assert hits
