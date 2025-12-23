"""
Luxera Emergency Lighting Module

Calculates and validates emergency lighting installations according to:
- EN 1838: Lighting applications - Emergency lighting
- EN 50172: Emergency escape lighting systems
- BS 5266-1: Emergency lighting

Emergency lighting categories:
1. Escape route lighting - illuminates paths to exits
2. Open area (anti-panic) lighting - prevents panic in large spaces
3. High risk task area lighting - enables safe shutdown of hazardous processes
4. Standby lighting - continues normal activities during power failure

Key requirements (EN 1838):
- Escape routes: ≥1 lux on centerline, 0.5 uniformity ratio
- Open areas: ≥0.5 lux at floor level
- Duration: minimum 1 hour, typically 3 hours
- Response time: 50% within 5 seconds, 100% within 60 seconds
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum, auto

from luxera.geometry.core import Vector3, Room, Polygon


# =============================================================================
# Emergency Lighting Types
# =============================================================================

class EmergencyLightType(Enum):
    """Types of emergency lighting."""
    ESCAPE_ROUTE = auto()      # Illuminates escape routes
    OPEN_AREA = auto()         # Anti-panic area lighting
    HIGH_RISK = auto()         # High-risk task areas
    STANDBY = auto()           # Maintains normal activities
    EXIT_SIGN = auto()         # Illuminated exit signs


class LuminaireType(Enum):
    """Types of emergency luminaires."""
    SELF_CONTAINED = auto()    # Battery in luminaire
    CENTRAL_BATTERY = auto()   # Central battery system
    GENERATOR = auto()         # Generator backup
    MAINTAINED = auto()        # Always on (with mains)
    NON_MAINTAINED = auto()    # Only on during emergency


# =============================================================================
# Emergency Luminaire
# =============================================================================

@dataclass
class EmergencyLuminaire:
    """
    An emergency luminaire with position and specifications.
    
    Attributes:
        position: Location (x, y, z) in meters
        emergency_lumens: Light output in emergency mode (lumens)
        beam_angle: Beam angle (degrees), for directional luminaires
        mounting_height: Height above floor (meters)
        luminaire_type: Self-contained, central battery, etc.
        duration_hours: Battery duration in hours
    """
    position: Vector3
    emergency_lumens: float
    mounting_height: float = 2.5
    beam_angle: float = 120.0  # Wide beam typical for emergency
    luminaire_type: LuminaireType = LuminaireType.SELF_CONTAINED
    duration_hours: float = 3.0
    is_exit_sign: bool = False
    
    def get_intensity_at_angle(self, angle_deg: float) -> float:
        """
        Get luminous intensity at given angle from nadir.
        
        Simplified cosine distribution for emergency luminaires.
        """
        if angle_deg > self.beam_angle / 2:
            return 0.0
        
        # Approximate intensity distribution
        # Total flux = π × I_peak for Lambertian
        # Adjusted for beam angle
        beam_rad = math.radians(self.beam_angle / 2)
        solid_angle = 2 * math.pi * (1 - math.cos(beam_rad))
        
        # Peak intensity
        I_peak = self.emergency_lumens / solid_angle
        
        # Cosine falloff
        angle_rad = math.radians(angle_deg)
        return I_peak * max(0, math.cos(angle_rad))


@dataclass
class ExitSign:
    """An illuminated exit sign."""
    position: Vector3
    direction: Vector3  # Direction the sign faces
    width: float = 0.4  # meters
    height: float = 0.2  # meters
    luminance: float = 500  # cd/m² (green on white)
    text: str = "EXIT"


# =============================================================================
# Escape Route
# =============================================================================

@dataclass
class EscapeRoute:
    """
    An escape route definition.
    
    Escape routes are paths from occupied areas to final exits.
    They must maintain minimum illuminance levels.
    """
    name: str
    centerline_points: List[Vector3]  # Points along route centerline
    width: float = 2.0  # Route width in meters
    
    @property
    def length(self) -> float:
        """Calculate total route length."""
        total = 0.0
        for i in range(len(self.centerline_points) - 1):
            p1 = self.centerline_points[i]
            p2 = self.centerline_points[i + 1]
            total += (p2 - p1).length()
        return total
    
    def get_sample_points(self, spacing: float = 1.0) -> List[Vector3]:
        """Generate sample points along centerline."""
        points = []
        
        for i in range(len(self.centerline_points) - 1):
            p1 = self.centerline_points[i]
            p2 = self.centerline_points[i + 1]
            
            segment_length = (p2 - p1).length()
            num_samples = max(1, int(segment_length / spacing))
            
            for j in range(num_samples):
                t = j / num_samples
                point = p1 + (p2 - p1) * t
                points.append(point)
        
        # Add final point
        if self.centerline_points:
            points.append(self.centerline_points[-1])
        
        return points


# =============================================================================
# Requirements
# =============================================================================

@dataclass
class EmergencyLightingRequirements:
    """Emergency lighting requirements based on standards."""
    
    # EN 1838 Escape Route Requirements
    escape_route_min_lux: float = 1.0  # Centerline minimum
    escape_route_uniformity: float = 40.0  # Max:Min ratio (inverse of normal Uo)
    
    # EN 1838 Open Area Requirements
    open_area_min_lux: float = 0.5  # Floor level minimum
    open_area_uniformity: float = 40.0  # Max:Min ratio
    
    # High Risk Task Area
    high_risk_min_lux: float = 10.0  # 10% of normal or 15 lux minimum
    high_risk_percentage: float = 0.10  # Minimum percentage of normal
    
    # Timing
    response_50_percent_seconds: float = 5.0
    response_100_percent_seconds: float = 60.0
    minimum_duration_hours: float = 1.0
    recommended_duration_hours: float = 3.0
    
    # Exit Signs
    exit_sign_viewing_distance: float = 30.0  # meters per 10cm height
    exit_sign_min_luminance: float = 2.0  # cd/m²


# =============================================================================
# Calculation Results
# =============================================================================

@dataclass
class EscapeRouteResult:
    """Results for an escape route calculation."""
    route: EscapeRoute
    sample_points: List[Vector3]
    illuminances: List[float]
    
    @property
    def min_lux(self) -> float:
        return min(self.illuminances) if self.illuminances else 0.0
    
    @property
    def max_lux(self) -> float:
        return max(self.illuminances) if self.illuminances else 0.0
    
    @property
    def avg_lux(self) -> float:
        return sum(self.illuminances) / len(self.illuminances) if self.illuminances else 0.0
    
    @property
    def uniformity_ratio(self) -> float:
        """Max:Min ratio (EN 1838 style)."""
        if self.min_lux < 0.001:
            return float('inf')
        return self.max_lux / self.min_lux
    
    def complies(self, req: EmergencyLightingRequirements = None) -> bool:
        """Check if route complies with requirements."""
        if req is None:
            req = EmergencyLightingRequirements()
        
        return (self.min_lux >= req.escape_route_min_lux and
                self.uniformity_ratio <= req.escape_route_uniformity)


@dataclass
class OpenAreaResult:
    """Results for an open area calculation."""
    area_name: str
    grid_points: List[Vector3]
    illuminances: List[float]
    area_m2: float
    
    @property
    def min_lux(self) -> float:
        return min(self.illuminances) if self.illuminances else 0.0
    
    @property
    def avg_lux(self) -> float:
        return sum(self.illuminances) / len(self.illuminances) if self.illuminances else 0.0
    
    def complies(self, req: EmergencyLightingRequirements = None) -> bool:
        """Check if area complies with requirements."""
        if req is None:
            req = EmergencyLightingRequirements()
        
        return self.min_lux >= req.open_area_min_lux


@dataclass
class EmergencyLightingResult:
    """Complete emergency lighting calculation results."""
    escape_routes: List[EscapeRouteResult] = field(default_factory=list)
    open_areas: List[OpenAreaResult] = field(default_factory=list)
    luminaires: List[EmergencyLuminaire] = field(default_factory=list)
    exit_signs: List[ExitSign] = field(default_factory=list)
    
    @property
    def all_routes_compliant(self) -> bool:
        return all(r.complies() for r in self.escape_routes)
    
    @property
    def all_areas_compliant(self) -> bool:
        return all(a.complies() for a in self.open_areas)
    
    @property
    def is_compliant(self) -> bool:
        return self.all_routes_compliant and self.all_areas_compliant
    
    def summary(self) -> str:
        """Generate summary text."""
        lines = [
            "Emergency Lighting Analysis Summary",
            "=" * 40,
            f"Total luminaires: {len(self.luminaires)}",
            f"Exit signs: {len(self.exit_signs)}",
            f"Escape routes: {len(self.escape_routes)}",
            f"Open areas: {len(self.open_areas)}",
            "",
        ]
        
        for route_result in self.escape_routes:
            status = "PASS" if route_result.complies() else "FAIL"
            lines.append(f"Route '{route_result.route.name}': {status}")
            lines.append(f"  Min: {route_result.min_lux:.2f} lux, "
                        f"Max: {route_result.max_lux:.2f} lux, "
                        f"Ratio: {route_result.uniformity_ratio:.1f}:1")
        
        for area_result in self.open_areas:
            status = "PASS" if area_result.complies() else "FAIL"
            lines.append(f"Area '{area_result.area_name}': {status}")
            lines.append(f"  Min: {area_result.min_lux:.2f} lux, "
                        f"Avg: {area_result.avg_lux:.2f} lux")
        
        overall = "COMPLIANT" if self.is_compliant else "NON-COMPLIANT"
        lines.append("")
        lines.append(f"Overall: {overall}")
        
        return "\n".join(lines)


# =============================================================================
# Calculation Engine
# =============================================================================

def calculate_emergency_illuminance(
    point: Vector3,
    luminaires: List[EmergencyLuminaire],
) -> float:
    """
    Calculate emergency illuminance at a point.
    
    Uses inverse square law with simple cosine distribution.
    """
    total_E = 0.0
    
    for lum in luminaires:
        # Vector from luminaire to point
        lum_pos = Vector3(lum.position.x, lum.position.y, lum.mounting_height)
        to_point = point - lum_pos
        distance = to_point.length()
        
        if distance < 0.1:
            continue
        
        # Angle from nadir
        cos_angle = -to_point.z / distance
        angle_deg = math.degrees(math.acos(max(-1, min(1, cos_angle))))
        
        # Get intensity at this angle
        intensity = lum.get_intensity_at_angle(angle_deg)
        
        # Illuminance at floor (assuming horizontal surface)
        E = intensity * abs(cos_angle) / (distance ** 2)
        total_E += E
    
    return total_E


def calculate_escape_route(
    route: EscapeRoute,
    luminaires: List[EmergencyLuminaire],
    sample_spacing: float = 1.0,
) -> EscapeRouteResult:
    """
    Calculate emergency lighting on an escape route.
    
    Args:
        route: Escape route definition
        luminaires: Emergency luminaires in the space
        sample_spacing: Distance between sample points (meters)
    
    Returns:
        EscapeRouteResult with illuminance values
    """
    sample_points = route.get_sample_points(sample_spacing)
    illuminances = []
    
    for point in sample_points:
        E = calculate_emergency_illuminance(point, luminaires)
        illuminances.append(E)
    
    return EscapeRouteResult(
        route=route,
        sample_points=sample_points,
        illuminances=illuminances,
    )


def calculate_open_area(
    area_name: str,
    room: Room,
    luminaires: List[EmergencyLuminaire],
    grid_spacing: float = 2.0,
) -> OpenAreaResult:
    """
    Calculate emergency lighting in an open area.
    
    Args:
        area_name: Name of the area
        room: Room geometry
        luminaires: Emergency luminaires
        grid_spacing: Grid spacing for calculation points
    
    Returns:
        OpenAreaResult with illuminance values
    """
    # Generate grid points
    bb_min, bb_max = room.get_bounding_box()
    
    grid_points = []
    illuminances = []
    
    x = bb_min.x + grid_spacing / 2
    while x < bb_max.x:
        y = bb_min.y + grid_spacing / 2
        while y < bb_max.y:
            point = Vector3(x, y, 0)  # Floor level
            
            # Check if inside room (simplified - assumes convex)
            floor_poly = Polygon(room.floor_vertices)
            if floor_poly.contains_point_2d(point):
                grid_points.append(point)
                E = calculate_emergency_illuminance(point, luminaires)
                illuminances.append(E)
            
            y += grid_spacing
        x += grid_spacing
    
    return OpenAreaResult(
        area_name=area_name,
        grid_points=grid_points,
        illuminances=illuminances,
        area_m2=room.floor_area,
    )


def suggest_luminaire_spacing(
    min_lux: float = 1.0,
    mounting_height: float = 2.5,
    luminaire_lumens: float = 200,
) -> float:
    """
    Suggest maximum spacing between emergency luminaires.
    
    Based on inverse square law and typical luminaire distributions.
    
    Args:
        min_lux: Minimum required illuminance (lux)
        mounting_height: Mounting height above floor (meters)
        luminaire_lumens: Emergency lumens per luminaire
    
    Returns:
        Recommended maximum spacing (meters)
    """
    # Simplified calculation
    # E = I × cos(θ) / d²
    # At 45° angle, cos(θ) ≈ 0.707, d ≈ h/cos(45°) ≈ 1.41h
    # Overlap needed at midpoint between luminaires
    
    # Approximate intensity
    I = luminaire_lumens / (2 * math.pi)  # Hemispherical distribution
    
    # Distance where E = min_lux
    d = math.sqrt(I * 0.707 / min_lux)
    
    # Spacing is approximately 2 × horizontal throw
    horizontal_throw = math.sqrt(d**2 - mounting_height**2) if d > mounting_height else 0
    
    # Conservative spacing
    max_spacing = horizontal_throw * 1.5
    
    return max(2.0, min(max_spacing, 15.0))


def create_escape_route_layout(
    route: EscapeRoute,
    mounting_height: float = 2.5,
    luminaire_lumens: float = 200,
    target_min_lux: float = 1.0,
) -> List[EmergencyLuminaire]:
    """
    Automatically place emergency luminaires along an escape route.
    
    Args:
        route: Escape route definition
        mounting_height: Luminaire mounting height
        luminaire_lumens: Lumens per luminaire in emergency mode
        target_min_lux: Target minimum illuminance
    
    Returns:
        List of positioned emergency luminaires
    """
    spacing = suggest_luminaire_spacing(
        target_min_lux, mounting_height, luminaire_lumens
    )
    
    luminaires = []
    
    # Place luminaires along route
    total_distance = 0.0
    last_luminaire_distance = -spacing / 2  # Start half-spacing before route
    
    for i in range(len(route.centerline_points) - 1):
        p1 = route.centerline_points[i]
        p2 = route.centerline_points[i + 1]
        segment = p2 - p1
        segment_length = segment.length()
        
        while total_distance + segment_length > last_luminaire_distance + spacing:
            # Position along this segment
            t = (last_luminaire_distance + spacing - total_distance) / segment_length
            if 0 <= t <= 1:
                pos = p1 + segment * t
                luminaire = EmergencyLuminaire(
                    position=Vector3(pos.x, pos.y, 0),
                    emergency_lumens=luminaire_lumens,
                    mounting_height=mounting_height,
                )
                luminaires.append(luminaire)
                last_luminaire_distance += spacing
            else:
                break
        
        total_distance += segment_length
    
    return luminaires
