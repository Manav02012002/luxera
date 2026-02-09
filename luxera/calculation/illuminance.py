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
from luxera.geometry.core import Vector3, Transform, Surface
from luxera.photometry.model import Photometry
from luxera.photometry.sample import sample_intensity_cd


@dataclass
class Luminaire:
    """
    A luminaire positioned in 3D space.
    
    Attributes:
        transform: World transform (position + rotation)
        photometry: Parsed photometric data
        flux_multiplier: Scale factor for output (e.g., for dimming)
    """
    photometry: Photometry
    transform: Transform = field(default_factory=Transform)
    flux_multiplier: float = 1.0
    tilt_deg: float = 0.0


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
    origin: Vector3
    width: float
    height: float
    elevation: float
    nx: int
    ny: int
    normal: Vector3 = field(default_factory=Vector3.up)
    
    def __post_init__(self):
        self.normal = self.normal.normalize()
    
    def get_points(self) -> List[Vector3]:
        """Generate all grid points."""
        points = []
        dx = self.width / max(self.nx - 1, 1)
        dy = self.height / max(self.ny - 1, 1)
        
        for j in range(self.ny):
            for i in range(self.nx):
                x = self.origin.x + i * dx
                y = self.origin.y + j * dy
                z = self.elevation
                points.append(Vector3(x, y, z))
        
        return points
    
    def get_point(self, i: int, j: int) -> Vector3:
        """Get a specific grid point."""
        dx = self.width / max(self.nx - 1, 1)
        dy = self.height / max(self.ny - 1, 1)
        x = self.origin.x + i * dx
        y = self.origin.y + j * dy
        return Vector3(x, y, self.elevation)


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


@dataclass(frozen=True)
class DirectCalcSettings:
    use_occlusion: bool = False
    occlusion_epsilon: float = 1e-6


@dataclass(frozen=True)
class _OcclusionAABB:
    min: Vector3
    max: Vector3

    def intersects_ray(self, origin: Vector3, direction: Vector3, t_max: float) -> bool:
        tmin = -math.inf
        tmax = t_max
        for axis in ("x", "y", "z"):
            o = getattr(origin, axis)
            d = getattr(direction, axis)
            mn = getattr(self.min, axis)
            mx = getattr(self.max, axis)
            if abs(d) < 1e-12:
                if o < mn or o > mx:
                    return False
                continue
            inv_d = 1.0 / d
            t0 = (mn - o) * inv_d
            t1 = (mx - o) * inv_d
            if t0 > t1:
                t0, t1 = t1, t0
            tmin = max(tmin, t0)
            tmax = min(tmax, t1)
            if tmax < tmin:
                return False
        return True


@dataclass
class _OcclusionBVHNode:
    aabb: _OcclusionAABB
    left: Optional["_OcclusionBVHNode"] = None
    right: Optional["_OcclusionBVHNode"] = None
    surfaces: Optional[List[Surface]] = None


def _surface_aabb(surface: Surface) -> _OcclusionAABB:
    bb_min, bb_max = surface.polygon.get_bounding_box()
    return _OcclusionAABB(min=bb_min, max=bb_max)


def _merge_aabbs(aabbs: List[_OcclusionAABB]) -> _OcclusionAABB:
    xs = [a.min.x for a in aabbs] + [a.max.x for a in aabbs]
    ys = [a.min.y for a in aabbs] + [a.max.y for a in aabbs]
    zs = [a.min.z for a in aabbs] + [a.max.z for a in aabbs]
    return _OcclusionAABB(min=Vector3(min(xs), min(ys), min(zs)), max=Vector3(max(xs), max(ys), max(zs)))


def _build_occlusion_bvh(surfaces: List[Surface], max_leaf: int = 8) -> Optional[_OcclusionBVHNode]:
    if not surfaces:
        return None
    if len(surfaces) <= max_leaf:
        return _OcclusionBVHNode(aabb=_merge_aabbs([_surface_aabb(s) for s in surfaces]), surfaces=surfaces)

    centroids = [s.centroid for s in surfaces]
    xs = [c.x for c in centroids]
    ys = [c.y for c in centroids]
    zs = [c.z for c in centroids]
    ranges = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    axis = ranges.index(max(ranges))
    key = (lambda s: s.centroid.x) if axis == 0 else (lambda s: s.centroid.y) if axis == 1 else (lambda s: s.centroid.z)
    sorted_surfaces = sorted(surfaces, key=key)
    mid = len(sorted_surfaces) // 2
    left = _build_occlusion_bvh(sorted_surfaces[:mid], max_leaf=max_leaf)
    right = _build_occlusion_bvh(sorted_surfaces[mid:], max_leaf=max_leaf)
    children = [n.aabb for n in (left, right) if n is not None]
    if not children:
        return None
    return _OcclusionBVHNode(aabb=_merge_aabbs(children), left=left, right=right)


def _query_bvh(node: Optional[_OcclusionBVHNode], origin: Vector3, direction: Vector3, t_max: float) -> List[Surface]:
    if node is None:
        return []
    if not node.aabb.intersects_ray(origin, direction, t_max):
        return []
    if node.surfaces is not None:
        return node.surfaces
    out: List[Surface] = []
    out.extend(_query_bvh(node.left, origin, direction, t_max))
    out.extend(_query_bvh(node.right, origin, direction, t_max))
    return out


