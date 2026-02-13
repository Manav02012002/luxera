from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from luxera.geometry.core import Surface, Vector3
from luxera.geometry.tolerance import EPS_PLANE, EPS_POS
from luxera.geometry.triangulate import triangulate_polygon_vertices


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
            return node
        node.aabb = merge_aabbs([triangle_aabb(t) for t in node.triangles])  # type: ignore[misc]
        return node
    refit_bvh(node.left)
    refit_bvh(node.right)
    children = [n.aabb for n in (node.left, node.right) if n is not None]
    if children:
        node.aabb = merge_aabbs(children)  # type: ignore[misc]
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
