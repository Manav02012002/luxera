from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional, Tuple, Any

from luxera.geometry.core import Vector3
from luxera.core.transform import from_euler_zyx, from_aim_up
from luxera.core.types import Transform


SchemaVersion = Literal[1, 2, 3, 4, 5]


@dataclass
class RotationSpec:
    type: Literal["euler_zyx", "aim_up", "matrix"]
    euler_deg: Optional[Tuple[float, float, float]] = None  # yaw, pitch, roll
    aim: Optional[Tuple[float, float, float]] = None
    up: Optional[Tuple[float, float, float]] = None
    matrix: Optional[List[List[float]]] = None  # 3x3

    def to_transform(self, position: Tuple[float, float, float]) -> Transform:
        pos = Vector3(*position)
        if self.type == "euler_zyx":
            if self.euler_deg is None:
                raise ValueError("RotationSpec.euler_deg required for euler_zyx")
            yaw, pitch, roll = self.euler_deg
            return from_euler_zyx(pos, yaw, pitch, roll)
        if self.type == "aim_up":
            if self.aim is None or self.up is None:
                raise ValueError("RotationSpec.aim and RotationSpec.up required for aim_up")
            return from_aim_up(pos, Vector3(*self.aim), Vector3(*self.up))
        if self.type == "matrix":
            if self.matrix is None:
                raise ValueError("RotationSpec.matrix required for matrix")
            return Transform.from_rotation_matrix(pos, matrix_to_array(self.matrix))
        raise ValueError(f"Unsupported rotation type: {self.type}")


@dataclass
class TransformSpec:
    position: Tuple[float, float, float]
    rotation: RotationSpec

    def to_transform(self) -> Transform:
        return self.rotation.to_transform(self.position)


@dataclass
class MaterialSpec:
    id: str
    name: str
    reflectance: float
    specularity: float = 0.0
    reflectance_rgb: Optional[Tuple[float, float, float]] = None
    maintenance_factor_placeholder: Optional[float] = None


@dataclass
class MaterialLibraryEntry:
    id: str
    name: str
    reflectance: float
    specularity: float = 0.0


@dataclass
class PhotometryAsset:
    id: str
    format: Literal["IES", "LDT"]
    path: Optional[str] = None
    embedded_b64: Optional[str] = None
    content_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LuminaireFamily:
    id: str
    name: str
    photometry_asset_id: str
    default_tilt_deg: float = 0.0
    default_flux_multiplier: float = 1.0


@dataclass
class LuminaireInstance:
    id: str
    name: str
    photometry_asset_id: str
    transform: TransformSpec
    maintenance_factor: float = 1.0
    flux_multiplier: float = 1.0
    tilt_deg: float = 0.0
    family_id: Optional[str] = None
    mounting_type: Optional[str] = None
    mounting_height_m: Optional[float] = None


@dataclass
class CalcGrid:
    id: str
    name: str
    origin: Tuple[float, float, float]
    width: float
    height: float
    elevation: float
    nx: int
    ny: int
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    room_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass
class Geometry:
    rooms: List[RoomSpec] = field(default_factory=list)
    zones: List[ZoneSpec] = field(default_factory=list)
    surfaces: List[SurfaceSpec] = field(default_factory=list)
    openings: List[OpeningSpec] = field(default_factory=list)
    obstructions: List[ObstructionSpec] = field(default_factory=list)
    levels: List[LevelSpec] = field(default_factory=list)
    coordinate_systems: List[CoordinateSystemSpec] = field(default_factory=list)
    length_unit: Literal["m", "ft"] = "m"


@dataclass
class RoomSpec:
    id: str
    name: str
    width: float
    length: float
    height: float
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    floor_reflectance: float = 0.2
    wall_reflectance: float = 0.5
    ceiling_reflectance: float = 0.7
    activity_type: Optional[str] = None
    level_id: Optional[str] = None
    coordinate_system_id: Optional[str] = None


