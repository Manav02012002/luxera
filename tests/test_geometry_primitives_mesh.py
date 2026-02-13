from __future__ import annotations

from luxera.geometry.mesh import extrusion_to_trimesh
from luxera.geometry.primitives import Extrusion, Polygon2D


def test_extrusion_to_trimesh_generates_valid_mesh() -> None:
    ext = Extrusion(profile2d=Polygon2D(points=[(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)]), height=3.0)
    mesh = extrusion_to_trimesh(ext)
    mesh.validate()
    assert len(mesh.vertices) == 8
    assert len(mesh.faces) >= 8

