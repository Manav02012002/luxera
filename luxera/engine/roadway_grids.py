from __future__ import annotations
"""Contract: docs/spec/roadway_grids.md."""

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from luxera.project.schema import RoadwayGridSpec, RoadwayObserverSpec, RoadwaySpec


@dataclass(frozen=True)
class LaneSlice:
    lane_index: int
    lane_number: int
    y0: int
    y1: int


def stable_float(v: float, digits: int = 8) -> float:
    return float(f"{float(v):.{digits}f}")


def resolve_lane_widths(roadway: RoadwaySpec | None, grid: RoadwayGridSpec) -> List[float]:
    lane_count = max(1, int((roadway.num_lanes if roadway is not None else grid.num_lanes) or 1))
    default_width = float((roadway.lane_width if roadway is not None else grid.lane_width) or 3.5)

    segment = getattr(roadway, "segment", None) if roadway is not None else None
    lane_widths = list(getattr(segment, "lane_widths_m", []) or [])
    if not lane_widths:
        lane_widths = [default_width] * lane_count
    lane_widths = [float(w) for w in lane_widths]

    lane_count_from_segment = int(getattr(segment, "lane_count", 0) or 0) if segment is not None else 0
    if lane_count_from_segment > 0:
        lane_count = lane_count_from_segment

    if len(lane_widths) < lane_count:
        lane_widths.extend([default_width] * (lane_count - len(lane_widths)))
    if len(lane_widths) > lane_count:
        lane_widths = lane_widths[:lane_count]

    return lane_widths


def resolve_lane_slices(num_lanes: int, ny: int) -> List[LaneSlice]:
    if num_lanes <= 0 or ny <= 0:
        return []
    base = ny // num_lanes
    rem = ny % num_lanes
    y = 0
    out: List[LaneSlice] = []
    for lane_idx in range(num_lanes):
        rows = base + (1 if lane_idx < rem else 0)
        y0 = y
        y1 = min(ny, y0 + rows)
        y = y1
        out.append(LaneSlice(lane_index=lane_idx, lane_number=lane_idx + 1, y0=y0, y1=y1))
    return out


def lane_center_offsets(lane_widths: Sequence[float], lateral_offset_m: float = 0.0) -> List[float]:
    y = float(lateral_offset_m)
    out: List[float] = []
    for width in lane_widths:
        w = float(width)
        out.append(y + 0.5 * w)
        y += w
    return out


def resolve_observers(
    roadway: RoadwaySpec | None,
    grid: RoadwayGridSpec,
    origin: Tuple[float, float, float],
    lane_widths: Sequence[float],
    settings: Dict[str, object],
) -> List[Dict[str, float | str]]:
    segment = getattr(roadway, "segment", None) if roadway is not None else None
    base_offsets = lane_center_offsets(lane_widths, float(getattr(segment, "lateral_offset_m", 0.0) or 0.0))
    default_h = float(settings.get("observer_height_m", getattr(grid, "observer_height_m", 1.5)))
    default_back = float(settings.get("observer_back_offset_m", 60.0))

    explicit: List[RoadwayObserverSpec] = []
    explicit.extend([o for o in getattr(roadway, "observers", []) or [] if bool(getattr(o, "enabled", True))])
    explicit.extend([o for o in getattr(grid, "observers", []) or [] if bool(getattr(o, "enabled", True))])

    auto_method = str(getattr(grid, "observer_method", "") or "luminance")
    out: List[Dict[str, float | str]] = []
    if explicit:
        for obs in explicit:
            lane_num = max(1, int(obs.lane_number))
            lane_idx = min(lane_num - 1, max(0, len(base_offsets) - 1))
            lat = float(obs.lateral_offset_m) if obs.lateral_offset_m is not None else float(base_offsets[lane_idx])
            out.append(
                {
                    "observer_id": str(obs.id),
                    "lane_number": float(lane_num),
                    "lane_index": float(lane_idx),
                    "method": str(obs.method),
                    "x": float(origin[0] - float(obs.back_offset_m)),
                    "y": float(origin[1] + lat),
                    "z": float(origin[2] + float(obs.height_m)),
                }
            )
    else:
        lat_list = settings.get("observer_lateral_positions_m")
        if isinstance(lat_list, list) and lat_list:
            y_vals = [float(v) for v in lat_list]
        else:
            y_vals = [float(y) for y in base_offsets]
        for i, y in enumerate(y_vals):
            out.append(
                {
                    "observer_id": f"auto_{i+1}",
                    "lane_number": float(min(i + 1, len(base_offsets))),
                    "lane_index": float(min(i, max(0, len(base_offsets) - 1))),
                    "method": auto_method,
                    "x": float(origin[0] - default_back),
                    "y": float(origin[1] + y),
                    "z": float(origin[2] + default_h),
                }
            )

    out.sort(key=lambda r: (str(r.get("method", "")), int(float(r.get("lane_number", 0.0))), str(r.get("observer_id", ""))))
    return out


def build_lane_grid_payload(
    points: np.ndarray,
    values: np.ndarray,
    nx: int,
    ny: int,
    lane_widths: Sequence[float],
) -> List[Dict[str, object]]:
    pts = points.reshape(ny, nx, 3)
    vals = values.reshape(ny, nx)
    slices = resolve_lane_slices(len(lane_widths), ny)

    payload: List[Dict[str, object]] = []
    for slc in slices:
        lane_pts = pts[slc.y0:slc.y1, :, :].reshape(-1, 3)
        lane_vals = vals[slc.y0:slc.y1, :].reshape(-1)
        point_list: List[Dict[str, float]] = []
        order = 0
        for local_y in range(slc.y1 - slc.y0):
            for x in range(nx):
                p = pts[slc.y0 + local_y, x, :]
                v = vals[slc.y0 + local_y, x]
                point_list.append(
                    {
                        "order": float(order),
                        "lane_row": float(local_y),
                        "lane_col": float(x),
                        "x": stable_float(float(p[0])),
                        "y": stable_float(float(p[1])),
                        "z": stable_float(float(p[2])),
                        "illuminance_lux": stable_float(float(v)),
                    }
                )
                order += 1

        payload.append(
            {
                "lane_index": slc.lane_index,
                "lane_number": slc.lane_number,
                "y0": int(slc.y0),
                "y1": int(slc.y1),
                "nx": int(nx),
                "ny": int(max(slc.y1 - slc.y0, 0)),
                "lane_width_m": stable_float(float(lane_widths[slc.lane_index])),
                "ordering": "lane,row,col",
                "points": point_list,
                "points_np": lane_pts,
                "values_np": lane_vals,
            }
        )
    return payload


def build_ti_stub(observers: Sequence[Dict[str, float | str]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for obs in observers:
        method = str(obs.get("method", "")).lower()
        if method in {"ti", "veiling_luminance", "vl", "ti_proxy"}:
            out.append(
                {
                    "observer_id": str(obs.get("observer_id", "")),
                    "method": str(obs.get("method", "ti")),
                    "status": "skipped",
                    "reason": "TI/veiling-luminance engine is not implemented yet",
                }
            )
    return out
