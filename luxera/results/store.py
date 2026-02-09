from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np


def results_root(project_root: Path) -> Path:
    return project_root / ".luxera" / "results"


def ensure_result_dir(project_root: Path, job_hash: str) -> Path:
    root = results_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    out = root / job_hash
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_result_json(out_dir: Path, result: Dict[str, Any]) -> Path:
    out_path = out_dir / "result.json"
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def write_named_json(out_dir: Path, name: str, payload: Dict[str, Any]) -> Path:
    out_path = out_dir / name
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def write_grid_csv(out_dir: Path, points: np.ndarray, values: np.ndarray) -> Path:
    out_path = out_dir / "grid.csv"
    data = np.column_stack([points, values.reshape(-1, 1)])
    header = "x,y,z,illuminance"
    np.savetxt(out_path, data, delimiter=",", header=header, comments="")
    return out_path


def write_residuals_csv(out_dir: Path, residuals: list[float]) -> Path:
    out_path = out_dir / "residuals.csv"
    data = np.array(residuals, dtype=float).reshape(-1, 1)
    np.savetxt(out_path, data, delimiter=",", header="residual", comments="")
    return out_path


def write_surface_illuminance_csv(out_dir: Path, surface_illuminance: dict[str, float]) -> Path:
    out_path = out_dir / "surface_illuminance.csv"
    rows = [(k, v) for k, v in surface_illuminance.items()]
    lines = ["surface_id,illuminance"] + [f"{k},{v}" for k, v in rows]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def write_surface_grid_csv(out_dir: Path, surface_id: str, points: np.ndarray, values: np.ndarray) -> Path:
    out_path = out_dir / f"{surface_id}_grid.csv"
    data = np.column_stack([points, values.reshape(-1, 1)])
    header = "x,y,z,illuminance"
    np.savetxt(out_path, data, delimiter=",", header=header, comments="")
    return out_path


def write_manifest(out_dir: Path) -> Path:
    from luxera.core.hashing import sha256_file

    entries = {}
    for path in sorted(out_dir.glob("*")):
        if path.name == "manifest.json":
            continue
        if path.is_file():
            entries[path.name] = sha256_file(str(path))

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path
