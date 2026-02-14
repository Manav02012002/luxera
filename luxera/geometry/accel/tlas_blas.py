from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from luxera.geometry.bvh import AABB, BVHNode, Triangle, build_bvh, merge_aabbs, query_triangles, ray_intersects_triangle
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
    bounds_local: Optional[AABB]


@dataclass
class MeshInstance:
    instance_id: str
    mesh_id: str
    transform_4x4: List[List[float]]


@dataclass
class TLASNode:
    aabb: AABB
    left: Optional["TLASNode"] = None
    right: Optional["TLASNode"] = None
    instance_indices: Optional[List[int]] = None


@dataclass
class TLAS:
    instances: List[MeshInstance] = field(default_factory=list)
    instance_bounds: List[Optional[AABB]] = field(default_factory=list)
    instance_tree: Optional[TLASNode] = None
    # Back-compat placeholders for older call-sites.
    triangles_world: List[Triangle] = field(default_factory=list)
    bvh_world: Optional[BVHNode] = None


@dataclass
class TwoLevelBVH:
    blas: Dict[str, MeshBLAS] = field(default_factory=dict)
    tlas: TLAS = field(default_factory=TLAS)
    # Diagnostic counters to validate incremental behavior.
    tlas_rebuild_count: int = 0
    tlas_refit_count: int = 0
    blas_rebuild_count: int = 0

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


def _tx_dir(m: np.ndarray, d: Vector3) -> Vector3:
    v = np.array([d.x, d.y, d.z, 0.0], dtype=float)
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


def _transform_aabb(local: AABB, m: np.ndarray) -> AABB:
    mn = local.min
    mx = local.max
    corners = [
        Vector3(mn.x, mn.y, mn.z),
        Vector3(mx.x, mn.y, mn.z),
        Vector3(mn.x, mx.y, mn.z),
        Vector3(mx.x, mx.y, mn.z),
        Vector3(mn.x, mn.y, mx.z),
        Vector3(mx.x, mn.y, mx.z),
        Vector3(mn.x, mx.y, mx.z),
        Vector3(mx.x, mx.y, mx.z),
    ]
    tx = [_tx_point(m, c) for c in corners]
    xs = [p.x for p in tx]
    ys = [p.y for p in tx]
    zs = [p.z for p in tx]
    return AABB(min=Vector3(min(xs), min(ys), min(zs)), max=Vector3(max(xs), max(ys), max(zs)))


def _instance_bounds(inst: MeshInstance, blas: Dict[str, MeshBLAS]) -> Optional[AABB]:
    b = blas.get(inst.mesh_id)
    if b is None or b.bounds_local is None:
        return None
    m = np.asarray(inst.transform_4x4, dtype=float).reshape(4, 4)
    return _transform_aabb(b.bounds_local, m)


def _build_tlas_tree(indices: List[int], bounds: List[Optional[AABB]], max_leaf: int = 8) -> Optional[TLASNode]:
    present = [i for i in indices if bounds[i] is not None]
    if not present:
        return None
    if len(present) <= max_leaf:
        return TLASNode(
            aabb=merge_aabbs([bounds[i] for i in present if bounds[i] is not None]),
            instance_indices=present,
        )

    cents = [
        Vector3(
            (bounds[i].min.x + bounds[i].max.x) * 0.5,
            (bounds[i].min.y + bounds[i].max.y) * 0.5,
            (bounds[i].min.z + bounds[i].max.z) * 0.5,
        )
        for i in present
        if bounds[i] is not None
    ]
    xs = [c.x for c in cents]
    ys = [c.y for c in cents]
    zs = [c.z for c in cents]
    spans = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    axis = spans.index(max(spans))
    key = (
        (lambda idx: (bounds[idx].min.x + bounds[idx].max.x) * 0.5)
        if axis == 0
        else (lambda idx: (bounds[idx].min.y + bounds[idx].max.y) * 0.5)
        if axis == 1
        else (lambda idx: (bounds[idx].min.z + bounds[idx].max.z) * 0.5)
    )
    ordered = sorted(present, key=key)
    mid = len(ordered) // 2
    left = _build_tlas_tree(ordered[:mid], bounds=bounds, max_leaf=max_leaf)
    right = _build_tlas_tree(ordered[mid:], bounds=bounds, max_leaf=max_leaf)
    children = [n.aabb for n in (left, right) if n is not None]
    if not children:
        return None
    return TLASNode(aabb=merge_aabbs(children), left=left, right=right)


