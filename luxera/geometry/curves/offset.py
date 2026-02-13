from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from luxera.geometry.polygon2d import validate_polygon_with_holes
from luxera.geometry.primitives import Polygon2D


@dataclass(frozen=True)
class OffsetFailure:
    code: str
    message: str


@dataclass(frozen=True)
class OffsetResult:
    ok: bool
    polygon: Optional[Polygon2D] = None
    failure: Optional[OffsetFailure] = None


def offset_polygon_v2(polygon: Polygon2D, distance: float) -> OffsetResult:
    if abs(float(distance)) <= 0.0:
        return OffsetResult(ok=True, polygon=polygon)

    try:
        from shapely.geometry import Polygon  # type: ignore

        poly = Polygon(list(polygon.points))
        off = poly.buffer(float(distance), join_style=2)
        if off.is_empty:
            return OffsetResult(ok=False, failure=OffsetFailure(code="empty", message="offset produced empty polygon"))
        if not hasattr(off, "exterior"):
            return OffsetResult(ok=False, failure=OffsetFailure(code="non_simple", message="offset produced non-polygon result"))
        pts = [(float(x), float(y)) for x, y in list(off.exterior.coords)[:-1]]
        if len(pts) < 3:
            return OffsetResult(ok=False, failure=OffsetFailure(code="degenerate", message="offset polygon has fewer than 3 points"))
        rep = validate_polygon_with_holes(pts, ())
        if not rep.valid:
            return OffsetResult(ok=False, failure=OffsetFailure(code="invalid", message="offset polygon failed validity checks"))
        return OffsetResult(ok=True, polygon=Polygon2D(points=pts))
    except Exception:
        return OffsetResult(ok=False, failure=OffsetFailure(code="backend_unavailable", message="robust offset backend unavailable"))
