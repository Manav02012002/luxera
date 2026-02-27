from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional, Tuple, Any

from luxera.geometry.core import Vector3
from luxera.geometry.param.model import ParamModel
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
    diffuse_reflectance_rgb: Optional[Tuple[float, float, float]] = None
    specular_reflectance: Optional[float] = None
    roughness: Optional[float] = None
    transmittance: float = 0.0
    maintenance_factor_placeholder: Optional[float] = None


@dataclass
class MaterialLibraryEntry:
    id: str
    name: str
    reflectance: float
    specularity: float = 0.0
    diffuse_reflectance_rgb: Optional[Tuple[float, float, float]] = None
    specular_reflectance: Optional[float] = None
    roughness: Optional[float] = None
    transmittance: float = 0.0


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
    layer_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)


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
    layer_id: Optional[str] = None
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    evaluation_height_offset: float = 0.0
    mask_near_openings: bool = False
    opening_mask_margin: float = 0.0
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "U1"])
    sample_points: List[Tuple[float, float, float]] = field(default_factory=list)
    sample_mask: List[bool] = field(default_factory=list)


@dataclass
class Geometry:
    rooms: List[RoomSpec] = field(default_factory=list)
    zones: List[ZoneSpec] = field(default_factory=list)
    no_go_zones: List[NoGoZoneSpec] = field(default_factory=list)
    surfaces: List[SurfaceSpec] = field(default_factory=list)
    openings: List[OpeningSpec] = field(default_factory=list)
    obstructions: List[ObstructionSpec] = field(default_factory=list)
    levels: List[LevelSpec] = field(default_factory=list)
    coordinate_systems: List[CoordinateSystemSpec] = field(default_factory=list)
    length_unit: Literal["m", "mm", "cm", "ft", "in"] = "m"
    scale_to_meters: float = 1.0
    source_length_unit: Optional[str] = None
    axis_transform_applied: Optional[str] = None


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
    layer_id: Optional[str] = None
    level_id: Optional[str] = None
    coordinate_system_id: Optional[str] = None
    footprint: Optional[List[Tuple[float, float]]] = None


@dataclass
class ZoneSpec:
    id: str
    name: str
    room_id: Optional[str] = None
    room_ids: List[str] = field(default_factory=list)
    polygon2d: Optional[List[Tuple[float, float]]] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class NoGoZoneSpec:
    id: str
    name: str
    room_id: Optional[str] = None
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    note: str = ""


@dataclass
class SurfaceSpec:
    id: str
    name: str
    kind: Literal["floor", "wall", "ceiling", "custom"] = "custom"
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    normal: Optional[Tuple[float, float, float]] = None
    room_id: Optional[str] = None
    material_id: Optional[str] = None
    layer: Optional[str] = None
    layer_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    two_sided: bool = True
    wall_room_side_a: Optional[str] = None
    wall_room_side_b: Optional[str] = None
    wall_material_side_a: Optional[str] = None
    wall_material_side_b: Optional[str] = None


@dataclass
class OpeningSpec:
    id: str
    name: str
    opening_type: Literal["window", "door", "void"] = "window"
    kind: Literal["window", "door", "void", "custom"] = "custom"
    layer_id: Optional[str] = None
    host_surface_id: Optional[str] = None
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    is_daylight_aperture: bool = False
    vt: Optional[float] = None
    frame_fraction: Optional[float] = None
    shade_factor: Optional[float] = None
    visible_transmittance: Optional[float] = None
    shading_factor: Optional[float] = None


@dataclass
class ObstructionSpec:
    id: str
    name: str
    kind: Literal["partition", "furniture", "column", "custom"] = "custom"
    layer_id: Optional[str] = None
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
    # `units` retained for backward compatibility with earlier schema payloads.
    units: Literal["m", "mm", "cm", "ft", "in"] = "m"
    length_unit: Literal["m", "mm", "cm", "ft", "in"] = "m"
    scale_to_meters: float = 1.0


@dataclass
class WorkplaneSpec:
    id: str
    name: str
    elevation: float
    margin: float
    spacing: float
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "U1"])


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
    host_surface_id: Optional[str] = None
    mask_openings: bool = True
    subrect_u0: Optional[float] = None
    subrect_u1: Optional[float] = None
    subrect_v0: Optional[float] = None
    subrect_v1: Optional[float] = None
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    offset_m: float = 0.0
    evaluation_height_offset: float = 0.0
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "U1"])


