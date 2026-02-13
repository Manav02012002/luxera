from __future__ import annotations

import numpy as np

from luxera.geometry.openings.subtract import UVPolygon
from luxera.geometry.openings.triangulate_wall import triangulate_polygon_with_holes, wall_mesh_from_uv


def test_wall_triangulation_with_hole_produces_valid_mesh() -> None:
    poly = UVPolygon(
        outer=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
        holes=[[(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]],
    )
    faces = triangulate_polygon_with_holes(poly)
    assert faces

    mesh = wall_mesh_from_uv(
        poly,
        origin=np.array([0.0, 0.0, 0.0]),
        u=np.array([1.0, 0.0, 0.0]),
        v=np.array([0.0, 0.0, 1.0]),
    )
    assert mesh.faces
    mesh.validate()
