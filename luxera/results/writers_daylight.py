from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np

from luxera.results.grid_viz import write_grid_heatmap_and_isolux
from luxera.results.store import write_grid_csv_named, write_named_json, write_points_csv


def write_daylight_target_artifacts(
    out_dir: Path,
    target_id: str,
    target_type: str,
    points: np.ndarray,
    values: np.ndarray,
    nx: int = 0,
    ny: int = 0,
) -> Dict[str, str]:
    artifacts: Dict[str, str] = {}
    csv_name = f"daylight_{target_id}.csv"
    if target_type == "point_set":
        p = write_points_csv(out_dir, csv_name, points, values)
    else:
        p = write_grid_csv_named(out_dir, csv_name, points, values)
    artifacts["csv"] = str(p)
    if target_type in {"grid", "vertical_plane"} and nx > 0 and ny > 0:
        viz = write_grid_heatmap_and_isolux(out_dir, points, values, nx=nx, ny=ny)
        heatmap = viz.get("heatmap")
        if heatmap is not None:
            out = out_dir / f"daylight_{target_id}_heatmap.png"
            out.write_bytes(Path(heatmap).read_bytes())
            Path(heatmap).unlink(missing_ok=True)
            artifacts["heatmap"] = str(out)
        isolux = viz.get("isolux")
        if isolux is not None:
            Path(isolux).unlink(missing_ok=True)
    return artifacts


def write_daylight_summary(out_dir: Path, payload: Dict[str, object]) -> Path:
    return write_named_json(out_dir, "daylight_summary.json", payload)


def write_daylight_annual_target_artifacts(
    out_dir: Path,
    target_id: str,
    points: np.ndarray,
    sda_point_percent: np.ndarray,
    ase_point_percent: np.ndarray,
    udi_point_percent: np.ndarray,
    nx: int = 0,
    ny: int = 0,
) -> Dict[str, str]:
    artifacts: Dict[str, str] = {}
    write_points_csv(out_dir, f"sda_{target_id}.csv", points, sda_point_percent)
    write_points_csv(out_dir, f"ase_{target_id}.csv", points, ase_point_percent)
    write_points_csv(out_dir, f"udi_{target_id}.csv", points, udi_point_percent)
    artifacts["sda_csv"] = str(out_dir / f"sda_{target_id}.csv")
    artifacts["ase_csv"] = str(out_dir / f"ase_{target_id}.csv")
    artifacts["udi_csv"] = str(out_dir / f"udi_{target_id}.csv")
    if nx > 0 and ny > 0:
        for metric_name, values in (
            ("sda", sda_point_percent),
            ("ase", ase_point_percent),
            ("udi", udi_point_percent),
        ):
            viz = write_grid_heatmap_and_isolux(out_dir, points, values, nx=nx, ny=ny)
            heatmap = viz.get("heatmap")
            if heatmap is not None:
                out = out_dir / f"{metric_name}_{target_id}.png"
                out.write_bytes(Path(heatmap).read_bytes())
                Path(heatmap).unlink(missing_ok=True)
                artifacts[f"{metric_name}_heatmap"] = str(out)
            isolux = viz.get("isolux")
            if isolux is not None:
                Path(isolux).unlink(missing_ok=True)
    return artifacts
