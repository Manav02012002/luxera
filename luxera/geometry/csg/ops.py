from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from luxera.geometry.openings.subtract import UVPolygon, subtract_openings
from luxera.geometry.csg.tree import CSGExpr, CSGNode, SolidNode
from luxera.geometry.tolerance import EPS_AREA, EPS_POS


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class CSGError:
    code: str
    message: str


@dataclass(frozen=True)
class CSGResult:
    ok: bool
    solids: List[SolidNode] = field(default_factory=list)
    error: CSGError | None = None


@dataclass(frozen=True)
class ExtrusionSolid:
    profile: List[Point2]
    z0: float
    z1: float

    def to_solid_node(self) -> SolidNode:
        return SolidNode(
            kind="extrusion",
            params={
                "profile": [(float(x), float(y)) for x, y in self.profile],
                "z0": float(self.z0),
                "z1": float(self.z1),
            },
        )


def _solid_to_extrusion(s: SolidNode) -> ExtrusionSolid:
    if s.kind != "extrusion":
        raise ValueError(f"Unsupported solid kind: {s.kind}")
    profile_raw = list(s.params.get("profile", []))
    profile = [(float(p[0]), float(p[1])) for p in profile_raw]
    z0 = float(s.params.get("z0", 0.0))
    if "z1" in s.params:
        z1 = float(s.params["z1"])
    else:
        z1 = z0 + float(s.params.get("height", 0.0))
    if z1 < z0:
        z0, z1 = z1, z0
    return ExtrusionSolid(profile=profile, z0=z0, z1=z1)


def _poly_area(poly: Sequence[Point2]) -> float:
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def _extrusion_diff(a: ExtrusionSolid, b: ExtrusionSolid) -> CSGResult:
    if a.z1 - a.z0 <= EPS_POS:
        return CSGResult(ok=False, error=CSGError(code="degenerate_a", message="A extrusion has zero height"))
    if b.z1 - b.z0 <= EPS_POS:
        return CSGResult(ok=True, solids=[a.to_solid_node()])

    z_overlap = min(a.z1, b.z1) - max(a.z0, b.z0)
    if z_overlap <= EPS_POS:
        return CSGResult(ok=True, solids=[a.to_solid_node()])

    wall = UVPolygon(outer=list(a.profile))
    cut = subtract_openings(wall, [list(b.profile)])
    polys = [cut] if isinstance(cut, UVPolygon) else list(cut.polygons)
    if not polys:
        return CSGResult(ok=False, error=CSGError(code="empty", message="difference removes entire solid"))
    out: List[SolidNode] = []
    for poly in polys:
        if poly.holes:
            return CSGResult(
                ok=False,
                error=CSGError(code="unsupported_hole", message="difference produced holes not representable in v1 extrusion"),
            )
        ext = [(float(x), float(y)) for x, y in poly.outer]
        if len(ext) < 3 or abs(_poly_area(ext)) <= EPS_AREA:
            continue
        out.append(ExtrusionSolid(profile=ext, z0=a.z0, z1=a.z1).to_solid_node())
    if not out:
        return CSGResult(ok=False, error=CSGError(code="invalid", message="difference produced no valid solids"))
    return CSGResult(ok=True, solids=out)


def _extrusion_union(a: ExtrusionSolid, b: ExtrusionSolid) -> CSGResult:
    # V1 conservative: keep as separate solids when union cannot be represented as one extrusion.
    return CSGResult(ok=True, solids=[a.to_solid_node(), b.to_solid_node()])


def _extrusion_isect(a: ExtrusionSolid, b: ExtrusionSolid) -> CSGResult:
    z0 = max(a.z0, b.z0)
    z1 = min(a.z1, b.z1)
    if z1 - z0 <= EPS_POS:
        return CSGResult(ok=False, error=CSGError(code="empty", message="no Z overlap"))
    try:
        from shapely.geometry import Polygon  # type: ignore

        pa = Polygon(list(a.profile))
        pb = Polygon(list(b.profile))
        gi = pa.intersection(pb)
        if gi.is_empty:
            return CSGResult(ok=False, error=CSGError(code="empty", message="no XY overlap"))
        g = gi.geoms[0] if hasattr(gi, "geoms") else gi
        ext = [(float(x), float(y)) for x, y in list(g.exterior.coords)[:-1]]
        if len(ext) < 3 or abs(_poly_area(ext)) <= EPS_AREA:
            return CSGResult(ok=False, error=CSGError(code="invalid", message="invalid intersection profile"))
        return CSGResult(ok=True, solids=[ExtrusionSolid(profile=ext, z0=z0, z1=z1).to_solid_node()])
    except Exception:
        return CSGResult(ok=False, error=CSGError(code="backend_unavailable", message="2D boolean backend unavailable"))


def eval_csg(expr: CSGExpr) -> CSGResult:
    if isinstance(expr, SolidNode):
        return CSGResult(ok=True, solids=[expr])

    left = eval_csg(expr.A)
    if not left.ok:
        return left
    right = eval_csg(expr.B)
    if not right.ok:
        return right
    if len(left.solids) != 1 or len(right.solids) != 1:
        return CSGResult(ok=False, error=CSGError(code="unsupported", message="v1 supports binary ops on single solids"))

    a = _solid_to_extrusion(left.solids[0])
    b = _solid_to_extrusion(right.solids[0])
    if expr.op == "diff":
        return _extrusion_diff(a, b)
    if expr.op == "union":
        return _extrusion_union(a, b)
    if expr.op == "isect":
        return _extrusion_isect(a, b)
    return CSGResult(ok=False, error=CSGError(code="invalid_op", message=f"unsupported op: {expr.op}"))


def extrusion_node(profile: Sequence[Point2], *, z0: float = 0.0, height: float = 3.0) -> SolidNode:
    h = float(height)
    return SolidNode(
        kind="extrusion",
        params={
            "profile": [(float(x), float(y)) for x, y in profile],
            "z0": float(z0),
            "z1": float(z0 + h),
        },
    )
