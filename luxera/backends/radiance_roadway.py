from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from luxera.backends.interface import BackendRunResult
from luxera.backends.radiance import run_radiance_direct
from luxera.engine.road_luminance import compute_road_luminance_metrics
from luxera.project.schema import CalcGrid, JobSpec, Project


def run_radiance_roadway(project: Project, job: JobSpec, out_dir: Path) -> BackendRunResult:
    if not project.roadway_grids:
        raise RuntimeError("Roadway Radiance backend requires at least one roadway grid")
    rg = project.roadway_grids[0]
    roadway = next((rw for rw in project.roadways if rw.id == rg.roadway_id), None) if getattr(rg, "roadway_id", None) else None
    scale = float(job.settings.get("length_scale_to_m", 1.0))

    lane_width = float((roadway.lane_width if roadway is not None else rg.lane_width) * scale)
    num_lanes = int(roadway.num_lanes if roadway is not None else rg.num_lanes)
    origin = tuple(float(v) * scale for v in (roadway.start if roadway is not None else rg.origin))
    if roadway is not None:
        dx = float(roadway.end[0] - roadway.start[0]) * scale
        dy = float(roadway.end[1] - roadway.start[1]) * scale
        dz = float(roadway.end[2] - roadway.start[2]) * scale
        road_length = float(np.sqrt(dx * dx + dy * dy + dz * dz))
    else:
        road_length = float(rg.road_length) * scale

    nx = int(rg.longitudinal_points or rg.nx)
    if rg.transverse_points_per_lane:
        ny = int(max(1, num_lanes) * int(rg.transverse_points_per_lane))
    else:
        ny = int(rg.ny)
    nx = max(1, nx)
    ny = max(1, ny)

    road_grid = CalcGrid(
        id=rg.id,
        name=rg.name,
        origin=origin,
        width=road_length,
        height=lane_width * max(1, num_lanes),
        elevation=origin[2],
        nx=nx,
        ny=ny,
        normal=(0.0, 0.0, 1.0),
    )

    p2 = copy.deepcopy(project)
    p2.grids = [road_grid]
    direct_job = JobSpec(id=f"{job.id}:roadway_radiance_direct", type="direct", backend="radiance", settings=dict(job.settings), seed=job.seed)
    rr = run_radiance_direct(p2, direct_job, out_dir)

    points = np.asarray(rr.result_data.get("grid_points", np.zeros((0, 3), dtype=float)), dtype=float)
    values = np.asarray(rr.result_data.get("grid_values", np.zeros((0,), dtype=float)), dtype=float).reshape(-1)
    road = compute_road_luminance_metrics(
        points,
        values,
        nx=nx,
        ny=ny,
        lane_width_m=lane_width,
        num_lanes=num_lanes,
        road_length_m=road_length,
        origin=origin,
        settings=dict(job.settings),
    )
    road.summary["road_class"] = str(job.settings.get("road_class", "M3"))
    if roadway is not None:
        road.summary["roadway_id"] = roadway.id
        road.summary["roadway_name"] = roadway.name
        road.summary["pole_spacing_m"] = roadway.pole_spacing_m
        road.summary["mounting_height_m"] = roadway.mounting_height_m
        road.summary["setback_m"] = roadway.setback_m
    else:
        road.summary["pole_spacing_m"] = rg.pole_spacing_m
        road.summary["mounting_height_m"] = rg.mounting_height_m
        road.summary["setback_m"] = rg.setback_m

    summary = dict(rr.summary)
    summary.update(road.summary)
    summary["backend_mode"] = "radiance_roadway"

    result_data = dict(rr.result_data)
    result_data.update(
        {
            "grid_points": points,
            "grid_values": values,
            "grid_nx": nx,
            "grid_ny": ny,
            "lane_grids": road.lane_grids,
        }
    )
    return BackendRunResult(summary=summary, assets=dict(rr.assets), artifacts=dict(rr.artifacts), result_data=result_data)
