"""
Illuminance Calculation Engine for Luxera

This module implements point-by-point illuminance calculations using
photometric data. This is the fundamental calculation that Dialux and
Agi32 perform.

Key concepts:
- Direct illuminance: Light arriving directly from luminaires
- Reflected illuminance: Light bounced off surfaces (inter-reflections)
- Maintained illuminance: Accounts for lamp depreciation and dirt

The inverse square law for illuminance:
    E = I(θ,φ) × cos(α) / d²

Where:
    E = illuminance at point (lux)
    I(θ,φ) = luminous intensity at angles θ,φ (candela)
    α = angle of incidence on surface
    d = distance from light source to point
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable
import numpy as np

from luxera.parser.ies_parser import ParsedIES


@dataclass
class Point3D:
    """A point in 3D space (meters)."""
    x: float
    y: float
    z: float
    
    def __add__(self, other: 'Point3D') -> 'Point3D':
        return Point3D(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other: 'Point3D') -> 'Point3D':
        return Point3D(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __mul__(self, scalar: float) -> 'Point3D':
        return Point3D(self.x * scalar, self.y * scalar, self.z * scalar)
    
    def dot(self, other: 'Point3D') -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z
    
    def length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    
    def normalize(self) -> 'Point3D':
        L = self.length()
        if L < 1e-10:
            return Point3D(0, 0, 1)
        return Point3D(self.x / L, self.y / L, self.z / L)
    
    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class Luminaire:
    """
    A luminaire positioned in 3D space.
    
    Attributes:
        position: Location in meters (x, y, z)
        aim_direction: Unit vector pointing in the luminaire's aim direction
                       (default: straight down for Type C)
        rotation_deg: Rotation about the aim axis (C-plane rotation)
        ies_data: Parsed IES photometric data
        flux_multiplier: Scale factor for output (e.g., for dimming)
    """
    position: Point3D
    ies_data: ParsedIES
    aim_direction: Point3D = field(default_factory=lambda: Point3D(0, 0, -1))
    rotation_deg: float = 0.0
    flux_multiplier: float = 1.0
    
    def __post_init__(self):
        # Normalize aim direction
        self.aim_direction = self.aim_direction.normalize()


@dataclass
class CalculationGrid:
    """
    A rectangular grid of calculation points on a work plane.
    
    Attributes:
        origin: Bottom-left corner of grid (meters)
        width: Grid width in x-direction (meters)
        height: Grid height in y-direction (meters)
        elevation: Z-height of work plane (meters)
        nx: Number of points in x-direction
        ny: Number of points in y-direction
        normal: Surface normal (default: facing up)
    """
    origin: Point3D
    width: float
    height: float
    elevation: float
    nx: int
    ny: int
    normal: Point3D = field(default_factory=lambda: Point3D(0, 0, 1))
    
    def __post_init__(self):
        self.normal = self.normal.normalize()
    
    def get_points(self) -> List[Point3D]:
        """Generate all grid points."""
        points = []
        dx = self.width / max(self.nx - 1, 1)
        dy = self.height / max(self.ny - 1, 1)
        
        for j in range(self.ny):
            for i in range(self.nx):
                x = self.origin.x + i * dx
                y = self.origin.y + j * dy
                z = self.elevation
                points.append(Point3D(x, y, z))
        
        return points
    
    def get_point(self, i: int, j: int) -> Point3D:
        """Get a specific grid point."""
        dx = self.width / max(self.nx - 1, 1)
        dy = self.height / max(self.ny - 1, 1)
        x = self.origin.x + i * dx
        y = self.origin.y + j * dy
        return Point3D(x, y, self.elevation)


@dataclass(frozen=True)
class IlluminanceResult:
    """Results of illuminance calculation on a grid."""
    grid: CalculationGrid
    values: np.ndarray  # Shape: [ny, nx] - illuminance in lux
    
    @property
    def min_lux(self) -> float:
        return float(np.min(self.values))
    
    @property
    def max_lux(self) -> float:
        return float(np.max(self.values))
    
    @property
    def mean_lux(self) -> float:
        return float(np.mean(self.values))
    
    @property
    def uniformity_ratio(self) -> float:
        """Minimum to average ratio (Emin/Eavg)."""
        avg = self.mean_lux
        if avg < 1e-10:
            return 0.0
        return self.min_lux / avg
    
    @property
    def uniformity_diversity(self) -> float:
        """Minimum to maximum ratio (Emin/Emax)."""
        max_val = self.max_lux
        if max_val < 1e-10:
            return 0.0
        return self.min_lux / max_val


def interpolate_candela(
    ies: ParsedIES,
    gamma_deg: float,
    c_deg: float,
) -> float:
    """
    Interpolate candela value from IES data at given angles.
    
    Args:
        ies: Parsed IES data
        gamma_deg: Vertical angle (0=nadir for Type C)
        c_deg: Horizontal angle (C-plane)
    
    Returns:
        Interpolated candela value
    """
    if ies.angles is None or ies.candela is None:
        return 0.0
    
    v_angles = ies.angles.vertical_deg
    h_angles = ies.angles.horizontal_deg
    candela = ies.candela.values_cd_scaled
    
    # Clamp angles to valid range
    gamma_deg = max(v_angles[0], min(v_angles[-1], gamma_deg))
    
    # Handle C-angle wrapping and symmetry
    c_deg = c_deg % 360
    h_range = h_angles[-1] - h_angles[0]
    
    # Handle symmetry
    if h_range <= 90:  # Quadrant symmetry
        if c_deg > 90:
            c_deg = 180 - c_deg if c_deg <= 180 else c_deg - 180
            if c_deg > 90:
                c_deg = 360 - c_deg if c_deg > 270 else 180 - c_deg
        c_deg = min(c_deg, 90)
    elif h_range <= 180:  # Bilateral symmetry
        if c_deg > 180:
            c_deg = 360 - c_deg
    
    c_deg = max(h_angles[0], min(h_angles[-1], c_deg))
    
    # Find surrounding indices for bilinear interpolation
    def find_bracket(val: float, arr: List[float]) -> Tuple[int, int, float]:
        """Find indices bracketing value and interpolation factor."""
        for i in range(len(arr) - 1):
            if arr[i] <= val <= arr[i + 1]:
                t = (val - arr[i]) / (arr[i + 1] - arr[i]) if arr[i + 1] != arr[i] else 0
                return i, i + 1, t
        # Edge cases
        if val <= arr[0]:
            return 0, 0, 0.0
        return len(arr) - 1, len(arr) - 1, 0.0
    
    v_lo, v_hi, v_t = find_bracket(gamma_deg, v_angles)
    h_lo, h_hi, h_t = find_bracket(c_deg, h_angles)
    
    # Bilinear interpolation
    c00 = candela[h_lo][v_lo]
    c01 = candela[h_lo][v_hi]
    c10 = candela[h_hi][v_lo]
    c11 = candela[h_hi][v_hi]
    
    c0 = c00 * (1 - v_t) + c01 * v_t
    c1 = c10 * (1 - v_t) + c11 * v_t
    
    return c0 * (1 - h_t) + c1 * h_t


def calculate_direct_illuminance(
    point: Point3D,
    surface_normal: Point3D,
    luminaire: Luminaire,
) -> float:
    """
    Calculate direct illuminance at a point from a single luminaire.
    
    Uses the formula: E = I(θ,φ) × cos(α) / d²
    
    Args:
        point: Calculation point in 3D space
        surface_normal: Unit normal of the surface at the point
        luminaire: Luminaire with position and photometric data
    
    Returns:
        Direct illuminance in lux
    """
    # Vector from luminaire to point
    to_point = point - luminaire.position
    distance = to_point.length()
    
    if distance < 0.001:  # Too close, avoid division issues
        return 0.0
    
    # Direction from luminaire to point (normalized)
    direction = to_point.normalize()
    
    # Calculate angles relative to luminaire orientation
    # For Type C: gamma = angle from nadir (aim direction)
    # aim_direction points in the direction the luminaire is aimed (typically down)
    aim = luminaire.aim_direction
    
    # The angle gamma is the angle between the aim direction and the direction to the point
    # When looking straight down and the point is directly below, gamma = 0
    cos_gamma = direction.dot(aim)  # Both point in same direction when aligned
    cos_gamma = max(-1.0, min(1.0, cos_gamma))  # Clamp for numerical stability
    gamma_deg = math.degrees(math.acos(abs(cos_gamma)))
    
    # If point is behind the luminaire (opposite to aim), no light reaches it
    if cos_gamma < 0:
        return 0.0
    
    # Calculate C-plane angle (rotation around aim axis)
    # Project direction onto plane perpendicular to aim
    if abs(aim.z) > 0.99:  # Nearly vertical aim
        # C=0 is toward +X, C=90 is toward +Y
        c_deg = math.degrees(math.atan2(direction.y, direction.x))
        c_deg = (c_deg + luminaire.rotation_deg) % 360
    else:
        # General case - more complex rotation handling
        c_deg = 0
    
    # Get intensity at calculated angles
    intensity = interpolate_candela(luminaire.ies_data, gamma_deg, c_deg)
    intensity *= luminaire.flux_multiplier
    
    # Calculate incidence angle on surface
    # cos(α) = -direction · surface_normal (negative because direction points away from surface)
    cos_incidence = -direction.dot(surface_normal)
    
    if cos_incidence <= 0:
        return 0.0  # Light hitting back of surface
    
    # Inverse square law with cosine correction
    illuminance = intensity * cos_incidence / (distance ** 2)
    
    return max(0.0, illuminance)


def calculate_grid_illuminance(
    grid: CalculationGrid,
    luminaires: List[Luminaire],
) -> IlluminanceResult:
    """
    Calculate illuminance on a grid from multiple luminaires.
    
    Args:
        grid: Calculation grid specification
        luminaires: List of luminaires in the scene
    
    Returns:
        IlluminanceResult with values at each grid point
    """
    values = np.zeros((grid.ny, grid.nx))
    
    for j in range(grid.ny):
        for i in range(grid.nx):
            point = grid.get_point(i, j)
            total_illuminance = 0.0
            
            for luminaire in luminaires:
                total_illuminance += calculate_direct_illuminance(
                    point, grid.normal, luminaire
                )
            
            values[j, i] = total_illuminance
    
    return IlluminanceResult(grid=grid, values=values)


def create_room_luminaire_layout(
    room_width: float,
    room_length: float,
    mounting_height: float,
    work_plane_height: float,
    ies_data: ParsedIES,
    rows: int = 2,
    cols: int = 2,
    margin_x: float = 1.0,
    margin_y: float = 1.0,
) -> Tuple[List[Luminaire], CalculationGrid]:
    """
    Create a regular grid layout of luminaires in a room.
    
    Args:
        room_width: Room width in X direction (meters)
        room_length: Room length in Y direction (meters)
        mounting_height: Height of luminaires above floor (meters)
        work_plane_height: Height of calculation plane above floor (meters)
        ies_data: Photometric data for luminaires
        rows: Number of rows of luminaires
        cols: Number of columns of luminaires
        margin_x: Margin from walls in X direction (meters)
        margin_y: Margin from walls in Y direction (meters)
    
    Returns:
        Tuple of (luminaires list, calculation grid)
    """
    luminaires = []
    
    # Calculate luminaire spacing
    usable_width = room_width - 2 * margin_x
    usable_length = room_length - 2 * margin_y
    
    spacing_x = usable_width / max(cols, 1) if cols > 1 else 0
    spacing_y = usable_length / max(rows, 1) if rows > 1 else 0
    
    start_x = margin_x + spacing_x / 2
    start_y = margin_y + spacing_y / 2
    
    for row in range(rows):
        for col in range(cols):
            x = start_x + col * spacing_x
            y = start_y + row * spacing_y
            z = mounting_height
            
            luminaire = Luminaire(
                position=Point3D(x, y, z),
                ies_data=ies_data,
            )
            luminaires.append(luminaire)
    
    # Create calculation grid
    grid = CalculationGrid(
        origin=Point3D(0.5, 0.5, work_plane_height),  # 0.5m from walls
        width=room_width - 1.0,
        height=room_length - 1.0,
        elevation=work_plane_height,
        nx=int(room_width * 2),  # 0.5m spacing
        ny=int(room_length * 2),
    )
    
    return luminaires, grid


def quick_room_calculation(
    ies_data: ParsedIES,
    room_width: float = 6.0,
    room_length: float = 8.0,
    mounting_height: float = 2.8,
    work_plane_height: float = 0.8,
    num_luminaires_x: int = 2,
    num_luminaires_y: int = 3,
) -> IlluminanceResult:
    """
    Quick calculation for a simple rectangular room.
    
    This is a convenience function for rapid analysis.
    
    Args:
        ies_data: Parsed IES photometric data
        room_width: Room width (meters), default 6m
        room_length: Room length (meters), default 8m
        mounting_height: Luminaire height (meters), default 2.8m
        work_plane_height: Work plane height (meters), default 0.8m (desk height)
        num_luminaires_x: Luminaires in width direction
        num_luminaires_y: Luminaires in length direction
    
    Returns:
        IlluminanceResult with grid values
    """
    luminaires, grid = create_room_luminaire_layout(
        room_width=room_width,
        room_length=room_length,
        mounting_height=mounting_height,
        work_plane_height=work_plane_height,
        ies_data=ies_data,
        rows=num_luminaires_y,
        cols=num_luminaires_x,
    )
    
    return calculate_grid_illuminance(grid, luminaires)
