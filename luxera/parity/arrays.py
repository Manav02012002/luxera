from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


def load_csv_grid(path: Path) -> np.ndarray:
    arr = np.loadtxt(Path(path), delimiter=",", dtype=float)
    return np.asarray(arr, dtype=float)


def stats_delta(a: np.ndarray, b: np.ndarray) -> dict:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    if aa.shape != bb.shape:
        raise ValueError(f"shape mismatch: {aa.shape} != {bb.shape}")
    diff = np.abs(aa - bb)
    return {
        "max_abs": float(np.max(diff)),
        "rmse": float(np.sqrt(np.mean((aa - bb) ** 2))),
        "mean_abs": float(np.mean(diff)),
        "p95_abs": float(np.percentile(diff, 95)),
        "p99_abs": float(np.percentile(diff, 99)),
    }


def compare_arrays(a: np.ndarray, b: np.ndarray, thresholds: dict) -> tuple[bool, dict, list[str]]:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    failures: List[str] = []

    if aa.shape != bb.shape:
        return (
            False,
            {
                "shape_actual": list(aa.shape),
                "shape_expected": list(bb.shape),
            },
            [f"shape mismatch: actual={list(aa.shape)} expected={list(bb.shape)}"],
        )

    stats = stats_delta(aa, bb)

    for key in ("max_abs", "rmse", "mean_abs", "p95_abs", "p99_abs"):
        if key not in thresholds:
            continue
        limit = float(thresholds[key])
        val = float(stats[key])
        if val > limit:
            failures.append(f"{key}={val:.8g} > {limit:.8g}")

    return (not failures, stats, failures)


def array_sha256(arr: np.ndarray) -> str:
    aa = np.asarray(arr, dtype=float)
    hasher = hashlib.sha256()
    hasher.update(str(tuple(int(x) for x in aa.shape)).encode("utf-8"))
    hasher.update(aa.tobytes(order="C"))
    return f"sha256:{hasher.hexdigest()}"


def write_array_capture(
    out_dir: Path,
    name: str,
    arr: np.ndarray,
    *,
    fmt: str = "csv",
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name)
    aa = np.asarray(arr, dtype=float)

    if fmt.lower() == "npy":
        dst = out / f"{safe_name}.npy"
        np.save(dst, aa)
        return dst

    dst = out / f"{safe_name}.csv"
    np.savetxt(dst, aa, delimiter=",", fmt="%.10g")
    return dst
