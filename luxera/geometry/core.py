"""
Luxera Geometry Module

Core 3D geometry primitives and scene representation for lighting calculations.
This module provides the foundation for room modeling, surface definitions,
and spatial calculations required for accurate lighting simulation.

Based on standard computational geometry approaches used in professional
lighting software like Dialux, AGI32, and Radiance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Iterator
from enum import Enum, auto
import numpy as np


# =============================================================================
# Vector and Point Classes
# =============================================================================

@dataclass
class Vector3:
    """3D vector for directions, normals, and displacements."""
    x: float
    y: float
    z: float
    
    def __add__(self, other: 'Vector3') -> 'Vector3':
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other: 'Vector3') -> 'Vector3':
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __mul__(self, scalar: float) -> 'Vector3':
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)
    
    def __rmul__(self, scalar: float) -> 'Vector3':
        return self.__mul__(scalar)
    
    def __truediv__(self, scalar: float) -> 'Vector3':
        return Vector3(self.x / scalar, self.y / scalar, self.z / scalar)
    
    def __neg__(self) -> 'Vector3':
        return Vector3(-self.x, -self.y, -self.z)
    
    def dot(self, other: 'Vector3') -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y + self.z * other.z
    
    def cross(self, other: 'Vector3') -> 'Vector3':
        """Cross product."""
        return Vector3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )
    
    def length(self) -> float:
        """Euclidean length."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    
    def length_squared(self) -> float:
        """Squared length (faster when comparing distances)."""
        return self.x**2 + self.y**2 + self.z**2
    
    def normalize(self) -> 'Vector3':
        """Return unit vector."""
        L = self.length()
        if L < 1e-10:
            return Vector3(0, 0, 1)
        return self / L
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.x, self.y, self.z])
    
    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)
    
    @staticmethod
    def from_array(arr: np.ndarray) -> 'Vector3':
        return Vector3(float(arr[0]), float(arr[1]), float(arr[2]))
    
    @staticmethod
    def zero() -> 'Vector3':
        return Vector3(0, 0, 0)
    
    @staticmethod
    def up() -> 'Vector3':
        return Vector3(0, 0, 1)
    
    @staticmethod
    def down() -> 'Vector3':
        return Vector3(0, 0, -1)


# Alias for clarity
Point3 = Vector3


# =============================================================================
# Transform and Rotation
# =============================================================================

