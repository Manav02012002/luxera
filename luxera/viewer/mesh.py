"""
Luxera 3D Mesh

Mesh data structures for OpenGL rendering.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum, auto

from luxera.geometry.lod import build_lod
from luxera.geometry.mesh import TriMesh


class PrimitiveType(Enum):
    """OpenGL primitive types."""
    TRIANGLES = auto()
    LINES = auto()
    POINTS = auto()


@dataclass
class Mesh:
    """
    3D mesh for OpenGL rendering.
    
    Stores vertices, normals, colors, and indices.
    """
    vertices: np.ndarray  # Nx3 float32
    normals: np.ndarray   # Nx3 float32
    colors: np.ndarray    # Nx3 float32
    indices: np.ndarray   # Mx3 uint32 (triangles)
    
    primitive_type: PrimitiveType = PrimitiveType.TRIANGLES
    
    # OpenGL buffer IDs (set during upload)
    vao: int = 0
    vbo_vertices: int = 0
    vbo_normals: int = 0
    vbo_colors: int = 0
    ebo: int = 0
    
    @property
    def num_vertices(self) -> int:
        return len(self.vertices)
    
    @property
    def num_indices(self) -> int:
        return len(self.indices.flatten())
    
    def get_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get bounding box (min, max)."""
        return self.vertices.min(axis=0), self.vertices.max(axis=0)


