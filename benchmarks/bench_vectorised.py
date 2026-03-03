"""
Benchmark: vectorised vs loop engine on 20x15m room with 20 luminaires,
80x60 = 4800 grid points.
"""

from __future__ import annotations

import time

import numpy as np

from luxera.engine.vectorised import ParallelEngine, VectorisedDirectEngine


def loop_engine(
    grid_points: np.ndarray,
    grid_normals: np.ndarray,
    lum_positions: np.ndarray,
    lum_intensities: np.ndarray,
    lum_flux: np.ndarray,
    lum_mf: np.ndarray,
) -> np.ndarray:
    m = grid_points.shape[0]
    n = lum_positions.shape[0]
    out = np.zeros((m,), dtype=float)
    for i in range(m):
        px, py, pz = grid_points[i]
        nx, ny, nz = grid_normals[i]
        total = 0.0
        for j in range(n):
            dx, dy, dz = lum_positions[j] - np.array([px, py, pz])
            d2 = dx * dx + dy * dy + dz * dz
            if d2 <= 1e-12:
                continue
            d = d2 ** 0.5
            ux, uy, uz = dx / d, dy / d, dz / d
            cos_t = ux * nx + uy * ny + uz * nz
            if cos_t <= 0.0:
                continue
            total += lum_intensities[j] * cos_t / d2 * lum_flux[j] * lum_mf[j]
        out[i] = total
    return out


def scenario(seed: int = 1):
    rng = np.random.default_rng(seed)
    nx, ny = 80, 60
    xs = np.linspace(0.0, 20.0, nx)
    ys = np.linspace(0.0, 15.0, ny)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    pts = np.column_stack([xx.reshape(-1), yy.reshape(-1), np.full((nx * ny,), 0.8)])
    nrms = np.zeros_like(pts)
    nrms[:, 2] = 1.0

    n_lum = 20
    lpos = np.column_stack(
        [
            rng.uniform(1.0, 19.0, size=n_lum),
            rng.uniform(1.0, 14.0, size=n_lum),
            rng.uniform(2.6, 3.2, size=n_lum),
        ]
    )
    lint = rng.uniform(3000.0, 12000.0, size=n_lum)
    lflux = rng.uniform(0.8, 1.1, size=n_lum)
    lmf = rng.uniform(0.75, 1.0, size=n_lum)
    return pts, nrms, lpos, lint, lflux, lmf


def time_it(fn, runs: int = 3) -> float:
    vals = []
    for _ in range(runs):
        t0 = time.perf_counter()
        _ = fn()
        vals.append(time.perf_counter() - t0)
    return float(np.median(vals))


def main() -> None:
    pts, nrms, lpos, lint, lflux, lmf = scenario()

    vec = VectorisedDirectEngine()
    par = ParallelEngine()

    # warm-up
    _ = vec.compute_grid(pts, nrms, lpos, lint, lflux, lmf)

    t_loop = time_it(lambda: loop_engine(pts, nrms, lpos, lint, lflux, lmf))
    t_vec = time_it(lambda: vec.compute_grid(pts, nrms, lpos, lint, lflux, lmf))
    t_par = time_it(lambda: par.compute_parallel(vec, pts, nrms, lpos, lint, lflux, lmf))

    print("\nEngine                          Time (s)   Speedup")
    print("---------------------------------------------------")
    print(f"Original loop engine           {t_loop:8.4f}   {1.0:7.2f}x")
    print(f"Vectorised engine (1 thread)  {t_vec:8.4f}   {t_loop / max(t_vec, 1e-9):7.2f}x")
    print(f"Vectorised + parallel         {t_par:8.4f}   {t_loop / max(t_par, 1e-9):7.2f}x")


if __name__ == "__main__":
    main()
