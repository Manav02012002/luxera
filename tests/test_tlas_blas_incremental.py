from __future__ import annotations

from luxera.geometry.accel import MeshInstance, Ray, build_two_level_bvh, ray_intersect, refit_tlas
from luxera.geometry.bvh import Triangle
from luxera.geometry.core import Vector3


def test_transform_only_updates_refit_tlas_without_blas_rebuild() -> None:
    mesh = {
        "panel": [
            Triangle(Vector3(0.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)),
            Triangle(Vector3(1.0, 0.0, 0.0), Vector3(1.0, 1.0, 0.0), Vector3(0.0, 1.0, 0.0)),
        ]
    }
    instances = [
        MeshInstance(
            instance_id=f"lum_{i}",
            mesh_id="panel",
            transform_4x4=[[1, 0, 0, float(i) * 2.0], [0, 1, 0, 0.0], [0, 0, 1, 2.5], [0, 0, 0, 1]],
        )
        for i in range(200)
    ]

    scene = build_two_level_bvh(mesh, instances)
    assert scene.tlas_rebuild_count == 1
    assert scene.blas_rebuild_count == 0

    moved = {
        f"lum_{i}": [[1, 0, 0, float(i) * 2.0 + 0.5], [0, 1, 0, 1.25], [0, 0, 1, 2.5], [0, 0, 0, 1]]
        for i in range(200)
    }
    refit_tlas(scene, moved)

    assert scene.tlas_rebuild_count == 1
    assert scene.tlas_refit_count == 1
    assert scene.blas_rebuild_count == 0

    hit = ray_intersect(
        scene,
        Ray(origin=Vector3(0.7, 1.3, 10.0), direction=Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=100.0),
    )
    assert hit is not None
    assert hit.instance_id == "lum_0"
