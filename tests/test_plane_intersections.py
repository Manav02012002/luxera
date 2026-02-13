from __future__ import annotations

from luxera.geometry.mesh import extrusion_to_trimesh
from luxera.geometry.primitives import Extrusion, Polygon2D
from luxera.geometry.views.intersect import Plane, intersect_trimesh_with_plane, stitch_segments_to_polylines


def test_intersect_trimesh_with_plan_plane_and_stitch() -> None:
    mesh = extrusion_to_trimesh(
        Extrusion(profile2d=Polygon2D(points=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]), height=3.0)
    )
    segs = intersect_trimesh_with_plane(mesh, Plane(origin=(0.0, 0.0, 1.5), normal=(0.0, 0.0, 1.0)))
    assert segs
    polys = stitch_segments_to_polylines(segs)
    assert polys
    assert any(len(p.points) >= 4 for p in polys)
