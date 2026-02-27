from __future__ import annotations

from pathlib import Path

import numpy as np

from luxera.parity.arrays import compare_arrays, load_csv_grid, stats_delta, write_array_capture


def test_stats_delta_correctness() -> None:
    a = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float)
    b = np.array([[1.0, 2.5], [2.0, 5.0]], dtype=float)
    stats = stats_delta(a, b)

    # abs diffs: [0, 0.5, 1.0, 1.0]
    assert stats["max_abs"] == 1.0
    assert stats["mean_abs"] == 0.625
    assert stats["rmse"] == np.sqrt((0.0**2 + 0.5**2 + 1.0**2 + 1.0**2) / 4.0)
    assert 0.0 <= stats["p95_abs"] <= 1.0
    assert 0.0 <= stats["p99_abs"] <= 1.0


def test_compare_arrays_pass_and_fail_thresholds() -> None:
    a = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float)
    b = np.array([[1.0, 2.1], [2.9, 4.0]], dtype=float)

    ok_loose, stats_loose, failures_loose = compare_arrays(
        a,
        b,
        {
            "max_abs": 0.2,
            "rmse": 0.2,
            "mean_abs": 0.2,
            "p95_abs": 0.2,
            "p99_abs": 0.2,
        },
    )
    assert ok_loose
    assert failures_loose == []
    assert stats_loose["max_abs"] <= 0.2

    ok_tight, _, failures_tight = compare_arrays(
        a,
        b,
        {
            "max_abs": 0.05,
            "rmse": 0.05,
            "mean_abs": 0.05,
            "p95_abs": 0.05,
            "p99_abs": 0.05,
        },
    )
    assert not ok_tight
    assert failures_tight


def test_compare_arrays_shape_mismatch_detection() -> None:
    a = np.array([[1.0, 2.0]], dtype=float)
    b = np.array([[1.0], [2.0]], dtype=float)

    ok, stats, failures = compare_arrays(a, b, {"max_abs": 1.0})
    assert not ok
    assert "shape_actual" in stats
    assert "shape_expected" in stats
    assert failures and "shape mismatch" in failures[0]


def test_csv_load_and_capture_helpers(tmp_path: Path) -> None:
    arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float)

    csv_path = tmp_path / "g.csv"
    np.savetxt(csv_path, arr, delimiter=",", fmt="%.10g")
    loaded = load_csv_grid(csv_path)
    assert loaded.shape == (2, 2)
    assert np.allclose(arr, loaded)

    captured_csv = write_array_capture(tmp_path / "capture", "grid_a", arr, fmt="csv")
    assert captured_csv.exists()

    captured_npy = write_array_capture(tmp_path / "capture", "grid_b", arr, fmt="npy")
    assert captured_npy.exists()
