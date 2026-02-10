"""
Luxera Radiosity Engine

Implements the radiosity method for calculating inter-reflections
in lighting simulations. This is the core algorithm that distinguishes
professional lighting software from simple direct illuminance calculations.

The radiosity equation:
    B_i = E_i + ρ_i * Σ(B_j * F_ij)

Where:
    B_i = radiosity (exitance) of patch i [lm/m²]
    E_i = self-emission of patch i [lm/m²]
    ρ_i = reflectance of patch i [0-1]
    F_ij = form factor from patch j to patch i
    
The form factor F_ij represents the fraction of light leaving patch j
that arrives at patch i, accounting for geometry and visibility.

References:
- Cohen & Wallace: "Radiosity and Realistic Image Synthesis" (1993)
- Sillion & Puech: "Radiosity & Global Illumination" (1994)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
import numpy as np
from enum import Enum, auto

from luxera.geometry.core import Vector3, Surface, Polygon, Scene, Room


# =============================================================================
# BVH Acceleration (AABB)
# =============================================================================

@dataclass(frozen=True)
class AABB:
    min: Vector3
    max: Vector3

    def intersects_ray(self, origin: Vector3, direction: Vector3, t_max: float) -> bool:
        # Slab intersection
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
class BVHNode:
    aabb: AABB
    left: Optional["BVHNode"] = None
    right: Optional["BVHNode"] = None
    surfaces: Optional[List[Surface]] = None


def _surface_aabb(surface: Surface) -> AABB:
    xs = [v.x for v in surface.polygon.vertices]
    ys = [v.y for v in surface.polygon.vertices]
    zs = [v.z for v in surface.polygon.vertices]
    return AABB(min=Vector3(min(xs), min(ys), min(zs)), max=Vector3(max(xs), max(ys), max(zs)))


def build_bvh(surfaces: List[Surface], max_leaf: int = 4) -> Optional[BVHNode]:
    if not surfaces:
        return None
    if len(surfaces) <= max_leaf:
        aabb = _merge_aabbs([_surface_aabb(s) for s in surfaces])
        return BVHNode(aabb=aabb, surfaces=surfaces)

    # Split by longest axis of centroids
    centroids = [s.polygon.get_centroid() for s in surfaces]
    xs = [c.x for c in centroids]
    ys = [c.y for c in centroids]
    zs = [c.z for c in centroids]
    ranges = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    axis = ranges.index(max(ranges))
    key = (lambda s: s.polygon.get_centroid().x) if axis == 0 else (lambda s: s.polygon.get_centroid().y) if axis == 1 else (lambda s: s.polygon.get_centroid().z)
    surfaces_sorted = sorted(surfaces, key=key)
    mid = len(surfaces_sorted) // 2
    left = build_bvh(surfaces_sorted[:mid], max_leaf=max_leaf)
    right = build_bvh(surfaces_sorted[mid:], max_leaf=max_leaf)
    aabb = _merge_aabbs([left.aabb, right.aabb])  # type: ignore[arg-type]
    return BVHNode(aabb=aabb, left=left, right=right)


def _merge_aabbs(aabbs: List[AABB]) -> AABB:
    xs = [a.min.x for a in aabbs] + [a.max.x for a in aabbs]
    ys = [a.min.y for a in aabbs] + [a.max.y for a in aabbs]
    zs = [a.min.z for a in aabbs] + [a.max.z for a in aabbs]
    return AABB(min=Vector3(min(xs), min(ys), min(zs)), max=Vector3(max(xs), max(ys), max(zs)))


# =============================================================================
# Form Factor Calculation
# =============================================================================

def _visibility_ray(
    p1: Vector3, 
    p2: Vector3, 
    surfaces: List[Surface],
    exclude_ids: Tuple[str, str],
    bvh: Optional[BVHNode] = None,
) -> bool:
    """
    Check if two points can see each other.
    
    Simple ray-surface intersection test. Returns True if visible.
    
    Args:
        p1, p2: Points to check visibility between
        surfaces: All surfaces in scene
        exclude_ids: Surface IDs to exclude (the surfaces containing p1, p2)
    
    Returns:
        True if p1 and p2 can see each other
    """
    direction = p2 - p1
    dist = direction.length()
    
    if dist < 1e-6:
        return True
    
    direction = direction.normalize()
    
    candidates = surfaces
    if bvh is not None:
        candidates = _bvh_query(bvh, p1, direction, dist)

    for surface in candidates:
        if surface.id in exclude_ids:
            continue
        
        # Ray-polygon intersection
        normal = surface.normal
        denom = direction.dot(normal)
        
        if abs(denom) < 1e-10:
            continue  # Ray parallel to surface
        
        # Distance to plane
        d = (surface.centroid - p1).dot(normal) / denom
        
        if d <= 0 or d >= dist - 1e-6:
            continue  # Behind ray origin or beyond target
        
        # Intersection point
        hit_point = p1 + direction * d
        
        # Check if inside polygon (simplified 2D projection)
        if surface.polygon.contains_point_2d(hit_point):
            return False
    
    return True


def _bvh_query(node: BVHNode, origin: Vector3, direction: Vector3, t_max: float) -> List[Surface]:
    hits: List[Surface] = []
    if not node.aabb.intersects_ray(origin, direction, t_max):
        return hits
    if node.surfaces is not None:
        return node.surfaces
    if node.left:
        hits.extend(_bvh_query(node.left, origin, direction, t_max))
    if node.right:
        hits.extend(_bvh_query(node.right, origin, direction, t_max))
    return hits


def compute_form_factor_analytic(
    patch_i: Surface,
    patch_j: Surface,
) -> float:
    """
    Compute form factor from patch j to patch i using analytic method.
    
    For small patches relative to their separation, we can use:
        F_ij ≈ (cos(θ_i) * cos(θ_j) * A_j) / (π * r²)
    
    Where:
        θ_i = angle between normal of i and direction to j
        θ_j = angle between normal of j and direction to i
        A_j = area of patch j
        r = distance between centroids
    """
    # Direction from i to j
    r_vec = patch_j.centroid - patch_i.centroid
    r = r_vec.length()
    
    if r < 1e-6:
        return 0.0
    
    r_dir = r_vec.normalize()
    
    # Angles
    cos_i = patch_i.normal.dot(r_dir)
    cos_j = -patch_j.normal.dot(r_dir)  # Negative because pointing toward j
    
    if cos_i <= 0 or cos_j <= 0:
        return 0.0  # Patches facing away from each other
    
    # Form factor
    F = (cos_i * cos_j * patch_j.area) / (math.pi * r * r)
    
    return max(0.0, min(1.0, F))


def compute_form_factor_monte_carlo(
    patch_i: Surface,
    patch_j: Surface,
    surfaces: List[Surface],
    num_samples: int = 16,
    rng: Optional[np.random.Generator] = None,
    bvh: Optional[BVHNode] = None,
) -> float:
    """
    Compute form factor using Monte Carlo sampling with visibility.
    
    This is more accurate for complex scenes with occlusion.
    """
    if patch_i.id == patch_j.id:
        return 0.0
    
    # Sample points on both patches
    # For simplicity, use centroid + jittered samples
    centroid_i = patch_i.centroid
    centroid_j = patch_j.centroid
    
    visible_samples = 0
    total_factor = 0.0
    
    if rng is None:
        raise ValueError("Deterministic RNG required: pass a numpy Generator from solver settings/seed.")

    for _ in range(num_samples):
        # Jitter sample points slightly
        offset_i = Vector3(
            (rng.random() - 0.5) * 0.1,
            (rng.random() - 0.5) * 0.1,
            (rng.random() - 0.5) * 0.1
        )
        offset_j = Vector3(
            (rng.random() - 0.5) * 0.1,
            (rng.random() - 0.5) * 0.1,
            (rng.random() - 0.5) * 0.1
        )
        
        p_i = centroid_i + offset_i
        p_j = centroid_j + offset_j
        
        # Check visibility
        if _visibility_ray(p_i, p_j, surfaces, (patch_i.id, patch_j.id), bvh=bvh):
            visible_samples += 1
            
            # Compute contribution
            r_vec = p_j - p_i
            r = r_vec.length()
            if r < 1e-6:
                continue
            
            r_dir = r_vec.normalize()
            cos_i = patch_i.normal.dot(r_dir)
            cos_j = -patch_j.normal.dot(r_dir)
            
            if cos_i > 0 and cos_j > 0:
                total_factor += (cos_i * cos_j) / (math.pi * r * r)
    
    if visible_samples == 0:
        return 0.0
    
    # Average and scale by area
    avg_factor = total_factor / num_samples
    F = avg_factor * patch_j.area
    
    return max(0.0, min(1.0, F))


# =============================================================================
# Radiosity Solver
# =============================================================================

class RadiosityMethod(Enum):
    """Radiosity solving method."""
    GATHERING = auto()  # Gauss-Seidel iteration (gather light)
    SHOOTING = auto()   # Progressive refinement (shoot light)
    MATRIX = auto()     # Direct matrix solution


@dataclass
class RadiositySettings:
    """Settings for radiosity calculation."""
    max_iterations: int = 100
    convergence_threshold: float = 0.001  # 0.1% change
    patch_max_area: float = 0.5  # Maximum patch area in m²
    method: RadiosityMethod = RadiosityMethod.GATHERING
    use_visibility: bool = True
    ambient_light: float = 0.0  # Ambient term (lux)
    seed: int = 0
    monte_carlo_samples: int = 16


@dataclass
class Patch:
    """
    A patch for radiosity calculation.
    
    Patches are subdivided surfaces used for more accurate calculations.
    """
    id: int
    polygon: Polygon
    parent_surface: Surface
    area: float
    normal: Vector3
    centroid: Vector3
    reflectance: float
    
    # Radiosity values
    emission: float = 0.0  # Self-emission [lm/m²]
    radiosity: float = 0.0  # Total exitance [lm/m²]
    irradiance: float = 0.0  # Incident [lm/m²]
    residual: float = 0.0  # Unshot energy for progressive


@dataclass
class RadiosityResult:
    """Results of radiosity calculation."""
    patches: List[Patch]
    surfaces: List[Surface]
    iterations: int
    converged: bool
    total_flux: float  # Total light in scene [lm]
    avg_illuminance: float  # Average floor illuminance [lux]
    residuals: List[float]  # per-iteration max change
    stop_reason: str  # "converged" or "max_iterations"
    
    def get_surface_illuminance(self, surface_id: str) -> float:
        """Get average illuminance on a surface."""
        patches = [p for p in self.patches if p.parent_surface.id == surface_id]
        if not patches:
            return 0.0
        
        total_area = sum(p.area for p in patches)
        if total_area < 1e-10:
            return 0.0
        
        weighted_sum = sum(p.irradiance * p.area for p in patches)
        return weighted_sum / total_area


class RadiositySolver:
    """
    Radiosity equation solver.
    
    Implements the classic radiosity method for calculating inter-reflections
    in enclosed spaces. This produces physically accurate lighting levels
    that account for light bouncing off walls, floors, and ceilings.
    """
    
    def __init__(self, settings: RadiositySettings = None):
        self.settings = settings or RadiositySettings()
        self.patches: List[Patch] = []
        self.form_factors: Optional[np.ndarray] = None
        self.rng = np.random.default_rng(self.settings.seed)
        self.bvh: Optional[BVHNode] = None
    
    def _create_patches(self, surfaces: List[Surface]) -> List[Patch]:
        """Subdivide surfaces into patches."""
        patches = []
        patch_id = 0
        
        for surface in surfaces:
            # Subdivide if needed
            sub_polys = surface.polygon.subdivide(self.settings.patch_max_area)
            
            for poly in sub_polys:
                patch = Patch(
                    id=patch_id,
                    polygon=poly,
                    parent_surface=surface,
                    area=poly.get_area(),
                    normal=poly.get_normal(),
                    centroid=poly.get_centroid(),
                    reflectance=surface.material.reflectance,
                    emission=surface.emission if surface.is_emissive else 0.0,
                )
                patches.append(patch)
                patch_id += 1
        
        return patches
    
    def _compute_form_factors(self, patches: List[Patch], surfaces: List[Surface]) -> np.ndarray:
        """
        Compute form factor matrix.
        
        F[i,j] = form factor from patch j to patch i
        """
        n = len(patches)
        F = np.zeros((n, n))
        
        for i, patch_i in enumerate(patches):
            for j, patch_j in enumerate(patches):
                if i == j:
                    continue
                
                if self.settings.use_visibility:
                    F[i, j] = compute_form_factor_monte_carlo(
                        patch_i,
                        patch_j,
                        surfaces,
                        num_samples=self.settings.monte_carlo_samples,
                        rng=self.rng,
                        bvh=self.bvh,
                    )
                else:
                    F[i, j] = compute_form_factor_analytic(patch_i, patch_j)
        
        return F
    
    def _solve_gathering(self) -> tuple[int, List[float]]:
        """
        Solve using Gauss-Seidel iteration (gathering).
        
        Each patch gathers light from all other patches.
        """
        n = len(self.patches)
        F = self.form_factors
        
        # Initialize radiosity to emission
        for patch in self.patches:
            patch.radiosity = patch.emission
        
        residuals: List[float] = []
        for iteration in range(self.settings.max_iterations):
            max_change = 0.0
            
            for i, patch in enumerate(self.patches):
                # Gather incoming light
                incoming = 0.0
                for j, other in enumerate(self.patches):
                    if i != j:
                        incoming += other.radiosity * F[i, j]
                
                # New radiosity
                new_radiosity = patch.emission + patch.reflectance * incoming
                
                # Track convergence
                if patch.radiosity > 0:
                    change = abs(new_radiosity - patch.radiosity) / patch.radiosity
                else:
                    change = abs(new_radiosity - patch.radiosity)
                max_change = max(max_change, change)
                
                patch.radiosity = new_radiosity
                patch.irradiance = incoming
            
            residuals.append(max_change)
            if max_change < self.settings.convergence_threshold:
                return iteration + 1, residuals
        
        return self.settings.max_iterations, residuals
    
    def _solve_shooting(self) -> tuple[int, List[float]]:
        """
        Solve using progressive refinement (shooting).
        
        Patches shoot their unshot energy to other patches.
        This converges faster for scenes with few bright sources.
        """
        n = len(self.patches)
        F = self.form_factors
        
        # Initialize
        for patch in self.patches:
            patch.radiosity = patch.emission
            patch.residual = patch.emission
        
        residuals: List[float] = []
        for iteration in range(self.settings.max_iterations):
            # Find patch with most unshot energy
            max_energy = 0
            shooter_idx = -1
            
            for i, patch in enumerate(self.patches):
                energy = patch.residual * patch.area
                if energy > max_energy:
                    max_energy = energy
                    shooter_idx = i
            
            residuals.append(max_energy)
            if shooter_idx < 0 or max_energy < self.settings.convergence_threshold:
                return iteration + 1, residuals
            
            shooter = self.patches[shooter_idx]
            
            # Shoot to all other patches
            for j, receiver in enumerate(self.patches):
                if j == shooter_idx:
                    continue
                
                # Form factor from shooter to receiver
                delta_rad = shooter.residual * F[j, shooter_idx]
                
                # Receiver gains this, then reflects fraction
                reflected = receiver.reflectance * delta_rad
                
                receiver.radiosity += reflected
                receiver.residual += reflected
                receiver.irradiance += delta_rad
            
            # Clear shooter's residual
            shooter.residual = 0
        
        return self.settings.max_iterations, residuals
    
    def solve(
        self, 
        surfaces: List[Surface],
        direct_illuminance: Optional[Dict[str, float]] = None
    ) -> RadiosityResult:
        """
        Solve the radiosity equation for the given surfaces.
        
        Args:
            surfaces: List of surfaces in the scene
            direct_illuminance: Optional dict mapping surface IDs to their
                               direct illuminance from luminaires (lux).
                               This is added as emission for radiosity.
        
        Returns:
            RadiosityResult with patch-level and surface-level results
        """
        # Create patches
        self.patches = self._create_patches(surfaces)
        
        if not self.patches:
            return RadiosityResult(
                patches=[],
                surfaces=surfaces,
                iterations=0,
                converged=True,
                total_flux=0,
                avg_illuminance=0,
                residuals=[],
                stop_reason="converged",
            )
        
        # Set emission from direct illuminance
        if direct_illuminance:
            for patch in self.patches:
                surf_id = patch.parent_surface.id
                if surf_id in direct_illuminance:
                    # Convert illuminance to exitance (reflected)
                    E = direct_illuminance[surf_id]
                    patch.emission = E * patch.reflectance
        
        # Build BVH for visibility acceleration
        self.bvh = build_bvh(surfaces)

        # Compute form factors
        self.form_factors = self._compute_form_factors(self.patches, surfaces)
        
        # Solve
        if self.settings.method == RadiosityMethod.GATHERING:
            iterations, residuals = self._solve_gathering()
        elif self.settings.method == RadiosityMethod.SHOOTING:
            iterations, residuals = self._solve_shooting()
        else:
            iterations, residuals = self._solve_gathering()
        
        converged = iterations < self.settings.max_iterations
        stop_reason = "converged" if converged else "max_iterations"
        
        # Compute total flux
        total_flux = sum(p.radiosity * p.area for p in self.patches)
        
        # Compute average floor illuminance
        floor_patches = [p for p in self.patches if 'floor' in p.parent_surface.id.lower()]
        if floor_patches:
            total_floor_area = sum(p.area for p in floor_patches)
            avg_illuminance = sum(p.irradiance * p.area for p in floor_patches) / total_floor_area
        else:
            avg_illuminance = 0
        
        # Update parent surfaces with aggregate values
        for surface in surfaces:
            patches = [p for p in self.patches if p.parent_surface.id == surface.id]
            if patches:
                total_area = sum(p.area for p in patches)
                surface.illuminance = sum(p.irradiance * p.area for p in patches) / total_area
                surface.exitance = sum(p.radiosity * p.area for p in patches) / total_area
        
        return RadiosityResult(
            patches=self.patches,
            surfaces=surfaces,
            iterations=iterations,
            converged=converged,
            total_flux=total_flux,
            avg_illuminance=avg_illuminance,
            residuals=residuals,
            stop_reason=stop_reason,
        )


# =============================================================================
# Combined Direct + Indirect Calculation
# =============================================================================

def calculate_room_lighting(
    room: Room,
    luminaires: List,  # List of Luminaire objects from calculation module
    settings: RadiositySettings = None,
) -> RadiosityResult:
    """
    Calculate complete room lighting including direct and indirect components.
    
    This is the main entry point for full room calculations.
    
    Args:
        room: Room geometry
        luminaires: List of luminaires with IES data and positions
        settings: Radiosity calculation settings
    
    Returns:
        RadiosityResult with complete lighting solution
    """
    from luxera.calculation.illuminance import (
        calculate_direct_illuminance, 
        CalculationGrid,
        Luminaire
    )
    
    surfaces = room.get_surfaces()
    
    # Calculate direct illuminance on each surface
    direct_illuminance = {}
    
    for surface in surfaces:
        # Sample points on surface
        centroid = surface.centroid
        normal = surface.normal
        
        total_E = 0.0
        for luminaire in luminaires:
            E = calculate_direct_illuminance(centroid, normal, luminaire)
            total_E += E
        
        direct_illuminance[surface.id] = total_E
    
    # Solve radiosity for inter-reflections
    solver = RadiositySolver(settings or RadiositySettings())
    result = solver.solve(surfaces, direct_illuminance)
    
    return result
