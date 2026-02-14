from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from luxera.geometry.curves.kernel import Arc2D
from luxera.geometry.polygon2d import validate_polygon_with_holes
from luxera.geometry.primitives import Polygon2D
from luxera.geometry.tolerance import EPS_POS


@dataclass(frozen=True)
class OffsetFailure:
    code: str
    message: str


@dataclass(frozen=True)
class OffsetResult:
    ok: bool
    polygon: Optional[Polygon2D] = None
    failure: Optional[OffsetFailure] = None


JoinStyle = Literal["miter", "round", "bevel"]


def offset_arc2d(arc: Arc2D, distance: float) -> Arc2D | OffsetFailure:
    r = float(arc.radius) + float(distance)
    if r <= EPS_POS:
        return OffsetFailure(code="degenerate_arc", message="offset arc radius became non-positive")
    return Arc2D(
        center=(float(arc.center[0]), float(arc.center[1])),
        radius=r,
        start_deg=float(arc.start_deg),
        end_deg=float(arc.end_deg),
        ccw=bool(arc.ccw),
    )


def offset_polygon_v2(
    polygon: Polygon2D,
    distance: float,
    *,
    join_style: JoinStyle = "miter",
    miter_limit: float = 5.0,
) -> OffsetResult:
    if abs(float(distance)) <= 0.0:
        return OffsetResult(ok=True, polygon=polygon)

    try:
        from shapely.geometry import Polygon  # type: ignore

        poly = Polygon(list(polygon.points))
        if not poly.is_valid:
            return OffsetResult(ok=False, failure=OffsetFailure(code="invalid_input", message="input polygon is invalid"))
        js = 2
        if join_style == "round":
            js = 1
        elif join_style == "bevel":
            js = 3
        off = poly.buffer(float(distance), join_style=js, mitre_limit=max(1.0, float(miter_limit)))
        if off.is_empty:
            return OffsetResult(ok=False, failure=OffsetFailure(code="empty", message="offset produced empty polygon"))
        if hasattr(off, "geoms"):
            geoms = list(off.geoms)
            if len(geoms) != 1:
                return OffsetResult(
                    ok=False,
                    failure=OffsetFailure(code="split", message="offset produced multiple disjoint polygons"),
                )
            off = geoms[0]
        if not hasattr(off, "exterior"):
            return OffsetResult(ok=False, failure=OffsetFailure(code="non_simple", message="offset produced non-polygon result"))
        pts = [(float(x), float(y)) for x, y in list(off.exterior.coords)[:-1]]
        if len(pts) < 3:
            return OffsetResult(ok=False, failure=OffsetFailure(code="degenerate", message="offset polygon has fewer than 3 points"))
        area = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            area += x1 * y2 - x2 * y1
        if abs(area) <= EPS_POS:
            return OffsetResult(ok=False, failure=OffsetFailure(code="degenerate", message="offset area is near zero"))
        rep = validate_polygon_with_holes(pts, ())
        if not rep.valid:
            return OffsetResult(ok=False, failure=OffsetFailure(code="invalid", message="offset polygon failed validity checks"))
        return OffsetResult(ok=True, polygon=Polygon2D(points=pts))
    except Exception:
        return OffsetResult(ok=False, failure=OffsetFailure(code="backend_unavailable", message="robust offset backend unavailable"))