def _project_to_2d(point: Vector3, normal: Vector3) -> Tuple[float, float]:
    ax = abs(normal.x)
    ay = abs(normal.y)
    az = abs(normal.z)
    # Drop dominant axis for stable projection.
    if ax >= ay and ax >= az:
        return (point.y, point.z)
    if ay >= ax and ay >= az:
        return (point.x, point.z)
    return (point.x, point.y)


def _point_in_polygon_3d(point: Vector3, surface: Surface) -> bool:
    """
    Point-in-polygon in a best-fit 2D projection based on polygon normal.
    """
    verts = surface.polygon.vertices
    if len(verts) < 3:
        return False
    n = surface.normal
    px, py = _project_to_2d(point, n)
    poly2 = [_project_to_2d(v, n) for v in verts]
    inside = False
    j = len(poly2) - 1
    for i in range(len(poly2)):
        xi, yi = poly2[i]
        xj, yj = poly2[j]
        denom = (yj - yi)
        cross = ((xj - xi) * (py - yi) / denom + xi) if abs(denom) > 1e-12 else xi
        if ((yi > py) != (yj > py)) and (px < cross):
            inside = not inside
        j = i
    return inside


def _is_occluded(
    point: Vector3,
    luminaire_pos: Vector3,
    occluders: List[Surface],
    eps: float,
    bvh: Optional[_OcclusionBVHNode] = None,
) -> bool:
    direction = point - luminaire_pos
    dist = direction.length()
    if dist <= eps:
        return False
    ray_dir = direction / dist

    candidates = _query_bvh(bvh, luminaire_pos, ray_dir, dist) if bvh is not None else occluders
    for surface in candidates:
        n = surface.normal
        denom = ray_dir.dot(n)
        if abs(denom) < 1e-10:
            continue
        # ray-plane intersection
        t = (surface.centroid - luminaire_pos).dot(n) / denom
        if t <= eps or t >= dist - eps:
            continue
        hit = luminaire_pos + ray_dir * t
        if _point_in_polygon_3d(hit, surface):
            return True
    return False


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
    point: Vector3,
    surface_normal: Vector3,
    luminaire: Luminaire,
    occluders: Optional[List[Surface]] = None,
    settings: Optional[DirectCalcSettings] = None,
    occluder_bvh: Optional[_OcclusionBVHNode] = None,
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
    to_point = point - luminaire.transform.position
    distance = to_point.length()
    
    if distance < 0.001:  # Too close, avoid division issues
        return 0.0
    
    # Direction from luminaire to point (normalized)
    direction = to_point.normalize()

    cfg = settings or DirectCalcSettings()
    if cfg.use_occlusion and occluders:
        if _is_occluded(
            point,
            luminaire.transform.position,
            occluders,
            cfg.occlusion_epsilon,
            bvh=occluder_bvh,
        ):
            return 0.0
    
    # Convert world direction into luminaire local frame
    # Local frame convention: +X right, +Y forward, +Z up; nadir is -Z.
    R = luminaire.transform.get_rotation_matrix()
    local_dir = Vector3.from_array(R.T @ direction.to_array())

    # If point is behind luminaire (local +Z), no light reaches it
    if local_dir.z >= 0:
        return 0.0
    
    # Get intensity at calculated angles
    intensity = sample_intensity_cd(luminaire.photometry, local_dir, tilt_deg=luminaire.tilt_deg)
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
    occluders: Optional[List[Surface]] = None,
    settings: Optional[DirectCalcSettings] = None,
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
    cfg = settings or DirectCalcSettings()
    occluder_bvh = _build_occlusion_bvh(occluders or []) if (cfg.use_occlusion and occluders) else None
    
    for j in range(grid.ny):
        for i in range(grid.nx):
            point = grid.get_point(i, j)
            total_illuminance = 0.0
            
            for luminaire in luminaires:
                total_illuminance += calculate_direct_illuminance(
                    point,
                    grid.normal,
                    luminaire,
                    occluders=occluders,
                    settings=cfg,
                    occluder_bvh=occluder_bvh,
                )
            
            values[j, i] = total_illuminance
    
    return IlluminanceResult(grid=grid, values=values)


def create_room_luminaire_layout(
    room_width: float,
    room_length: float,
    mounting_height: float,
    work_plane_height: float,
    photometry: Photometry,
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
        photometry: Photometric data for luminaires
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
                transform=Transform(position=Vector3(x, y, z)),
                photometry=photometry,
            )
            luminaires.append(luminaire)
    
    # Create calculation grid
    grid = CalculationGrid(
        origin=Vector3(0.5, 0.5, work_plane_height),  # 0.5m from walls
        width=room_width - 1.0,
        height=room_length - 1.0,
        elevation=work_plane_height,
        nx=int(room_width * 2),  # 0.5m spacing
        ny=int(room_length * 2),
    )
    
    return luminaires, grid


def quick_room_calculation(
    photometry: Photometry,
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
        photometry: Parsed photometric data
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
        photometry=photometry,
        rows=num_luminaires_y,
        cols=num_luminaires_x,
    )
    
    return calculate_grid_illuminance(grid, luminaires)
