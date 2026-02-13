from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from luxera.geometry.bvh import BVHNode, Triangle, build_bvh, ray_intersects_triangle
from luxera.geometry.core import Vector3
from luxera.geometry.mesh import TriMesh
from luxera.geometry.tolerance import EPS_POS


Point3 = Tuple[float, float, float]


@dataclass(frozen=True)
class Ray:
    origin: Vector3
    direction: Vector3
    t_min: float = EPS_POS
    t_max: float = 1.0 / EPS_POS


@dataclass(frozen=True)
class RayHit:
    t: float
    triangle: Triangle
    instance_id: Optional[str]
    mesh_id: Optional[str]


@dataclass
class MeshBLAS:
    mesh_id: str
    triangles_local: List[Triangle]
    bvh_local: Optional[BVHNode]


@dataclass
class MeshInstance:
    instance_id: str
    mesh_id: str
    transform_4x4: List[List[float]]


@dataclass
class TLAS:
    instances: List[MeshInstance] = field(default_factory=list)
    triangles_world: List[Triangle] = field(default_factory=list)
    bvh_world: Optional[BVHNode] = None


@dataclass
class TwoLevelBVH:
    blas: Dict[str, MeshBLAS] = field(default_factory=dict)
    tlas: TLAS = field(default_factory=TLAS)

    # Back-compat aliases used in existing code/tests.
    @property
    def instances(self) -> List[MeshInstance]:
        return self.tlas.instances

    @instances.setter
    def instances(self, value: List[MeshInstance]) -> None:
        self.tlas.instances = value

    @property
    def triangles_world(self) -> List[Triangle]:
        return self.tlas.triangles_world

    @triangles_world.setter
    def triangles_world(self, value: List[Triangle]) -> None:
        self.tlas.triangles_world = value

    @property
    def tlas_world(self) -> Optional[BVHNode]:
        return self.tlas.bvh_world

    @tlas_world.setter
    def tlas_world(self, value: Optional[BVHNode]) -> None:
        self.tlas.bvh_world = value


def _tx_point(m: np.ndarray, p: Vector3) -> Vector3:
    v = np.array([p.x, p.y, p.z, 1.0], dtype=float)
    o = m @ v
    return Vector3(float(o[0]), float(o[1]), float(o[2]))


def _triangles_from_trimesh(mesh: TriMesh, payload: Any = None) -> List[Triangle]:
    tris: List[Triangle] = []
    for a, b, c in mesh.faces:
        tris.append(
            Triangle(
                a=Vector3(*mesh.vertices[a]),
                b=Vector3(*mesh.vertices[b]),
                c=Vector3(*mesh.vertices[c]),
                payload=payload,
                two_sided=True,
            )
        )
    return tris


def build_blas(mesh: TriMesh | Sequence[Triangle], mesh_id: str = "mesh") -> MeshBLAS:
    if isinstance(mesh, TriMesh):
        triangles = _triangles_from_trimesh(mesh, payload=mesh_id)
    else:
        triangles = list(mesh)
    return MeshBLAS(mesh_id=str(mesh_id), triangles_local=triangles, bvh_local=(build_bvh(triangles) if triangles else None))


def build_tlas(instances: Sequence[MeshInstance], blas: Dict[str, MeshBLAS]) -> TLAS:
    world_tris: List[Triangle] = []
    for inst in instances:
        b = blas.get(inst.mesh_id)
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
    return TLAS(instances=list(instances), triangles_world=world_tris, bvh_world=(build_bvh(world_tris) if world_tris else None))


def build_two_level_bvh(meshes: Dict[str, Sequence[Triangle]], instances: Sequence[MeshInstance]) -> TwoLevelBVH:
    blas = {mid: build_blas(list(tris), mesh_id=mid) for mid, tris in meshes.items()}
    tlas = build_tlas(instances, blas=blas)
    return TwoLevelBVH(blas=blas, tlas=tlas)


def ray_intersect(scene: TwoLevelBVH | TLAS, ray: Ray) -> Optional[RayHit]:
    if isinstance(scene, TwoLevelBVH):
        bvh = scene.tlas.bvh_world
        triangles = scene.tlas.triangles_world
    else:
        bvh = scene.bvh_world
        triangles = scene.triangles_world

    # BVH query utility is list-returning in current code; keep simple candidate list.
    if bvh is None or not triangles:
        return None

    from luxera.geometry.bvh import query_triangles

    candidates = query_triangles(bvh, ray.origin, ray.direction, t_min=float(ray.t_min), t_max=float(ray.t_max))
    best: Optional[RayHit] = None
    best_t = float(ray.t_max)
    for tri in candidates:
        t = ray_intersects_triangle(ray.origin, ray.direction, tri, t_min=float(ray.t_min), t_max=best_t)
        if t is None:
            continue
        payload = tri.payload if isinstance(tri.payload, dict) else {}
        hit = RayHit(t=float(t), triangle=tri, instance_id=payload.get("instance_id"), mesh_id=payload.get("mesh_id"))
        if hit.t < best_t:
            best_t = hit.t
            best = hit
    return best
