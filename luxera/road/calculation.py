"""
Luxera Road Lighting Calculation

Calculates road lighting per EN 13201 (Road Lighting).

Key metrics:
- Luminance (L): Brightness of road surface (cd/m²)
- Illuminance (E): Light level on road surface (lux)
- Uniformity (Uo, Ul): Distribution evenness
- Glare (TI): Threshold Increment for disability glare
- Surround Ratio (SR): Light on surroundings

Road Classes (EN 13201-2):
- M1-M6: Motorized traffic routes
- C0-C5: Conflict areas
- P1-P6: Pedestrian areas
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from enum import Enum, auto

from luxera.geometry.core import Vector3


class RoadClass(Enum):
    """EN 13201 road lighting classes."""
    M1 = auto()  # Highest - motorways
    M2 = auto()
    M3 = auto()
    M4 = auto()
    M5 = auto()
    M6 = auto()  # Lowest motorized
    C0 = auto()  # Conflict areas
    C1 = auto()
    C2 = auto()
    P1 = auto()  # Pedestrian highest
    P2 = auto()
    P3 = auto()
    P4 = auto()
    P5 = auto()
    P6 = auto()  # Pedestrian lowest


@dataclass
class RoadRequirements:
    """Lighting requirements for a road class."""
    road_class: RoadClass
    luminance_min: Optional[float] = None  # cd/m²
    illuminance_min: Optional[float] = None  # lux
    uniformity_overall: float = 0.4
    uniformity_longitudinal: float = 0.6
    glare_ti_max: float = 15  # %
    surround_ratio: float = 0.5


# EN 13201-2 Requirements
ROAD_REQUIREMENTS: Dict[RoadClass, RoadRequirements] = {
    RoadClass.M1: RoadRequirements(RoadClass.M1, luminance_min=2.0, uniformity_overall=0.4, uniformity_longitudinal=0.7, glare_ti_max=10),
    RoadClass.M2: RoadRequirements(RoadClass.M2, luminance_min=1.5, uniformity_overall=0.4, uniformity_longitudinal=0.7, glare_ti_max=10),
    RoadClass.M3: RoadRequirements(RoadClass.M3, luminance_min=1.0, uniformity_overall=0.4, uniformity_longitudinal=0.6, glare_ti_max=15),
    RoadClass.M4: RoadRequirements(RoadClass.M4, luminance_min=0.75, uniformity_overall=0.4, uniformity_longitudinal=0.6, glare_ti_max=15),
    RoadClass.M5: RoadRequirements(RoadClass.M5, luminance_min=0.5, uniformity_overall=0.35, uniformity_longitudinal=0.4, glare_ti_max=15),
    RoadClass.M6: RoadRequirements(RoadClass.M6, luminance_min=0.3, uniformity_overall=0.35, uniformity_longitudinal=0.4, glare_ti_max=15),
    RoadClass.P1: RoadRequirements(RoadClass.P1, illuminance_min=15, uniformity_overall=0.4),
    RoadClass.P2: RoadRequirements(RoadClass.P2, illuminance_min=10, uniformity_overall=0.4),
    RoadClass.P3: RoadRequirements(RoadClass.P3, illuminance_min=7.5, uniformity_overall=0.4),
    RoadClass.P4: RoadRequirements(RoadClass.P4, illuminance_min=5, uniformity_overall=0.4),
    RoadClass.P5: RoadRequirements(RoadClass.P5, illuminance_min=3, uniformity_overall=0.4),
    RoadClass.P6: RoadRequirements(RoadClass.P6, illuminance_min=2, uniformity_overall=0.4),
}


@dataclass
class RoadGeometry:
    """Road geometry for lighting calculation."""
    width: float  # Total carriageway width (m)
    num_lanes: int = 2
    lane_width: float = 3.5
    median_width: float = 0.0
    shoulder_width: float = 0.5
    surface_r_class: str = "R3"  # R1-R4, W1-W4


@dataclass
class StreetLight:
    """Street light pole and luminaire."""
    position: Vector3  # Base of pole
    mounting_height: float = 8.0
    arm_length: float = 1.5  # Overhang
    tilt_angle: float = 5.0  # degrees
    lumens: float = 10000
    ies_data: Optional[object] = None


@dataclass
class RoadLightingResult:
    """Road lighting calculation results."""
    avg_luminance: float  # cd/m²
    min_luminance: float
    max_luminance: float
    avg_illuminance: float  # lux
    min_illuminance: float
    uniformity_overall: float  # Uo = Lmin/Lavg
    uniformity_longitudinal: float  # Ul = Lmin/Lmax along lane
    threshold_increment: float  # TI %
    surround_ratio: float
    compliant: bool
    
    def summary(self) -> str:
        status = "COMPLIANT" if self.compliant else "NON-COMPLIANT"
        return (
            f"Road Lighting: {status}\n"
            f"  Luminance: {self.avg_luminance:.2f} cd/m² (avg)\n"
            f"  Illuminance: {self.avg_illuminance:.1f} lux (avg)\n"
            f"  Uo: {self.uniformity_overall:.2f}\n"
            f"  Ul: {self.uniformity_longitudinal:.2f}\n"
            f"  TI: {self.threshold_increment:.1f}%"
        )


def get_road_requirements(road_class: RoadClass) -> RoadRequirements:
    """Get lighting requirements for road class."""
    return ROAD_REQUIREMENTS.get(road_class, ROAD_REQUIREMENTS[RoadClass.M3])


def _calculate_illuminance_point(
    point: Vector3,
    lights: List[StreetLight]
) -> float:
    """Calculate illuminance at a road point."""
    total_E = 0.0
    
    for light in lights:
        # Light position (at mounting height, with arm overhang)
        light_pos = Vector3(
            light.position.x + light.arm_length,
            light.position.y,
            light.mounting_height
        )
        
        to_point = point - light_pos
        dist = to_point.length()
        if dist < 0.5:
            continue
        
        # Vertical angle from nadir
        cos_gamma = abs(to_point.z) / dist
        
        # Simple inverse square with cosine
        # Intensity assumed uniform for simplification
        I = light.lumens / (2 * math.pi)  # Approximate
        E = I * cos_gamma / (dist ** 2)
        
        total_E += E
    
    return total_E


def _calculate_luminance(
    illuminance: float,
    r_class: str = "R3",
    observer_angle: float = 1.0  # degrees
) -> float:
    """Convert illuminance to luminance using r-table."""
    # Simplified q0 values for R-classes
    q0_values = {"R1": 0.10, "R2": 0.07, "R3": 0.07, "R4": 0.08}
    q0 = q0_values.get(r_class, 0.07)
    
    return illuminance * q0


def calculate_road_lighting(
    road: RoadGeometry,
    lights: List[StreetLight],
    section_length: float = 100.0,  # m
    road_class: RoadClass = RoadClass.M3
) -> RoadLightingResult:
    """
    Calculate road lighting for a section.
    
    Grid: 10 points across width, points every 5m along length.
    """
    req = get_road_requirements(road_class)
    
    # Generate calculation grid
    points_across = 10
    spacing_along = 5.0
    
    illuminances = []
    luminances = []
    
    y = 0
    while y < section_length:
        x = 0
        while x < road.width:
            point = Vector3(x, y, 0)
            E = _calculate_illuminance_point(point, lights)
            L = _calculate_luminance(E, road.surface_r_class)
            illuminances.append(E)
            luminances.append(L)
            x += road.width / points_across
        y += spacing_along
    
    if not illuminances:
        return RoadLightingResult(
            avg_luminance=0, min_luminance=0, max_luminance=0,
            avg_illuminance=0, min_illuminance=0,
            uniformity_overall=0, uniformity_longitudinal=0,
            threshold_increment=0, surround_ratio=0, compliant=False
        )
    
    avg_L = sum(luminances) / len(luminances)
    min_L = min(luminances)
    max_L = max(luminances)
    avg_E = sum(illuminances) / len(illuminances)
    min_E = min(illuminances)
    
    Uo = min_L / avg_L if avg_L > 0 else 0
    Ul = min_L / max_L if max_L > 0 else 0
    
    # Simplified TI calculation
    TI = 15 * (1 - Uo) if Uo < 1 else 0
    
    # Check compliance
    compliant = True
    if req.luminance_min and avg_L < req.luminance_min:
        compliant = False
    if req.illuminance_min and avg_E < req.illuminance_min:
        compliant = False
    if Uo < req.uniformity_overall:
        compliant = False
    if TI > req.glare_ti_max:
        compliant = False
    
    return RoadLightingResult(
        avg_luminance=avg_L,
        min_luminance=min_L,
        max_luminance=max_L,
        avg_illuminance=avg_E,
        min_illuminance=min_E,
        uniformity_overall=Uo,
        uniformity_longitudinal=Ul,
        threshold_increment=TI,
        surround_ratio=0.5,
        compliant=compliant,
    )
