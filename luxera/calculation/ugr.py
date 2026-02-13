"""
Luxera UGR (Unified Glare Rating) Calculation Module

Calculates the Unified Glare Rating according to CIE 117:1995 and
EN 12464-1. UGR is the standard metric for evaluating discomfort
glare from luminaires in indoor lighting installations.

The UGR formula:
    UGR = 8 × log₁₀ [ (0.25/Lb) × Σ(L²ω/p²) ]

Where:
    Lb = Background luminance (cd/m²)
    L = Luminance of luminous parts of luminaire in observer direction (cd/m²)
    ω = Solid angle subtended by luminous parts (sr)
    p = Guth position index (accounts for luminaire position in field of view)

Standard UGR limits (EN 12464-1):
    - Offices, schools: 19
    - Industrial fine work: 16
    - Corridors: 25
    - Technical drawing: 16

Reference positions:
    UGR is typically calculated at seated (1.2m) and standing (1.7m) eye heights,
    looking in directions parallel to the main axis of the room.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
import numpy as np

from luxera.geometry.core import Vector3, Room
from luxera.geometry.bvh import BVHNode, any_hit, build_bvh, triangulate_surfaces
from luxera.geometry.ray_config import scaled_ray_policy


@dataclass
class LuminaireForUGR:
    """
    Luminaire data required for UGR calculation.
    
    Attributes:
        position: Luminaire center position (x, y, z) in meters
        luminous_area: Area of luminous surface (m²)
        luminance: Average luminance in observer direction (cd/m²)
        width: Luminaire width (m)
        length: Luminaire length (m)
    """
    position: Vector3
    luminous_area: float
    luminance: float  # cd/m²
    width: float = 0.6
    length: float = 0.6
    
    @staticmethod
    def from_ies_and_position(
        position: Vector3,
        ies_candela_at_angle: float,
        luminous_width: float,
        luminous_length: float,
    ) -> 'LuminaireForUGR':
        """
        Create from IES data and position.
        
        Args:
            position: Luminaire position
            ies_candela_at_angle: Candela in the viewing direction
            luminous_width: Width of luminous area (m)
            luminous_length: Length of luminous area (m)
        """
        area = luminous_width * luminous_length
        # Luminance = Intensity / (Area × cos(θ))
        # For direct view (θ ≈ 0), L = I / A
        luminance = ies_candela_at_angle / area if area > 0 else 0
        
        return LuminaireForUGR(
            position=position,
            luminous_area=area,
            luminance=luminance,
            width=luminous_width,
            length=luminous_length,
        )


@dataclass
class UGRObserverPosition:
    """
    Observer position for UGR calculation.
    
    Standard positions per EN 12464-1:
    - Seated: 1.2m eye height
    - Standing: 1.7m eye height
    - View direction: Along main room axis
    """
    eye_position: Vector3
    view_direction: Vector3  # Unit vector
    name: str = "Observer"
    
    def __post_init__(self):
        # Normalize view direction
        length = self.view_direction.length()
        if length > 0:
            self.view_direction = self.view_direction / length


@dataclass
class UGRResult:
    """Result of UGR calculation at one observer position."""
    observer: UGRObserverPosition
    ugr_value: float
    background_luminance: float  # cd/m²
    luminaire_contributions: List[Tuple[int, float]]  # (luminaire_index, contribution)
    
    @property
    def ugr_class(self) -> int:
        """
        Get UGR class (rounded to standard values).
        
        Standard UGR values: 10, 13, 16, 19, 22, 25, 28
        """
        if self.ugr_value <= 10:
            return 10
        elif self.ugr_value <= 13:
            return 13
        elif self.ugr_value <= 16:
            return 16
        elif self.ugr_value <= 19:
            return 19
        elif self.ugr_value <= 22:
            return 22
        elif self.ugr_value <= 25:
            return 25
        else:
            return 28
    
    def complies_with(self, ugr_limit: float) -> bool:
        """Check if UGR is within limit."""
        return self.ugr_value <= ugr_limit


@dataclass
class UGRAnalysis:
    """Complete UGR analysis for a room."""
    room_name: str
    results: List[UGRResult]
    max_ugr: float
    min_ugr: float
    positions_analyzed: int
    
    @property
    def worst_case_ugr(self) -> float:
        """Get worst case (highest) UGR value."""
        return self.max_ugr
    
    @property
    def representative_ugr(self) -> float:
        """
        Get representative UGR (average of worst 25% of positions).
        This is sometimes used for reporting.
        """
        if not self.results:
            return 0.0
        
        sorted_results = sorted(self.results, key=lambda r: r.ugr_value, reverse=True)
        n = max(1, len(sorted_results) // 4)
        return sum(r.ugr_value for r in sorted_results[:n]) / n
    
    def complies_with(self, ugr_limit: float) -> bool:
        """Check if all positions comply with limit."""
        return all(r.complies_with(ugr_limit) for r in self.results)


# =============================================================================
# Guth Position Index
# =============================================================================

def calculate_guth_position_index(
    H: float,  # Vertical angle from line of sight (degrees)
    T: float,  # Horizontal angle from line of sight (degrees)
) -> float:
    """
    Calculate Guth position index.
    
    The position index accounts for the position of a glare source
    in the observer's field of view. Sources directly in front have
    higher glare potential than those to the side.
    
    Based on CIE 117:1995 formulation.
    
    Args:
        H: Vertical angle above horizontal line of sight (degrees)
        T: Horizontal angle from line of sight (degrees)
    
    Returns:
        Position index p (dimensionless)
    """
    # Convert to radians
    H_rad = math.radians(abs(H))
    T_rad = math.radians(abs(T))
    
    # Guth position index formula
    # p = exp[(35.2 - 0.31889T - 1.22e^(-T/9)) × 10^(-3) × (H + σ)]
    # where σ is a factor depending on T
    
    # Simplified version commonly used:
    if T < 0.1:
        T = 0.1  # Avoid division issues
    
    # Position index (simplified Guth formula)
    sigma = 1.0 + 0.5 * T_rad
    exponent = (35.2 - 0.31889 * abs(T) - 1.22 * math.exp(-abs(T) / 9)) * 1e-3 * (abs(H) + sigma)
    
    p = math.exp(exponent)
    
    # Clamp to reasonable range
    return max(1.0, min(p, 100.0))


def calculate_solid_angle(
    luminaire: LuminaireForUGR,
    observer_pos: Vector3,
) -> float:
    """
    Calculate solid angle subtended by luminaire at observer position.
    
    For a rectangular luminaire:
        ω ≈ A × cos(θ) / d²
    
    Where A is luminaire area, θ is angle from luminaire normal,
    d is distance.
    
    Args:
        luminaire: Luminaire data
        observer_pos: Observer eye position
    
    Returns:
        Solid angle in steradians
    """
    # Vector from observer to luminaire
    to_lum = luminaire.position - observer_pos
    distance = to_lum.length()
    
    if distance < 0.1:
        return 0.0  # Too close
    
    # Assume luminaire faces down (typical for ceiling mounted)
    # Angle from luminaire normal to observer direction
    lum_normal = Vector3(0, 0, -1)  # Pointing down
    cos_theta = abs(to_lum.normalize().dot(lum_normal))
    
    # Solid angle
    omega = (luminaire.luminous_area * cos_theta) / (distance ** 2)
    
    return max(0.0, omega)


# =============================================================================
# UGR Calculation
# =============================================================================

def calculate_background_luminance(
    room: Room,
    total_luminaire_flux: float,
) -> float:
    """
    Calculate background luminance for UGR calculation.
    
    Background luminance is approximated from the indirect illuminance
    on walls and ceiling, converted to luminance using average reflectance.
    
    Simplified calculation:
        Lb = E_indirect × ρ_avg / π
    
    Args:
        room: Room geometry with materials
        total_luminaire_flux: Total luminous flux from all luminaires (lumens)
    
    Returns:
        Background luminance in cd/m²
    """
    # Calculate average indirect illuminance on walls/ceiling
    # Using simplified cavity theory
    
    floor_area = room.floor_area
    wall_area = sum(s.polygon.get_area() for s in room.get_surfaces() if 'wall' in s.id)
    ceiling_area = floor_area  # Assume same as floor
    
    total_area = floor_area + wall_area + ceiling_area
    
    # Average reflectance weighted by area
    rho_floor = room.floor_material.reflectance
    rho_wall = room.wall_material.reflectance
    rho_ceiling = room.ceiling_material.reflectance
    
    rho_avg = (rho_floor * floor_area + rho_wall * wall_area + rho_ceiling * ceiling_area) / total_area
    
    # Indirect flux (assume 30% of light is indirect after first reflection)
    indirect_flux = total_luminaire_flux * 0.3 * rho_avg
    
    # Average indirect illuminance on vertical surfaces (walls)
    E_indirect = indirect_flux / (wall_area + ceiling_area) if (wall_area + ceiling_area) > 0 else 0
    
    # Convert to luminance (Lambertian surface)
    Lb = E_indirect * rho_avg / math.pi
    
    # Minimum background luminance (prevent extreme UGR values)
    return max(10.0, Lb)  # At least 10 cd/m²


def calculate_ugr_at_position(
    observer: UGRObserverPosition,
    luminaires: List[LuminaireForUGR],
    background_luminance: float,
    occluder_bvh: Optional[BVHNode] = None,
) -> UGRResult:
    """
    Calculate UGR at a specific observer position.
    
    UGR = 8 × log₁₀ [ (0.25/Lb) × Σ(L²ω/p²) ]
    
    Args:
        observer: Observer position and view direction
        luminaires: List of luminaires in the room
        background_luminance: Background luminance (cd/m²)
    
    Returns:
        UGRResult with calculated value and contributions
    """
    if background_luminance <= 0:
        background_luminance = 10.0
    
    sum_term = 0.0
    contributions = []
    
    for i, lum in enumerate(luminaires):
        # Vector from observer to luminaire
        to_lum = lum.position - observer.eye_position
        distance = to_lum.length()
        
        if distance < 0.1:
            continue
        
        direction = to_lum.normalize()
        if occluder_bvh is not None:
            policy = scaled_ray_policy(scene_scale=distance, user_eps=1e-4)
            origin = observer.eye_position + direction * policy.origin_eps
            if any_hit(
                occluder_bvh,
                origin,
                direction,
                t_min=policy.t_min,
                t_max=max(distance - policy.t_min, policy.t_min),
            ):
                continue
        
        # Calculate angles
        # Vertical angle (above/below horizontal)
        H = math.degrees(math.asin(direction.z))
        
        # Only consider luminaires above the line of sight
        if H < 0:
            continue
        
        # Horizontal angle (from view direction)
        # Project onto horizontal plane
        dir_horiz = Vector3(direction.x, direction.y, 0).normalize()
        view_horiz = Vector3(observer.view_direction.x, observer.view_direction.y, 0).normalize()
        
        cos_T = dir_horiz.dot(view_horiz)
        T = math.degrees(math.acos(max(-1, min(1, cos_T))))
        
        # Only consider luminaires within 90° of view direction
        if T > 90:
            continue
        
        # Solid angle
        omega = calculate_solid_angle(lum, observer.eye_position)
        
        if omega <= 0:
            continue
        
        # Position index
        p = calculate_guth_position_index(H, T)
        
        # Luminance (adjusted for viewing angle)
        L = lum.luminance
        
        # Contribution to sum
        contribution = (L ** 2 * omega) / (p ** 2)
        sum_term += contribution
        contributions.append((i, contribution))
    
    # Calculate UGR
    if sum_term > 0:
        ugr = 8 * math.log10(0.25 / background_luminance * sum_term)
    else:
        ugr = 0.0
    
    # Clamp to realistic range
    ugr = max(0, min(40, ugr))
    
    return UGRResult(
        observer=observer,
        ugr_value=ugr,
        background_luminance=background_luminance,
        luminaire_contributions=contributions,
    )


def analyze_room_ugr(
    room: Room,
    luminaires: List[LuminaireForUGR],
    total_flux: float,
    grid_spacing: float = 2.0,
    eye_height: float = 1.2,  # Seated
    occluder_bvh: Optional[BVHNode] = None,
) -> UGRAnalysis:
    """
    Perform complete UGR analysis for a room.
    
    Calculates UGR at a grid of observer positions, looking in
    both main axis directions (along length and width).
    
    Args:
        room: Room geometry
        luminaires: List of luminaires
        total_flux: Total luminous flux (lumens)
        grid_spacing: Spacing between observer positions (m)
        eye_height: Observer eye height (m)
    
    Returns:
        UGRAnalysis with results for all positions
    """
    # Calculate background luminance
    Lb = calculate_background_luminance(room, total_flux)
    bvh = occluder_bvh if occluder_bvh is not None else build_bvh(triangulate_surfaces(room.get_surfaces()))
    
    # Get room bounds
    bb_min, bb_max = room.get_bounding_box()
    
    # Generate observer positions on a grid
    results = []
    
    x = bb_min.x + grid_spacing
    while x < bb_max.x - grid_spacing:
        y = bb_min.y + grid_spacing
        while y < bb_max.y - grid_spacing:
            eye_pos = Vector3(x, y, eye_height)
            
            # Look in +X direction
            observer_px = UGRObserverPosition(
                eye_position=eye_pos,
                view_direction=Vector3(1, 0, 0),
                name=f"({x:.1f}, {y:.1f}) +X"
            )
            result_px = calculate_ugr_at_position(observer_px, luminaires, Lb, occluder_bvh=bvh)
            results.append(result_px)
            
            # Look in -X direction
            observer_nx = UGRObserverPosition(
                eye_position=eye_pos,
                view_direction=Vector3(-1, 0, 0),
                name=f"({x:.1f}, {y:.1f}) -X"
            )
            result_nx = calculate_ugr_at_position(observer_nx, luminaires, Lb, occluder_bvh=bvh)
            results.append(result_nx)
            
            # Look in +Y direction
            observer_py = UGRObserverPosition(
                eye_position=eye_pos,
                view_direction=Vector3(0, 1, 0),
                name=f"({x:.1f}, {y:.1f}) +Y"
            )
            result_py = calculate_ugr_at_position(observer_py, luminaires, Lb, occluder_bvh=bvh)
            results.append(result_py)
            
            # Look in -Y direction
            observer_ny = UGRObserverPosition(
                eye_position=eye_pos,
                view_direction=Vector3(0, -1, 0),
                name=f"({x:.1f}, {y:.1f}) -Y"
            )
            result_ny = calculate_ugr_at_position(observer_ny, luminaires, Lb, occluder_bvh=bvh)
            results.append(result_ny)
            
            y += grid_spacing
        x += grid_spacing
    
    if not results:
        return UGRAnalysis(
            room_name=room.name,
            results=[],
            max_ugr=0,
            min_ugr=0,
            positions_analyzed=0,
        )
    
    max_ugr = max(r.ugr_value for r in results)
    min_ugr = min(r.ugr_value for r in results)
    
    return UGRAnalysis(
        room_name=room.name,
        results=results,
        max_ugr=max_ugr,
        min_ugr=min_ugr,
        positions_analyzed=len(results) // 4,  # 4 directions per position
    )


def quick_ugr_estimate(
    room_length: float,
    room_width: float,
    room_height: float,
    mounting_height: float,
    luminaire_luminance: float,  # cd/m²
    num_luminaires: int,
    reflectances: Tuple[float, float, float] = (0.7, 0.5, 0.2),  # ceiling, wall, floor
) -> float:
    """
    Quick UGR estimate using simplified method.
    
    This provides a rough estimate for initial design checks
    without full calculation.
    
    Args:
        room_length: Room length (m)
        room_width: Room width (m)  
        room_height: Room height (m)
        mounting_height: Luminaire mounting height (m)
        luminaire_luminance: Average luminaire luminance (cd/m²)
        num_luminaires: Number of luminaires
        reflectances: (ceiling, wall, floor) reflectances
    
    Returns:
        Estimated UGR value
    """
    # Room Index
    h = mounting_height - 0.8  # Height above work plane
    k = (room_length * room_width) / (h * (room_length + room_width))
    
    # Simplified UGR from lookup tables (interpolated)
    # This is a rough approximation
    
    # Base UGR depends on room index and luminaire luminance
    if luminaire_luminance < 1000:
        base_ugr = 16
    elif luminaire_luminance < 3000:
        base_ugr = 19
    elif luminaire_luminance < 7000:
        base_ugr = 22
    else:
        base_ugr = 25
    
    # Adjust for room index
    if k < 1:
        base_ugr += 3
    elif k > 3:
        base_ugr -= 2
    
    # Adjust for reflectances
    rho_avg = sum(reflectances) / 3
    if rho_avg > 0.5:
        base_ugr -= 1
    elif rho_avg < 0.3:
        base_ugr += 1
    
    return max(10, min(28, base_ugr))
