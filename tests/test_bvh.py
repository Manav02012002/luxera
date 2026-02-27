from __future__ import annotations

import numpy as np

from luxera.geometry.bvh import Triangle, any_hit, build_bvh, ray_intersects_triangle, triangulate_surfaces
from luxera.geometry.core import Material, Polygon, Surface, Vector3


def test_ray_intersects_triangle_hit_and_miss() -> None:
    tri = Triangle(
        a=Vector3(0.0, 0.0, 0.0),
        b=Vector3(1.0, 0.0, 0.0),
        c=Vector3(0.0, 1.0, 0.0),
    )
    hit_t = ray_intersects_triangle(Vector3(0.2, 0.2, 1.0), Vector3(0.0, 0.0, -1.0), tri, t_min=1e-6, t_max=10.0)
    miss_t = ray_intersects_triangle(Vector3(2.0, 2.0, 1.0), Vector3(0.0, 0.0, -1.0), tri, t_min=1e-6, t_max=10.0)
    assert hit_t is not None
    assert miss_t is None


def test_bvh_any_hit_matches_expected() -> None:
    tris = [
        Triangle(
            a=Vector3(-1.0, -1.0, 0.0),
            b=Vector3(1.0, -1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
        ),
        Triangle(
            a=Vector3(1.0, -1.0, 0.0),
            b=Vector3(1.0, 1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
        ),
    ]
    bvh = build_bvh(tris)
    assert any_hit(bvh, Vector3(0.0, 0.0, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-4, t_max=10.0)
    assert not any_hit(bvh, Vector3(3.0, 3.0, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-4, t_max=10.0)


def test_triangulate_surfaces_fan() -> None:
    s = Surface(
        id="s1",
        polygon=Polygon(
            [
                Vector3(0.0, 0.0, 0.0),
                Vector3(1.0, 0.0, 0.0),
                Vector3(1.0, 1.0, 0.0),
                Vector3(0.0, 1.0, 0.0),
            ]
        ),
        material=Material(name="m", reflectance=0.5),
    )
    tris = triangulate_surfaces([s])
    assert len(tris) == 2


def test_flatten_bvh_structure_and_cache() -> None:
    from luxera.geometry.bvh import build_flat_bvh

    tris = [
        Triangle(
            a=Vector3(-1.0, -1.0, 0.0),
            b=Vector3(1.0, -1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
            two_sided=True,
        ),
        Triangle(
            a=Vector3(1.0, -1.0, 0.0),
            b=Vector3(1.0, 1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
            two_sided=True,
        ),
    ]
    bvh = build_bvh(tris)
    assert bvh is not None

    f1 = build_flat_bvh(bvh)
    f2 = build_flat_bvh(bvh)
    assert f1 is f2
    assert f1.node_bounds.shape[1] == 6
    assert f1.tri_v0.shape[1] == 3
    assert f1.tri_v1.shape[1] == 3
    assert f1.tri_v2.shape[1] == 3
    assert f1.all_two_sided is True


def test_bvh_jit_batch_any_hit_matches_scalar() -> None:
    from luxera.geometry.bvh import _HAS_BVH_JIT, build_flat_bvh

    if not _HAS_BVH_JIT:
        return
    from luxera.geometry._bvh_jit import batch_any_hit

    tris = [
        Triangle(
            a=Vector3(-1.0, -1.0, 0.0),
            b=Vector3(1.0, -1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
        ),
        Triangle(
            a=Vector3(1.0, -1.0, 0.0),
            b=Vector3(1.0, 1.0, 0.0),
            c=Vector3(-1.0, 1.0, 0.0),
        ),
    ]
    bvh = build_bvh(tris)
    assert bvh is not None
    flat = build_flat_bvh(bvh)

    origins = np.asarray(
        [
            [0.0, 0.0, 2.0],
            [3.0, 3.0, 2.0],
            [0.25, 0.25, 2.0],
        ],
        dtype=np.float64,
    )
    directions = np.asarray([[0.0, 0.0, -1.0], [0.0, 0.0, -1.0], [0.0, 0.0, -1.0]], dtype=np.float64)
    max_ts = np.asarray([10.0, 10.0, 10.0], dtype=np.float64)
    got = batch_any_hit(
        origins,
        directions,
        max_ts,
        flat.node_bounds,
        flat.node_left,
        flat.node_right,
        flat.node_tri_start,
        flat.node_tri_count,
        flat.tri_v0,
        flat.tri_v1,
        flat.tri_v2,
        1e-6,
    )
    exp = np.asarray(
        [
            any_hit(bvh, Vector3(0.0, 0.0, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=10.0),
            any_hit(bvh, Vector3(3.0, 3.0, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=10.0),
            any_hit(bvh, Vector3(0.25, 0.25, 2.0), Vector3(0.0, 0.0, -1.0), t_min=1e-6, t_max=10.0),
        ],
        dtype=np.bool_,
    )
    assert np.array_equal(got, exp)