@dataclass
class Transform:
    """
    3D transformation: position, rotation, and scale.
    
    Rotation is stored as Euler angles (degrees) in ZYX order (yaw, pitch, roll),
    or as an explicit rotation matrix when provided.
    """
    position: Vector3 = field(default_factory=Vector3.zero)
    rotation: Vector3 = field(default_factory=Vector3.zero)  # Euler angles in degrees
    scale: Vector3 = field(default_factory=lambda: Vector3(1, 1, 1))
    rotation_matrix: Optional[np.ndarray] = None
    
    def get_rotation_matrix(self) -> np.ndarray:
        """Get 3x3 rotation matrix from Euler angles."""
        if self.rotation_matrix is not None:
            return self.rotation_matrix
        rx = math.radians(self.rotation.x)
        ry = math.radians(self.rotation.y)
        rz = math.radians(self.rotation.z)
        
        # Rotation matrices
        Rx = np.array([
            [1, 0, 0],
            [0, math.cos(rx), -math.sin(rx)],
            [0, math.sin(rx), math.cos(rx)]
        ])
        Ry = np.array([
            [math.cos(ry), 0, math.sin(ry)],
            [0, 1, 0],
            [-math.sin(ry), 0, math.cos(ry)]
        ])
        Rz = np.array([
            [math.cos(rz), -math.sin(rz), 0],
            [math.sin(rz), math.cos(rz), 0],
            [0, 0, 1]
        ])
        
        return Rz @ Ry @ Rx

    @classmethod
    def from_euler_zyx(
        cls,
        position: Vector3,
        yaw_deg: float,
        pitch_deg: float,
        roll_deg: float,
        scale: Optional[Vector3] = None,
    ) -> "Transform":
        """
        Build transform from Euler ZYX (yaw, pitch, roll) in degrees.
        """
        rot = Vector3(roll_deg, pitch_deg, yaw_deg)
        return cls(position=position, rotation=rot, scale=scale or Vector3(1, 1, 1))

    @classmethod
    def from_rotation_matrix(
        cls,
        position: Vector3,
        rotation_matrix: np.ndarray,
        scale: Optional[Vector3] = None,
    ) -> "Transform":
        """
        Build transform from an explicit 3x3 rotation matrix.
        """
        return cls(position=position, rotation=Vector3.zero(), scale=scale or Vector3(1, 1, 1), rotation_matrix=rotation_matrix)

    @classmethod
    def from_aim_up(
        cls,
        position: Vector3,
        aim: Vector3,
        up: Vector3,
        scale: Optional[Vector3] = None,
    ) -> "Transform":
        """
        Build transform from aim and up vectors.

        Convention: local -Z points along aim direction (nadir).
        """
        z_axis = (-aim).normalize()
        up_n = up.normalize()
        if abs(z_axis.dot(up_n)) > 0.999:
            up_n = Vector3(0, 1, 0)
            if abs(z_axis.dot(up_n)) > 0.999:
                up_n = Vector3(1, 0, 0)
        x_axis = up_n.cross(z_axis).normalize()
        y_axis = z_axis.cross(x_axis).normalize()
        R = np.array(
            [
                [x_axis.x, y_axis.x, z_axis.x],
                [x_axis.y, y_axis.y, z_axis.y],
                [x_axis.z, y_axis.z, z_axis.z],
            ],
            dtype=float,
        )
        return cls.from_rotation_matrix(position=position, rotation_matrix=R, scale=scale)
    
    def transform_point(self, p: Vector3) -> Vector3:
        """Apply transformation to a point."""
        # Scale
        scaled = Vector3(p.x * self.scale.x, p.y * self.scale.y, p.z * self.scale.z)
        
        # Rotate
        R = self.get_rotation_matrix()
        rotated = Vector3.from_array(R @ scaled.to_array())
        
        # Translate
        return rotated + self.position
    
    def transform_direction(self, d: Vector3) -> Vector3:
        """Apply rotation to a direction (no translation)."""
        R = self.get_rotation_matrix()
        return Vector3.from_array(R @ d.to_array())

    def inverse(self) -> "Transform":
        """
        Invert transform. Scale inversion is supported only when scale is uniform (1,1,1).
        """
        if abs(self.scale.x - 1.0) > 1e-9 or abs(self.scale.y - 1.0) > 1e-9 or abs(self.scale.z - 1.0) > 1e-9:
            raise ValueError("Transform.inverse does not support non-unit scale.")
        R = self.get_rotation_matrix()
        R_inv = R.T
        t = self.position.to_array()
        t_inv = Vector3.from_array(R_inv @ (-t))
        return Transform.from_rotation_matrix(position=t_inv, rotation_matrix=R_inv)


# =============================================================================
# Surface Material
# =============================================================================

class SurfaceType(Enum):
    """Types of surfaces for lighting calculations."""
    DIFFUSE = auto()      # Lambertian diffuse
    SPECULAR = auto()     # Mirror-like
    GLOSSY = auto()       # Partially specular
    TRANSPARENT = auto()  # Glass, etc.
    EMISSIVE = auto()     # Light-emitting


@dataclass
class Material:
    """
    Surface material properties for lighting calculations.
    
    The reflectance values are crucial for accurate inter-reflection
    calculations. Standard values:
    - White paint: 0.8
    - Light gray: 0.5
    - Dark gray: 0.2
    - Carpet: 0.1-0.2
    - Wood floor: 0.2-0.4
    - Acoustic ceiling: 0.7-0.8
    """
    name: str
    reflectance: float = 0.5  # 0-1, fraction of light reflected
    transmittance: float = 0.0  # 0-1, fraction transmitted (for glass)
    specularity: float = 0.0  # 0-1, fraction of specular reflection
    surface_type: SurfaceType = SurfaceType.DIFFUSE
    color: Tuple[float, float, float] = (0.8, 0.8, 0.8)  # RGB 0-1
    
    def __post_init__(self):
        # Ensure physical validity
        self.reflectance = max(0.0, min(1.0, self.reflectance))
        self.transmittance = max(0.0, min(1.0, self.transmittance))
        # Reflectance + transmittance shouldn't exceed 1
        if self.reflectance + self.transmittance > 1.0:
            total = self.reflectance + self.transmittance
            self.reflectance /= total
            self.transmittance /= total


