from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/performance_contract.md."""

import math
import multiprocessing as mp
from typing import Callable, List, Optional, Tuple, TYPE_CHECKING

import numpy as np

from luxera.geometry.bvh import any_hit, ray_intersects_triangle
from luxera.geometry.core import Vector3
from luxera.geometry.ray_config import scaled_ray_policy

if TYPE_CHECKING:
    from luxera.geometry.bvh import BVHNode, Triangle


IntensityLookupFn = Callable[[np.ndarray, int], np.ndarray]


def _validate_inputs(
    grid_points: np.ndarray,
    grid_normals: np.ndarray,
    luminaire_positions: np.ndarray,
    luminaire_intensities: np.ndarray,
    luminaire_flux_multipliers: np.ndarray,
    luminaire_maintenance_factors: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pts = np.asarray(grid_points, dtype=float)
    nrms = np.asarray(grid_normals, dtype=float)
    lpos = np.asarray(luminaire_positions, dtype=float)
    lint = np.asarray(luminaire_intensities, dtype=float).reshape(-1)
    lflux = np.asarray(luminaire_flux_multipliers, dtype=float).reshape(-1)
    lmf = np.asarray(luminaire_maintenance_factors, dtype=float).reshape(-1)

    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("grid_points must be shape (M, 3)")
    if nrms.ndim != 2 or nrms.shape != pts.shape:
        raise ValueError("grid_normals must be shape (M, 3)")
    if lpos.ndim != 2 or lpos.shape[1] != 3:
        raise ValueError("luminaire_positions must be shape (N, 3)")
    n = lpos.shape[0]
    if lint.shape[0] != n or lflux.shape[0] != n or lmf.shape[0] != n:
        raise ValueError("luminaire arrays must all have length N")

    return pts, nrms, lpos, lint, lflux, lmf


def _point_pair_occluded(
    point_xyz: np.ndarray,
    target_xyz: np.ndarray,
    occlusion_triangles: List["Triangle"],
    bvh: Optional["BVHNode"],
) -> bool:
    p = Vector3(float(point_xyz[0]), float(point_xyz[1]), float(point_xyz[2]))
    t = Vector3(float(target_xyz[0]), float(target_xyz[1]), float(target_xyz[2]))

    direction = t - p
    dist = direction.length()
    if dist <= 0.0:
        return False

    policy = scaled_ray_policy(scene_scale=dist, user_eps=1e-6)
    ray_dir = direction / dist
    origin = p + ray_dir * policy.origin_eps
    t_max = max((t - origin).length() - policy.t_min, 0.0)
    if t_max <= policy.t_min:
        return False

    if bvh is not None:
        return any_hit(bvh, origin, ray_dir, t_min=policy.t_min, t_max=t_max)

    for tri in occlusion_triangles:
        if ray_intersects_triangle(origin, ray_dir, tri, t_min=policy.t_min, t_max=t_max) is not None:
            return True
    return False


def _compute_chunk_with_occlusion(
    grid_points: np.ndarray,
    grid_normals: np.ndarray,
    luminaire_positions: np.ndarray,
    luminaire_intensities: np.ndarray,
    luminaire_flux_multipliers: np.ndarray,
    luminaire_maintenance_factors: np.ndarray,
    occlusion_triangles: List["Triangle"],
    bvh: Optional["BVHNode"],
) -> np.ndarray:
    engine = VectorisedDirectEngine()
    return engine.compute_grid_with_occlusion(
        grid_points,
        grid_normals,
        luminaire_positions,
        luminaire_intensities,
        luminaire_flux_multipliers,
        luminaire_maintenance_factors,
        occlusion_triangles=occlusion_triangles,
        bvh=bvh,
    )


def _compute_chunk_no_occlusion(
    grid_points: np.ndarray,
    grid_normals: np.ndarray,
    luminaire_positions: np.ndarray,
    luminaire_intensities: np.ndarray,
    luminaire_flux_multipliers: np.ndarray,
    luminaire_maintenance_factors: np.ndarray,
) -> np.ndarray:
    engine = VectorisedDirectEngine()
    return engine.compute_grid(
        grid_points,
        grid_normals,
        luminaire_positions,
        luminaire_intensities,
        luminaire_flux_multipliers,
        luminaire_maintenance_factors,
    )


class VectorisedDirectEngine:
    """
    Fully NumPy-vectorised direct illuminance computation.
    """

    def __init__(self, max_pairs_per_batch: int = 10_000_000):
        self.max_pairs_per_batch = max(1, int(max_pairs_per_batch))

    def _luminaire_chunks(self, m: int, n: int) -> list[Tuple[int, int]]:
        total_pairs = m * n
        if total_pairs <= self.max_pairs_per_batch:
            return [(0, n)]
        chunk_n = max(1, self.max_pairs_per_batch // max(m, 1))
        return [(s, min(s + chunk_n, n)) for s in range(0, n, chunk_n)]

    def compute_grid(
        self,
        grid_points: np.ndarray,
        grid_normals: np.ndarray,
        luminaire_positions: np.ndarray,
        luminaire_intensities: np.ndarray,
        luminaire_flux_multipliers: np.ndarray,
        luminaire_maintenance_factors: np.ndarray,
        intensity_lookup_fn: Optional[IntensityLookupFn] = None,
    ) -> np.ndarray:
        pts, nrms, lpos, lint, lflux, lmf = _validate_inputs(
            grid_points,
            grid_normals,
            luminaire_positions,
            luminaire_intensities,
            luminaire_flux_multipliers,
            luminaire_maintenance_factors,
        )

        m = pts.shape[0]
        n = lpos.shape[0]
        if m == 0 or n == 0:
            return np.zeros((m,), dtype=float)

        scale = lflux * lmf
        out = np.zeros((m,), dtype=float)
        eps = 1e-12

        for start, end in self._luminaire_chunks(m, n):
            pos = lpos[start:end]
            vec = pos[None, :, :] - pts[:, None, :]
            d2 = np.sum(vec * vec, axis=2)
            d = np.sqrt(np.maximum(d2, eps))
            u = vec / d[:, :, None]

            cos_theta = np.einsum("mnc,mc->mn", u, nrms)
            np.maximum(cos_theta, 0.0, out=cos_theta)

            if intensity_lookup_fn is None:
                intens = np.broadcast_to(lint[None, start:end], cos_theta.shape)
            else:
                intens = np.zeros_like(cos_theta)
                for local_idx, lum_idx in enumerate(range(start, end)):
                    sampled = np.asarray(intensity_lookup_fn(u[:, local_idx : local_idx + 1, :], lum_idx), dtype=float).reshape(m)
                    intens[:, local_idx] = sampled

            contrib = intens * cos_theta / np.maximum(d2, eps)
            out += np.sum(contrib * scale[None, start:end], axis=1)

        return np.maximum(out, 0.0)

    def compute_grid_with_occlusion(
        self,
        grid_points: np.ndarray,
        grid_normals: np.ndarray,
        luminaire_positions: np.ndarray,
        luminaire_intensities: np.ndarray,
        luminaire_flux_multipliers: np.ndarray,
        luminaire_maintenance_factors: np.ndarray,
        occlusion_triangles: List["Triangle"],
        bvh: Optional["BVHNode"] = None,
        intensity_lookup_fn: Optional[IntensityLookupFn] = None,
    ) -> np.ndarray:
        pts, nrms, lpos, lint, lflux, lmf = _validate_inputs(
            grid_points,
            grid_normals,
            luminaire_positions,
            luminaire_intensities,
            luminaire_flux_multipliers,
            luminaire_maintenance_factors,
        )

        m = pts.shape[0]
        n = lpos.shape[0]
        if m == 0 or n == 0:
            return np.zeros((m,), dtype=float)

        scale = lflux * lmf
        out = np.zeros((m,), dtype=float)
        eps = 1e-12

        for start, end in self._luminaire_chunks(m, n):
            pos = lpos[start:end]
            vec = pos[None, :, :] - pts[:, None, :]
            d2 = np.sum(vec * vec, axis=2)
            d = np.sqrt(np.maximum(d2, eps))
            u = vec / d[:, :, None]
            cos_theta = np.einsum("mnc,mc->mn", u, nrms)
            np.maximum(cos_theta, 0.0, out=cos_theta)

            visible = np.ones((m, end - start), dtype=bool)
            for mm in range(m):
                p = pts[mm]
                for ll, lum_idx in enumerate(range(start, end)):
                    if cos_theta[mm, ll] <= 0.0:
                        visible[mm, ll] = False
                        continue
                    visible[mm, ll] = not _point_pair_occluded(p, lpos[lum_idx], occlusion_triangles, bvh)

            if intensity_lookup_fn is None:
                intens = np.broadcast_to(lint[None, start:end], cos_theta.shape)
            else:
                intens = np.zeros_like(cos_theta)
                for local_idx, lum_idx in enumerate(range(start, end)):
                    sampled = np.asarray(intensity_lookup_fn(u[:, local_idx : local_idx + 1, :], lum_idx), dtype=float).reshape(m)
                    intens[:, local_idx] = sampled

            contrib = intens * cos_theta / np.maximum(d2, eps)
            contrib *= visible
            out += np.sum(contrib * scale[None, start:end], axis=1)

        return np.maximum(out, 0.0)


class ParallelEngine:
    """
    Multiprocessing wrapper that splits grid points across CPU cores.
    """

    def __init__(self, n_workers: Optional[int] = None):
        import os

        self.n_workers = n_workers or max(1, (os.cpu_count() or 1))

    def _split_indices(self, m: int) -> List[Tuple[int, int]]:
        if m <= 0:
            return []
        workers = max(1, min(self.n_workers, m))
        chunk = int(math.ceil(m / float(workers)))
        return [(i, min(i + chunk, m)) for i in range(0, m, chunk)]

    def compute_parallel(
        self,
        engine: VectorisedDirectEngine,
        grid_points: np.ndarray,
        grid_normals: np.ndarray,
        luminaire_positions: np.ndarray,
        luminaire_intensities: np.ndarray,
        luminaire_flux_multipliers: np.ndarray,
        luminaire_maintenance_factors: np.ndarray,
        occlusion_triangles=None,
        bvh=None,
    ) -> np.ndarray:
        pts, nrms, lpos, lint, lflux, lmf = _validate_inputs(
            grid_points,
            grid_normals,
            luminaire_positions,
            luminaire_intensities,
            luminaire_flux_multipliers,
            luminaire_maintenance_factors,
        )
        _ = engine

        spans = self._split_indices(pts.shape[0])
        if not spans:
            return np.zeros((0,), dtype=float)
        if len(spans) == 1:
            if occlusion_triangles is None:
                return _compute_chunk_no_occlusion(pts, nrms, lpos, lint, lflux, lmf)
            return _compute_chunk_with_occlusion(pts, nrms, lpos, lint, lflux, lmf, occlusion_triangles, bvh)

        tasks = []
        for s, e in spans:
            p_chunk = pts[s:e]
            n_chunk = nrms[s:e]
            if occlusion_triangles is None:
                tasks.append((p_chunk, n_chunk, lpos, lint, lflux, lmf))
            else:
                tasks.append((p_chunk, n_chunk, lpos, lint, lflux, lmf, occlusion_triangles, bvh))

        ctx = mp.get_context("fork")
        with ctx.Pool(processes=len(spans)) as pool:
            if occlusion_triangles is None:
                parts = pool.starmap(_compute_chunk_no_occlusion, tasks)
            else:
                parts = pool.starmap(_compute_chunk_with_occlusion, tasks)

        return np.concatenate(parts, axis=0) if parts else np.zeros((0,), dtype=float)
