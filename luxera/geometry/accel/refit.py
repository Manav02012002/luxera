from __future__ import annotations

from typing import Dict, List, Sequence, Set

from luxera.geometry.accel.tlas_blas import MeshInstance, TwoLevelBVH, build_blas, recompute_instance_bounds
from luxera.geometry.bvh import Triangle


def refit_tlas(scene: TwoLevelBVH, new_transforms: Dict[str, List[List[float]]]) -> TwoLevelBVH:
    if not scene.instances:
        return scene

    touched: Set[str] = set()
    for i, inst in enumerate(scene.instances):
        tf = new_transforms.get(inst.instance_id)
        if tf is None:
            continue
        scene.instances[i] = MeshInstance(
            instance_id=inst.instance_id,
            mesh_id=inst.mesh_id,
            transform_4x4=tf,
        )
        touched.add(inst.instance_id)

    if touched:
        recompute_instance_bounds(scene, instance_ids=touched)
        scene.tlas_refit_count += 1
    return scene


def rebuild_affected_blas(scene: TwoLevelBVH, meshes: Dict[str, Sequence[Triangle]]) -> TwoLevelBVH:
    if not meshes:
        return scene

    changed_mesh_ids: Set[str] = set()
    for mesh_id, tris in meshes.items():
        scene.blas[mesh_id] = build_blas(list(tris), mesh_id=mesh_id)
        changed_mesh_ids.add(mesh_id)
        scene.blas_rebuild_count += 1

    touched_instances: Set[str] = {inst.instance_id for inst in scene.instances if inst.mesh_id in changed_mesh_ids}
    if touched_instances:
        recompute_instance_bounds(scene, instance_ids=touched_instances)
        scene.tlas_refit_count += 1
    return scene
