from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

from luxera.parity.arrays import compare_arrays, stats_delta
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import Project
from luxera.runner import run_job


@dataclass(frozen=True)
class InvarianceMismatch:
    transform: str
    metric: str
    baseline: float | None
    variant: float | None
    abs_error: float | None
    rel_error: float | None
    abs_tol: float | None
    rel_tol: float | None
    reason: str


@dataclass(frozen=True)
class InvarianceResult:
    passed: bool
    transforms_checked: int
    mismatches: List[InvarianceMismatch]
    details: Dict[str, Any]


def _rot_z_90_point(p: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (-y, x, z)


def _rot_z_90_vec(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return (-y, x, z)


def _scale_point(p: Tuple[float, float, float], s: float) -> Tuple[float, float, float]:
    return (float(p[0]) * s, float(p[1]) * s, float(p[2]) * s)


def _apply_to_points(points: Iterable[Tuple[float, float, float]], fn) -> List[Tuple[float, float, float]]:
    return [fn((float(p[0]), float(p[1]), float(p[2]))) for p in points]


def _transform_project(project: Project, transform_name: str) -> Project:
    q = copy.deepcopy(project)

    if transform_name == "translate_large":
        t = (1000.0, -2000.0, 30.0)

        def map_p(p: Tuple[float, float, float]) -> Tuple[float, float, float]:
            return (float(p[0]) + t[0], float(p[1]) + t[1], float(p[2]) + t[2])

        map_v = lambda v: v
        az_shift = 0.0
        scalar = 1.0
        z_shift = t[2]
    elif transform_name == "rotate_z_90":
        map_p = _rot_z_90_point
        map_v = _rot_z_90_vec
        az_shift = 90.0
        scalar = 1.0
        z_shift = 0.0
    elif transform_name == "unit_mm":
        s = 1000.0
        map_p = lambda p: _scale_point(p, s)
        map_v = lambda v: tuple(float(x) for x in v)
        az_shift = 0.0
        scalar = s
        z_shift = 0.0
        q.geometry.length_unit = "mm"
        q.geometry.scale_to_meters = 0.001
        for cs in q.geometry.coordinate_systems:
            cs.length_unit = "mm"
            cs.units = "mm"
            cs.scale_to_meters = 0.001
    else:
        raise ValueError(f"Unsupported invariance transform: {transform_name}")

    for room in q.geometry.rooms:
        ox, oy, oz = tuple(room.origin)
        rw = float(room.width) * scalar
        rl = float(room.length) * scalar
        rh = float(room.height) * scalar
        if transform_name == "rotate_z_90":
            room.origin = (-(float(oy) + rl), float(ox), float(oz))
            room.width = rl
            room.length = rw
        else:
            room.origin = map_p(tuple(room.origin))
            room.width = rw
            room.length = rl
        room.height = rh

    for ng in q.geometry.no_go_zones:
        ng.vertices = _apply_to_points(ng.vertices, map_p)
    for srf in q.geometry.surfaces:
        srf.vertices = _apply_to_points(srf.vertices, map_p)
        if srf.normal is not None:
            srf.normal = map_v(tuple(srf.normal))
    for op in q.geometry.openings:
        op.vertices = _apply_to_points(op.vertices, map_p)
    for ob in q.geometry.obstructions:
        ob.vertices = _apply_to_points(ob.vertices, map_p)
        if ob.height is not None:
            ob.height = float(ob.height) * scalar
    for lvl in q.geometry.levels:
        lvl.elevation = float(lvl.elevation) * scalar + (0.0 if transform_name != "translate_large" else 30.0)

    for lum in q.luminaires:
        pos = tuple(lum.transform.position)
        lum.transform.position = map_p(pos)
        rot = lum.transform.rotation
        if rot.type == "euler_zyx" and rot.euler_deg is not None:
            yaw, pitch, roll = rot.euler_deg
            rot.euler_deg = (float(yaw) + az_shift, float(pitch), float(roll))
        elif rot.type == "aim_up":
            if rot.aim is not None:
                rot.aim = map_p(tuple(rot.aim))
            if rot.up is not None:
                rot.up = map_v(tuple(rot.up))

    for g in q.grids:
        ox, oy, oz = tuple(g.origin)
        gw = float(g.width) * scalar
        gh = float(g.height) * scalar
        if transform_name == "rotate_z_90":
            g.origin = (-(float(oy) + gh), float(ox), float(oz))
            g.width = gh
            g.height = gw
            g.nx, g.ny = int(g.ny), int(g.nx)
        else:
            g.origin = map_p(tuple(g.origin))
            g.width = gw
            g.height = gh
        g.elevation = float(g.elevation) * scalar + z_shift
        g.normal = map_v(tuple(g.normal))
        g.sample_points = _apply_to_points(g.sample_points, map_p)

    for vp in q.vertical_planes:
        vp.origin = map_p(tuple(vp.origin))
        vp.width = float(vp.width) * scalar
        vp.height = float(vp.height) * scalar
        vp.azimuth_deg = float(vp.azimuth_deg) + az_shift
        vp.offset_m = float(vp.offset_m) * scalar
        vp.evaluation_height_offset = float(vp.evaluation_height_offset) * scalar

    for ap in q.arbitrary_planes:
        ap.origin = map_p(tuple(ap.origin))
        ap.axis_u = map_v(tuple(ap.axis_u))
        ap.axis_v = map_v(tuple(ap.axis_v))
        ap.width = float(ap.width) * scalar
        ap.height = float(ap.height) * scalar
        ap.evaluation_height_offset = float(ap.evaluation_height_offset) * scalar

    for pw in q.polygon_workplanes:
        pw.origin = map_p(tuple(pw.origin))
        pw.axis_u = map_v(tuple(pw.axis_u))
        pw.axis_v = map_v(tuple(pw.axis_v))
        if transform_name == "unit_mm":
            pw.polygon_uv = [(float(u) * scalar, float(v) * scalar) for u, v in pw.polygon_uv]
            pw.holes_uv = [[(float(u) * scalar, float(v) * scalar) for u, v in hole] for hole in pw.holes_uv]
        pw.evaluation_height_offset = float(pw.evaluation_height_offset) * scalar

    for ps in q.point_sets:
        ps.points = _apply_to_points(ps.points, map_p)
    for lg in q.line_grids:
        lg.polyline = _apply_to_points(lg.polyline, map_p)
        lg.spacing = float(lg.spacing) * scalar

    for er in q.escape_routes:
        er.polyline = _apply_to_points(er.polyline, map_p)
        er.width_m = float(er.width_m) * scalar
        er.height_m = float(er.height_m) * scalar
        er.spacing_m = float(er.spacing_m) * scalar
        er.end_margin_m = float(er.end_margin_m) * scalar

    for rw in q.roadways:
        rw.start = map_p(tuple(rw.start))
        rw.end = map_p(tuple(rw.end))
        rw.lane_width = float(rw.lane_width) * scalar
        if rw.mounting_height_m is not None:
            rw.mounting_height_m = float(rw.mounting_height_m) * scalar
        if rw.setback_m is not None:
            rw.setback_m = float(rw.setback_m) * scalar
        if rw.pole_spacing_m is not None:
            rw.pole_spacing_m = float(rw.pole_spacing_m) * scalar
        seg = rw.segment
        if seg is not None:
            if seg.length_m is not None:
                seg.length_m = float(seg.length_m) * scalar
            seg.lane_widths_m = [float(v) * scalar for v in seg.lane_widths_m]
            seg.lateral_offset_m = float(seg.lateral_offset_m) * scalar
            seg.vertical_offset_m = float(seg.vertical_offset_m) * scalar
        for row in rw.pole_rows:
            row.spacing_m = float(row.spacing_m) * scalar
            row.offset_m = float(row.offset_m) * scalar
            row.mounting_height_m = float(row.mounting_height_m) * scalar
        for obs in rw.observers:
            obs.height_m = float(obs.height_m) * scalar
            obs.back_offset_m = float(obs.back_offset_m) * scalar
            if obs.lateral_offset_m is not None:
                obs.lateral_offset_m = float(obs.lateral_offset_m) * scalar

    for rg in q.roadway_grids:
        rg.origin = map_p(tuple(rg.origin))
        rg.lane_width = float(rg.lane_width) * scalar
        rg.road_length = float(rg.road_length) * scalar
        if rg.pole_spacing_m is not None:
            rg.pole_spacing_m = float(rg.pole_spacing_m) * scalar
        if rg.mounting_height_m is not None:
            rg.mounting_height_m = float(rg.mounting_height_m) * scalar
        if rg.setback_m is not None:
            rg.setback_m = float(rg.setback_m) * scalar
        rg.observer_height_m = float(rg.observer_height_m) * scalar
        for obs in rg.observers:
            obs.height_m = float(obs.height_m) * scalar
            obs.back_offset_m = float(obs.back_offset_m) * scalar
            if obs.lateral_offset_m is not None:
                obs.lateral_offset_m = float(obs.lateral_offset_m) * scalar

    return q


def _extract_csv_arrays(result_dir: Path) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for p in sorted(result_dir.glob("*.csv"), key=lambda x: x.name):
        try:
            raw = np.loadtxt(p, delimiter=",", skiprows=1, dtype=float)
        except Exception:
            continue
        arr = np.asarray(raw, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] < 4:
            continue
        out[p.name] = np.asarray(arr[:, 3], dtype=float)
    return out


def _metric_compare(
    base: Mapping[str, Any],
    other: Mapping[str, Any],
    *,
    abs_tol: float,
    rel_tol: float,
) -> List[Tuple[str, float, float, float, float]]:
    keys = [
        ("mean_lux", "E_avg"),
        ("min_lux", "E_min"),
        ("uniformity_ratio", "uniformity"),
    ]
    rows: List[Tuple[str, float, float, float, float]] = []
    for key, label in keys:
        if key not in base or key not in other:
            continue
        bv = float(base[key])
        ov = float(other[key])
        ae = abs(ov - bv)
        re = ae / max(abs(bv), 1e-12)
        rows.append((label, bv, ov, ae, re))
    return rows


def run_invariance_for_scene(
    scene_path: Path,
    *,
    job_ids: Sequence[str],
    out_dir: Path,
    transforms: Sequence[str] = ("translate_large", "rotate_z_90", "unit_mm"),
    scalar_abs_tol: float = 1e-4,
    scalar_rel_tol: float = 1e-5,
    array_thresholds: Mapping[str, float] | None = None,
) -> InvarianceResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    thr = {
        "max_abs": 1e-3,
        "rmse": 1e-4,
        "p95_abs": 1e-3,
    }
    if isinstance(array_thresholds, Mapping):
        for k, v in array_thresholds.items():
            try:
                thr[str(k)] = float(v)
            except Exception:
                pass

    base_refs = [run_job(scene_path, jid) for jid in job_ids]
    base_summary = dict(base_refs[0].summary) if base_refs else {}
    base_arrays = _extract_csv_arrays(Path(base_refs[0].result_dir)) if base_refs else {}

    mismatches: List[InvarianceMismatch] = []
    details: Dict[str, Any] = {"base": {"scene": str(scene_path), "metrics": base_summary}, "transforms": {}}

    base_project = load_project_schema(scene_path)
    base_scene_stem = scene_path.name.replace(".lux.json", "")

    for tname in transforms:
        variant_project = _transform_project(base_project, tname)
        vpath = out / f"{base_scene_stem}.__invariance_{tname}.lux.json"
        save_project_schema(variant_project, vpath)
        try:
            refs = [run_job(vpath, jid) for jid in job_ids]
            var_summary = dict(refs[0].summary) if refs else {}
            var_arrays = _extract_csv_arrays(Path(refs[0].result_dir)) if refs else {}

            metric_rows = _metric_compare(base_summary, var_summary, abs_tol=scalar_abs_tol, rel_tol=scalar_rel_tol)
            transform_failures: List[Dict[str, Any]] = []
            for label, bv, ov, ae, re in metric_rows:
                if ae > scalar_abs_tol and re > scalar_rel_tol:
                    mismatches.append(
                        InvarianceMismatch(
                            transform=tname,
                            metric=label,
                            baseline=bv,
                            variant=ov,
                            abs_error=ae,
                            rel_error=re,
                            abs_tol=scalar_abs_tol,
                            rel_tol=scalar_rel_tol,
                            reason="scalar_tolerance_exceeded",
                        )
                    )
                    transform_failures.append(
                        {
                            "kind": "scalar",
                            "metric": label,
                            "baseline": bv,
                            "variant": ov,
                            "abs_error": ae,
                            "rel_error": re,
                            "abs_tol": scalar_abs_tol,
                            "rel_tol": scalar_rel_tol,
                        }
                    )

            common = sorted(set(base_arrays.keys()) & set(var_arrays.keys()))
            for name in common:
                b = np.asarray(base_arrays[name], dtype=float).reshape(-1)
                v = np.asarray(var_arrays[name], dtype=float).reshape(-1)
                bb = np.sort(b)
                vv = np.sort(v)
                ok, stats, fails = compare_arrays(bb, vv, thr)
                if not ok:
                    mismatches.append(
                        InvarianceMismatch(
                            transform=tname,
                            metric=f"array:{name}",
                            baseline=None,
                            variant=None,
                            abs_error=float(stats.get("max_abs", 0.0)) if isinstance(stats, Mapping) else None,
                            rel_error=None,
                            abs_tol=float(thr.get("max_abs", 0.0)),
                            rel_tol=None,
                            reason="array_tolerance_exceeded",
                        )
                    )
                    transform_failures.append(
                        {
                            "kind": "array",
                            "metric": name,
                            "stats": stats,
                            "thresholds": dict(thr),
                            "failures": list(fails),
                        }
                    )

            for missing in sorted(set(base_arrays.keys()) - set(var_arrays.keys())):
                mismatches.append(
                    InvarianceMismatch(
                        transform=tname,
                        metric=f"array:{missing}",
                        baseline=None,
                        variant=None,
                        abs_error=None,
                        rel_error=None,
                        abs_tol=None,
                        rel_tol=None,
                        reason="missing_array_in_variant",
                    )
                )
                transform_failures.append({"kind": "array", "metric": missing, "reason": "missing_array_in_variant"})

            details["transforms"][tname] = {
                "metrics": var_summary,
                "scalar_checks": [
                    {
                        "metric": label,
                        "baseline": bv,
                        "variant": ov,
                        "abs_error": ae,
                        "rel_error": re,
                    }
                    for (label, bv, ov, ae, re) in metric_rows
                ],
                "array_stats": {name: stats_delta(base_arrays[name], var_arrays[name]) for name in common},
                "failures": transform_failures,
            }
        finally:
            vpath.unlink(missing_ok=True)

    return InvarianceResult(
        passed=(len(mismatches) == 0),
        transforms_checked=len(list(transforms)),
        mismatches=mismatches,
        details=details,
    )
