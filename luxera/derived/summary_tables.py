from __future__ import annotations

import csv
import io
from typing import Dict, List

import numpy as np


def _as_array(values) -> np.ndarray:
    if values is None:
        return np.zeros((0,), dtype=float)
    try:
        arr = np.asarray(values, dtype=float).reshape(-1)
    except Exception:
        return np.zeros((0,), dtype=float)
    return arr


def _estimate_spacing(points, nx: int, ny: int) -> float | None:
    try:
        pts = np.asarray(points, dtype=float).reshape(-1, 3)
    except Exception:
        return None
    if pts.shape[0] < 2:
        return None
    if nx > 1:
        d = float(np.linalg.norm(pts[1] - pts[0]))
        if d > 0:
            return d
    if ny > 1 and pts.shape[0] >= nx + 1:
        d = float(np.linalg.norm(pts[nx] - pts[0]))
        if d > 0:
            return d
    return None


def grid_stats(values, spacing: float | None = None, area: float | None = None) -> Dict[str, float | None]:
    vals = _as_array(values)
    mean_v = float(np.mean(vals)) if vals.size else 0.0
    min_v = float(np.min(vals)) if vals.size else 0.0
    max_v = float(np.max(vals)) if vals.size else 0.0
    return {
        "point_count": float(vals.size),
        "spacing": float(spacing) if spacing is not None else None,
        "area": float(area) if area is not None else None,
        "min_lux": min_v,
        "mean_lux": mean_v,
        "max_lux": max_v,
        "uniformity_min_avg": (min_v / mean_v) if mean_v > 1e-9 else 0.0,
    }


def plane_stats(values, spacing: float | None = None, area: float | None = None) -> Dict[str, float | None]:
    return grid_stats(values, spacing=spacing, area=area)


def pointset_stats(values) -> Dict[str, float | None]:
    return grid_stats(values, spacing=None, area=None)


def aggregate_stats(rows: List[Dict[str, object]]) -> Dict[str, float]:
    if not rows:
        return {
            "global_worst_min_lux": 0.0,
            "global_worst_uniformity_ratio": 0.0,
            "global_mean_of_means_lux": 0.0,
        }
    mins = [float(r.get("min_lux", 0.0)) for r in rows]
    u0s = [float(r.get("uniformity_min_avg", 0.0)) for r in rows]
    means = [float(r.get("mean_lux", 0.0)) for r in rows]
    return {
        "global_worst_min_lux": min(mins),
        "global_worst_uniformity_ratio": min(u0s),
        "global_mean_of_means_lux": float(np.mean(means)) if means else 0.0,
    }


def _row_from_obj(obj: Dict[str, object]) -> Dict[str, object]:
    nx = int(obj.get("nx", 0) or 0)
    ny = int(obj.get("ny", 0) or 0)
    points = obj.get("points")
    values = obj.get("values")
    spacing = _estimate_spacing(points, nx=nx, ny=ny)
    area = None
    if str(obj.get("type", "")) == "grid":
        width = obj.get("width")
        height = obj.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            area = float(width) * float(height)
    elif str(obj.get("type", "")) == "vertical_plane":
        width = obj.get("width")
        height = obj.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            area = float(width) * float(height)
    elif nx > 0 and ny > 0 and spacing is not None:
        area = float(spacing * max(nx - 1, 0) * spacing * max(ny - 1, 0))

    if str(obj.get("type", "")) == "point_set":
        stats = pointset_stats(values)
    elif str(obj.get("type", "")) == "vertical_plane":
        stats = plane_stats(values, spacing=spacing, area=area)
    else:
        stats = grid_stats(values, spacing=spacing, area=area)

    point_count = int(stats["point_count"] or 0)
    return {
        "id": str(obj.get("id", "")),
        "name": str(obj.get("name", "")),
        "type": str(obj.get("type", "")),
        "spacing": stats["spacing"],
        "area": stats["area"],
        "point_count": (nx * ny) if nx > 0 and ny > 0 else point_count,
        "min_lux": float(stats["min_lux"] or 0.0),
        "mean_lux": float(stats["mean_lux"] or 0.0),
        "max_lux": float(stats["max_lux"] or 0.0),
        "uniformity_min_avg": float(stats["uniformity_min_avg"] or 0.0),
    }


def build_grid_table(calc_objects: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return [_row_from_obj(o) for o in calc_objects if str(o.get("type")) == "grid"]


def build_plane_table(calc_objects: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return [_row_from_obj(o) for o in calc_objects if str(o.get("type")) == "vertical_plane"]


def build_pointset_table(calc_objects: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return [_row_from_obj(o) for o in calc_objects if str(o.get("type")) == "point_set"]


def build_worstcase_summary(calc_objects: List[Dict[str, object]]) -> Dict[str, float]:
    rows = [_row_from_obj(o) for o in calc_objects]
    return aggregate_stats(rows)


def to_csv(rows: List[Dict[str, object]]) -> str:
    if not rows:
        return ""
    keys = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in keys})
    return buf.getvalue()