@dataclass
class ZoneSpec:
    id: str
    name: str
    room_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class SurfaceSpec:
    id: str
    name: str
    kind: Literal["floor", "wall", "ceiling", "custom"] = "custom"
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    normal: Optional[Tuple[float, float, float]] = None
    room_id: Optional[str] = None
    material_id: Optional[str] = None


@dataclass
class OpeningSpec:
    id: str
    name: str
    kind: Literal["window", "door", "void", "custom"] = "custom"
    host_surface_id: Optional[str] = None
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)


@dataclass
class ObstructionSpec:
    id: str
    name: str
    kind: Literal["partition", "furniture", "column", "custom"] = "custom"
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    height: Optional[float] = None


@dataclass
class LevelSpec:
    id: str
    name: str
    elevation: float


@dataclass
class CoordinateSystemSpec:
    id: str
    name: str
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: RotationSpec = field(default_factory=lambda: RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)))
    units: Literal["m", "ft"] = "m"


@dataclass
class WorkplaneSpec:
    id: str
    name: str
    elevation: float
    margin: float
    spacing: float
    room_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass
class VerticalPlaneSpec:
    id: str
    name: str
    origin: Tuple[float, float, float]
    width: float
    height: float
    nx: int
    ny: int
    azimuth_deg: float = 0.0
    room_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass
class PointSetSpec:
    id: str
    name: str
    points: List[Tuple[float, float, float]] = field(default_factory=list)
    room_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass
class GlareViewSpec:
    id: str
    name: str
    observer: Tuple[float, float, float]
    view_dir: Tuple[float, float, float]
    room_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass
class RoadwayGridSpec:
    id: str
    name: str
    lane_width: float
    road_length: float
    nx: int
    ny: int
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class ComplianceProfile:
    id: str
    name: str
    domain: Literal["indoor", "roadway", "emergency", "custom"] = "indoor"
    standard_ref: str = "EN 12464-1:2021"
    thresholds: Dict[str, float] = field(default_factory=dict)
    notes: str = ""


@dataclass
class ProjectVariant:
    id: str
    name: str
    description: str = ""
    luminaire_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    dimming_schemes: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class JobSpec:
    id: str
    type: Literal["direct", "radiosity", "roadway", "emergency", "daylight"]
    backend: Literal["cpu", "radiance"] = "cpu"
    settings: Dict[str, Any] = field(default_factory=dict)
    seed: int = 0


@dataclass
class JobResultRef:
    job_id: str
    job_hash: str
    result_dir: str
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
    schema_version: SchemaVersion = 5
    name: str = ""
    geometry: Geometry = field(default_factory=Geometry)
    materials: List[MaterialSpec] = field(default_factory=list)
    material_library: List[MaterialLibraryEntry] = field(default_factory=list)
    photometry_assets: List[PhotometryAsset] = field(default_factory=list)
    luminaire_families: List[LuminaireFamily] = field(default_factory=list)
    luminaires: List[LuminaireInstance] = field(default_factory=list)
    grids: List[CalcGrid] = field(default_factory=list)
    workplanes: List[WorkplaneSpec] = field(default_factory=list)
    vertical_planes: List[VerticalPlaneSpec] = field(default_factory=list)
    point_sets: List[PointSetSpec] = field(default_factory=list)
    glare_views: List[GlareViewSpec] = field(default_factory=list)
    roadway_grids: List[RoadwayGridSpec] = field(default_factory=list)
    compliance_profiles: List[ComplianceProfile] = field(default_factory=list)
    variants: List[ProjectVariant] = field(default_factory=list)
    active_variant_id: Optional[str] = None
    jobs: List[JobSpec] = field(default_factory=list)
    results: List[JobResultRef] = field(default_factory=list)
    root_dir: Optional[str] = None
    asset_bundle_path: Optional[str] = None
    agent_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def matrix_to_array(m: List[List[float]]):
    import numpy as np
    return np.array(m, dtype=float)
