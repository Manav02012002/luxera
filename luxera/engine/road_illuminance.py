from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/roadway_grid_definition.md."""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.engine.direct_illuminance import run_direct_grid
from luxera.engine.roadway_grids import resolve_lane_slices
from luxera.project.schema import CalcGrid, RoadwayGridSpec, RoadwaySpec


@dataclass(frozen=True)
class RoadIlluminanceResult:
    points: np.ndarray
    values: np.ndarray
    nx: int
    ny: int
    lane_grids: List[Dict[str, object]]
    summary: Dict[str, object]


def compute_lane_luminance_metrics(
    luminance_grid: np.ndarray,
    *,
    lane_ranges: List[tuple[int, int, int]],
    longitudinal_line_policy: str = "center",
) -> tuple[List[Dict[str, float]], Dict[str, float]]:
    arr = np.asarray(luminance_grid, dtype=float)
    lanes: List[Dict[str, float]] = []
    for lane_number, y0, y1 in lane_ranges:
        band = arr[int(y0):int(y1), :]
        if band.size == 0:
            continue
        lavg = float(np.mean(band))
        lmin = float(np.min(band))
        uo = lmin / lavg if lavg > 1e-12 else 0.0
        if str(longitudinal_line_policy).lower() == "center":
            row = band[min(max(band.shape[0] // 2, 0), band.shape[0] - 1), :]
        else:
            row = band[0, :]
        row_min = float(np.min(row)) if row.size else 0.0
        row_max = float(np.max(row)) if row.size else 0.0
        ul = row_min / row_max if row_max > 1e-12 else 0.0
        lanes.append(
            {
                "lane_number": float(lane_number),
                "Lavg_cd_m2": lavg,
                "Uo_luminance": uo,
                "Ul_luminance": ul,
            }
        )
    worst = {
        "lavg_min_cd_m2": float(min((l["Lavg_cd_m2"] for l in lanes), default=0.0)),
        "uo_min": float(min((l["Uo_luminance"] for l in lanes), default=0.0)),
        "ul_min": float(min((l["Ul_luminance"] for l in lanes), default=0.0)),
    }
    return lanes, worst


def _compute_grid_stats(values: np.ndarray) -> Dict[str, float]:
    vals = values.reshape(-1)
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
    origin: tuple[float, float, float],
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


def _resolve_grid_dimensions(rg: RoadwayGridSpec) -> tuple[int, int]:
    nx = int(rg.longitudinal_points or rg.nx)
    if rg.transverse_points_per_lane:
        ny = int(max(1, rg.num_lanes) * int(rg.transverse_points_per_lane))
    else:
        ny = int(rg.ny)
    return max(1, nx), max(1, ny)


def run_road_illuminance(
    roadway: Optional[RoadwaySpec],
    grid: RoadwayGridSpec,
    luminaires: List[Luminaire],
    settings: Dict[str, object],
) -> RoadIlluminanceResult:
    scale = float(settings.get("length_scale_to_m", 1.0))
    nx, ny = _resolve_grid_dimensions(grid)
    lane_width = float(grid.lane_width) * scale
    num_lanes = int(grid.num_lanes)
    road_length = float(grid.road_length) * scale
    origin = tuple(float(v) * scale for v in grid.origin)

    if roadway is not None:
        lane_width = float(roadway.lane_width) * scale
        num_lanes = int(roadway.num_lanes)
        origin = tuple(float(v) * scale for v in roadway.start)
        dx = (roadway.end[0] - roadway.start[0]) * scale
        dy = (roadway.end[1] - roadway.start[1]) * scale
        dz = (roadway.end[2] - roadway.start[2]) * scale
        road_length = float(math.sqrt(dx * dx + dy * dy + dz * dz))

    road_grid = CalcGrid(
        id=grid.id,
        name=grid.name,
        origin=origin,
        width=road_length,
        height=lane_width * max(1, num_lanes),
        elevation=origin[2],
        nx=nx,
        ny=ny,
        normal=(0.0, 0.0, 1.0),
    )
    road = run_direct_grid(road_grid, luminaires, occluders=None, use_occlusion=False, occlusion_epsilon=1e-6)
    vals = np.array(road.result.values, dtype=float).reshape(ny, nx)
    points = np.array(road.points, dtype=float)

    # Optional geometric roadway segment transform (curve + bank) for reporting grids.
    segment = getattr(roadway, "segment", None) if roadway is not None else None
    if segment is not None:
        local = points - np.array([[origin[0], origin[1], origin[2]]], dtype=float)
        x = local[:, 0]
        y = local[:, 1]
        z = local[:, 2]
        radius = float(getattr(segment, "curve_radius_m", 0.0) or 0.0)
        angle_deg = float(getattr(segment, "curve_angle_deg", 0.0) or 0.0)
        if radius > 1e-9 and abs(angle_deg) > 1e-9 and road_length > 1e-9:
            # Map longitudinal x to arc angle to preserve equal arc-length spacing.
            arc_theta = (x / road_length) * math.radians(angle_deg)
            sign = 1.0 if str(getattr(segment, "curve_direction", "left")).lower() == "left" else -1.0
            x = radius * np.sin(sign * arc_theta)
            y = y + sign * (radius * (1.0 - np.cos(arc_theta)))
        bank_deg = float(getattr(segment, "bank_angle_deg", 0.0) or 0.0)
        if abs(bank_deg) > 1e-9:
            z = z + y * math.tan(math.radians(bank_deg))
        points = np.stack([x + origin[0], y + origin[1], z + origin[2]], axis=1)
    centerline = vals[ny // 2, :]
    ul = float(np.min(centerline) / np.mean(centerline)) if centerline.size and float(np.mean(centerline)) > 1e-9 else 0.0
    rho = float(settings.get("road_surface_reflectance", 0.07))
    luminance = np.array(road.result.values, dtype=float).reshape(-1) * rho / math.pi
    luminance_grid = vals * rho / math.pi
    views = _observer_luminance(points, luminance, origin, lane_width, settings)
    mean_lum = float(np.mean(luminance)) if luminance.size else 0.0
    max_view_lum = max((float(v.get("luminance_cd_m2", 0.0)) for v in views), default=0.0)
    ti_proxy = 65.0 * max_view_lum / max(mean_lum + 1.0, 1.0)
    if ny >= 3:
        edge = np.concatenate([vals[0, :], vals[-1, :]])
        center = vals[ny // 2, :]
        surround_ratio_proxy = float(np.mean(edge) / np.mean(center)) if center.size and float(np.mean(center)) > 1e-9 else 0.0
    else:
        surround_ratio_proxy = 0.0

    summary: Dict[str, object] = dict(_compute_grid_stats(vals))
    summary["overall_uniformity_min_avg"] = float(summary.get("uniformity_ratio", 0.0))
    lane_metrics: List[Dict[str, float]] = []
    lane_grids: List[Dict[str, object]] = []
    if num_lanes > 0 and ny > 0:
        lane_band = max(1, ny // max(1, num_lanes))
        for lane_idx in range(num_lanes):
            y0 = lane_idx * lane_band
            y1 = ny if lane_idx == num_lanes - 1 else min(ny, (lane_idx + 1) * lane_band)
            lane_vals = vals[y0:y1, :].reshape(-1)
            if lane_vals.size == 0:
                continue
            lane_mean = float(np.mean(lane_vals))
            lane_min = float(np.min(lane_vals))
            lane_max = float(np.max(lane_vals))
            lane_uo = lane_min / lane_mean if lane_mean > 1e-9 else 0.0
            lane_center = vals[min((y0 + y1) // 2, ny - 1), :]
            lane_ul = float(np.min(lane_center) / np.mean(lane_center)) if lane_center.size and float(np.mean(lane_center)) > 1e-9 else 0.0
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
                    "luminance_mean_cd_m2": float(np.mean(lane_vals * rho / math.pi)),
                }
            )
            lane_points = points.reshape(ny, nx, 3)[y0:y1, :, :].reshape(-1, 3)
            lane_values = vals[y0:y1, :].reshape(-1)
            lane_grids.append(
                {
                    "lane_index": lane_idx,
                    "lane_number": lane_idx + 1,
                    "points": lane_points,
                    "values": lane_values,
                    "nx": nx,
                    "ny": max(y1 - y0, 0),
                }
            )
    lane_ranges = [(int(m["lane_number"]), int(s.y0), int(s.y1)) for m, s in zip(lane_metrics, resolve_lane_slices(num_lanes, ny))]
    luminance_lane_metrics, worst_case = compute_lane_luminance_metrics(
        luminance_grid,
        lane_ranges=lane_ranges,
        longitudinal_line_policy="center",
    )
    by_lane_num = {int(float(m["lane_number"])): m for m in lane_metrics}
    for lm in luminance_lane_metrics:
        base = by_lane_num.get(int(float(lm["lane_number"])))
        if base is not None:
            base.update(lm)

    summary.update(
        {
            "ul_longitudinal": ul,
            "lane_width_m": lane_width,
            "num_lanes": num_lanes,
            "road_length_m": road_length,
            "pole_spacing_m": roadway.pole_spacing_m if roadway is not None else grid.pole_spacing_m,
            "mounting_height_m": roadway.mounting_height_m if roadway is not None else grid.mounting_height_m,
            "setback_m": roadway.setback_m if roadway is not None else grid.setback_m,
            "road_surface_reflectance": rho,
            "road_luminance_mean_cd_m2": mean_lum,
            "observer_luminance_views": views,
            "observer_luminance_max_cd_m2": max_view_lum,
            "threshold_increment_ti_proxy_percent": float(ti_proxy),
            "surround_ratio_proxy": surround_ratio_proxy,
            "lane_metrics": lane_metrics,
            "lanes": lane_metrics,
            "roadway_worst_case": worst_case,
            "overall": {
                "avg_lux": summary.get("mean_lux", 0.0),
                "min_lux": summary.get("min_lux", 0.0),
                "max_lux": summary.get("max_lux", 0.0),
                "u0": summary.get("uniformity_ratio", 0.0),
            },
        }
    )
    if roadway is not None:
        summary["roadway_id"] = roadway.id
        summary["roadway_name"] = roadway.name

    return RoadIlluminanceResult(points=points, values=road.values, nx=nx, ny=ny, lane_grids=lane_grids, summary=summary)
