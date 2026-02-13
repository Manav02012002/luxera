from __future__ import annotations

import math

from luxera.geometry.curves.arc import Arc


def test_arc_from_bulge_nearest_point_and_segment_intersection() -> None:
    arc = Arc.from_bulge((0.0, 0.0), (2.0, 0.0), bulge=1.0)
    assert arc.radius > 0.0

    q = arc.nearest_point((1.0, 2.0))
    # Returned point should lie on arc circle and on angular span.
    dq = math.hypot(q[0] - arc.center[0], q[1] - arc.center[1])
    assert abs(dq - arc.radius) < 1e-6
    assert arc.contains_angle(math.atan2(q[1] - arc.center[1], q[0] - arc.center[0]))

    hits = arc.intersections_with_line_segment((1.0, -1.0), (1.0, 2.0))
    assert hits
    assert any(abs(h[0] - 1.0) < 1e-6 for h in hits)


def test_arc_arc_intersections() -> None:
    a = Arc(center=(0.0, 0.0), radius=2.0, start_rad=0.0, end_rad=math.pi, ccw=True)
    b = Arc(center=(1.0, 0.0), radius=2.0, start_rad=math.pi, end_rad=0.0, ccw=False)
    hits = a.intersections_with_arc(b)
    assert hits