def create_box_mesh(
    width: float, length: float, height: float,
    color: Tuple[float, float, float] = (0.7, 0.7, 0.7),
    origin: Tuple[float, float, float] = (0, 0, 0)
) -> Mesh:
    """Create a box mesh."""
    x, y, z = origin
    w, l, h = width, length, height
    
    # 8 corners
    corners = np.array([
        [x, y, z],
        [x+w, y, z],
        [x+w, y+l, z],
        [x, y+l, z],
        [x, y, z+h],
        [x+w, y, z+h],
        [x+w, y+l, z+h],
        [x, y+l, z+h],
    ], dtype=np.float32)
    
    # 6 faces, 2 triangles each = 12 triangles, 36 vertices
    faces = [
        ([0,1,2,3], [0,0,-1]),  # Bottom
        ([4,7,6,5], [0,0,1]),   # Top
        ([0,4,5,1], [0,-1,0]),  # Front
        ([2,6,7,3], [0,1,0]),   # Back
        ([0,3,7,4], [-1,0,0]),  # Left
        ([1,5,6,2], [1,0,0]),   # Right
    ]
    
    vertices = []
    normals = []
    indices = []
    
    idx = 0
    for face_indices, normal in faces:
        for i in face_indices:
            vertices.append(corners[i])
            normals.append(normal)
        
        # Two triangles per face
        indices.append([idx, idx+1, idx+2])
        indices.append([idx, idx+2, idx+3])
        idx += 4
    
    vertices = np.array(vertices, dtype=np.float32)
    normals = np.array(normals, dtype=np.float32)
    colors = np.full((len(vertices), 3), color, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    
    return Mesh(vertices, normals, colors, indices)


def create_room_mesh(
    width: float, length: float, height: float,
    floor_color: Tuple[float, float, float] = (0.3, 0.3, 0.35),
    wall_color: Tuple[float, float, float] = (0.8, 0.8, 0.75),
    ceiling_color: Tuple[float, float, float] = (0.9, 0.9, 0.85),
) -> Mesh:
    """Create room interior mesh (floor, walls, ceiling visible from inside)."""
    w, l, h = width, length, height
    
    vertices = []
    normals = []
    colors = []
    indices = []
    idx = 0
    
    def add_quad(v0, v1, v2, v3, normal, color):
        nonlocal idx
        for v in [v0, v1, v2, v3]:
            vertices.append(v)
            normals.append(normal)
            colors.append(color)
        indices.append([idx, idx+1, idx+2])
        indices.append([idx, idx+2, idx+3])
        idx += 4
    
    # Floor (normal up)
    add_quad([0,0,0], [w,0,0], [w,l,0], [0,l,0], [0,0,1], floor_color)
    
    # Ceiling (normal down)
    add_quad([0,0,h], [0,l,h], [w,l,h], [w,0,h], [0,0,-1], ceiling_color)
    
    # Walls (normals inward)
    add_quad([0,0,0], [0,l,0], [0,l,h], [0,0,h], [1,0,0], wall_color)   # Left
    add_quad([w,0,0], [w,0,h], [w,l,h], [w,l,0], [-1,0,0], wall_color)  # Right
    add_quad([0,0,0], [0,0,h], [w,0,h], [w,0,0], [0,1,0], wall_color)   # Front
    add_quad([0,l,0], [w,l,0], [w,l,h], [0,l,h], [0,-1,0], wall_color)  # Back
    
    return Mesh(
        np.array(vertices, dtype=np.float32),
        np.array(normals, dtype=np.float32),
        np.array(colors, dtype=np.float32),
        np.array(indices, dtype=np.uint32),
    )


def create_grid_mesh(
    size: float = 20.0,
    divisions: int = 20,
    color: Tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> Mesh:
    """Create a ground grid mesh."""
    half = size / 2
    step = size / divisions
    
    vertices = []
    
    for i in range(divisions + 1):
        p = -half + i * step
        # X-parallel lines
        vertices.append([-half, p, 0])
        vertices.append([half, p, 0])
        # Y-parallel lines
        vertices.append([p, -half, 0])
        vertices.append([p, half, 0])
    
    vertices = np.array(vertices, dtype=np.float32)
    normals = np.zeros_like(vertices)
    colors = np.full((len(vertices), 3), color, dtype=np.float32)
    
    # Line indices
    indices = np.arange(len(vertices), dtype=np.uint32).reshape(-1, 2)
    
    mesh = Mesh(vertices, normals, colors, indices)
    mesh.primitive_type = PrimitiveType.LINES
    return mesh


def create_luminaire_mesh(
    width: float = 0.6,
    length: float = 0.6,
    height: float = 0.08,
    color: Tuple[float, float, float] = (1.0, 1.0, 0.8),
) -> Mesh:
    """Create a simple luminaire box mesh."""
    return create_box_mesh(width, length, height, color, (-width/2, -length/2, -height))


def create_sphere_mesh(
    radius: float = 0.1,
    segments: int = 16,
    color: Tuple[float, float, float] = (1.0, 0.8, 0.2),
) -> Mesh:
    """Create a sphere mesh (for point light visualization)."""
    vertices = []
    normals = []
    indices = []
    
    for i in range(segments + 1):
        lat = np.pi * (-0.5 + float(i) / segments)
        z = radius * np.sin(lat)
        r = radius * np.cos(lat)
        
        for j in range(segments + 1):
            lon = 2 * np.pi * float(j) / segments
            x = r * np.cos(lon)
            y = r * np.sin(lon)
            
            vertices.append([x, y, z])
            normal = np.array([x, y, z]) / radius
            normals.append(normal)
    
    for i in range(segments):
        for j in range(segments):
            p1 = i * (segments + 1) + j
            p2 = p1 + (segments + 1)
            
            indices.append([p1, p2, p1 + 1])
            indices.append([p1 + 1, p2, p2 + 1])
    
    vertices = np.array(vertices, dtype=np.float32)
    normals = np.array(normals, dtype=np.float32)
    colors = np.full((len(vertices), 3), color, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    
    return Mesh(vertices, normals, colors, indices)


def mesh_from_trimesh(
    tri: TriMesh,
    *,
    color: Tuple[float, float, float] = (0.7, 0.7, 0.7),
    use_lod: bool = True,
    lod_ratio: float = 0.4,
) -> Mesh:
    src = build_lod(tri, viewport_ratio=lod_ratio).simplified if use_lod else tri
    vertices = np.asarray(src.vertices, dtype=np.float32)
    if len(vertices) == 0:
        vertices = np.zeros((0, 3), dtype=np.float32)
    indices = np.asarray(src.faces, dtype=np.uint32)
    if indices.size == 0:
        indices = np.zeros((0, 3), dtype=np.uint32)

    normals = np.zeros_like(vertices, dtype=np.float32)
    for a, b, c in indices.tolist():
        va = vertices[a]
        vb = vertices[b]
        vc = vertices[c]
        n = np.cross(vb - va, vc - va)
        ln = float(np.linalg.norm(n))
        if ln > 0.0:
            n = n / ln
        normals[a] += n
        normals[b] += n
        normals[c] += n
    nl = np.linalg.norm(normals, axis=1, keepdims=True)
    nl[nl == 0.0] = 1.0
    normals = normals / nl
    colors = np.full((len(vertices), 3), color, dtype=np.float32)
    return Mesh(vertices=vertices, normals=normals, colors=colors, indices=indices)
