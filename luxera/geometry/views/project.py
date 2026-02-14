from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Sequence, Tuple

import numpy as np

from luxera.geometry.primitives import Polyline2D
from luxera.geometry.views.intersect import Polyline3D


Point2 = Tuple[float, float]
Basis = Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


@dataclass(frozen=True)
class DrawingPrimitive:
    type: Literal["line", "polyline", "arc", "text"]
    points: List[Point2] = field(default_factory=list)
    bulges: List[float] = field(default_factory=list)
    closed: bool = False
    layer: str = "0"
    style: str = "solid"
    depth: float = 0.0
    text: str = ""


def project_polyline_to_view(poly3d: Polyline3D, basis: Basis) -> Polyline2D:
    origin, u, v, _n = basis
    pts: List[Point2] = []
    for p in poly3d.points:
        d = np.asarray(p, dtype=float) - origin
        pts.append((float(np.dot(d, u)), float(np.dot(d, v))))
    return Polyline2D(points=pts)


def _polyline_depth(poly3d: Polyline3D, basis: Basis) -> float:
    origin, _u, _v, n = basis
    if not poly3d.points:
        return 0.0
    vals = [float(np.dot(np.asarray(p, dtype=float) - origin, n)) for p in poly3d.points]
    return float(sum(vals) / len(vals))


def polylines_to_primitives(
    polys3d: Sequence[Polyline3D],
    basis: Basis,
    *,
    layer: str = "CUT",
    style: str = "solid",
    by_layer: Dict[str, str] | None = None,
) -> List[DrawingPrimitive]:
    out: List[DrawingPrimitive] = []
    layer_map = by_layer or {}
    lay = layer_map.get(layer, layer)
    for p3 in polys3d:
        p2 = project_polyline_to_view(p3, basis)
        out.append(
            DrawingPrimitive(
                type="polyline",
                points=list(p2.points),
                layer=str(lay),
                style=str(style),
                depth=_polyline_depth(p3, basis),
            )
        )
    out.sort(key=lambda x: (x.layer, x.style, len(x.points), x.points[0] if x.points else (0.0, 0.0)))
    return out
