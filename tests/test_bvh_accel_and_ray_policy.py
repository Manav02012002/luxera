from __future__ import annotations

from luxera.engine.direct_illuminance import build_direct_occlusion_context, update_occlusion_instance_transforms
from luxera.geometry.accel import MeshInstance, Ray, build_two_level_bvh, refit_two_level_bvh, ray_intersect
from luxera.geometry.bvh import Triangle, ray_intersects_triangle
from luxera.geometry.core import Vector3
from luxera.project.schema import Project, SurfaceSpec


def test_ray_intersection_single_vs_double_sided() -> None:
    tri = Triangle(
        a=Vector3(0.0, 0.0, 0.0),
        b=Vector3(1.0, 0.0, 0.0),
        c=Vector3(0.0, 1.0, 0.0),
        two_sided=False,
    )
    # Ray from below points up: backface for winding above.
    hit_single = ray_intersects_triangle(Vector3(0.2, 0.2, -1.0), Vector3(0.0, 0.0, 1.0), tri, two_sided=False)
    hit_double = ray_intersects_triangle(Vector3(0.2, 0.2, -1.0), Vector3(0.0, 0.0, 1.0), tri, two_sided=True)
    assert hit_single is None
    assert hit_double is not None


def test_direct_occlusion_context_cache_reuses_static_geometry() -> None:
    p = Project(name="cache")
    p.geometry.surfaces.append(
        SurfaceSpec(id="s1", name="S1", kind="wall", vertices=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0)])
    )
    c1 = build_direct_occlusion_context(p)
    c2 = build_direct_occlusion_context(p)
    assert len(c1.triangles) == len(c2.triangles)
    assert c1.two_level is not None
    c3 = update_occlusion_instance_transforms(c1, {})
    assert c3.bvh is not None


def test_two_level_bvh_refit_for_instance_transforms() -> None:
    mesh = {
        "m1": [
            Triangle(Vector3(0.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)),
        ]
    }
    inst = [
        MeshInstance(instance_id="i1", mesh_id="m1", transform_4x4=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    ]
    accel = build_two_level_bvh(mesh, inst)
    r = Ray(origin=Vector3(0.1, 0.1, 1.0), direction=Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=10.0)
    assert ray_intersect(accel, r) is not None
    refit_two_level_bvh(
        accel,
        {"i1": [[1, 0, 0, 5], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
    )
    assert ray_intersect(accel, r) is None