@dataclass
class ArbitraryPlaneSpec:
    id: str
    name: str
    origin: Tuple[float, float, float]
    axis_u: Tuple[float, float, float]
    axis_v: Tuple[float, float, float]
    width: float
    height: float
    nx: int
    ny: int
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    evaluation_height_offset: float = 0.0
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "U1"])


@dataclass
class PolygonWorkplaneSpec:
    id: str
    name: str
    origin: Tuple[float, float, float]
    axis_u: Tuple[float, float, float]
    axis_v: Tuple[float, float, float]
    polygon_uv: List[Tuple[float, float]] = field(default_factory=list)
    holes_uv: List[List[Tuple[float, float]]] = field(default_factory=list)
    sample_count: int = 64
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "U1"])


@dataclass
class PointSetSpec:
    id: str
    name: str
    points: List[Tuple[float, float, float]] = field(default_factory=list)
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "P50", "P90"])


@dataclass
class LineGridSpec:
    id: str
    name: str
    polyline: List[Tuple[float, float, float]] = field(default_factory=list)
    spacing: float = 0.5
    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0"])


@dataclass
class GlareViewSpec:
    id: str
    name: str
    observer: Tuple[float, float, float]
    view_dir: Tuple[float, float, float]
    fov_deg: float = 90.0
    room_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass
class RoadwaySpec:
    id: str
    name: str
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    num_lanes: int = 1
    lane_width: float = 3.5
    mounting_height_m: Optional[float] = None
    setback_m: Optional[float] = None
    pole_spacing_m: Optional[float] = None
    tilt_deg: Optional[float] = None
    aim_deg: Optional[float] = None


@dataclass
class RoadwayGridSpec:
    id: str
    name: str
    lane_width: float
    road_length: float
    nx: int
    ny: int
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    roadway_id: Optional[str] = None
    num_lanes: int = 1
    longitudinal_points: Optional[int] = None
    transverse_points_per_lane: Optional[int] = None
    pole_spacing_m: Optional[float] = None
    mounting_height_m: Optional[float] = None
    setback_m: Optional[float] = None
    observer_height_m: float = 1.5
    metric_set: List[str] = field(default_factory=lambda: ["E_avg", "E_min", "E_max", "U0", "UL", "L_avg"])


@dataclass
class ComplianceProfile:
    id: str
    name: str
    domain: Literal["indoor", "roadway", "emergency", "custom"] = "indoor"
    standard_ref: str = "EN 12464-1:2021"
    thresholds: Dict[str, float] = field(default_factory=dict)
    notes: str = ""


@dataclass
class LayerSpec:
    id: str
    name: str
    color: Optional[str] = None
    style: Optional[str] = None
    visible: bool = True
    order: int = 0


@dataclass
class Symbol2DSpec:
    id: str
    name: str
    anchor: Tuple[float, float] = (0.0, 0.0)
    default_rotation_deg: float = 0.0
    default_scale: float = 1.0
    layer_id: str = "symbol"
    tags: List[str] = field(default_factory=list)


@dataclass
class BlockInstanceSpec:
    id: str
    symbol_id: str
    position: Tuple[float, float] = (0.0, 0.0)
    rotation_deg: float = 0.0
    scale: float = 1.0
    layer_id: Optional[str] = None
    room_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class SelectionSetSpec:
    id: str
    name: str
    query: str = ""
    object_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class ProjectVariant:
    id: str
    name: str
    description: str = ""
    diff_ops: List[Dict[str, Any]] = field(default_factory=list)
    luminaire_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    dimming_schemes: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class DaylightAnnualSpec:
    weather_file: Optional[str] = None
    occupancy_schedule: str | List[float] = "office_8_to_18"
    grid_targets: List[str] = field(default_factory=list)
    annual_method_preference: Literal["matrix", "hourly_rtrace", "auto"] = "auto"
    sda_target_lux: float = 300.0
    sda_target_percent: float = 50.0
    ase_threshold_lux: float = 1000.0
    ase_hours_limit: float = 250.0
    udi_low: float = 100.0
    udi_high: float = 2000.0


