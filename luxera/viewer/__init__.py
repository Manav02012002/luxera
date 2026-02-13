"""
Luxera 3D Viewer Module

OpenGL-based 3D visualization for lighting scenes.
"""

from luxera.viewer.camera import Camera
from luxera.viewer.mesh import (
    Mesh, 
    PrimitiveType,
    create_box_mesh,
    create_room_mesh,
    create_grid_mesh,
    create_luminaire_mesh,
    create_sphere_mesh,
    mesh_from_trimesh,
)
from luxera.viewer.renderer import Renderer, SceneObject

__all__ = [
    "Camera",
    "Mesh",
    "PrimitiveType",
    "create_box_mesh",
    "create_room_mesh",
    "create_grid_mesh",
    "create_luminaire_mesh",
    "create_sphere_mesh",
    "mesh_from_trimesh",
    "Renderer",
    "SceneObject",
]

try:
    from luxera.viewer.widget import LuxeraGLWidget, create_demo_scene
except ImportError:
    pass
else:
    __all__.extend(["LuxeraGLWidget", "create_demo_scene"])
