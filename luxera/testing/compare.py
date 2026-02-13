from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from luxera.testing.golden import GoldenCase


@dataclass(frozen=True)
class GoldenCompareResult:
    case_id: str
    produced_dir: Path
    expected_dir: Path
    report_path: Path
    heatmap_paths: List[Path]
    passed: bool
    metrics: Dict[str, object]


def _load_grid_csv(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.loadtxt(path, delimiter=",", skiprows=1)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[1] < 4:
        raise ValueError(f"Grid CSV must contain x,y,z,value columns: {path}")
    return arr[:, 0:3], arr[:, 3].reshape(-1)


def _error_metrics(expected: np.ndarray, actual: np.ndarray) -> Dict[str, float]:
    if expected.shape != actual.shape:
        raise ValueError(f"Mismatched grid sizes: expected={expected.shape}, actual={actual.shape}")
    diff = actual - expected
    abs_diff = np.abs(diff)
    denom = np.maximum(np.abs(expected), 1e-9)
    rel = abs_diff / denom
    return {
        "max_abs_lux": float(np.max(abs_diff)) if abs_diff.size else 0.0,
        "mean_abs_lux": float(np.mean(abs_diff)) if abs_diff.size else 0.0,
        "mean_rel": float(np.mean(rel)) if rel.size else 0.0,
        "p95_abs_lux": float(np.percentile(abs_diff, 95.0)) if abs_diff.size else 0.0,
        "max_rel": float(np.max(rel)) if rel.size else 0.0,
    }


def _write_diff_heatmap(points: np.ndarray, abs_diff: np.ndarray, out_path: Path, title: str) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    sc = ax.scatter(points[:, 0], points[:, 1], c=abs_diff, cmap="inferno", s=36)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title(title)
    fig.colorbar(sc, ax=ax, label="|Δlux|")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def compare_golden_case(case: GoldenCase, produced_dir: Path) -> GoldenCompareResult:
    produced_dir = produced_dir.expanduser().resolve()
    expected_dir = case.expected_dir.expanduser().resolve()
    expected_grids = sorted(expected_dir.glob("grid_*.csv"))
    if not expected_grids:
        expected_grids = sorted(expected_dir.glob("surface_grid_*.csv"))
    if not expected_grids:
        expected_grids = sorted(expected_dir.glob("*_grid.csv"))
    if not expected_grids:
        raise FileNotFoundError(f"No expected grid CSV files in {expected_dir}")

    per_grid: List[Dict[str, object]] = []
    heatmaps: List[Path] = []
    passed = True
    summary_delta: Dict[str, object] = {}

    for eg in expected_grids:
        name = eg.name
        pg = produced_dir / name
        if not pg.exists() and len(expected_grids) == 1 and name.startswith("grid_") and (produced_dir / "grid.csv").exists():
            pg = produced_dir / "grid.csv"
        if not pg.exists():
            raise FileNotFoundError(f"Produced grid file missing: {pg}")

        exp_pts, exp_vals = _load_grid_csv(eg)
        act_pts, act_vals = _load_grid_csv(pg)
        if exp_pts.shape != act_pts.shape or not np.allclose(exp_pts, act_pts, rtol=0.0, atol=1e-9):
            raise ValueError(f"Point locations do not match for {name}")

        m = _error_metrics(exp_vals, act_vals)
        abs_diff = np.abs(act_vals - exp_vals)
        max_idx = int(np.argmax(abs_diff)) if abs_diff.size else 0
        max_xyz = exp_pts[max_idx].tolist() if abs_diff.size else [0.0, 0.0, 0.0]

        grid_pass = (
            m["max_abs_lux"] <= case.tolerances.get("max_abs_lux", float("inf"))
            and m["mean_rel"] <= case.tolerances.get("mean_rel", float("inf"))
            and m["p95_abs_lux"] <= case.tolerances.get("p95_abs_lux", float("inf"))
        )
        passed = passed and grid_pass

        stem = name.replace(".csv", "")
        hm_path = produced_dir / f"diff_heatmap_{stem}.png"
        _write_diff_heatmap(exp_pts, abs_diff, hm_path, title=f"{case.case_id} {stem} |Δlux|")
        heatmaps.append(hm_path)

        per_grid.append(
            {
                "grid_file": name,
                "produced_file": pg.name,
                "pass": bool(grid_pass),
                "metrics": m,
                "max_error_index": max_idx,
                "max_error_point_xyz": [float(x) for x in max_xyz],
            }
        )

    expected_summary_path = expected_dir / "summary.json"
    produced_summary_path = produced_dir / "summary.json"
    if expected_summary_path.exists() and produced_summary_path.exists():
        exp_summary = json.loads(expected_summary_path.read_text(encoding="utf-8"))
        act_summary = json.loads(produced_summary_path.read_text(encoding="utf-8"))
        if isinstance(exp_summary, dict) and isinstance(act_summary, dict):
            keys = sorted(set(exp_summary.keys()) | set(act_summary.keys()))
            for k in keys:
                ev = exp_summary.get(k)
                av = act_summary.get(k)
                if isinstance(ev, (int, float)) and isinstance(av, (int, float)):
                    summary_delta[k] = {"expected": float(ev), "actual": float(av), "delta": float(av) - float(ev)}
                else:
                    summary_delta[k] = {"expected": ev, "actual": av}

    if heatmaps:
        alias = produced_dir / "diff_heatmap.png"
        alias.write_bytes(heatmaps[0].read_bytes())

    report_payload: Dict[str, object] = {
        "case_id": case.case_id,
        "pass": bool(passed),
        "tolerances": dict(case.tolerances),
        "per_grid": per_grid,
        "summary_delta": summary_delta,
    }
    report_path = produced_dir / "diff_report.json"
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")

    return GoldenCompareResult(
        case_id=case.case_id,
        produced_dir=produced_dir,
        expected_dir=expected_dir,
        report_path=report_path,
        heatmap_paths=heatmaps,
        passed=bool(passed),
        metrics=report_payload,
    )