# Standard material library
MATERIALS = {
    'white_paint': Material('White Paint', reflectance=0.80),
    'light_gray': Material('Light Gray', reflectance=0.50),
    'medium_gray': Material('Medium Gray', reflectance=0.30),
    'dark_gray': Material('Dark Gray', reflectance=0.20),
    'white_ceiling': Material('White Ceiling Tile', reflectance=0.75),
    'acoustic_ceiling': Material('Acoustic Ceiling', reflectance=0.70),
    'carpet_dark': Material('Dark Carpet', reflectance=0.10),
    'carpet_medium': Material('Medium Carpet', reflectance=0.20),
    'wood_floor': Material('Wood Floor', reflectance=0.30),
    'concrete': Material('Concrete', reflectance=0.25),
    'glass': Material('Clear Glass', reflectance=0.08, transmittance=0.85, 
                      surface_type=SurfaceType.TRANSPARENT),
    'mirror': Material('Mirror', reflectance=0.90, specularity=1.0,
                      surface_type=SurfaceType.SPECULAR),
}


# =============================================================================
# Polygon and Surface
# =============================================================================

@dataclass
class Polygon:
    """
    A planar polygon defined by vertices in order.
    
    Vertices should be specified in counter-clockwise order when
    viewed from the front (normal pointing toward viewer).
    """
    vertices: List[Vector3]
    
    def __post_init__(self):
        if len(self.vertices) < 3:
            raise ValueError("Polygon requires at least 3 vertices")
    
    @property
    def num_vertices(self) -> int:
        return len(self.vertices)
    
    def get_normal(self) -> Vector3:
        """Calculate surface normal using Newell's method."""
        n = Vector3.zero()
        verts = self.vertices
        num = len(verts)
        
        for i in range(num):
            v_curr = verts[i]
            v_next = verts[(i + 1) % num]
            n = n + Vector3(
                (v_curr.y - v_next.y) * (v_curr.z + v_next.z),
                (v_curr.z - v_next.z) * (v_curr.x + v_next.x),
                (v_curr.x - v_next.x) * (v_curr.y + v_next.y)
            )
        
        return n.normalize()
    
    def get_area(self) -> float:
        """Calculate polygon area using cross product method."""
        if len(self.vertices) < 3:
            return 0.0
        
        # Triangulate from first vertex and sum areas
        total_area = 0.0
        v0 = self.vertices[0]
        
        for i in range(1, len(self.vertices) - 1):
            v1 = self.vertices[i]
            v2 = self.vertices[i + 1]
            
            edge1 = v1 - v0
            edge2 = v2 - v0
            cross = edge1.cross(edge2)
            total_area += cross.length() / 2
        
        return total_area
    
    def get_centroid(self) -> Vector3:
        """Calculate centroid (center of mass)."""
        if not self.vertices:
            return Vector3.zero()
        
        cx = sum(v.x for v in self.vertices) / len(self.vertices)
        cy = sum(v.y for v in self.vertices) / len(self.vertices)
        cz = sum(v.z for v in self.vertices) / len(self.vertices)
        
        return Vector3(cx, cy, cz)
    
    def get_bounding_box(self) -> Tuple[Vector3, Vector3]:
        """Get axis-aligned bounding box as (min_corner, max_corner)."""
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        zs = [v.z for v in self.vertices]
        
        return (
            Vector3(min(xs), min(ys), min(zs)),
            Vector3(max(xs), max(ys), max(zs))
        )
    
    def contains_point_2d(self, point: Vector3) -> bool:
        """
        Check if point lies within polygon (2D projection to XY plane).
        Uses ray casting algorithm.
        """
        x, y = point.x, point.y
        n = len(self.vertices)
        inside = False
        
        j = n - 1
        for i in range(n):
            xi, yi = self.vertices[i].x, self.vertices[i].y
            xj, yj = self.vertices[j].x, self.vertices[j].y
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def sample_point(self) -> Vector3:
        """Sample a random point on the polygon surface."""
        # For simple implementation, return centroid
        # Full implementation would use proper uniform sampling
        return self.get_centroid()
    
    def subdivide(self, max_area: float = 1.0) -> List['Polygon']:
        """
        Subdivide polygon into smaller patches for radiosity.
        
        Args:
            max_area: Maximum area per patch in square meters
            
        Returns:
            List of smaller polygons
        """
        area = self.get_area()
        if area <= max_area:
            return [self]
        
        # Simple subdivision for quads
        if len(self.vertices) == 4:
            v = self.vertices
            mid01 = (v[0] + v[1]) * 0.5
            mid12 = (v[1] + v[2]) * 0.5
            mid23 = (v[2] + v[3]) * 0.5
            mid30 = (v[3] + v[0]) * 0.5
            center = self.get_centroid()
            
            quads = [
                Polygon([v[0], mid01, center, mid30]),
                Polygon([mid01, v[1], mid12, center]),
                Polygon([center, mid12, v[2], mid23]),
                Polygon([mid30, center, mid23, v[3]]),
            ]
            
            result = []
            for q in quads:
                result.extend(q.subdivide(max_area))
            return result
        
        # For triangles
        if len(self.vertices) == 3:
            v = self.vertices
            mid01 = (v[0] + v[1]) * 0.5
            mid12 = (v[1] + v[2]) * 0.5
            mid20 = (v[2] + v[0]) * 0.5
            
            tris = [
                Polygon([v[0], mid01, mid20]),
                Polygon([mid01, v[1], mid12]),
                Polygon([mid20, mid12, v[2]]),
                Polygon([mid01, mid12, mid20]),
            ]
            
            result = []
            for t in tris:
                result.extend(t.subdivide(max_area))
            return result
        
        # For other polygons, return as-is for now
        return [self]


