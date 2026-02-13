from __future__ import annotations

import inspect
import re
from pathlib import Path

from luxera.geometry import cleaning, polygon2d, ray_config, spatial
from luxera.geometry.tolerance import (
    EPS_ANG,
    EPS_AREA,
    EPS_PLANE,
    EPS_POS,
    EPS_RAY_ORIGIN,
    EPS_WELD,
)


def test_tolerance_constants_exist() -> None:
    assert EPS_POS > 0.0
    assert EPS_ANG > 0.0
    assert EPS_AREA > 0.0
    assert EPS_PLANE > 0.0
    assert EPS_RAY_ORIGIN > 0.0
    assert EPS_WELD > 0.0


def test_key_geometry_functions_use_central_tolerance_defaults() -> None:
    assert inspect.signature(polygon2d.make_polygon_valid).parameters["snap_eps"].default == EPS_WELD
    assert inspect.signature(polygon2d.make_polygon_with_holes_valid).parameters["snap_eps"].default == EPS_WELD
    assert inspect.signature(cleaning.merge_vertices).parameters["eps"].default == EPS_WELD
    assert inspect.signature(cleaning.remove_degenerate_triangles).parameters["area_eps"].default == EPS_AREA
    assert ray_config.RAY_ORIGIN_EPS == EPS_RAY_ORIGIN
    assert ray_config.RAY_TMIN == EPS_RAY_ORIGIN * 0.1


def test_key_geometry_modules_reference_shared_tolerance_symbols() -> None:
    assert polygon2d.EPS_WELD == EPS_WELD
    assert polygon2d.EPS_POS == EPS_POS
    assert spatial.EPS_POS == EPS_POS
    assert cleaning.EPS_WELD == EPS_WELD
    assert cleaning.EPS_AREA == EPS_AREA


def test_geometry_package_has_no_inline_scientific_epsilon_literals() -> None:
    root = Path(__file__).resolve().parents[1] / "luxera" / "geometry"
    pattern = re.compile(r"\b1e-\d+\b")
    offenders: list[str] = []
    for p in sorted(root.rglob("*.py")):
        if p.name == "tolerance.py":
            continue
        text = p.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(p.relative_to(root.parent.parent)))
    assert offenders == []
