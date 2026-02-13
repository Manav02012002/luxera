"""
Luxera Geometry Module

Provides 3D geometry primitives, room modeling, and scene representation.
"""

from __future__ import annotations

from typing import Any

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
    "Triangle",
    "AABB",
    "BVHNode",
    "build_bvh",
    "ray_intersects_triangle",
    "triangulate_surfaces",
    "TriangulationConfig",
    "merge_vertices",
    "normalize_faces",
    "triangulate_face",
    "triangulate_faces",
    "triangulate_polygon_vertices",
    "canonicalize_mesh",
    "Polyline2D",
    "Polygon2D",
    "Arc2D",
    "Circle2D",
    "RoomFootprint2D",
    "Opening2D",
    "Extrusion",
    "TriMesh",
    "ManifoldMesh",
    "extrusion_to_trimesh",
    "stable_id",
    "derived_id",
    "assert_valid_polygon",
    "assert_orthonormal_basis",
    "assert_surface",
]


def __getattr__(name: str) -> Any:
    if name in {
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
    }:
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
        return {
            "Vector3": Vector3,
            "Point3": Point3,
            "Transform": Transform,
            "Material": Material,
            "SurfaceType": SurfaceType,
            "MATERIALS": MATERIALS,
            "Polygon": Polygon,
            "Surface": Surface,
            "Room": Room,
            "Scene": Scene,
        }[name]

    if name in {"Polyline2D", "Polygon2D", "Arc2D", "Circle2D", "RoomFootprint2D", "Opening2D", "Extrusion"}:
        from luxera.geometry.primitives import Arc2D, Circle2D, Extrusion, Opening2D, Polygon2D, Polyline2D, RoomFootprint2D
        return {
            "Polyline2D": Polyline2D,
            "Polygon2D": Polygon2D,
            "Arc2D": Arc2D,
            "Circle2D": Circle2D,
            "RoomFootprint2D": RoomFootprint2D,
            "Opening2D": Opening2D,
            "Extrusion": Extrusion,
        }[name]

    if name in {"TriMesh", "ManifoldMesh", "extrusion_to_trimesh"}:
        from luxera.geometry.mesh import ManifoldMesh, TriMesh, extrusion_to_trimesh
        return {
            "TriMesh": TriMesh,
            "ManifoldMesh": ManifoldMesh,
            "extrusion_to_trimesh": extrusion_to_trimesh,
        }[name]

    if name in {"stable_id", "derived_id"}:
        from luxera.geometry.id import derived_id, stable_id
        return {
            "stable_id": stable_id,
            "derived_id": derived_id,
        }[name]

    if name in {"assert_valid_polygon", "assert_orthonormal_basis", "assert_surface"}:
        from luxera.geometry.contracts import assert_orthonormal_basis, assert_surface, assert_valid_polygon
        return {
            "assert_valid_polygon": assert_valid_polygon,
            "assert_orthonormal_basis": assert_orthonormal_basis,
            "assert_surface": assert_surface,
        }[name]

    if name in {
        "clean_scene_surfaces",
        "detect_room_volumes_from_surfaces",
        "fix_surface_normals",
        "close_tiny_gaps",
        "merge_coplanar_surfaces",
        "detect_non_manifold_edges",
        "ScenePrepReport",
    }:
        from luxera.geometry.scene_prep import (
            clean_scene_surfaces,
            detect_room_volumes_from_surfaces,
            fix_surface_normals,
            close_tiny_gaps,
            merge_coplanar_surfaces,
            detect_non_manifold_edges,
            ScenePrepReport,
        )
        return {
            "clean_scene_surfaces": clean_scene_surfaces,
            "detect_room_volumes_from_surfaces": detect_room_volumes_from_surfaces,
            "fix_surface_normals": fix_surface_normals,
            "close_tiny_gaps": close_tiny_gaps,
            "merge_coplanar_surfaces": merge_coplanar_surfaces,
            "detect_non_manifold_edges": detect_non_manifold_edges,
            "ScenePrepReport": ScenePrepReport,
        }[name]

    if name in {"Triangle", "AABB", "BVHNode", "build_bvh", "ray_intersects_triangle", "triangulate_surfaces"}:
        from luxera.geometry.bvh import Triangle, AABB, BVHNode, build_bvh, ray_intersects_triangle, triangulate_surfaces
        return {
            "Triangle": Triangle,
            "AABB": AABB,
            "BVHNode": BVHNode,
            "build_bvh": build_bvh,
            "ray_intersects_triangle": ray_intersects_triangle,
            "triangulate_surfaces": triangulate_surfaces,
        }[name]

    if name in {
        "TriangulationConfig",
        "merge_vertices",
        "normalize_faces",
        "triangulate_face",
        "triangulate_faces",
        "triangulate_polygon_vertices",
        "canonicalize_mesh",
    }:
        from luxera.geometry.triangulate import (
            TriangulationConfig,
            canonicalize_mesh,
            merge_vertices,
            normalize_faces,
            triangulate_face,
            triangulate_faces,
            triangulate_polygon_vertices,
        )
        return {
            "TriangulationConfig": TriangulationConfig,
            "merge_vertices": merge_vertices,
            "normalize_faces": normalize_faces,
            "triangulate_face": triangulate_face,
            "triangulate_faces": triangulate_faces,
            "triangulate_polygon_vertices": triangulate_polygon_vertices,
            "canonicalize_mesh": canonicalize_mesh,
        }[name]

    raise AttributeError(name)
