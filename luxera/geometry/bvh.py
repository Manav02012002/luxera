from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

import numpy as np

from luxera.geometry.core import Surface, Vector3
from luxera.geometry.tolerance import EPS_PLANE, EPS_POS
from luxera.geometry.triangulate import triangulate_polygon_vertices

try:
    from ._bvh_jit import any_hit_flat as _any_hit_flat_jit

    _HAS_BVH_JIT = True
except Exception:
    _any_hit_flat_jit = None
    _HAS_BVH_JIT = False


@dataclass(frozen=True)
class Triangle:
    a: Vector3
    b: Vector3
    c: Vector3
    payload: Any = None
    two_sided: bool = True

    @property
    def centroid(self) -> Vector3:
        return Vector3((self.a.x + self.b.x + self.c.x) / 3.0, (self.a.y + self.b.y + self.c.y) / 3.0, (self.a.z + self.b.z + self.c.z) / 3.0)


@dataclass(frozen=True)
class AABB:
    min: Vector3
    max: Vector3

    def intersects_ray(self, origin: Vector3, direction: Vector3, t_min: float = 0.0, t_max: float = math.inf) -> bool:
        lo = t_min
        hi = t_max
        for axis in ("x", "y", "z"):
            o = getattr(origin, axis)
            d = getattr(direction, axis)
            mn = getattr(self.min, axis)
            mx = getattr(self.max, axis)
            if abs(d) < EPS_POS:
                if o < mn or o > mx:
                    return False
                continue
            inv_d = 1.0 / d
            t0 = (mn - o) * inv_d
            t1 = (mx - o) * inv_d
            if t0 > t1:
                t0, t1 = t1, t0
            lo = max(lo, t0)
            hi = min(hi, t1)
            if hi < lo:
                return False
        return True


@dataclass
class BVHNode:
    aabb: AABB
    left: Optional["BVHNode"] = None
    right: Optional["BVHNode"] = None
    triangles: Optional[List[Triangle]] = None


@dataclass(frozen=True)
class FlatBVH:
    node_bounds: np.ndarray
    node_left: np.ndarray
    node_right: np.ndarray
    node_tri_start: np.ndarray
    node_tri_count: np.ndarray
    tri_v0: np.ndarray
    tri_v1: np.ndarray
    tri_v2: np.ndarray
    all_two_sided: bool


_FLAT_BVH_CACHE: dict[int, FlatBVH] = {}


def triangle_aabb(tri: Triangle) -> AABB:
    xs = [tri.a.x, tri.b.x, tri.c.x]
    ys = [tri.a.y, tri.b.y, tri.c.y]
    zs = [tri.a.z, tri.b.z, tri.c.z]
    return AABB(min=Vector3(min(xs), min(ys), min(zs)), max=Vector3(max(xs), max(ys), max(zs)))


def merge_aabbs(boxes: Sequence[AABB]) -> AABB:
    xs = [b.min.x for b in boxes] + [b.max.x for b in boxes]
    ys = [b.min.y for b in boxes] + [b.max.y for b in boxes]
    zs = [b.min.z for b in boxes] + [b.max.z for b in boxes]
    return AABB(min=Vector3(min(xs), min(ys), min(zs)), max=Vector3(max(xs), max(ys), max(zs)))


def build_bvh(triangles: List[Triangle], max_leaf: int = 8) -> Optional[BVHNode]:
    if not triangles:
        return None
    if len(triangles) <= max_leaf:
        return BVHNode(aabb=merge_aabbs([triangle_aabb(t) for t in triangles]), triangles=triangles)

    cents = [t.centroid for t in triangles]
    xs = [c.x for c in cents]
    ys = [c.y for c in cents]
    zs = [c.z for c in cents]
    spans = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    axis = spans.index(max(spans))
    key = (lambda t: t.centroid.x) if axis == 0 else (lambda t: t.centroid.y) if axis == 1 else (lambda t: t.centroid.z)
    ordered = sorted(triangles, key=key)
    mid = len(ordered) // 2
    left = build_bvh(ordered[:mid], max_leaf=max_leaf)
    right = build_bvh(ordered[mid:], max_leaf=max_leaf)
    children = [n.aabb for n in (left, right) if n is not None]
    if not children:
        return None
    return BVHNode(aabb=merge_aabbs(children), left=left, right=right)