@dataclass
class Surface:
    """
    A surface in the scene with geometry and material.
    
    Surfaces are the fundamental elements for lighting calculations.
    Each surface has:
    - Geometry (polygon)
    - Material properties
    - Calculated/stored radiosity values
    """
    id: str
    polygon: Polygon
    material: Material
    is_emissive: bool = False
    emission: float = 0.0  # Luminous exitance in lm/m² if emissive
    
    # Radiosity calculation values (populated during solve)
    incident_flux: float = 0.0  # Total incident light (lm)
    exitance: float = 0.0  # Outgoing light per unit area (lm/m²)
    illuminance: float = 0.0  # Incident light per unit area (lux)
    
    @property
    def area(self) -> float:
        return self.polygon.get_area()
    
    @property
    def normal(self) -> Vector3:
        return self.polygon.get_normal()
    
    @property
    def centroid(self) -> Vector3:
        return self.polygon.get_centroid()


# =============================================================================
# Room Geometry
# =============================================================================

@dataclass
class Room:
    """
    A room defined by its boundary and height.
    
    The room is represented as an extruded polygon with:
    - Floor at z=0
    - Ceiling at z=height
    - Walls connecting floor to ceiling
    """
    name: str
    floor_vertices: List[Vector3]  # 2D points (z ignored), counter-clockwise
    height: float
    floor_material: Material = field(default_factory=lambda: MATERIALS['carpet_medium'])
    ceiling_material: Material = field(default_factory=lambda: MATERIALS['white_ceiling'])
    wall_material: Material = field(default_factory=lambda: MATERIALS['light_gray'])
    
    def __post_init__(self):
        if len(self.floor_vertices) < 3:
            raise ValueError("Room requires at least 3 floor vertices")
        # Ensure floor vertices are at z=0
        self.floor_vertices = [Vector3(v.x, v.y, 0) for v in self.floor_vertices]
    
    @staticmethod
    def rectangular(
        name: str,
        width: float,
        length: float,
        height: float,
        origin: Vector3 = None,
        **material_kwargs
    ) -> 'Room':
        """Create a rectangular room."""
        if origin is None:
            origin = Vector3.zero()
        
        floor_verts = [
            Vector3(origin.x, origin.y, 0),
            Vector3(origin.x + width, origin.y, 0),
            Vector3(origin.x + width, origin.y + length, 0),
            Vector3(origin.x, origin.y + length, 0),
        ]
        
        return Room(name, floor_verts, height, **material_kwargs)
    
    @property
    def floor_area(self) -> float:
        """Calculate floor area."""
        floor_poly = Polygon(self.floor_vertices)
        return floor_poly.get_area()
    
    @property
    def volume(self) -> float:
        """Calculate room volume."""
        return self.floor_area * self.height
    
    def get_surfaces(self) -> List[Surface]:
        """
        Generate all surfaces (floor, ceiling, walls) for the room.
        
        Returns:
            List of Surface objects ready for lighting calculations
        """
        surfaces = []
        
        # Floor (at z=0, normal pointing up)
        floor_poly = Polygon(self.floor_vertices)
        surfaces.append(Surface(
            id=f"{self.name}_floor",
            polygon=floor_poly,
            material=self.floor_material,
        ))
        
        # Ceiling (at z=height, normal pointing down)
        ceiling_verts = [Vector3(v.x, v.y, self.height) for v in reversed(self.floor_vertices)]
        ceiling_poly = Polygon(ceiling_verts)
        surfaces.append(Surface(
            id=f"{self.name}_ceiling",
            polygon=ceiling_poly,
            material=self.ceiling_material,
        ))
        
        # Walls
        n = len(self.floor_vertices)
        for i in range(n):
            v0 = self.floor_vertices[i]
            v1 = self.floor_vertices[(i + 1) % n]
            
            # Wall vertices (counter-clockwise when viewed from inside)
            wall_verts = [
                Vector3(v0.x, v0.y, 0),
                Vector3(v1.x, v1.y, 0),
                Vector3(v1.x, v1.y, self.height),
                Vector3(v0.x, v0.y, self.height),
            ]
            wall_poly = Polygon(wall_verts)
            
            surfaces.append(Surface(
                id=f"{self.name}_wall_{i}",
                polygon=wall_poly,
                material=self.wall_material,
            ))
        
        return surfaces
    
    def get_bounding_box(self) -> Tuple[Vector3, Vector3]:
        """Get room bounding box."""
        xs = [v.x for v in self.floor_vertices]
        ys = [v.y for v in self.floor_vertices]
        
        return (
            Vector3(min(xs), min(ys), 0),
            Vector3(max(xs), max(ys), self.height)
        )


