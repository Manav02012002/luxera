from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Union

from luxera.geometry.curves.arc import Arc
from luxera.geometry.curves.intersections import Segment2D, polycurve_intersections


Point2 = Tuple[float, float]
CurvePart = Union[Segment2D, Arc]


@dataclass(frozen=True)
class PolyCurve:
    parts: List[CurvePart] = field(default_factory=list)

    def intersections(self, other: "PolyCurve") -> List[Point2]:
        return polycurve_intersections(self.parts, other.parts)


def polycurve_from_polyline(points: List[Point2], *, closed: bool = False) -> PolyCurve:
    if len(points) < 2:
        return PolyCurve(parts=[])
    parts: List[CurvePart] = []
    for i in range(len(points) - 1):
        parts.append(Segment2D(points[i], points[i + 1]))
    if closed:
        parts.append(Segment2D(points[-1], points[0]))
    return PolyCurve(parts=parts)
