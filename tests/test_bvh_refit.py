from __future__ import annotations

from luxera.geometry.accel import MeshInstance, Ray, build_two_level_bvh, ray_intersect, refit_tlas
from luxera.geometry.bvh import Triangle
from luxera.geometry.core import Vector3


def test_bvh_refit_transform_only_update_moves_hit_location() -> None:
    mesh = {
        "m1": [
            Triangle(Vector3(0.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)),
        ]
    }
    instances = [
        MeshInstance(instance_id="i1", mesh_id="m1", transform_4x4=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    ]
    accel = build_two_level_bvh(mesh, instances)
    assert accel.tlas_world is not None

    r0 = Ray(origin=Vector3(0.2, 0.2, 1.0), direction=Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=10.0)
    assert ray_intersect(accel, r0) is not None

    refit_tlas(
        accel,
        {"i1": [[1, 0, 0, 5], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
    )

    assert ray_intersect(accel, r0) is None
    r1 = Ray(origin=Vector3(5.2, 0.2, 1.0), direction=Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=10.0)
    assert ray_intersect(accel, r1) is not None