# =============================================================================
# Scene
# =============================================================================

@dataclass
class Scene:
    """
    A complete lighting scene containing rooms, surfaces, and luminaires.
    
    The scene is the top-level container for all geometry and is passed
    to the calculation engine.
    """
    name: str = "Untitled Scene"
    rooms: List[Room] = field(default_factory=list)
    surfaces: List[Surface] = field(default_factory=list)  # Additional surfaces
    
    def add_room(self, room: Room) -> None:
        """Add a room to the scene."""
        self.rooms.append(room)
    
    def add_surface(self, surface: Surface) -> None:
        """Add a standalone surface to the scene."""
        self.surfaces.append(surface)
    
    def get_all_surfaces(self) -> List[Surface]:
        """Get all surfaces in the scene (from rooms and standalone)."""
        all_surfaces = []
        for room in self.rooms:
            all_surfaces.extend(room.get_surfaces())
        all_surfaces.extend(self.surfaces)
        return all_surfaces
    
    def get_bounding_box(self) -> Tuple[Vector3, Vector3]:
        """Get scene bounding box."""
        if not self.rooms and not self.surfaces:
            return (Vector3.zero(), Vector3.zero())
        
        all_min = Vector3(float('inf'), float('inf'), float('inf'))
        all_max = Vector3(float('-inf'), float('-inf'), float('-inf'))
        
        for room in self.rooms:
            bb_min, bb_max = room.get_bounding_box()
            all_min = Vector3(
                min(all_min.x, bb_min.x),
                min(all_min.y, bb_min.y),
                min(all_min.z, bb_min.z)
            )
            all_max = Vector3(
                max(all_max.x, bb_max.x),
                max(all_max.y, bb_max.y),
                max(all_max.z, bb_max.z)
            )
        
        for surface in self.surfaces:
            bb_min, bb_max = surface.polygon.get_bounding_box()
            all_min = Vector3(
                min(all_min.x, bb_min.x),
                min(all_min.y, bb_min.y),
                min(all_min.z, bb_min.z)
            )
            all_max = Vector3(
                max(all_max.x, bb_max.x),
                max(all_max.y, bb_max.y),
                max(all_max.z, bb_max.z)
            )
        
        return (all_min, all_max)
