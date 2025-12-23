"""
Luxera 3D Camera Controller

Orbit camera for navigating 3D lighting scenes.
Supports orbit, pan, and zoom controls.
"""

import math
import numpy as np
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class Camera:
    """
    Orbit camera for 3D scene navigation.
    
    Uses spherical coordinates centered on a target point.
    """
    # Target point (orbit center)
    target: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))
    
    # Spherical coordinates
    distance: float = 10.0  # Distance from target
    azimuth: float = 45.0   # Horizontal angle (degrees)
    elevation: float = 30.0  # Vertical angle (degrees)
    
    # Projection
    fov: float = 45.0       # Field of view (degrees)
    near: float = 0.1       # Near clip plane
    far: float = 1000.0     # Far clip plane
    aspect: float = 1.0     # Aspect ratio (width/height)
    
    # Constraints
    min_distance: float = 1.0
    max_distance: float = 500.0
    min_elevation: float = -89.0
    max_elevation: float = 89.0
    
    @property
    def position(self) -> np.ndarray:
        """Calculate camera position from spherical coordinates."""
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        
        x = self.distance * math.cos(el) * math.sin(az)
        y = self.distance * math.cos(el) * math.cos(az)
        z = self.distance * math.sin(el)
        
        return self.target + np.array([x, y, z])
    
    @property
    def up_vector(self) -> np.ndarray:
        """Get camera up vector."""
        return np.array([0.0, 0.0, 1.0])
    
    @property
    def forward_vector(self) -> np.ndarray:
        """Get normalized forward direction."""
        forward = self.target - self.position
        return forward / np.linalg.norm(forward)
    
    @property
    def right_vector(self) -> np.ndarray:
        """Get normalized right direction."""
        right = np.cross(self.forward_vector, self.up_vector)
        return right / np.linalg.norm(right)
    
    def orbit(self, delta_azimuth: float, delta_elevation: float):
        """Rotate camera around target."""
        self.azimuth += delta_azimuth
        self.elevation = np.clip(
            self.elevation + delta_elevation,
            self.min_elevation,
            self.max_elevation
        )
    
    def pan(self, delta_x: float, delta_y: float):
        """Pan camera (move target)."""
        right = self.right_vector
        up = np.array([0.0, 0.0, 1.0])
        
        scale = self.distance * 0.002
        self.target += right * delta_x * scale
        self.target += up * delta_y * scale
    
    def zoom(self, delta: float):
        """Zoom in/out (change distance)."""
        factor = 1.0 - delta * 0.1
        self.distance = np.clip(
            self.distance * factor,
            self.min_distance,
            self.max_distance
        )
    
    def fit_to_bounds(self, min_bound: np.ndarray, max_bound: np.ndarray):
        """Fit camera to view bounding box."""
        center = (min_bound + max_bound) / 2
        size = np.linalg.norm(max_bound - min_bound)
        
        self.target = center
        self.distance = size * 1.5
        self.azimuth = 45.0
        self.elevation = 30.0
    
    def get_view_matrix(self) -> np.ndarray:
        """Get 4x4 view matrix."""
        pos = self.position
        target = self.target
        up = self.up_vector
        
        # Look-at matrix
        f = target - pos
        f = f / np.linalg.norm(f)
        
        s = np.cross(f, up)
        s = s / np.linalg.norm(s)
        
        u = np.cross(s, f)
        
        view = np.eye(4, dtype=np.float32)
        view[0, :3] = s
        view[1, :3] = u
        view[2, :3] = -f
        view[0, 3] = -np.dot(s, pos)
        view[1, 3] = -np.dot(u, pos)
        view[2, 3] = np.dot(f, pos)
        
        return view
    
    def get_projection_matrix(self) -> np.ndarray:
        """Get 4x4 perspective projection matrix."""
        f = 1.0 / math.tan(math.radians(self.fov) / 2)
        
        proj = np.zeros((4, 4), dtype=np.float32)
        proj[0, 0] = f / self.aspect
        proj[1, 1] = f
        proj[2, 2] = (self.far + self.near) / (self.near - self.far)
        proj[2, 3] = (2 * self.far * self.near) / (self.near - self.far)
        proj[3, 2] = -1.0
        
        return proj
