from __future__ import annotations

from luxera.geometry.polygon2d import make_polygon_valid, validate_polygon_with_holes


def test_polygon_validity_detects_self_intersection() -> None:
    bowtie = [(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0)]
    report = validate_polygon_with_holes(bowtie)
    assert not report.valid
    assert report.self_intersections > 0


def test_make_polygon_valid_fixes_and_enforces_ccw() -> None:
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    fixed = make_polygon_valid(points)
    report = validate_polygon_with_holes(fixed)
    assert report.valid
    assert report.winding == "CCW"

