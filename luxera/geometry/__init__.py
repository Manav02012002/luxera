"""
Luxera Geometry Module

Provides 3D geometry primitives, room modeling, and scene representation.
"""

from luxera.geometry.core import (
    Vector3,
    Point3,
    Transform,
    Material,
    SurfaceType,
    MATERIALS,
    Polygon,
    Surface,
    Room,
    Scene,
)
from luxera.geometry.scene_prep import (
    clean_scene_surfaces,
    detect_room_volumes_from_surfaces,
    fix_surface_normals,
    close_tiny_gaps,
    merge_coplanar_surfaces,
    detect_non_manifold_edges,
    ScenePrepReport,
)

__all__ = [
    "Vector3",
    "Point3",
    "Transform",
    "Material",
    "SurfaceType",
    "MATERIALS",
    "Polygon",
    "Surface",
    "Room",
    "Scene",
    "clean_scene_surfaces",
    "detect_room_volumes_from_surfaces",
    "fix_surface_normals",
    "close_tiny_gaps",
    "merge_coplanar_surfaces",
    "detect_non_manifold_edges",
    "ScenePrepReport",
]
