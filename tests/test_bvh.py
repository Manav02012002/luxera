from __future__ import annotations

from luxera.geometry.bvh import Triangle, any_hit, build_bvh, ray_intersects_triangle, triangulate_surfaces
from luxera.geometry.core import Material, Polygon, Surface, Vector3


def test_ray_intersects_triangle_hit_and_miss() -> None:
    tri = Triangle(
        a=Vector3(0.0, 0.0, 0.0),
        b=Vector3(1.0, 0.0, 0.0),
        c=Vector3(0.0, 1.0, 0.0),
    )
    hit_t = ray_intersects_triangle(Vector3(0.2, 0.2, 1.0), Vector3(0.0, 0.0, -1.0), tri, t_min=1e-6, t_max=10.0)
    miss_t = ray_intersects_triangle(Vector3(2.0, 2.0, 1.0), Vector3(0.0, 0.0, -1.0), tri, t_min=1e-6, t_max=10.0)
    assert hit_t is not None
    assert miss_t is None


def test_bvh_any_hit_matches_expected() -> None:
    tris = [
        Triangle(
            a=Vector3(-1.0, -1.0, 0.0),
            b=Vector3(1.0, -1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
        ),
        Triangle(
            a=Vector3(1.0, -1.0, 0.0),
            b=Vector3(1.0, 1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
        ),
    ]
    bvh = build_bvh(tris)
    assert any_hit(bvh, Vector3(0.0, 0.0, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-4, t_max=10.0)
    assert not any_hit(bvh, Vector3(3.0, 3.0, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-4, t_max=10.0)


def test_triangulate_surfaces_fan() -> None:
    s = Surface(
        id="s1",
        polygon=Polygon(
            [
                Vector3(0.0, 0.0, 0.0),
                Vector3(1.0, 0.0, 0.0),
                Vector3(1.0, 1.0, 0.0),
                Vector3(0.0, 1.0, 0.0),
            ]
        ),
        material=Material(name="m", reflectance=0.5),
    )
    tris = triangulate_surfaces([s])
    assert len(tris) == 2
