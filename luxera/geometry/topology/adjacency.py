from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from luxera.geometry.param.model import RoomParam
from luxera.geometry.tolerance import EPS_WELD


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class SharedEdge:
    room_a: str
    edge_a: int
    room_b: str
    edge_b: int
    overlap_segment: Tuple[Point2, Point2]


def _sub(a: Point2, b: Point2) -> Point2:
    return (float(a[0] - b[0]), float(a[1] - b[1]))


def _dot(a: Point2, b: Point2) -> float:
    return float(a[0] * b[0] + a[1] * b[1])


def _cross(a: Point2, b: Point2) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _norm(a: Point2) -> float:
    return (_dot(a, a)) ** 0.5


def _edge(poly: List[Point2], i: int) -> Tuple[Point2, Point2]:
    return poly[i], poly[(i + 1) % len(poly)]


def _overlap_segment(a0: Point2, a1: Point2, b0: Point2, b1: Point2, tol: float) -> Tuple[Point2, Point2] | None:
    da = _sub(a1, a0)
    la = _norm(da)
    if la <= tol:
        return None
    ua = (da[0] / la, da[1] / la)
    # Collinearity check.
    if abs(_cross(da, _sub(b0, a0))) > tol * la:
        return None
    if abs(_cross(da, _sub(b1, a0))) > tol * la:
        return None

    t_a0 = 0.0
    t_a1 = la
    t_b0 = _dot(_sub(b0, a0), ua)
    t_b1 = _dot(_sub(b1, a0), ua)
    lo = max(min(t_a0, t_a1), min(t_b0, t_b1))
    hi = min(max(t_a0, t_a1), max(t_b0, t_b1))
    if hi - lo <= tol:
        return None
    p0 = (a0[0] + ua[0] * lo, a0[1] + ua[1] * lo)
    p1 = (a0[0] + ua[0] * hi, a0[1] + ua[1] * hi)
    return p0, p1


def find_shared_edges(rooms: list[RoomParam], tolerance: float = EPS_WELD) -> list[SharedEdge]:
    out: list[SharedEdge] = []
    for i in range(len(rooms)):
        ra = rooms[i]
        pa = [(float(x), float(y)) for x, y in ra.polygon2d]
        if len(pa) < 3:
            continue
        for j in range(i + 1, len(rooms)):
            rb = rooms[j]
            pb = [(float(x), float(y)) for x, y in rb.polygon2d]
            if len(pb) < 3:
                continue
            for ea in range(len(pa)):
                a0, a1 = _edge(pa, ea)
                da = _sub(a1, a0)
                if _norm(da) <= tolerance:
                    continue
                for eb in range(len(pb)):
                    b0, b1 = _edge(pb, eb)
                    db = _sub(b1, b0)
                    if _norm(db) <= tolerance:
                        continue
                    # Shared walls should be opposite-direction edges (tolerant).
                    if _dot(da, db) >= 0.0:
                        continue
                    ov = _overlap_segment(a0, a1, b0, b1, tolerance)
                    if ov is None:
                        continue
                    out.append(SharedEdge(room_a=ra.id, edge_a=ea, room_b=rb.id, edge_b=eb, overlap_segment=ov))
    return out

