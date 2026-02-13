from __future__ import annotations

from luxera.geometry.accel import MeshInstance, Ray, build_two_level_bvh, ray_intersect
from luxera.geometry.bvh import Triangle, any_hit, build_bvh
from luxera.geometry.core import Vector3


def test_tlas_blas_equivalence_with_flattened_bvh() -> None:
    mesh = {
        "m1": [
            Triangle(Vector3(0.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)),
            Triangle(Vector3(1.0, 0.0, 0.0), Vector3(1.0, 1.0, 0.0), Vector3(0.0, 1.0, 0.0)),
        ]
    }
    instances = [
        MeshInstance(instance_id="i1", mesh_id="m1", transform_4x4=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]),
        MeshInstance(instance_id="i2", mesh_id="m1", transform_4x4=[[1, 0, 0, 3], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]),
    ]

    two = build_two_level_bvh(mesh, instances)
    assert two.tlas_world is not None

    flat_bvh = build_bvh(two.triangles_world)
    rays = [
        (Vector3(0.25, 0.25, 1.0), Vector3(0.0, 0.0, -1.0)),
        (Vector3(3.25, 0.25, 1.0), Vector3(0.0, 0.0, -1.0)),
        (Vector3(1.75, 0.25, 1.0), Vector3(0.0, 0.0, -1.0)),
    ]

    for o, d in rays:
        h_flat = any_hit(flat_bvh, o, d, t_min=1e-6, t_max=10.0)
        h_two = ray_intersect(two, Ray(origin=o, direction=d, t_min=1e-6, t_max=10.0)) is not None
        assert h_flat == h_two
