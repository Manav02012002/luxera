from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RoomContext:
    id: str
    name: str
    dims_m: Dict[str, float]
    materials: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class LuminaireContext:
    id: str
    name: str
    photometry_asset_id: str
    mounting_height_m: Optional[float]
    tilt_deg: float


@dataclass(frozen=True)
class CalcObjectContext:
    id: str
    kind: str
    metric_set: List[str] = field(default_factory=list)
    pass_fail: Optional[str] = None


@dataclass(frozen=True)
class ConstraintContext:
    target_lux: Optional[float] = None
    uniformity_min: Optional[float] = None
    ugr_max: Optional[float] = None
    max_fittings: Optional[int] = None
    max_spacing_m: Optional[float] = None
    budget: Optional[float] = None


@dataclass(frozen=True)
class ProjectContext:
    project_name: str
    rooms: List[RoomContext] = field(default_factory=list)
    luminaires: List[LuminaireContext] = field(default_factory=list)
    calc_objects: List[CalcObjectContext] = field(default_factory=list)
    constraints: ConstraintContext = field(default_factory=ConstraintContext)
    latest_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