def _query_tlas_instances(
    node: Optional[TLASNode],
    origin: Vector3,
    direction: Vector3,
    t_min: float,
    t_max: float,
) -> List[int]:
    if node is None:
        return []
    if not node.aabb.intersects_ray(origin, direction, t_min=t_min, t_max=t_max):
        return []
    if node.instance_indices is not None:
        return list(node.instance_indices)
    out: List[int] = []
    out.extend(_query_tlas_instances(node.left, origin, direction, t_min=t_min, t_max=t_max))
    out.extend(_query_tlas_instances(node.right, origin, direction, t_min=t_min, t_max=t_max))
    return out


def _refit_tlas_tree(node: Optional[TLASNode], bounds: List[Optional[AABB]]) -> Optional[AABB]:
    if node is None:
        return None
    if node.instance_indices is not None:
        boxes = [bounds[i] for i in node.instance_indices if bounds[i] is not None]
        if boxes:
            node.aabb = merge_aabbs(boxes)
            return node.aabb
        return None
    left = _refit_tlas_tree(node.left, bounds)
    right = _refit_tlas_tree(node.right, bounds)
    children = [b for b in (left, right) if b is not None]
    if children:
        node.aabb = merge_aabbs(children)
        return node.aabb
    return None


def build_blas(mesh: TriMesh | Sequence[Triangle], mesh_id: str = "mesh") -> MeshBLAS:
    if isinstance(mesh, TriMesh):
        triangles = _triangles_from_trimesh(mesh, payload=mesh_id)
    else:
        triangles = list(mesh)
    bvh = build_bvh(triangles) if triangles else None
    bounds = bvh.aabb if bvh is not None else None
    return MeshBLAS(mesh_id=str(mesh_id), triangles_local=triangles, bvh_local=bvh, bounds_local=bounds)


def build_tlas(instances: Sequence[MeshInstance], blas: Dict[str, MeshBLAS]) -> TLAS:
    inst_list = list(instances)
    bounds = [_instance_bounds(inst, blas) for inst in inst_list]
    tree = _build_tlas_tree(list(range(len(inst_list))), bounds=bounds)
    return TLAS(instances=inst_list, instance_bounds=bounds, instance_tree=tree)


def recompute_instance_bounds(
    scene: TwoLevelBVH,
    instance_ids: Optional[Set[str]] = None,
) -> None:
    if not scene.tlas.instances:
        scene.tlas.instance_bounds = []
        scene.tlas.instance_tree = None
        return

    if not scene.tlas.instance_bounds or len(scene.tlas.instance_bounds) != len(scene.tlas.instances):
        scene.tlas.instance_bounds = [None] * len(scene.tlas.instances)

    changed_any = False
    for idx, inst in enumerate(scene.tlas.instances):
        if instance_ids is not None and inst.instance_id not in instance_ids:
            continue
        scene.tlas.instance_bounds[idx] = _instance_bounds(inst, scene.blas)
        changed_any = True

    if scene.tlas.instance_tree is None:
        scene.tlas.instance_tree = _build_tlas_tree(list(range(len(scene.tlas.instances))), bounds=scene.tlas.instance_bounds)
        if scene.tlas.instance_tree is not None:
            scene.tlas_rebuild_count += 1
        return

    if changed_any:
        _refit_tlas_tree(scene.tlas.instance_tree, scene.tlas.instance_bounds)