@dataclass
class DaylightSpec:
    mode: Literal["df", "radiance", "annual"] = "df"
    sky: Literal["CIE_overcast", "CIE_clear", "CIE_intermediate"] = "CIE_overcast"
    external_horizontal_illuminance_lux: Optional[float] = None
    glass_visible_transmittance_default: float = 0.70
    surface_reflectance_override: Dict[str, float] = field(default_factory=dict)
    radiance_quality: Literal["draft", "normal", "high"] = "normal"
    random_seed: int = 0
    annual: Optional[DaylightAnnualSpec] = None


@dataclass
class EmergencyModeSpec:
    emergency_factor: float = 1.0
    include_luminaires: List[str] = field(default_factory=list)
    include_luminaire_ids: List[str] = field(default_factory=list)
    include_tags: List[str] = field(default_factory=list)
    include_tag: Optional[str] = None
    exclude_luminaires: List[str] = field(default_factory=list)


@dataclass
class EscapeRouteSpec:
    id: str
    polyline: List[Tuple[float, float, float]] = field(default_factory=list)
    width_m: float = 1.0
    height_m: float = 0.0
    spacing_m: float = 0.5
    end_margin_m: float = 0.0
    name: str = ""


@dataclass
class EmergencySpec:
    standard: Literal["EN1838", "BS5266"] = "EN1838"
    route_min_lux: float = 1.0
    route_u0_min: float = 0.1
    open_area_min_lux: float = 0.5
    open_area_u0_min: float = 0.1
    high_risk_min_lux: Optional[float] = None


@dataclass
class JobSpec:
    id: str
    type: Literal["direct", "radiosity", "roadway", "emergency", "daylight"]
    backend: Literal["cpu", "df", "radiance"] = "cpu"
    settings: Dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    daylight: Optional[DaylightSpec] = None
    targets: List[str] = field(default_factory=list)
    emergency: Optional[EmergencySpec] = None
    mode: Optional[EmergencyModeSpec] = None
    routes: List[str] = field(default_factory=list)
    open_area_targets: List[str] = field(default_factory=list)


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
    arbitrary_planes: List[ArbitraryPlaneSpec] = field(default_factory=list)
    polygon_workplanes: List[PolygonWorkplaneSpec] = field(default_factory=list)
    point_sets: List[PointSetSpec] = field(default_factory=list)
    line_grids: List[LineGridSpec] = field(default_factory=list)
    glare_views: List[GlareViewSpec] = field(default_factory=list)
    escape_routes: List[EscapeRouteSpec] = field(default_factory=list)
    roadways: List[RoadwaySpec] = field(default_factory=list)
    roadway_grids: List[RoadwayGridSpec] = field(default_factory=list)
    compliance_profiles: List[ComplianceProfile] = field(default_factory=list)
    symbols_2d: List[Symbol2DSpec] = field(default_factory=list)
    block_instances: List[BlockInstanceSpec] = field(default_factory=list)
    selection_sets: List[SelectionSetSpec] = field(default_factory=list)
    layers: List[LayerSpec] = field(
        default_factory=lambda: [
            LayerSpec(id="room", name="Rooms", visible=True, order=10),
            LayerSpec(id="wall", name="Walls", visible=True, order=20),
            LayerSpec(id="ceiling_grid", name="Ceiling Grid", visible=True, order=30),
            LayerSpec(id="opening", name="Openings", visible=True, order=40),
            LayerSpec(id="luminaire", name="Luminaires", visible=True, order=50),
            LayerSpec(id="grid", name="Calc Grids", visible=True, order=60),
            LayerSpec(id="symbol", name="Symbols", visible=True, order=70),
        ]
    )
    variants: List[ProjectVariant] = field(default_factory=list)
    active_variant_id: Optional[str] = None
    jobs: List[JobSpec] = field(default_factory=list)
    results: List[JobResultRef] = field(default_factory=list)
    root_dir: Optional[str] = None
    asset_bundle_path: Optional[str] = None
    agent_history: List[Dict[str, Any]] = field(default_factory=list)
    assistant_undo_stack: List[Dict[str, Any]] = field(default_factory=list)
    assistant_redo_stack: List[Dict[str, Any]] = field(default_factory=list)
    param: ParamModel = field(default_factory=ParamModel)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def matrix_to_array(m: List[List[float]]):
    import numpy as np
    return np.array(m, dtype=float)
