from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

import pytest

from luxera.geometry.curves.arc import Arc
from luxera.geometry.curves.offset import offset_polygon_v2
from luxera.geometry.primitives import Polygon2D
from luxera.io.dxf_roundtrip import load_roundtrip_dxf


Point2 = Tuple[float, float]


def _sample_bulge_poly(vertices: List[Point2], bulges: List[float], closed: bool) -> List[Point2]:
    if not vertices:
        return []
    out: List[Point2] = []
    n = len(vertices)
    seg_count = n if closed else n - 1
    for i in range(seg_count):
        a = vertices[i]
        b = vertices[(i + 1) % n]
        bulge = float(bulges[i]) if i < len(bulges) else 0.0
        if abs(bulge) <= 1e-12:
            pts = [a, b]
        else:
            arc = Arc.from_bulge(a, b, bulge)
            sweep = max(arc.sweep(), 1e-9)
            arc_len = abs(float(arc.radius) * sweep)
            steps = max(6, int(math.ceil(arc_len / 0.15)))
            pts = [arc.point_at(j / float(steps)) for j in range(steps + 1)]
        if not out:
            out.extend((float(x), float(y)) for x, y in pts)
        else:
            out.extend((float(x), float(y)) for x, y in pts[1:])
    if closed and out and out[0] == out[-1]:
        out.pop()
    return out


def _curved_corridor_dxf() -> str:
    # Closed LWPOLYLINE with two bulged curved end segments.
    return """0
SECTION
2
ENTITIES
0
LWPOLYLINE
8
WALL
90
8
70
1
10
0
20
0
42
0
10
8
20
0
42
0.5
10
10
20
2
42
0
10
10
20
8
42
0
10
8
20
10
42
0.5
10
0
20
10
42
0
10
-2
20
8
42
0
10
-2
20
2
42
0
0
ENDSEC
0
EOF
"""


def test_gate_curved_corridor_dxf_offset_is_valid(tmp_path: Path) -> None:
    src = tmp_path / "curved_corridor.dxf"
    src.write_text(_curved_corridor_dxf(), encoding="utf-8")
    doc = load_roundtrip_dxf(src)
    assert doc.polylines
    poly = doc.polylines[0]
    pts = _sample_bulge_poly(poly.vertices, poly.bulges, poly.closed)
    assert len(pts) >= 8
    outline = Polygon2D(points=pts)

    outer = offset_polygon_v2(outline, 0.2, join_style="round")
    if not outer.ok and outer.failure and outer.failure.code == "backend_unavailable":
        pytest.skip("robust offset backend unavailable")
    assert outer.ok and outer.polygon is not None

    inner = offset_polygon_v2(outline, -0.2, join_style="round")
    assert inner.ok and inner.polygon is not None
