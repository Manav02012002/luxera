from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Union

from luxera.geometry.curves.arc import Arc
from luxera.geometry.curves.intersections import (
    Segment2D,
    arc_arc_intersections,
    segment_arc_intersections,
    segment_segment_intersections,
)


Point2 = Tuple[float, float]
CurvePart = Union[Segment2D, Arc]


@dataclass(frozen=True)
class PolyCurve:
    parts: List[CurvePart] = field(default_factory=list)

    def intersections(self, other: "PolyCurve") -> List[Point2]:
        out: List[Point2] = []
        for a in self.parts:
            for b in other.parts:
                pts: List[Point2]
                if isinstance(a, Segment2D) and isinstance(b, Segment2D):
                    pts = segment_segment_intersections(a, b)
                elif isinstance(a, Segment2D) and isinstance(b, Arc):
                    pts = segment_arc_intersections(a, b)
                elif isinstance(a, Arc) and isinstance(b, Segment2D):
                    pts = segment_arc_intersections(b, a)
                else:
                    pts = arc_arc_intersections(a, b)  # type: ignore[arg-type]
                for p in pts:
                    if p not in out:
                        out.append(p)
        return out


def polycurve_from_polyline(points: List[Point2], *, closed: bool = False) -> PolyCurve:
    if len(points) < 2:
        return PolyCurve(parts=[])
    parts: List[CurvePart] = []
    for i in range(len(points) - 1):
        parts.append(Segment2D(points[i], points[i + 1]))
    if closed:
        parts.append(Segment2D(points[-1], points[0]))
    return PolyCurve(parts=parts)
