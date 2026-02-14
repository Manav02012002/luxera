from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple


Point2 = Tuple[float, float]


@dataclass
class FootprintHoleParam:
    id: str
    polygon2d: List[Point2] = field(default_factory=list)
    vertex_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)


@dataclass
class FootprintParam:
    id: str
    polygon2d: List[Point2] = field(default_factory=list)
    # Stable authored IDs for outer ring vertices/edges.
    vertex_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    # Hole rings are authored entities with stable IDs.
    holes: List[FootprintHoleParam] = field(default_factory=list)
    # DXF bulge fidelity by edge ID (or fallback key "i:j").
    edge_bulges: Dict[str, float] = field(default_factory=dict)


@dataclass
class RoomParam:
    id: str
    footprint_id: str
    height: float
    wall_thickness: float = 0.2
    # Room-wide wall thickness policy.
    wall_thickness_policy: Literal["inside", "outside", "center"] = "center"
    wall_align_mode: Literal["inside", "outside", "center"] = "center"
    name: str = ""
    origin_z: float = 0.0
    floor_slab_thickness: float = 0.0
    ceiling_slab_thickness: float = 0.0
    floor_offset: float = 0.0
    ceiling_offset: float = 0.0
    polygon2d: List[Point2] = field(default_factory=list)


@dataclass
class WallParam:
    id: str
    room_id: str
    edge_ref: Tuple[int, int]
    edge_id: Optional[str] = None
    shared_edge_id: Optional[str] = None
    thickness: float = 0.2
    align_mode: Literal["inside", "outside", "center"] = "center"
    finish_thickness: float = 0.0
    height: Optional[float] = None
    name: str = ""


@dataclass
class SharedWallParam:
    id: str
    edge_geom: Tuple[Point2, Point2]
    room_a: str
    room_b: Optional[str] = None
    shared_edge_id: Optional[str] = None
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
    host_wall_id: Optional[str] = None
    anchor: float = 0.5
    anchor_mode: Literal[
        "from_start_distance",
        "from_end_distance",
        "center_at_fraction",
        "snap_to_nearest",
        "nearest_gridline_center",
        "equal_spacing",
    ] = "center_at_fraction"
    from_start_distance: Optional[float] = None
    from_end_distance: Optional[float] = None
    center_at_fraction: Optional[float] = None
    snap_to_nearest: bool = False
    gridline_spacing: Optional[float] = None
    spacing_group_id: Optional[str] = None
    width: float = 1.0
    height: float = 1.2
    sill: float = 0.9
    polygon2d: List[Point2] = field(default_factory=list)
    type: Literal["window", "door", "void"] = "window"
    glazing_material_id: Optional[str] = None
    visible_transmittance: Optional[float] = None


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
    holes2d: List[List[Point2]] = field(default_factory=list)
    rule_pack_id: Optional[str] = None


@dataclass
class InstanceParam:
    id: str
    symbol_id: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    room_id: Optional[str] = None


@dataclass
class ParamModel:
    footprints: List[FootprintParam] = field(default_factory=list)
    rooms: List[RoomParam] = field(default_factory=list)
    walls: List[WallParam] = field(default_factory=list)
    shared_walls: List[SharedWallParam] = field(default_factory=list)
    openings: List[OpeningParam] = field(default_factory=list)
    slabs: List[SlabParam] = field(default_factory=list)
    zones: List[ZoneParam] = field(default_factory=list)
    instances: List[InstanceParam] = field(default_factory=list)