def query_triangles(node: Optional[BVHNode], origin: Vector3, direction: Vector3, t_min: float, t_max: float) -> List[Triangle]:
    if node is None:
        return []
    if not node.aabb.intersects_ray(origin, direction, t_min=t_min, t_max=t_max):
        return []
    if node.triangles is not None:
        return node.triangles
    out: List[Triangle] = []
    out.extend(query_triangles(node.left, origin, direction, t_min=t_min, t_max=t_max))
    out.extend(query_triangles(node.right, origin, direction, t_min=t_min, t_max=t_max))
    return out


def flatten_bvh(root: Optional[BVHNode]) -> FlatBVH:
    if root is None:
        return FlatBVH(
            node_bounds=np.zeros((0, 6), dtype=np.float64),
            node_left=np.zeros((0,), dtype=np.int32),
            node_right=np.zeros((0,), dtype=np.int32),
            node_tri_start=np.zeros((0,), dtype=np.int32),
            node_tri_count=np.zeros((0,), dtype=np.int32),
            tri_v0=np.zeros((0, 3), dtype=np.float64),
            tri_v1=np.zeros((0, 3), dtype=np.float64),
            tri_v2=np.zeros((0, 3), dtype=np.float64),
            all_two_sided=True,
        )

    node_bounds: List[List[float]] = []
    node_left: List[int] = []
    node_right: List[int] = []
    node_tri_start: List[int] = []
    node_tri_count: List[int] = []
    tri_v0: List[List[float]] = []
    tri_v1: List[List[float]] = []
    tri_v2: List[List[float]] = []
    all_two_sided = True

    def _append_node(node: BVHNode) -> int:
        nonlocal all_two_sided
        idx = len(node_bounds)
        node_bounds.append(
            [
                node.aabb.min.x,
                node.aabb.min.y,
                node.aabb.min.z,
                node.aabb.max.x,
                node.aabb.max.y,
                node.aabb.max.z,
            ]
        )
        node_left.append(-1)
        node_right.append(-1)
        node_tri_start.append(-1)
        node_tri_count.append(0)

        if node.triangles is not None:
            start = len(tri_v0)
            count = len(node.triangles)
            for tri in node.triangles:
                tri_v0.append([tri.a.x, tri.a.y, tri.a.z])
                tri_v1.append([tri.b.x, tri.b.y, tri.b.z])
                tri_v2.append([tri.c.x, tri.c.y, tri.c.z])
                all_two_sided = all_two_sided and bool(getattr(tri, "two_sided", True))
            node_tri_start[idx] = start
            node_tri_count[idx] = count
        else:
            if node.left is not None:
                node_left[idx] = _append_node(node.left)
            if node.right is not None:
                node_right[idx] = _append_node(node.right)
        return idx

    _append_node(root)

    return FlatBVH(
        node_bounds=np.asarray(node_bounds, dtype=np.float64),
        node_left=np.asarray(node_left, dtype=np.int32),
        node_right=np.asarray(node_right, dtype=np.int32),
        node_tri_start=np.asarray(node_tri_start, dtype=np.int32),
        node_tri_count=np.asarray(node_tri_count, dtype=np.int32),
        tri_v0=np.asarray(tri_v0, dtype=np.float64) if tri_v0 else np.zeros((0, 3), dtype=np.float64),
        tri_v1=np.asarray(tri_v1, dtype=np.float64) if tri_v1 else np.zeros((0, 3), dtype=np.float64),
        tri_v2=np.asarray(tri_v2, dtype=np.float64) if tri_v2 else np.zeros((0, 3), dtype=np.float64),
        all_two_sided=all_two_sided,
    )


