from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal, Optional, Sequence, Tuple


MetricSet = List[str]


@dataclass(frozen=True)
class CalcObject:
    id: str
    name: str
    object_type: str
    evaluation_height_offset: float = 0.0
    metric_set: MetricSet = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "U1"])

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HorizontalGrid(CalcObject):
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_u: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    axis_v: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    width: float = 1.0
    height: float = 1.0
    rows: int = 2
    cols: int = 2
    object_type: str = "HorizontalGrid"
    clip_polygon_xy: Optional[List[Tuple[float, float]]] = None
    holes_xy: List[List[Tuple[float, float]]] = field(default_factory=list)


@dataclass(frozen=True)
class VerticalGrid(CalcObject):
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_u: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    axis_v: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    width: float = 1.0
    height: float = 1.0
    rows: int = 2
    cols: int = 2
    object_type: str = "VerticalGrid"


@dataclass(frozen=True)
class ArbitraryPlaneGrid(CalcObject):
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_u: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    axis_v: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    width: float = 1.0
    height: float = 1.0
    rows: int = 2
    cols: int = 2
    object_type: str = "ArbitraryPlaneGrid"


@dataclass(frozen=True)
class PointSet(CalcObject):
    points: List[Tuple[float, float, float]] = field(default_factory=list)
    object_type: str = "PointSet"


@dataclass(frozen=True)
class LineGrid(CalcObject):
    polyline: List[Tuple[float, float, float]] = field(default_factory=list)
    spacing: float = 0.5
    object_type: str = "LineGrid"


@dataclass(frozen=True)
class UGRView(CalcObject):
    observer: Tuple[float, float, float] = (0.0, 0.0, 1.2)
    view_direction: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    fov_deg: float = 90.0
    object_type: str = "UGRView"
    up_direction: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    near_clip: float = 0.1
    far_clip: float = 200.0


@dataclass(frozen=True)
class Viewpoint(CalcObject):
    position: Tuple[float, float, float] = (0.0, 0.0, 1.2)
    look_dir: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    up_dir: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    fov_deg: float = 90.0
    near_clip: float = 0.1
    far_clip: float = 200.0
    object_type: str = "Viewpoint"


@dataclass(frozen=True)
class RoadwayGrid(CalcObject):
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    lane_width: float = 3.5
    road_length: float = 40.0
    lanes: int = 1
    longitudinal_points: int = 10
    transverse_points_per_lane: int = 3
    observer_height_m: float = 1.5
    object_type: str = "RoadwayGrid"


def calc_object_from_dict(d: Dict[str, object]) -> CalcObject:
    t = str(d.get("object_type", ""))
    mapping = {
        "HorizontalGrid": HorizontalGrid,
        "VerticalGrid": VerticalGrid,
        "ArbitraryPlaneGrid": ArbitraryPlaneGrid,
        "PointSet": PointSet,
        "LineGrid": LineGrid,
        "UGRView": UGRView,
        "Viewpoint": Viewpoint,
        "RoadwayGrid": RoadwayGrid,
    }
    cls = mapping.get(t)
    if cls is None:
        raise ValueError(f"Unsupported calc object type: {t}")
    return cls(**d)  # type: ignore[arg-type]


def serialize_calc_objects(objs: Sequence[CalcObject]) -> List[Dict[str, object]]:
    return [o.to_dict() for o in objs]
