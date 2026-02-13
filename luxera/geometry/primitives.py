from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Polyline2D:
    points: List[Tuple[float, float]]


@dataclass(frozen=True)
class Polygon2D:
    points: List[Tuple[float, float]]

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValueError("Polygon2D requires at least 3 points")


@dataclass(frozen=True)
class Arc2D:
    center: Tuple[float, float]
    radius: float
    start_deg: float
    end_deg: float


@dataclass(frozen=True)
class Circle2D:
    center: Tuple[float, float]
    radius: float


@dataclass(frozen=True)
class RoomFootprint2D:
    outer: Polygon2D
    holes: List[Polygon2D] = field(default_factory=list)


@dataclass(frozen=True)
class Opening2D:
    id: str
    kind: str
    polygon: Polygon2D


@dataclass(frozen=True)
class Extrusion:
    profile2d: Polygon2D
    height: float
    cap_top: bool = True
    cap_bottom: bool = True
    holes: List[Polygon2D] = field(default_factory=list)
    # Optional semantic reference ids for generated surfaces.
    surface_ids: Optional[List[str]] = None
