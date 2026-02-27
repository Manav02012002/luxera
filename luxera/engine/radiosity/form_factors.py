from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

import numpy as np

from luxera.geometry.bvh import (
    BVHNode,
    any_hit,
    build_bvh,
    query_triangles,
    ray_intersects_triangle,
    triangulate_surfaces,
)
from luxera.geometry.core import Surface, Vector3
from luxera.geometry.tolerance import EPS_POS


@dataclass(frozen=True)
class FormFactorConfig:
    method: Literal["analytic", "monte_carlo"] = "monte_carlo"
    use_visibility: bool = True
    monte_carlo_samples: int = 16


def build_form_factor_matrix(
    patches: List[Surface],
    all_surfaces: List[Surface],
    *,
    config: FormFactorConfig,
    rng: np.random.Generator,
    bvh: Optional[BVHNode] = None,
) -> np.ndarray:
    """
    Build diffuse form-factor matrix for radiosity patches.

    Used in the radiosity balance:
        B_i = E_i + rho_i * sum_j(F_ij * B_j)
    """
    n = len(patches)
    F = np.zeros((n, n), dtype=float)
    if n == 0:
        return F

    areas = np.array([max(float(_patch_area(p)), 1e-12) for p in patches], dtype=float)
    centroids = np.array([[p.centroid.x, p.centroid.y, p.centroid.z] for p in patches], dtype=float)
    normals = np.array([_normal_array(p) for p in patches], dtype=float)
    normals = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    id_to_index = {p.id: i for i, p in enumerate(patches)}

    if config.method == "analytic" or not config.use_visibility:
        delta = centroids[None, :, :] - centroids[:, None, :]
        dist2 = np.einsum("ijk,ijk->ij", delta, delta)
        dist = np.sqrt(np.maximum(dist2, 1e-12))
        dir_ij = delta / dist[:, :, None]
        cos_i = np.einsum("ik,ijk->ij", normals, dir_ij)
        cos_j = np.einsum("jk,ijk->ij", normals, -dir_ij)
        F = (np.maximum(cos_i, 0.0) * np.maximum(cos_j, 0.0) * areas[None, :]) / (np.pi * np.maximum(dist2, 1e-12))
        np.fill_diagonal(F, 0.0)
    else:
        tri_source = patches if patches else all_surfaces
        triangles = triangulate_surfaces(tri_source)
        visibility_bvh: Optional[BVHNode] = bvh if (bvh is not None and hasattr(bvh, "triangles")) else build_bvh(triangles)
        samples = max(1, int(config.monte_carlo_samples))
        eps = max(10.0 * EPS_POS, 1e-6)

        for i in range(n):
            n_i = normals[i]
            c_i = centroids[i]
            origins = np.repeat((c_i + eps * n_i)[None, :], samples, axis=0)
            dirs_local = _sample_cosine_hemisphere(samples=samples, rng=rng)
            dirs_world = _to_world(dirs_local, n_i)
            cos_i_batch = np.maximum(dirs_world @ n_i, 0.0)

            for s in range(samples):
                if cos_i_batch[s] <= 0.0:
                    continue
                origin_v = _vec3(origins[s])
                dir_v = _vec3(dirs_world[s])
                if not any_hit(visibility_bvh, origin_v, dir_v, t_min=eps, t_max=float("inf"), two_sided=True):
                    continue

                hit_index = -1
                nearest_t = float("inf")
                for tri in query_triangles(visibility_bvh, origin_v, dir_v, t_min=eps, t_max=float("inf")):
                    t = ray_intersects_triangle(origin_v, dir_v, tri, t_min=eps, t_max=nearest_t, two_sided=True)
                    if t is None:
                        continue
                    j = id_to_index.get(str(tri.payload))
                    if j is None or j == i:
                        continue
                    nearest_t = t
                    hit_index = j

                if hit_index < 0:
                    continue

                j = hit_index
                r_vec = centroids[j] - c_i
                r2 = float(np.dot(r_vec, r_vec))
                if r2 <= 1e-12:
                    continue
                cos_j = max(0.0, float((-dirs_world[s]) @ normals[j]))
                if cos_j <= 0.0:
                    continue
                F[i, j] += (cos_i_batch[s] * cos_j) / (np.pi * r2)

            F[i, :] /= float(samples)

    # Enforce reciprocity: F_ij * A_i == F_ji * A_j
    for i in range(n):
        for j in range(i + 1, n):
            phi = 0.5 * (F[i, j] * areas[i] + F[j, i] * areas[j])
            F[i, j] = phi / areas[i]
            F[j, i] = phi / areas[j]

    np.fill_diagonal(F, 0.0)
    F = np.clip(F, 0.0, 1.0)

    # Enforce basic energy conservation in transfer matrix.
    row_sums = np.sum(F, axis=1)
    for i, s in enumerate(row_sums):
        if s > 1.0 and s > 1e-12:
            F[i, :] = F[i, :] / s
    return F


def _sample_cosine_hemisphere(*, samples: int, rng: np.random.Generator) -> np.ndarray:
    """Vectorized cosine-weighted hemisphere sampling in local (+Z) frame."""
    u1 = rng.random(samples)
    u2 = rng.random(samples)
    r = np.sqrt(u1)
    phi = 2.0 * np.pi * u2
    x = r * np.cos(phi)
    y = r * np.sin(phi)
    z = np.sqrt(np.maximum(0.0, 1.0 - u1))
    return np.stack((x, y, z), axis=1)


def _to_world(local_dirs: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Rotate local hemisphere samples into world frame aligned to normal n."""
    n = n / max(float(np.linalg.norm(n)), 1e-12)
    helper = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(n, helper))) > 0.99:
        helper = np.array([0.0, 1.0, 0.0], dtype=float)
    t = np.cross(helper, n)
    t = t / max(float(np.linalg.norm(t)), 1e-12)
    b = np.cross(n, t)
    basis = np.stack((t, b, n), axis=1)
    out = local_dirs @ basis.T
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    return out


def _vec3(v: np.ndarray) -> Vector3:
    return Vector3(float(v[0]), float(v[1]), float(v[2]))


def _patch_area(patch: Surface) -> float:
    area = getattr(patch.polygon, "area", None)
    if area is not None:
        return float(area)
    return float(patch.polygon.get_area())


def _normal_array(patch: Surface) -> np.ndarray:
    normal = getattr(patch.polygon, "normal", None)
    if normal is None:
        normal = patch.polygon.get_normal()
    return np.array([float(normal.x), float(normal.y), float(normal.z)], dtype=float)