def build_flat_bvh(root: Optional[BVHNode]) -> FlatBVH:
    if root is None:
        return flatten_bvh(root)
    key = id(root)
    cached = _FLAT_BVH_CACHE.get(key)
    if cached is not None:
        return cached
    flat = flatten_bvh(root)
    _FLAT_BVH_CACHE[key] = flat
    return flat


def ray_intersects_triangle(
    origin: Vector3,
    direction: Vector3,
    tri: Triangle,
    t_min: float = EPS_PLANE,
    t_max: float = math.inf,
    *,
    two_sided: Optional[bool] = None,
) -> Optional[float]:
    # Moller-Trumbore intersection
    e1 = tri.b - tri.a
    e2 = tri.c - tri.a
    pvec = direction.cross(e2)
    det = e1.dot(pvec)
    use_two_sided = tri.two_sided if two_sided is None else bool(two_sided)
    if use_two_sided:
        if abs(det) < EPS_POS:
            return None
    else:
        # Backface culling for single-sided surfaces.
        if det < EPS_POS:
            return None
    if abs(det) < EPS_POS:
        return None
    inv_det = 1.0 / det
    tvec = origin - tri.a
    u = tvec.dot(pvec) * inv_det
    if u < 0.0 or u > 1.0:
        return None
    qvec = tvec.cross(e1)
    v = direction.dot(qvec) * inv_det
    if v < 0.0 or (u + v) > 1.0:
        return None
    t = e2.dot(qvec) * inv_det
    if t < t_min or t > t_max:
        return None
    return t


def any_hit(
    node: Optional[BVHNode],
    origin: Vector3,
    direction: Vector3,
    t_min: float,
    t_max: float,
    *,
    two_sided: Optional[bool] = None,
) -> bool:
    if node is None:
        return False
    if _HAS_BVH_JIT and _any_hit_flat_jit is not None:
        flat = build_flat_bvh(node)
        if two_sided is True or (two_sided is None and flat.all_two_sided):
            origin_np = np.asarray((origin.x, origin.y, origin.z), dtype=np.float64)
            direction_np = np.asarray((direction.x, direction.y, direction.z), dtype=np.float64)
            return bool(
                _any_hit_flat_jit(
                    origin_np,
                    direction_np,
                    float(t_max),
                    flat.node_bounds,
                    flat.node_left,
                    flat.node_right,
                    flat.node_tri_start,
                    flat.node_tri_count,
                    flat.tri_v0,
                    flat.tri_v1,
                    flat.tri_v2,
                    float(max(t_min, EPS_POS)),
                )
            )

    candidates = query_triangles(node, origin, direction, t_min=t_min, t_max=t_max)
    for tri in candidates:
        if ray_intersects_triangle(origin, direction, tri, t_min=t_min, t_max=t_max, two_sided=two_sided) is not None:
            return True
    return False


def refit_bvh(node: Optional[BVHNode]) -> Optional[BVHNode]:
    if node is None:
        return None
    if node.triangles is not None:
        if not node.triangles:
            _FLAT_BVH_CACHE.pop(id(node), None)
            return node
        node.aabb = merge_aabbs([triangle_aabb(t) for t in node.triangles])  # type: ignore[misc]
        _FLAT_BVH_CACHE.pop(id(node), None)
        return node
    refit_bvh(node.left)
    refit_bvh(node.right)
    children = [n.aabb for n in (node.left, node.right) if n is not None]
    if children:
        node.aabb = merge_aabbs(children)  # type: ignore[misc]
    _FLAT_BVH_CACHE.pop(id(node), None)
    return node


def triangulate_surfaces(surfaces: List[Surface]) -> List[Triangle]:
    tris: List[Triangle] = []
    for s in surfaces:
        verts = s.polygon.vertices
        for a, b, c in triangulate_polygon_vertices([(v.x, v.y, v.z) for v in verts]):
            tris.append(
                Triangle(
                    a=Vector3(*a),
                    b=Vector3(*b),
                    c=Vector3(*c),
                    payload=s.id,
                    two_sided=bool(getattr(s, "two_sided", True)),
                )
            )
    return tris
