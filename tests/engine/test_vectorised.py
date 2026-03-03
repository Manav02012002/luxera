from __future__ import annotations

import time

import numpy as np

from luxera.engine.vectorised import ParallelEngine, VectorisedDirectEngine


def _loop_reference(
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
        px, py, pz = (float(grid_points[i, 0]), float(grid_points[i, 1]), float(grid_points[i, 2]))
        nx, ny, nz = (float(grid_normals[i, 0]), float(grid_normals[i, 1]), float(grid_normals[i, 2]))
        total = 0.0
        for j in range(n):
            dx = float(lum_positions[j, 0]) - px
            dy = float(lum_positions[j, 1]) - py
            dz = float(lum_positions[j, 2]) - pz
            d2 = dx * dx + dy * dy + dz * dz
            if d2 <= 1e-12:
                continue
            d = d2 ** 0.5
            ux = dx / d
            uy = dy / d
            uz = dz / d
            cos_t = ux * nx + uy * ny + uz * nz
            if cos_t <= 0.0:
                continue
            total += float(lum_intensities[j]) * cos_t / d2 * float(lum_flux[j]) * float(lum_mf[j])
        out[i] = total
    return out


def _sample_data(m: int, n: int, seed: int = 7):
    rng = np.random.default_rng(seed)
    pts = np.zeros((m, 3), dtype=float)
    pts[:, 0] = rng.uniform(0.0, 20.0, size=m)
    pts[:, 1] = rng.uniform(0.0, 15.0, size=m)
    pts[:, 2] = 0.8
    nrm = np.zeros((m, 3), dtype=float)
    nrm[:, 2] = 1.0
    lpos = np.zeros((n, 3), dtype=float)
    lpos[:, 0] = rng.uniform(1.0, 19.0, size=n)
    lpos[:, 1] = rng.uniform(1.0, 14.0, size=n)
    lpos[:, 2] = rng.uniform(2.5, 3.2, size=n)
    lint = rng.uniform(3000.0, 12000.0, size=n)
    lflux = rng.uniform(0.7, 1.2, size=n)
    lmf = rng.uniform(0.75, 1.0, size=n)
    return pts, nrm, lpos, lint, lflux, lmf


def test_vectorised_matches_loop() -> None:
    pts, nrm, lpos, lint, lflux, lmf = _sample_data(240, 12, seed=11)
    eng = VectorisedDirectEngine()
    v = eng.compute_grid(pts, nrm, lpos, lint, lflux, lmf)
    r = _loop_reference(pts, nrm, lpos, lint, lflux, lmf)
    np.testing.assert_allclose(v, r, rtol=1e-6, atol=1e-9)


def test_vectorised_speed() -> None:
    pts, nrm, lpos, lint, lflux, lmf = _sample_data(4800, 20, seed=21)
    eng = VectorisedDirectEngine()

    # Warm-up
    _ = eng.compute_grid(pts, nrm, lpos, lint, lflux, lmf)

    loop_times = []
    vec_times = []
    for _ in range(3):
        t0 = time.perf_counter()
        _ = _loop_reference(pts, nrm, lpos, lint, lflux, lmf)
        loop_times.append(time.perf_counter() - t0)

        t1 = time.perf_counter()
        _ = eng.compute_grid(pts, nrm, lpos, lint, lflux, lmf)
        vec_times.append(time.perf_counter() - t1)

    loop_t = float(np.median(loop_times))
    vec_t = float(np.median(vec_times))
    assert vec_t * 5.0 <= loop_t


def test_parallel_matches_single() -> None:
    pts, nrm, lpos, lint, lflux, lmf = _sample_data(1200, 18, seed=37)
    eng = VectorisedDirectEngine()
    single = eng.compute_grid(pts, nrm, lpos, lint, lflux, lmf)

    par = ParallelEngine(n_workers=2)
    parallel = par.compute_parallel(eng, pts, nrm, lpos, lint, lflux, lmf)
    np.testing.assert_allclose(parallel, single, rtol=0.0, atol=1e-12)


def test_chunking_large_grid() -> None:
    pts, nrm, lpos, lint, lflux, lmf = _sample_data(10000, 50, seed=99)
    eng_chunked = VectorisedDirectEngine(max_pairs_per_batch=100_000)
    eng_full = VectorisedDirectEngine(max_pairs_per_batch=100_000_000)

    chunked = eng_chunked.compute_grid(pts, nrm, lpos, lint, lflux, lmf)
    full = eng_full.compute_grid(pts, nrm, lpos, lint, lflux, lmf)

    assert chunked.shape == (10000,)
    assert np.all(np.isfinite(chunked))
    np.testing.assert_allclose(chunked, full, rtol=1e-9, atol=1e-9)


def test_cos_theta_clamp() -> None:
    pts = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=float)
    nrm = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=float)
    lpos = np.array([[0.0, 0.0, 3.0], [0.0, 0.0, -2.0]], dtype=float)
    lint = np.array([1000.0, 1000.0], dtype=float)
    lflux = np.array([1.0, 1.0], dtype=float)
    lmf = np.array([1.0, 1.0], dtype=float)

    eng = VectorisedDirectEngine()
    out = eng.compute_grid(pts, nrm, lpos, lint, lflux, lmf)

    # Second luminaire is below the plane normal direction and should not contribute.
    assert np.all(out > 0.0)
    out_only_top = eng.compute_grid(pts, nrm, lpos[:1], lint[:1], lflux[:1], lmf[:1])
    np.testing.assert_allclose(out, out_only_top, rtol=0.0, atol=1e-12)
