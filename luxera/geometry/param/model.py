from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple


Point2 = Tuple[float, float]


@dataclass
class FootprintParam:
    id: str
    polygon2d: List[Point2] = field(default_factory=list)


@dataclass
class RoomParam:
    id: str
    footprint_id: str
    height: float
    wall_thickness: float = 0.2
    wall_align_mode: Literal["inside", "outside", "center"] = "center"
    name: str = ""
    origin_z: float = 0.0
    polygon2d: List[Point2] = field(default_factory=list)


@dataclass
class WallParam:
    id: str
    room_id: str
    edge_ref: Tuple[int, int]
    thickness: float = 0.2
    align_mode: Literal["inside", "outside", "center"] = "center"
    height: Optional[float] = None
    name: str = ""


@dataclass
class SharedWallParam:
    id: str
    edge_geom: Tuple[Point2, Point2]
    room_a: str
    room_b: Optional[str] = None
    thickness: float = 0.2
    align_mode: Literal["inside", "outside", "center"] = "center"
    height: Optional[float] = None
    name: str = ""
    wall_material_side_a: Optional[str] = None
    wall_material_side_b: Optional[str] = None


@dataclass
class OpeningParam:
    id: str
    wall_id: str
    anchor: float = 0.5
    width: float = 1.0
    height: float = 1.2
    sill: float = 0.9
    type: Literal["window", "door", "void"] = "window"


@dataclass
class SlabParam:
    id: str
    room_id: str
    thickness: float = 0.2
    elevation: float = 0.0


@dataclass
class ZoneParam:
    id: str
    room_id: str
    polygon2d: List[Point2] = field(default_factory=list)
    rule_pack_id: Optional[str] = None


@dataclass
class ParamModel:
    footprints: List[FootprintParam] = field(default_factory=list)
    rooms: List[RoomParam] = field(default_factory=list)
    walls: List[WallParam] = field(default_factory=list)
    shared_walls: List[SharedWallParam] = field(default_factory=list)
    openings: List[OpeningParam] = field(default_factory=list)
    slabs: List[SlabParam] = field(default_factory=list)
    zones: List[ZoneParam] = field(default_factory=list)
