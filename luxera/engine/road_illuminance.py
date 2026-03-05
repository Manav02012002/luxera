from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/roadway_grid_definition.md."""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.engine.direct_illuminance import run_direct_grid
from luxera.engine.road_glare import compute_observer_glare_metrics
from luxera.engine.road_reflection import compute_observer_point_luminance, resolve_surface_class
from luxera.engine.roadway_grids import resolve_lane_slices, resolve_lane_widths, resolve_observers
from luxera.project.schema import CalcGrid, RoadwayGridSpec, RoadwaySpec

TI_PROXY_COEFFICIENT = 57.486819


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
    lane_ranges: List[tuple[int, int, int]],
    longitudinal_line_policy: str = "center",
) -> tuple[List[Dict[str, float]], Dict[str, float]]:
    """
    Compute per-lane luminance metrics.

    lane_ranges entries are tuples of:
    (lane_number, y0_inclusive, y1_exclusive)
    """
    lum = np.asarray(luminance_grid, dtype=float)
    if lum.ndim != 2:
        raise ValueError("luminance_grid must be 2D")

    lanes: List[Dict[str, float]] = []
    for lane_number, y0, y1 in lane_ranges:
        y0i = int(max(0, y0))
        y1i = int(min(lum.shape[0], y1))
        lane = lum[y0i:y1i, :]
        if lane.size == 0:
            continue
        lavg = float(np.mean(lane))
        lmin = float(np.min(lane))
        lmax = float(np.max(lane))
        uo = lmin / lavg if lavg > 1e-12 else 0.0

        if str(longitudinal_line_policy).lower() == "center":
            center_line = lane[lane.shape[0] // 2, :]
        else:
            center_line = lane.reshape(-1)
        cl_min = float(np.min(center_line)) if center_line.size else 0.0
        cl_max = float(np.max(center_line)) if center_line.size else 0.0
        ul = cl_min / cl_max if cl_max > 1e-12 else 0.0

        lanes.append(
            {
                "lane_number": float(lane_number),
                "Lavg_cd_m2": lavg,
                "Lmin_cd_m2": lmin,
                "Lmax_cd_m2": lmax,
                "Uo_luminance": uo,
                "Ul_luminance": ul,
            }
        )

    worst = {
        "lavg_min_cd_m2": float(min((r["Lavg_cd_m2"] for r in lanes), default=0.0)),
        "uo_min": float(min((r["Uo_luminance"] for r in lanes), default=0.0)),
        "ul_min": float(min((r["Ul_luminance"] for r in lanes), default=0.0)),
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


def _map_road_point(
    origin: tuple[float, float, float],
    heading: float,
    road_length: float,
    total_width: float,
    nx: int,
    ny: int,
    col: int,
    row: int,
    curve_radius_m: Optional[float],
    curve_angle_deg: Optional[float],
    curve_direction: str,
    bank_angle_deg: float,
) -> np.ndarray:
    s = 0.0 if nx <= 1 else (float(col) / float(max(nx - 1, 1))) * float(road_length)
    y_off = 0.0 if ny <= 1 else (float(row) / float(max(ny - 1, 1))) * float(total_width)

    if curve_radius_m is not None and curve_angle_deg is not None and abs(float(curve_angle_deg)) > 1e-9:
        sign = 1.0 if str(curve_direction).lower() != "right" else -1.0
        theta = sign * math.radians(abs(float(curve_angle_deg))) * (s / max(float(road_length), 1e-9))
        x_local = float(curve_radius_m) * math.sin(theta)
        y_center = sign * float(curve_radius_m) * (1.0 - math.cos(theta))
        y_local = y_center + y_off
    else:
        x_local = s
        y_local = y_off

    z_local = float(origin[2]) + y_local * math.tan(math.radians(float(bank_angle_deg)))

    ch = math.cos(heading)
    sh = math.sin(heading)
    x = float(origin[0]) + x_local * ch - y_local * sh
    y = float(origin[1]) + x_local * sh + y_local * ch
    return np.array([x, y, z_local], dtype=float)


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
    lane_widths = [float(w) * scale for w in resolve_lane_widths(roadway, grid)]
    if lane_widths:
        num_lanes = len(lane_widths)
        lane_width = float(sum(lane_widths) / max(1, len(lane_widths)))
    else:
        lane_widths = [lane_width] * max(1, num_lanes)
    heading = math.atan2((roadway.end[1] - roadway.start[1]) if roadway is not None else 0.0, (roadway.end[0] - roadway.start[0]) if roadway is not None else 1.0)

    seg = roadway.segment if roadway is not None else None
    curve_radius_m = float(seg.curve_radius_m) * scale if (seg is not None and seg.curve_radius_m is not None) else None
    curve_angle_deg = float(seg.curve_angle_deg) if (seg is not None and seg.curve_angle_deg is not None) else None
    curve_direction = str(seg.curve_direction) if seg is not None else "left"
    bank_angle_deg = float(seg.bank_angle_deg) if seg is not None else 0.0

    road_grid = CalcGrid(
        id=grid.id,
        name=grid.name,
        origin=origin,
        width=road_length,
        height=float(sum(lane_widths)),
        elevation=origin[2],
        nx=nx,
        ny=ny,
        normal=(0.0, 0.0, 1.0),
    )
    road = run_direct_grid(road_grid, luminaires, occluders=None, use_occlusion=False, occlusion_epsilon=1e-6)

    vals = np.array(road.result.values, dtype=float).reshape(ny, nx)
    points = road.points
    mapped_points = np.zeros_like(points, dtype=float)
    total_width = float(sum(lane_widths))
    k = 0
    for j in range(ny):
        for i in range(nx):
            mapped_points[k] = _map_road_point(
                origin=origin,
                heading=heading,
                road_length=road_length,
                total_width=total_width,
                nx=nx,
                ny=ny,
                col=i,
                row=j,
                curve_radius_m=curve_radius_m,
                curve_angle_deg=curve_angle_deg,
                curve_direction=curve_direction,
                bank_angle_deg=bank_angle_deg,
            )
            k += 1
    centerline = vals[ny // 2, :]
    ul = float(np.min(centerline) / np.mean(centerline)) if centerline.size and float(np.mean(centerline)) > 1e-9 else 0.0
    rho = float(settings.get("road_surface_reflectance", 0.07))
    observers = resolve_observers(roadway, grid, origin, lane_widths, settings)
    try:
        surface_class = resolve_surface_class(settings)
        obs_lum, reflection_meta = compute_observer_point_luminance(
            mapped_points,
            observers=observers,
            luminaires=luminaires,
            surface_class=surface_class,
        )
        luminance = np.asarray(obs_lum[0], dtype=float).reshape(-1) if obs_lum.size else np.zeros((mapped_points.shape[0],), dtype=float)
        views = []
        for i, obs in enumerate(observers):
            lv = float(np.mean(obs_lum[i])) if (obs_lum.ndim == 2 and i < obs_lum.shape[0]) else 0.0
            views.append(
                {
                    "observer_index": float(i),
                    "observer_id": str(obs.get("observer_id", f"obs_{i+1}")),
                    "method": str(obs.get("method", "luminance")),
                    "x": float(obs.get("x", 0.0)),
                    "y": float(obs.get("y", 0.0)),
                    "z": float(obs.get("z", 0.0)),
                    "luminance_cd_m2": lv,
                }
            )
    except Exception:
        surface_class = "R3"
        reflection_meta = {}
        luminance = np.array(road.result.values, dtype=float).reshape(-1) * rho / math.pi
        views = _observer_luminance(mapped_points, luminance, origin, lane_width, settings)
    mean_lum = float(np.mean(luminance)) if luminance.size else 0.0
    max_view_lum = max((float(v.get("luminance_cd_m2", 0.0)) for v in views), default=0.0)
    ti_proxy = TI_PROXY_COEFFICIENT * max_view_lum / max(mean_lum + 1.0, 1.0)
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
        lane_slices = resolve_lane_slices(num_lanes, ny)
        lane_ranges: List[tuple[int, int, int]] = []
        for lane_idx, slc in enumerate(lane_slices):
            y0 = int(slc.y0)
            y1 = int(slc.y1)
            lane_ranges.append((lane_idx + 1, y0, y1))
            lane_vals = vals[y0:y1, :].reshape(-1)
            if lane_vals.size == 0:
                continue
            lane_mean = float(np.mean(lane_vals))
            lane_min = float(np.min(lane_vals))
            lane_max = float(np.max(lane_vals))
            lane_uo = lane_min / lane_mean if lane_mean > 1e-9 else 0.0
            lane_center = vals[min((y0 + y1) // 2, ny - 1), :]
            lane_ul = float(np.min(lane_center) / np.mean(lane_center)) if lane_center.size and float(np.mean(lane_center)) > 1e-9 else 0.0
            lane_row = (
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
                    "lane_width_m": float(lane_widths[lane_idx] if lane_idx < len(lane_widths) else lane_width),
                    "nx": float(nx),
                    "ny": float(max(y1 - y0, 0)),
                    "luminance_mean_cd_m2": float(np.mean(luminance.reshape(ny, nx)[y0:y1, :])) if (y1 - y0) > 0 else 0.0,
                }
            )
            lane_metrics.append(lane_row)
            lane_points_grid = mapped_points.reshape(ny, nx, 3)[y0:y1, :, :]
            lane_points = lane_points_grid.reshape(-1, 3)
            lane_values = vals[y0:y1, :].reshape(-1)
            luminance_grid: List[Dict[str, float]] = []
            order = 0
            for lr in range(max(y1 - y0, 0)):
                for lc in range(nx):
                    p = lane_points_grid[lr, lc]
                    lum_cd_m2 = float(luminance.reshape(ny, nx)[y0 + lr, lc])
                    luminance_grid.append(
                        {
                            "order": float(order),
                            "lane_row": float(lr),
                            "lane_col": float(lc),
                            "x": float(p[0]),
                            "y": float(p[1]),
                            "z": float(p[2]),
                            "illuminance_lux": float(vals[y0 + lr, lc]),
                            "luminance_cd_m2": lum_cd_m2,
                        }
                    )
                    order += 1
            lane_row["luminance_grid"] = luminance_grid
            lane_grids.append(
                {
                    "lane_index": lane_idx,
                    "lane_number": lane_idx + 1,
                    "points": lane_points,
                    "values": lane_values,
                    "luminance_grid": luminance_grid,
                    "nx": nx,
                    "ny": max(y1 - y0, 0),
                }
            )
        lum_grid = luminance.reshape(ny, nx)
        lum_lane_metrics, lum_worst = compute_lane_luminance_metrics(lum_grid, lane_ranges=lane_ranges, longitudinal_line_policy="center")
        by_lane_num = {int(float(x.get("lane_number", 0.0))): x for x in lum_lane_metrics}
        for row in lane_metrics:
            ln = int(float(row.get("lane_number", 0.0)))
            if ln in by_lane_num:
                row.update(by_lane_num[ln])
        summary["roadway_worst_case"] = lum_worst
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
            "road_surface_class": surface_class,
            "road_reflection_meta": reflection_meta,
            "road_luminance_mean_cd_m2": mean_lum,
            "observer_luminance_views": views,
            "observer_luminance_max_cd_m2": max_view_lum,
            "threshold_increment_ti_proxy_percent": float(ti_proxy),
            "threshold_increment_ti_percent": float(ti_proxy),
            "surround_ratio_proxy": surround_ratio_proxy,
            "lane_metrics": lane_metrics,
            "lanes": lane_metrics,
            "overall": {
                "avg_lux": summary.get("mean_lux", 0.0),
                "min_lux": summary.get("min_lux", 0.0),
                "max_lux": summary.get("max_lux", 0.0),
                "u0": summary.get("uniformity_ratio", 0.0),
            },
        }
    )
    glare_rows, glare_worst = compute_observer_glare_metrics(
        observers,
        luminaires,
        lavg_reference_cd_m2=mean_lum,
        settings=settings,
    )
    summary["observer_glare_views"] = glare_rows
    summary["worst_case_glare"] = glare_worst
    summary["rp8_veiling_ratio_worst"] = float(glare_worst.get("rp8_veiling_ratio_worst", 0.0))
    summary["ti_proxy_percent_worst"] = float(glare_worst.get("ti_proxy_percent_worst", 0.0))
    summary["ti_percent_worst"] = float(glare_worst.get("ti_percent_worst", 0.0))
    roadway_payload = summary.get("roadway")
    if isinstance(roadway_payload, dict):
        metrics = roadway_payload.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        metrics["worst_case_glare"] = glare_worst
        roadway_payload["metrics"] = metrics
        summary["roadway"] = roadway_payload
    if roadway is not None:
        summary["roadway_id"] = roadway.id
        summary["roadway_name"] = roadway.name

    return RoadIlluminanceResult(points=mapped_points, values=road.values, nx=nx, ny=ny, lane_grids=lane_grids, summary=summary)
