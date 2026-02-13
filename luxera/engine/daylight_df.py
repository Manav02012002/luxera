from __future__ import annotations
"""Contract: docs/spec/daylight_contract.md, docs/spec/solver_contracts.md."""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from luxera.engine.direct_illuminance import build_grid_from_spec, build_vertical_plane_points
from luxera.project.schema import DaylightSpec, JobSpec, OpeningSpec, Project


@dataclass(frozen=True)
class DaylightTargetResult:
    target_id: str
    target_type: str
    points: np.ndarray
    values: np.ndarray
    nx: int = 0
    ny: int = 0


@dataclass(frozen=True)
class DaylightResult:
    summary: Dict[str, object]
    targets: List[DaylightTargetResult]


def _grid_points(project: Project, target_id: str) -> Tuple[np.ndarray, int, int] | None:
    g = next((x for x in project.grids if x.id == target_id), None)
    if g is None:
        return None
    grid = build_grid_from_spec(g)
    pts = np.asarray([p.to_tuple() for p in grid.get_points()], dtype=float)
    return pts, int(grid.nx), int(grid.ny)


def _vplane_points(project: Project, target_id: str) -> Tuple[np.ndarray, int, int] | None:
    vp = next((x for x in project.vertical_planes if x.id == target_id), None)
    if vp is None:
        return None
    pts, _, nx, ny = build_vertical_plane_points(vp)
    return np.asarray(pts, dtype=float), int(nx), int(ny)


def _pointset_points(project: Project, target_id: str) -> np.ndarray | None:
    ps = next((x for x in project.point_sets if x.id == target_id), None)
    if ps is None:
        return None
    return np.asarray(ps.points, dtype=float) if ps.points else np.zeros((0, 3), dtype=float)


def _opening_geom(op: OpeningSpec) -> Tuple[np.ndarray, np.ndarray, float]:
    verts = np.asarray(op.vertices, dtype=float)
    if verts.shape[0] < 3:
        return np.zeros((3,), dtype=float), np.array([0.0, 0.0, 1.0], dtype=float), 0.0
    center = np.mean(verts, axis=0)
    area = 0.0
    n = np.zeros((3,), dtype=float)
    base = verts[0]
    for i in range(1, verts.shape[0] - 1):
        a = verts[i] - base
        b = verts[i + 1] - base
        tri_n = np.cross(a, b)
        area += 0.5 * float(np.linalg.norm(tri_n))
        n += tri_n
    nn = np.linalg.norm(n)
    normal = (n / nn) if nn > 1e-9 else np.array([0.0, 0.0, 1.0], dtype=float)
    return center, normal, float(area)


def _target_ids(project: Project, job: JobSpec) -> List[Tuple[str, str]]:
    if job.targets:
        out: List[Tuple[str, str]] = []
        for tid in job.targets:
            if any(g.id == tid for g in project.grids):
                out.append((tid, "grid"))
            elif any(v.id == tid for v in project.vertical_planes):
                out.append((tid, "vertical_plane"))
            elif any(p.id == tid for p in project.point_sets):
                out.append((tid, "point_set"))
        return out
    return (
        [(g.id, "grid") for g in project.grids]
        + [(v.id, "vertical_plane") for v in project.vertical_planes]
        + [(p.id, "point_set") for p in project.point_sets]
    )


def _df_at_points(points: np.ndarray, apertures: List[OpeningSpec], spec: DaylightSpec) -> np.ndarray:
    vals = np.zeros((points.shape[0],), dtype=float)
    for op in apertures:
        center, normal, area = _opening_geom(op)
        if area <= 1e-9:
            continue
        vt_raw = op.vt if op.vt is not None else op.visible_transmittance
        shade_raw = op.shade_factor if op.shade_factor is not None else op.shading_factor
        vt = float(vt_raw if vt_raw is not None else spec.glass_visible_transmittance_default)
        shade = float(shade_raw if shade_raw is not None else 1.0)
        rays = center[None, :] - points
        d = np.linalg.norm(rays, axis=1)
        valid = d > 1e-6
        if not np.any(valid):
            continue
        dirp = np.zeros_like(rays)
        dirp[valid] = rays[valid] / d[valid, None]
        cos_theta = np.clip(np.sum(dirp * normal[None, :], axis=1), 0.0, 1.0)
        solid = np.zeros((points.shape[0],), dtype=float)
        solid[valid] = area * cos_theta[valid] / np.maximum(d[valid] ** 2, 1e-12)
        # Baseline DF proxy: aperture visible sky fraction, normalized by hemispherical 2*pi.
        vals += 100.0 * vt * shade * np.clip(solid / (2.0 * np.pi), 0.0, 1.0)
    return vals


def run_daylight_df(project: Project, job: JobSpec, scene: object | None = None) -> DaylightResult:  # noqa: ARG001
    spec = job.daylight or DaylightSpec(mode="df")
    apertures = [o for o in project.geometry.openings if bool(getattr(o, "is_daylight_aperture", False))]
    targets: List[DaylightTargetResult] = []
    all_vals: List[np.ndarray] = []
    for tid, tkind in _target_ids(project, job):
        if tkind == "grid":
            got = _grid_points(project, tid)
            if got is None:
                continue
            points, nx, ny = got
            values = _df_at_points(points, apertures, spec)
            targets.append(DaylightTargetResult(target_id=tid, target_type=tkind, points=points, values=values, nx=nx, ny=ny))
        elif tkind == "vertical_plane":
            got = _vplane_points(project, tid)
            if got is None:
                continue
            points, nx, ny = got
            values = _df_at_points(points, apertures, spec)
            targets.append(DaylightTargetResult(target_id=tid, target_type=tkind, points=points, values=values, nx=nx, ny=ny))
        else:
            points = _pointset_points(project, tid)
            if points is None:
                continue
            values = _df_at_points(points, apertures, spec)
            targets.append(DaylightTargetResult(target_id=tid, target_type=tkind, points=points, values=values))
        all_vals.append(values)

    flat = np.concatenate([x.reshape(-1) for x in all_vals], axis=0) if all_vals else np.zeros((0,), dtype=float)
    e0 = float(spec.external_horizontal_illuminance_lux or 0.0)
    summary: Dict[str, object] = {
        "mode": "df",
        "sky": spec.sky,
        "external_horizontal_illuminance_lux": e0,
        "glass_visible_transmittance_default": float(spec.glass_visible_transmittance_default),
        "metric": "daylight_factor_percent",
        "min_df_percent": float(np.min(flat)) if flat.size else 0.0,
        "mean_df_percent": float(np.mean(flat)) if flat.size else 0.0,
        "max_df_percent": float(np.max(flat)) if flat.size else 0.0,
        "target_count": len(targets),
        "aperture_count": len(apertures),
        "obstruction_policy": "no_internal_obstruction_df_baseline",
    }
    return DaylightResult(summary=summary, targets=targets)
