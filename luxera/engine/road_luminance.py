from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/roadway_grid_definition.md."""

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np


@dataclass(frozen=True)
class RoadLuminanceResult:
    summary: Dict[str, object]
    lane_grids: List[Dict[str, object]]


def _grid_stats(values_2d: np.ndarray) -> Dict[str, float]:
    vals = values_2d.reshape(-1)
    mean_v = float(np.mean(vals)) if vals.size else 0.0
    min_v = float(np.min(vals)) if vals.size else 0.0
    max_v = float(np.max(vals)) if vals.size else 0.0
    return {
        "min_lux": min_v,
        "max_lux": max_v,
        "mean_lux": mean_v,
        "uniformity_ratio": (min_v / mean_v) if mean_v > 1e-9 else 0.0,
        "uniformity_diversity": (min_v / max_v) if max_v > 1e-9 else 0.0,
    }


def _observer_luminance(
    points: np.ndarray,
    luminance_cd_m2: np.ndarray,
    origin: Tuple[float, float, float],
    lane_width: float,
    settings: Dict[str, object],
) -> List[Dict[str, float]]:
    obs_h = float(settings.get("observer_height_m", 1.5))
    back = float(settings.get("observer_back_offset_m", 60.0))
    lat = settings.get("observer_lateral_positions_m")
    if isinstance(lat, list) and lat:
        lateral_positions = [float(v) for v in lat]
    else:
        lateral_positions = [lane_width * 0.5]
    out: List[Dict[str, float]] = []
    for i, y in enumerate(lateral_positions):
        ox = float(origin[0] - back)
        oy = float(origin[1] + y)
        oz = float(origin[2] + obs_h)
        observer = np.array([ox, oy, oz], dtype=float)
        rays = points - observer[None, :]
        d = np.linalg.norm(rays, axis=1)
        forward = rays[:, 0] > 0.0
        valid = forward & (d > 1e-9)
        if not np.any(valid):
            out.append({"observer_index": float(i), "x": ox, "y": oy, "z": oz, "luminance_cd_m2": 0.0})
            continue
        cos_theta = np.clip(rays[valid, 0] / d[valid], 0.0, 1.0)
        w = cos_theta / np.maximum(d[valid] ** 2, 1e-12)
        lv = float(np.sum(luminance_cd_m2[valid] * w) / np.sum(w)) if np.sum(w) > 1e-12 else 0.0
        out.append({"observer_index": float(i), "x": ox, "y": oy, "z": oz, "luminance_cd_m2": lv})
    return out


def compute_road_luminance_metrics(
    points: np.ndarray,
    lux_values: np.ndarray,
    *,
    nx: int,
    ny: int,
    lane_width_m: float,
    num_lanes: int,
    road_length_m: float,
    origin: Tuple[float, float, float],
    settings: Dict[str, object],
) -> RoadLuminanceResult:
    vals = np.asarray(lux_values, dtype=float).reshape(ny, nx)
    pts = np.asarray(points, dtype=float).reshape(ny, nx, 3)
    stats = _grid_stats(vals)
    centerline = vals[ny // 2, :]
    ul = float(np.min(centerline) / np.mean(centerline)) if centerline.size and float(np.mean(centerline)) > 1e-9 else 0.0

    rho = float(settings.get("road_surface_reflectance", 0.07))
    luminance = vals.reshape(-1) * rho / math.pi
    view_rows = _observer_luminance(points.reshape(-1, 3), luminance, origin, lane_width_m, settings)
    mean_lum = float(np.mean(luminance)) if luminance.size else 0.0
    max_view_lum = max((float(v.get("luminance_cd_m2", 0.0)) for v in view_rows), default=0.0)
    ti_proxy = 65.0 * max_view_lum / max(mean_lum + 1.0, 1.0)
    if ny >= 3:
        edge = np.concatenate([vals[0, :], vals[-1, :]])
        center = vals[ny // 2, :]
        surround_ratio_proxy = float(np.mean(edge) / np.mean(center)) if center.size and float(np.mean(center)) > 1e-9 else 0.0
    else:
        surround_ratio_proxy = 0.0

    lane_metrics: List[Dict[str, float]] = []
    lane_grids: List[Dict[str, object]] = []
    lane_band = max(1, ny // max(1, num_lanes))
    for lane_idx in range(max(0, num_lanes)):
        y0 = lane_idx * lane_band
        y1 = ny if lane_idx == num_lanes - 1 else min(ny, (lane_idx + 1) * lane_band)
        lane_vals = vals[y0:y1, :].reshape(-1)
        lane_pts = pts[y0:y1, :, :].reshape(-1, 3)
        if lane_vals.size == 0:
            continue
        lane_mean = float(np.mean(lane_vals))
        lane_min = float(np.min(lane_vals))
        lane_max = float(np.max(lane_vals))
        lane_uo = lane_min / lane_mean if lane_mean > 1e-9 else 0.0
        lane_center = vals[min((y0 + y1) // 2, ny - 1), :]
        lane_ul = float(np.min(lane_center) / np.mean(lane_center)) if lane_center.size and float(np.mean(lane_center)) > 1e-9 else 0.0
        lane_lum = lane_vals * rho / math.pi
        lane_metrics.append(
            {
                "lane_index": float(lane_idx),
                "lane_number": float(lane_idx + 1),
                "mean_lux": lane_mean,
                "min_lux": lane_min,
                "max_lux": lane_max,
                "uniformity_ratio": lane_uo,
                "uniformity_min_avg": lane_uo,
                "ul_longitudinal": lane_ul,
                "sample_count": float(lane_vals.size),
                "nx": float(nx),
                "ny": float(max(y1 - y0, 0)),
                "luminance_mean_cd_m2": float(np.mean(lane_lum)) if lane_lum.size else 0.0,
            }
        )
        lane_grids.append(
            {
                "lane_index": lane_idx,
                "lane_number": lane_idx + 1,
                "points": lane_pts,
                "values": lane_vals,
                "nx": nx,
                "ny": max(y1 - y0, 0),
            }
        )

    summary: Dict[str, object] = {
        **stats,
        "overall_uniformity_min_avg": float(stats.get("uniformity_ratio", 0.0)),
        "ul_longitudinal": ul,
        "lane_width_m": float(lane_width_m),
        "num_lanes": int(num_lanes),
        "road_length_m": float(road_length_m),
        "road_surface_reflectance": rho,
        "road_luminance_mean_cd_m2": mean_lum,
        "observer_luminance_views": view_rows,
        "observer_luminance_max_cd_m2": max_view_lum,
        "threshold_increment_ti_proxy_percent": float(ti_proxy),
        "surround_ratio_proxy": surround_ratio_proxy,
        "lane_metrics": lane_metrics,
        "lanes": lane_metrics,
        "overall": {
            "avg_lux": stats.get("mean_lux", 0.0),
            "min_lux": stats.get("min_lux", 0.0),
            "max_lux": stats.get("max_lux", 0.0),
            "u0": stats.get("uniformity_ratio", 0.0),
        },
    }
    return RoadLuminanceResult(summary=summary, lane_grids=lane_grids)