def flatten_world_triangles(scene: TwoLevelBVH | TLAS, blas: Optional[Dict[str, MeshBLAS]] = None) -> List[Triangle]:
    if isinstance(scene, TwoLevelBVH):
        tlas = scene.tlas
        blas_map = scene.blas
    else:
        tlas = scene
        blas_map = blas or {}

    out: List[Triangle] = []
    for inst in tlas.instances:
        b = blas_map.get(inst.mesh_id)
        if b is None:
            continue
        m = np.asarray(inst.transform_4x4, dtype=float).reshape(4, 4)
        for tri in b.triangles_local:
            out.append(
                Triangle(
                    a=_tx_point(m, tri.a),
                    b=_tx_point(m, tri.b),
                    c=_tx_point(m, tri.c),
                    payload={"instance_id": inst.instance_id, "mesh_id": inst.mesh_id, "payload": tri.payload},
                    two_sided=bool(getattr(tri, "two_sided", True)),
                )
            )
    return out


def build_two_level_bvh(meshes: Dict[str, Sequence[Triangle]], instances: Sequence[MeshInstance]) -> TwoLevelBVH:
    blas = {mid: build_blas(list(tris), mesh_id=mid) for mid, tris in meshes.items()}
    tlas = build_tlas(instances, blas=blas)
    return TwoLevelBVH(blas=blas, tlas=tlas, tlas_rebuild_count=1)


def ray_intersect(scene: TwoLevelBVH | TLAS, ray: Ray) -> Optional[RayHit]:
    if isinstance(scene, TwoLevelBVH):
        tlas = scene.tlas
        blas_map = scene.blas
    else:
        tlas = scene
        blas_map = {}

    if not tlas.instances:
        return None

    d_world = ray.direction
    d_world_len = d_world.length()
    if d_world_len <= EPS_POS:
        return None
    d_world_n = d_world / d_world_len

    if tlas.instance_tree is None:
        candidate_indices = list(range(len(tlas.instances)))
    else:
        candidate_indices = _query_tlas_instances(
            tlas.instance_tree,
            ray.origin,
            d_world_n,
            t_min=float(ray.t_min),
            t_max=float(ray.t_max),
        )

    best: Optional[RayHit] = None
    best_t = float(ray.t_max)
    seen: Set[int] = set()
    for idx in candidate_indices:
        if idx in seen or idx < 0 or idx >= len(tlas.instances):
            continue
        seen.add(idx)
        inst = tlas.instances[idx]
        b = blas_map.get(inst.mesh_id)
        if b is None or b.bvh_local is None:
            continue

        m_world = np.asarray(inst.transform_4x4, dtype=float).reshape(4, 4)
        try:
            m_local = np.linalg.inv(m_world)
        except np.linalg.LinAlgError:
            continue

        origin_local = _tx_point(m_local, ray.origin)
        dir_local = _tx_dir(m_local, d_world_n)
        dl = dir_local.length()
        if dl <= EPS_POS:
            continue
        dir_local_n = dir_local / dl

        local_candidates = query_triangles(
            b.bvh_local,
            origin_local,
            dir_local_n,
            t_min=max(float(ray.t_min), EPS_POS),
            t_max=1.0 / EPS_POS,
        )
        for tri_local in local_candidates:
            t_local = ray_intersects_triangle(
                origin_local,
                dir_local_n,
                tri_local,
                t_min=max(float(ray.t_min), EPS_POS),
                t_max=1.0 / EPS_POS,
            )
            if t_local is None:
                continue

            p_local = origin_local + (dir_local_n * float(t_local))
            p_world = _tx_point(m_world, p_local)
            world_t = (p_world - ray.origin).dot(d_world_n)
            if world_t < float(ray.t_min) or world_t > best_t:
                continue

            tri_world = Triangle(
                a=_tx_point(m_world, tri_local.a),
                b=_tx_point(m_world, tri_local.b),
                c=_tx_point(m_world, tri_local.c),
                payload={"instance_id": inst.instance_id, "mesh_id": inst.mesh_id, "payload": tri_local.payload},
                two_sided=bool(getattr(tri_local, "two_sided", True)),
            )
            best_t = float(world_t)
            best = RayHit(t=best_t, triangle=tri_world, instance_id=inst.instance_id, mesh_id=inst.mesh_id)

    return best
