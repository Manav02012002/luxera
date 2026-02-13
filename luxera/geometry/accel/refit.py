from __future__ import annotations

from typing import Dict, List

import numpy as np

from luxera.geometry.accel.tlas_blas import MeshInstance, TwoLevelBVH
from luxera.geometry.bvh import Triangle, build_bvh, refit_bvh
from luxera.geometry.core import Vector3


def _tx_point(m: np.ndarray, p: Vector3) -> Vector3:
    v = np.array([p.x, p.y, p.z, 1.0], dtype=float)
    o = m @ v
    return Vector3(float(o[0]), float(o[1]), float(o[2]))


def refit_tlas(scene: TwoLevelBVH, new_transforms: Dict[str, List[List[float]]]) -> TwoLevelBVH:
    if not scene.instances:
        return scene

    for i, inst in enumerate(scene.instances):
        if inst.instance_id in new_transforms:
            scene.instances[i] = MeshInstance(
                instance_id=inst.instance_id,
                mesh_id=inst.mesh_id,
                transform_4x4=new_transforms[inst.instance_id],
            )

    world_tris: List[Triangle] = []
    for inst in scene.instances:
        b = scene.blas.get(inst.mesh_id)
        if b is None:
            continue
        m = np.asarray(inst.transform_4x4, dtype=float).reshape(4, 4)
        for t in b.triangles_local:
            world_tris.append(
                Triangle(
                    a=_tx_point(m, t.a),
                    b=_tx_point(m, t.b),
                    c=_tx_point(m, t.c),
                    payload={"instance_id": inst.instance_id, "mesh_id": inst.mesh_id, "payload": t.payload},
                    two_sided=bool(getattr(t, "two_sided", True)),
                )
            )

    scene.triangles_world = world_tris
    if scene.tlas_world is None:
        scene.tlas_world = build_bvh(world_tris) if world_tris else None
    else:
        # Reassign leaves via rebuild currently; then refit to satisfy contract path.
        scene.tlas_world = build_bvh(world_tris) if world_tris else None
        if scene.tlas_world is not None:
            refit_bvh(scene.tlas_world)
    return scene
