from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional, Tuple, Any

from luxera.geometry.core import Vector3
from luxera.core.transform import from_euler_zyx, from_aim_up
from luxera.core.types import Transform


SchemaVersion = Literal[1, 2, 3, 4]


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


@dataclass
class Geometry:
    rooms: List[RoomSpec] = field(default_factory=list)


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


@dataclass
class JobSpec:
    id: str
    type: Literal["direct", "radiosity"]
    backend: Literal["cpu"] = "cpu"
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
    schema_version: SchemaVersion = 4
    name: str = ""
    geometry: Geometry = field(default_factory=Geometry)
    materials: List[MaterialSpec] = field(default_factory=list)
    material_library: List[MaterialLibraryEntry] = field(default_factory=list)
    photometry_assets: List[PhotometryAsset] = field(default_factory=list)
    luminaire_families: List[LuminaireFamily] = field(default_factory=list)
    luminaires: List[LuminaireInstance] = field(default_factory=list)
    grids: List[CalcGrid] = field(default_factory=list)
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
