from __future__ import annotations

from luxera.geometry.openings.subtract import MultiPolygon2D, UVPolygon, subtract_openings


def _poly_area(poly) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(0.5 * s)


def test_subtract_openings_multiple_and_near_edge() -> None:
    wall = UVPolygon(outer=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)])
    openings = [
        [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)],
        [(3.6, 0.0000001), (3.95, 0.0000001), (3.95, 0.8), (3.6, 0.8)],
    ]
    out = subtract_openings(wall, openings)
    polys = [out] if isinstance(out, UVPolygon) else list(out.polygons)

    assert isinstance(out, MultiPolygon2D)
    assert len(polys) >= 2
    total_area = sum(_poly_area(p.outer) for p in polys)
    expected = 12.0 - 1.0 - (0.35 * 0.7999999)
    assert abs(total_area - expected) < 1e-3
