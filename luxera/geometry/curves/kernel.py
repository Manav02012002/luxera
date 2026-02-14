from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from luxera.geometry.curves.arc import Arc
from luxera.geometry.curves.intersections import Segment2D
from luxera.geometry.tolerance import EPS_POS


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class Line2D:
    a: Point2
    b: Point2

    def as_segment(self) -> Segment2D:
        return Segment2D((float(self.a[0]), float(self.a[1])), (float(self.b[0]), float(self.b[1])))

    def length(self) -> float:
        return math.hypot(float(self.b[0]) - float(self.a[0]), float(self.b[1]) - float(self.a[1]))


@dataclass(frozen=True)
class Arc2D:
    center: Point2
    radius: float
    start_deg: float
    end_deg: float
    ccw: bool = True

    @staticmethod
    def from_bulge(start: Point2, end: Point2, bulge: float) -> "Arc2D":
        a = Arc.from_bulge(start, end, bulge)
        return Arc2D(
            center=(float(a.center[0]), float(a.center[1])),
            radius=float(a.radius),
            start_deg=float(math.degrees(a.start_rad)),
            end_deg=float(math.degrees(a.end_rad)),
            ccw=bool(a.ccw),
        )

    def as_arc(self) -> Arc:
        return Arc(
            center=(float(self.center[0]), float(self.center[1])),
            radius=float(self.radius),
            start_rad=math.radians(float(self.start_deg)),
            end_rad=math.radians(float(self.end_deg)),
            ccw=bool(self.ccw),
        )

    def start_point(self) -> Point2:
        a = self.as_arc().start_point
        return (float(a[0]), float(a[1]))

    def end_point(self) -> Point2:
        a = self.as_arc().end_point
        return (float(a[0]), float(a[1]))


Curve2D = Union[Line2D, Arc2D]


@dataclass(frozen=True)
class PolyCurve2D:
    parts: List[Curve2D] = field(default_factory=list)
    closed: bool = False

    def __post_init__(self) -> None:
        if not self.parts:
            return
        pts: List[Tuple[Point2, Point2]] = []
        for p in self.parts:
            if isinstance(p, Line2D):
                pts.append((p.a, p.b))
            else:
                pts.append((p.start_point(), p.end_point()))
        for i in range(len(pts) - 1):
            a = pts[i][1]
            b = pts[i + 1][0]
            if math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1])) > 1e-5:
                raise ValueError("polycurve parts are not end-to-start continuous")
        if self.closed:
            a = pts[-1][1]
            b = pts[0][0]
            if math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1])) > 1e-5:
                raise ValueError("closed polycurve must connect end-to-start")

    def as_intersection_parts(self) -> List[Segment2D | Arc]:
        out: List[Segment2D | Arc] = []
        for p in self.parts:
            if isinstance(p, Line2D):
                out.append(p.as_segment())
            else:
                out.append(p.as_arc())
        return out


@dataclass(frozen=True)
class Spline2D:
    control_points: List[Point2]
    degree: int = 3
    knots: Optional[List[float]] = None
    weights: Optional[List[float]] = None
    closed: bool = False

    def __post_init__(self) -> None:
        n = len(self.control_points)
        if n < 2:
            raise ValueError("Spline2D needs at least 2 control points")
        p = int(self.degree)
        if p < 1:
            raise ValueError("Spline2D degree must be >= 1")
        if p >= n:
            raise ValueError("Spline2D degree must be < number of control points")
        if self.knots is not None and len(self.knots) != n + p + 1:
            raise ValueError("Spline2D knots length must be n_control + degree + 1")
        if self.weights is not None and len(self.weights) != n:
            raise ValueError("Spline2D weights length must equal control points length")

    def _knot_vector(self) -> List[float]:
        if self.knots is not None:
            return [float(x) for x in self.knots]
        n = len(self.control_points)
        p = int(self.degree)
        if self.closed:
            m = n + p + 1
            return [float(i) for i in range(m)]
        inner = n - p - 1
        out: List[float] = [0.0] * (p + 1)
        if inner > 0:
            step = 1.0 / float(inner + 1)
            out.extend([step * float(i + 1) for i in range(inner)])
        out.extend([1.0] * (p + 1))
        return out

    def _weighted_ctrl(self) -> List[Tuple[float, float, float]]:
        w = [1.0] * len(self.control_points) if self.weights is None else [float(x) for x in self.weights]
        out: List[Tuple[float, float, float]] = []
        for i, p in enumerate(self.control_points):
            ww = w[i]
            out.append((float(p[0]) * ww, float(p[1]) * ww, ww))
        return out

    @staticmethod
    def _find_span(u: float, p: int, U: Sequence[float], n_ctrl: int) -> int:
        n = n_ctrl - 1
        if u >= U[n + 1]:
            return n
        if u <= U[p]:
            return p
        lo, hi = p, n + 1
        mid = (lo + hi) // 2
        while u < U[mid] or u >= U[mid + 1]:
            if u < U[mid]:
                hi = mid
            else:
                lo = mid
            mid = (lo + hi) // 2
        return mid

    @staticmethod
    def _de_boor_homo(u: float, p: int, U: Sequence[float], Pw: Sequence[Tuple[float, float, float]]) -> Tuple[float, float, float]:
        k = Spline2D._find_span(u, p, U, len(Pw))
        d = [list(Pw[j + k - p]) for j in range(0, p + 1)]
        for r in range(1, p + 1):
            for j in range(p, r - 1, -1):
                i = j + k - p
                den = U[i + p - r + 1] - U[i]
                alpha = 0.0 if abs(den) <= EPS_POS else (u - U[i]) / den
                d[j][0] = (1.0 - alpha) * d[j - 1][0] + alpha * d[j][0]
                d[j][1] = (1.0 - alpha) * d[j - 1][1] + alpha * d[j][1]
                d[j][2] = (1.0 - alpha) * d[j - 1][2] + alpha * d[j][2]
        return (float(d[p][0]), float(d[p][1]), float(d[p][2]))

    def evaluate(self, u: float) -> Point2:
        U = self._knot_vector()
        p = int(self.degree)
        Pw = self._weighted_ctrl()
        u_min = U[p]
        u_max = U[len(self.control_points)]
        uu = min(max(float(u), float(u_min)), float(u_max))
        xw, yw, w = self._de_boor_homo(uu, p, U, Pw)
        if abs(w) <= EPS_POS:
            raise ValueError("Spline2D evaluation produced near-zero homogeneous weight")
        return (float(xw / w), float(yw / w))

    def to_polyline(self, samples_per_span: int = 16) -> List[Point2]:
        U = self._knot_vector()
        p = int(self.degree)
        u0 = float(U[p])
        u1 = float(U[len(self.control_points)])
        if u1 <= u0 + EPS_POS:
            return [(float(self.control_points[0][0]), float(self.control_points[0][1]))]
        steps = max(8, int(samples_per_span) * max(1, len(self.control_points) - p))
        out: List[Point2] = []
        for i in range(steps + 1):
            t = float(i) / float(steps)
            u = u0 + (u1 - u0) * t
            pt = self.evaluate(u)
            if not out or math.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) > EPS_POS:
                out.append(pt)
        if self.closed and out:
            p0 = out[0]
            if math.hypot(out[-1][0] - p0[0], out[-1][1] - p0[1]) > EPS_POS:
                out.append(p0)
        return out


def polycurve_from_mixed(parts: Sequence[Curve2D], *, closed: bool = False) -> PolyCurve2D:
    return PolyCurve2D(parts=[p for p in parts], closed=bool(closed))
