from __future__ import annotations

import random
import time

from luxera.geometry.bvh import Triangle, any_hit, build_bvh, ray_intersects_triangle
from luxera.geometry.core import Vector3


def _random_triangles(n: int, seed: int = 7) -> list[Triangle]:
    rng = random.Random(seed)
    tris: list[Triangle] = []
    for _ in range(n):
        x = rng.uniform(-20.0, 20.0)
        y = rng.uniform(-20.0, 20.0)
        z = rng.uniform(0.0, 8.0)
        s = rng.uniform(0.2, 1.2)
        tris.append(
            Triangle(
                a=Vector3(x, y, z),
                b=Vector3(x + s, y, z),
                c=Vector3(x, y + s, z + 0.1 * s),
            )
        )
    return tris


def _bruteforce_hits(tris: list[Triangle], rays: list[tuple[Vector3, Vector3, float, float]]) -> int:
    hits = 0
    for origin, direction, t_min, t_max in rays:
        for tri in tris:
            if ray_intersects_triangle(origin, direction, tri, t_min=t_min, t_max=t_max) is not None:
                hits += 1
                break
    return hits


def _bvh_hits(tris: list[Triangle], rays: list[tuple[Vector3, Vector3, float, float]]) -> int:
    bvh = build_bvh(tris)
    hits = 0
    for origin, direction, t_min, t_max in rays:
        if any_hit(bvh, origin, direction, t_min=t_min, t_max=t_max):
            hits += 1
    return hits


def main() -> None:
    tris = _random_triangles(5000)
    rays: list[tuple[Vector3, Vector3, float, float]] = []
    for i in range(1200):
        ox = -30.0 + (i % 40) * 1.5
        oy = -30.0 + (i // 40) * 1.0
        origin = Vector3(ox, oy, 1.5)
        direction = Vector3(1.0, 1.0, 0.1).normalize()
        rays.append((origin, direction, 1e-4, 120.0))

    t0 = time.perf_counter()
    brute_hits = _bruteforce_hits(tris, rays)
    t1 = time.perf_counter()
    bvh_hits = _bvh_hits(tris, rays)
    t2 = time.perf_counter()

    brute_s = t1 - t0
    bvh_s = t2 - t1
    speedup = brute_s / bvh_s if bvh_s > 0 else float("inf")

    print("BVH Occlusion Benchmark")
    print(f"Triangles: {len(tris)}")
    print(f"Rays: {len(rays)}")
    print(f"Bruteforce: {brute_s:.4f}s ({brute_hits} hits)")
    print(f"BVH:        {bvh_s:.4f}s ({bvh_hits} hits)")
    print(f"Speedup:    {speedup:.2f}x")


if __name__ == "__main__":
    main()
