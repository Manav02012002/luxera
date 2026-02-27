from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/daylight_contract.md, docs/spec/emergency_contract.md."""

import base64
import json
import math
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from luxera.core.hashing import hash_job_spec, sha256_bytes, sha256_file
from luxera.project.schema import Project, JobSpec, JobResultRef, PhotometryAsset, CalcGrid
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.validator import validate_project_for_job, ProjectValidationError
from luxera.results.store import (
    ensure_result_dir,
    write_grid_csv,
    write_grid_csv_named,
    write_named_json,
    write_points_csv,
    write_result_json,
    write_residuals_csv,
    write_surface_illuminance_csv,
    write_surface_grid_csv,
    write_manifest,
)
from luxera.results.heatmaps import write_surface_heatmaps
from luxera.results.grid_viz import write_grid_heatmap_and_isolux
from luxera.results.surface_grids import compute_surface_grids
from luxera.results.writers import write_tables_csv, write_tables_json
from luxera.results.writers_daylight import (
    write_daylight_annual_target_artifacts,
    write_daylight_summary,
    write_daylight_target_artifacts,
)
from luxera.results.contracts import GridResult as ContractGridResult
from luxera.derived.summary_tables import (
    build_grid_table,
    build_plane_table,
    build_pointset_table,
    build_worstcase_summary,
)
import luxera
from luxera.engine.radiosity_engine import RadiosityMethod, RadiositySettings, run_radiosity
from luxera.engine.ugr_engine import compute_ugr_default, compute_ugr_for_views
from luxera.engine.direct_illuminance import (
    build_direct_occlusion_context,
    build_grid_from_spec,
    build_room_from_spec,
    load_luminaires,
    run_direct_points,
    run_direct_arbitrary_plane,
    run_direct_grid,
    run_direct_line_grid,
    run_direct_point_set,
    run_direct_vertical_plane,
)
from luxera.core.units import project_scale_to_meters
from luxera.geometry.bvh import build_bvh, triangulate_surfaces
from luxera.engine.road_illuminance import run_road_illuminance
from luxera.engine.daylight_df import run_daylight_df
from luxera.engine.daylight_annual_radiance import run_daylight_annual_radiance
from luxera.engine.daylight_radiance import run_daylight_radiance
from luxera.engine.emergency_escape_route import run_escape_routes
from luxera.engine.emergency_open_area import run_open_area
from luxera.compliance import ActivityType, check_compliance_from_grid
from luxera.compliance.emergency_standards import get_standard_profile
from luxera.photometry.verify import verify_photometry_file
from luxera.metrics.core import compute_basic_metrics
from luxera.viz.falsecolor import render_falsecolor_plane
from luxera.agent.audit import append_audit_event
from luxera.backends.radiance import build_radiance_run_manifest, get_radiance_version, run_radiance_direct
from luxera.backends.radiance_roadway import run_radiance_roadway
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.calcs.geometry_ops import build_vertical_grid_on_wall
from luxera.geometry.core import Vector3


class RunnerError(Exception):
    pass


def _scale_grid_spec(grid: CalcGrid, s: float) -> CalcGrid:
    return CalcGrid(
        id=grid.id,
        name=grid.name,
        origin=tuple(float(x) * s for x in grid.origin),
        width=float(grid.width) * s,
        height=float(grid.height) * s,
        elevation=float(grid.elevation) * s,
        nx=grid.nx,
        ny=grid.ny,
        normal=grid.normal,
        room_id=grid.room_id,
        zone_id=grid.zone_id,
        sample_points=[tuple(float(v) * s for v in p) for p in grid.sample_points],
        sample_mask=list(grid.sample_mask),
    )


def run_job(project_path: str | Path, job_id: str) -> JobResultRef:
    """
    Path-based runner contract:
    load project -> execute -> persist updated project -> return result ref.
    """
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    # Canonicalize runtime root to project file location for portable relative paths.
    project.root_dir = str(ppath.parent)
    ref = run_job_in_memory(project, job_id)
    save_project_schema(project, ppath)
    return ref


def _upsert_result_ref(project: Project, ref: JobResultRef) -> None:
    for i, existing in enumerate(project.results):
        if existing.job_id == ref.job_id:
            project.results[i] = ref
            return
    project.results.append(ref)


def _resolve_project_root(project: Project) -> Path:
    if project.root_dir:
        return Path(project.root_dir).expanduser().resolve()
    return Path.cwd()


def _hash_photometry_asset(asset: PhotometryAsset, project_root: Path) -> str:
    if asset.embedded_b64:
        return sha256_bytes(base64.b64decode(asset.embedded_b64.encode("utf-8")))
    if asset.path:
        p = Path(asset.path).expanduser()
        if not p.is_absolute():
            p = (project_root / p).resolve()
        return sha256_file(p)
    raise RunnerError(f"Photometry asset {asset.id} has no data")


def _asset_photometry_audit(project: Project) -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    root = _resolve_project_root(project)
    for a in project.photometry_assets:
        if not a.path:
            out[a.id] = {"tilt_mode": "UNKNOWN"}
            continue
        p = Path(a.path).expanduser()
        if not p.is_absolute():
            p = (root / p).resolve()
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
            if a.format == "IES":
                doc = parse_ies_text(raw, source_path=p)
                factors = doc.tilt_data[1] if doc.tilt_data else []
                out[a.id] = {
                    "tilt_mode": str(doc.tilt_mode or "NONE"),
                    "tilt_source": str(doc.tilt_mode or "NONE"),
                    "tilt_file": str(doc.tilt_file_path) if doc.tilt_file_path else None,
                    "tilt_count": len(factors),
                    "tilt_factor_min": float(min(factors)) if factors else None,
                    "tilt_factor_max": float(max(factors)) if factors else None,
                    "tilt_summary": {
                        "loaded": bool(doc.tilt_data is not None),
                        "geometry_factor": doc.tilt_lamp_to_luminaire_geometry,
                    },
                    "ies_units_type": int(doc.photometry.units_type) if doc.photometry is not None else None,
                    "photometric_type": int(doc.photometry.photometric_type) if doc.photometry is not None else None,
                }
            else:
                _ = parse_ldt_text(raw)
                out[a.id] = {"tilt_mode": "NONE", "ies_units_type": None, "photometric_type": 1}
        except Exception as e:
            out[a.id] = {"tilt_mode": "UNKNOWN", "error": str(e)}
    return out


def _get_job(project: Project, job_id: str) -> JobSpec:
    for job in project.jobs:
        if job.id == job_id:
            return job
    raise RunnerError(f"Job not found: {job_id}")


def _solver_info(project_root: Path) -> Dict[str, str]:
    info = {"package_version": getattr(luxera, "__version__", "unknown")}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        info["git_commit"] = commit
    except Exception:
        info["git_commit"] = "unknown"
    return info


def _units_contract() -> Dict[str, str]:
    return {
        "length": "m",
        "illuminance": "lux",
        "luminous_intensity": "cd",
        "luminous_flux": "lm",
        "angles": "deg",
    }


def _effective_job_settings(job: JobSpec) -> Dict[str, object]:
    if job.type not in {"radiosity", "roadway", "daylight", "emergency"}:
        defaults: Dict[str, object] = {
            "use_occlusion": False,
            "occlusion_include_room_shell": False,
            "occlusion_epsilon": 1e-6,
        }
        merged = dict(defaults)
        merged.update(job.settings or {})
        return merged

    if job.type == "radiosity":
        defaults: Dict[str, object] = {
            "max_iterations": 100,
            "max_iters": 100,
            "convergence_threshold": 0.001,
            "tol": 0.001,
            "damping": 1.0,
            "patch_max_area": 0.5,
            "method": "GATHERING",
            "use_visibility": True,
            "ambient_light": 0.0,
            "monte_carlo_samples": 16,
            "ugr_grid_spacing": 2.0,
            "ugr_eye_heights": [1.2, 1.7],
        }
    elif job.type == "roadway":
        defaults = {
            "road_class": "M3",
            "compliance_profile_id": None,
            "road_surface_reflectance": 0.07,
            "observer_height_m": 1.5,
            "observer_back_offset_m": 60.0,
            "observer_lateral_positions_m": None,
        }
    elif job.type == "emergency":
        defaults = {
            "mode": "escape_route",
            "compliance_profile_id": None,
            "target_min_lux": 1.0,
            "target_uniformity": 0.1,
            "battery_duration_min": 60.0,
            "battery_end_factor": 0.5,
            "battery_curve": "linear",
            "battery_steps": 7,
        }
    else:  # daylight
        defaults = {
            "mode": "daylight_factor",
            "exterior_horizontal_illuminance_lux": 10000.0,
            "daylight_factor_percent": 2.0,
            "target_lux": 300.0,
            "annual_hours": 8760,
            "exterior_hourly_lux": None,
            "daylight_depth_attenuation": 2.0,
            "sda_threshold_ratio": 0.5,
            "udi_low_lux": 100.0,
            "udi_high_lux": 2000.0,
        }
    merged = dict(defaults)
    merged.update(job.settings or {})
    if job.type == "radiosity":
        merged["max_iterations"] = int(merged.get("max_iters", merged.get("max_iterations", 100)))
        merged["convergence_threshold"] = float(merged.get("tol", merged.get("convergence_threshold", 0.001)))
    if isinstance(merged.get("ugr_eye_heights"), list):
        merged["ugr_eye_heights"] = [float(x) for x in merged["ugr_eye_heights"]]
    return merged


def run_job_in_memory(project: Project, job_id: str) -> JobResultRef:
    job = _get_job(project, job_id)
    try:
        validate_project_for_job(project, job)
    except ProjectValidationError as e:
        raise RunnerError(str(e)) from e
    job_hash = hash_job_spec(project, asdict(job))

    project_root = _resolve_project_root(project)
    out_dir = ensure_result_dir(project_root, job_hash)
    result_json = out_dir / "result.json"
    if result_json.exists():
        summary: Dict[str, object] = {}
        try:
            payload = json.loads(result_json.read_text(encoding="utf-8"))
            raw_summary = payload.get("summary")
            if isinstance(raw_summary, dict):
                summary = dict(raw_summary)
        except Exception:
            summary = {}
        ref = JobResultRef(job_id=job.id, job_hash=job_hash, result_dir=str(out_dir), summary=summary)
        _upsert_result_ref(project, ref)
        return ref

    if job.backend == "radiance":
        if job.type == "direct":
            run_fn = run_radiance_direct
        elif job.type == "roadway":
            run_fn = run_radiance_roadway
        elif job.type == "daylight":
            run_fn = None
        else:
            raise RunnerError("Radiance backend currently supports direct, roadway, and daylight jobs only")
        try:
            rr = _run_daylight(project, job) if job.type == "daylight" else run_fn(project, job, out_dir)
        except RuntimeError as e:
            raise RunnerError(str(e)) from e
        if isinstance(rr, dict):
            result = dict(rr)
        else:
            result = {
                "summary": dict(rr.summary),
                "assets": dict(rr.assets),
            }
            if rr.artifacts:
                result["backend_artifacts"] = dict(rr.artifacts)
            if rr.result_data:
                result.update(dict(rr.result_data))
    else:
        if job.type == "direct":
            result = _run_direct(project, job)
        elif job.type == "radiosity":
            result = _run_radiosity(project, job)
        elif job.type == "roadway":
            result = _run_roadway(project, job)
        elif job.type == "emergency":
            result = _run_emergency(project, job)
        elif job.type == "daylight":
            result = _run_daylight(project, job)
        else:
            raise RunnerError(f"Unsupported job type: {job.type}")

    result_meta = {
        "contract_version": "solver_result_v1",
        "job_id": job.id,
        "job_hash": job_hash,
        "project": {
            "name": project.name,
            "schema_version": project.schema_version,
        },
        "job": asdict(job),
        "effective_settings": _effective_job_settings(job),
        "settings_dump": {
            "job": asdict(job),
            "effective": _effective_job_settings(job),
            "seed": job.seed,
        },
        "summary": result["summary"],
        "assets": result["assets"],
        "backend": {
            "name": job.backend,
            "version": getattr(luxera, "__version__", "unknown"),
        },
        "solver": _solver_info(project_root),
        "units": _units_contract(),
        "seed": job.seed,
        "coordinate_convention": "Local luminaire frame: +Z up, nadir is -Z; C=0 toward +X, C=90 toward +Y",
        "assumptions": _build_run_assumptions(job, result),
        "unsupported_features": _build_unsupported_features(job),
    }
    result_meta["photometry_assets"] = _asset_photometry_audit(project)
    if "backend_artifacts" in result:
        result_meta["backend_artifacts"] = result["backend_artifacts"]

    verification = _build_photometry_verification(project, result.get("assets", {}))
    result_meta["photometry_verification"] = verification
    if job.backend == "radiance":
        result_meta["backend_manifest"] = build_radiance_run_manifest(project, job)
        result_meta["solver"]["radiance"] = get_radiance_version()

    write_result_json(out_dir, result_meta)
    write_named_json(out_dir, "photometry_verify.json", verification)

    calc_objects = result.get("calc_objects")
    if isinstance(calc_objects, list) and calc_objects:
        first_grid_written = False
        for obj in calc_objects:
            if not isinstance(obj, dict):
                continue
            obj_type = str(obj.get("type", "grid"))
            obj_id = str(obj.get("id", "unknown"))
            points = obj.get("points")
            values = obj.get("values")
            if not isinstance(points, np.ndarray) or not isinstance(values, np.ndarray):
                continue
            if obj_type in {"grid", "vertical_plane"}:
                if obj_type == "vertical_plane":
                    csv_name = f"vplane_{obj_id}.csv"
                    heatmap_name = f"vplane_{obj_id}_heatmap.png"
                    isolux_name = None
                else:
                    csv_name = f"grid_{obj_id}.csv"
                    heatmap_name = f"grid_{obj_id}_heatmap.png"
                    isolux_name = f"grid_{obj_id}_isolux.png"
                write_grid_csv_named(out_dir, csv_name, points, values)
                nx = int(obj.get("nx", 0))
                ny = int(obj.get("ny", 0))
                if nx > 0 and ny > 0:
                    viz = write_grid_heatmap_and_isolux(out_dir, points, values, nx=nx, ny=ny)
                    heatmap = viz.get("heatmap")
                    isolux = viz.get("isolux")
                    if heatmap is not None:
                        shutil.copyfile(heatmap, out_dir / heatmap_name)
                        heatmap.unlink(missing_ok=True)
                    if isolux is not None and isolux_name is not None:
                        shutil.copyfile(isolux, out_dir / isolux_name)
                        isolux.unlink(missing_ok=True)
                    elif isolux is not None:
                        isolux.unlink(missing_ok=True)
                    render_falsecolor_plane(
                        values=values.reshape(-1),
                        nx=nx,
                        ny=ny,
                        out_path=out_dir / f"{obj_type}_{obj_id}_falsecolor.png",
                        title=f"{obj_type}:{obj_id}",
                        with_contours=True,
                    )
                if not first_grid_written:
                    write_grid_csv(out_dir, points, values)
                    if int(obj.get("nx", 0)) > 0 and int(obj.get("ny", 0)) > 0:
                        write_grid_heatmap_and_isolux(
                            out_dir,
                            points,
                            values,
                            nx=int(obj["nx"]),
                            ny=int(obj["ny"]),
                        )
                    first_grid_written = True
                if job.type == "daylight":
                    write_daylight_target_artifacts(out_dir, obj_id, obj_type, points, values, nx=nx, ny=ny)
                if job.type == "emergency":
                    write_grid_csv_named(out_dir, f"open_area_{obj_id}.csv", points, values)
            elif obj_type == "point_set":
                write_points_csv(out_dir, f"points_{obj_id}.csv", points, values)
                if job.type == "daylight":
                    write_daylight_target_artifacts(out_dir, obj_id, obj_type, points, values)
            elif obj_type == "line_grid":
                write_points_csv(out_dir, f"line_{obj_id}.csv", points, values)
            elif obj_type == "escape_route":
                write_points_csv(out_dir, f"escape_route_{obj_id}.csv", points, values)
        write_named_json(out_dir, "summary.json", result["summary"])
        if job.type == "daylight":
            write_daylight_summary(out_dir, result["summary"])
            annual_rows = result.get("summary", {}).get("annual_metrics", []) if isinstance(result.get("summary"), dict) else []
            if isinstance(annual_rows, list) and annual_rows:
                by_target = {
                    str(r.get("target_id")): r for r in annual_rows if isinstance(r, dict) and r.get("target_id") is not None
                }
                for obj in calc_objects:
                    if not isinstance(obj, dict):
                        continue
                    tid = str(obj.get("id", ""))
                    row = by_target.get(tid)
                    points = obj.get("points")
                    if row is None or not isinstance(points, np.ndarray):
                        continue
                    sda = np.asarray(row.get("sda_point_percent", []), dtype=float)
                    ase = np.asarray(row.get("ase_point_percent", []), dtype=float)
                    udi = np.asarray(row.get("udi_point_percent", []), dtype=float)
                    write_daylight_annual_target_artifacts(
                        out_dir,
                        tid,
                        points,
                        sda,
                        ase,
                        udi,
                        nx=int(obj.get("nx", 0)),
                        ny=int(obj.get("ny", 0)),
                    )
                write_named_json(out_dir, "annual_summary.json", {"targets": annual_rows})
        if job.type == "emergency":
            write_named_json(out_dir, "emergency_summary.json", result["summary"])
            if isinstance(result.get("summary"), dict):
                write_named_json(
                    out_dir,
                    "emergency_compliance.json",
                    {
                        "standard": result["summary"].get("standard"),
                        "category": "default",
                        "thresholds": (result["summary"].get("compliance", {}) or {}).get("thresholds", {}),
                        "pass_fail": (result["summary"].get("compliance", {}) or {}).get("status"),
                        "reasons": (result["summary"].get("compliance", {}) or {}).get("reasons", []),
                    },
                )
        grid_rows = build_grid_table(calc_objects)
        plane_rows = build_plane_table(calc_objects)
        point_rows = build_pointset_table(calc_objects)
        worst = build_worstcase_summary(calc_objects)
        tables_payload = {
            "grids": grid_rows,
            "vertical_planes": plane_rows,
            "point_sets": point_rows,
            "worst_case": worst,
        }
        write_tables_json(out_dir, tables_payload)
        write_tables_csv(out_dir, grid_rows + plane_rows + point_rows)

    if "grid_points" in result and "grid_values" in result and not (isinstance(calc_objects, list) and calc_objects):
        write_grid_csv(out_dir, result["grid_points"], result["grid_values"])
        nx = int(result.get("grid_nx", 0))
        ny = int(result.get("grid_ny", 0))
        if nx > 0 and ny > 0:
            write_grid_heatmap_and_isolux(out_dir, result["grid_points"], result["grid_values"], nx=nx, ny=ny)
        if job.type == "roadway":
            shutil.copyfile(out_dir / "grid.csv", out_dir / "road_grid.csv")
            write_named_json(out_dir, "road_summary.json", result["summary"])
            lane_grids = result.get("lane_grids", [])
            if isinstance(lane_grids, list):
                for lane in lane_grids:
                    if not isinstance(lane, dict):
                        continue
                    lane_num = int(lane.get("lane_number", int(lane.get("lane_index", 0)) + 1))
                    points = lane.get("points")
                    values = lane.get("values")
                    if isinstance(points, np.ndarray) and isinstance(values, np.ndarray):
                        write_grid_csv_named(out_dir, f"road_grid_{lane_num}.csv", points, values)
            heatmap = out_dir / "grid_heatmap.png"
            isolux = out_dir / "grid_isolux.png"
            if heatmap.exists():
                shutil.copyfile(heatmap, out_dir / "road_heatmap.png")
            if isolux.exists():
                shutil.copyfile(isolux, out_dir / "road_isolux.png")
        if job.type == "emergency":
            write_named_json(out_dir, "emergency_summary.json", result["summary"])
    if "residuals" in result:
        write_residuals_csv(out_dir, result["residuals"])
    if "surface_illuminance" in result:
        write_surface_illuminance_csv(out_dir, result["surface_illuminance"])
        write_surface_heatmaps(out_dir, result["surface_illuminance"])
    if "room" in result and "luminaires" in result:
        grids = compute_surface_grids(result["room"].get_surfaces(), result["luminaires"], resolution=10)
        for sid, grid in grids.items():
            write_surface_grid_csv(out_dir, sid, grid.points, grid.values)
    manifest_metadata = {
        "job_id": job.id,
        "job_hash": job_hash,
        "seed": job.seed,
        "solver": result_meta.get("solver", {}),
        "solver_version": str(result_meta.get("solver", {}).get("package_version", "unknown")),
        "backend": result_meta.get("backend", {}),
        "assets": result_meta.get("assets", {}),
        "photometry_hashes": result_meta.get("assets", {}),
        "settings": result_meta.get("settings_dump", {}),
        "coordinate_convention": result_meta.get("coordinate_convention"),
        "units": result_meta.get("units", {}),
        "photometry_assets": result_meta.get("photometry_assets", {}),
    }
    if job.type == "roadway" and isinstance(result_meta.get("summary"), dict):
        rs = result_meta["summary"]
        manifest_metadata["road_parameters"] = {
            "lane_width_m": rs.get("lane_width_m"),
            "num_lanes": rs.get("num_lanes"),
            "road_length_m": rs.get("road_length_m"),
            "mounting_height_m": rs.get("mounting_height_m"),
            "setback_m": rs.get("setback_m"),
            "pole_spacing_m": rs.get("pole_spacing_m"),
        }
    if job.type == "daylight" and isinstance(result_meta.get("summary"), dict):
        rs = result_meta["summary"]
        manifest_metadata["daylight"] = {
            "mode": rs.get("mode"),
            "sky": rs.get("sky"),
            "external_horizontal_illuminance_lux": rs.get("external_horizontal_illuminance_lux"),
            "glass_visible_transmittance_default": rs.get("glass_visible_transmittance_default"),
            "radiance_quality": rs.get("radiance_quality"),
            "random_seed": rs.get("random_seed"),
            "metric": rs.get("metric", "daylight_factor_percent"),
            "weather_file": rs.get("weather_file"),
            "thresholds": rs.get("thresholds", {}),
        }
    if job.type == "emergency" and isinstance(result_meta.get("summary"), dict):
        rs = result_meta["summary"]
        manifest_metadata["emergency"] = {
            "mode": rs.get("mode"),
            "standard": rs.get("standard"),
            "emergency_factor": rs.get("emergency_factor"),
            "luminaire_count": rs.get("luminaire_count"),
            "compliance": rs.get("compliance"),
        }
    write_manifest(out_dir, metadata=manifest_metadata)
    append_audit_event(
        project,
        action="runner.run_job",
        plan="Execute job and persist immutable result artifacts.",
        job_hashes=[job_hash],
        artifacts=[str(out_dir)],
        metadata={"job_id": job.id, "job_type": job.type},
    )

    ref = JobResultRef(job_id=job.id, job_hash=job_hash, result_dir=str(out_dir), summary=result_meta["summary"])
    _upsert_result_ref(project, ref)
    return ref


def _build_photometry_verification(project: Project, asset_hashes: Dict[str, str]) -> Dict[str, object]:
    out: Dict[str, object] = {"assets": {}, "warnings": []}
    assets_by_id = {a.id: a for a in project.photometry_assets}
    warnings: List[str] = []
    report_assets: Dict[str, object] = {}
    for asset_id, expected_hash in asset_hashes.items():
        asset = assets_by_id.get(asset_id)
        if asset is None:
            warnings.append(f"Missing asset for verification: {asset_id}")
            continue
        if asset.path:
            try:
                verify = verify_photometry_file(asset.path, fmt=asset.format).to_dict()
                verify["expected_hash"] = expected_hash
                verify["hash_match"] = verify.get("file_hash_sha256") == expected_hash
                report_assets[asset_id] = verify
            except Exception as e:
                warnings.append(f"Verification failed for {asset_id}: {e}")
                report_assets[asset_id] = {"error": str(e), "expected_hash": expected_hash}
        else:
            warnings.append(f"Asset {asset_id} has no file path; photometry verify skipped.")
            report_assets[asset_id] = {"warning": "no_file_path", "expected_hash": expected_hash}
    out["assets"] = report_assets
    out["warnings"] = warnings
    return out


def _run_direct(project: Project, job: JobSpec) -> Dict[str, object]:
    if not (project.grids or project.vertical_planes or project.arbitrary_planes or project.point_sets or project.line_grids):
        raise RunnerError("Project has no calculation objects")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    luminaires, asset_hashes = _load_luminaires_and_hashes(project)
    length_scale = project_scale_to_meters(project)

    effective = _effective_job_settings(job)
    use_occlusion = bool(effective.get("use_occlusion", False))
    occlusion_epsilon = float(effective.get("occlusion_epsilon", 1e-6))
    occlusion = build_direct_occlusion_context(
        project,
        include_room_shell=bool(effective.get("occlusion_include_room_shell", False)),
        occlusion_epsilon=occlusion_epsilon,
    )

    calc_objects: List[Dict[str, object]] = []
    aggregate_values: List[np.ndarray] = []
    primary_grid = None

    for grid_spec in project.grids:
        sg = _scale_grid_spec(grid_spec, length_scale)
        grid_res = run_direct_grid(
            sg,
            luminaires,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )
        aggregate_values.append(grid_res.values.reshape(-1))
        summary_contract = ContractGridResult(
            values=np.asarray(grid_res.values, dtype=float),
            points_xyz=np.asarray(grid_res.points, dtype=float),
            normal=tuple(float(x) for x in sg.normal),
            metadata={"id": grid_spec.id, "name": grid_spec.name, "nx": grid_res.nx, "ny": grid_res.ny},
            units="lux",
        ).to_summary()
        calc_objects.append(
            {
                "type": "grid",
                "id": grid_spec.id,
                "name": grid_spec.name,
                "points": grid_res.points,
                "values": grid_res.values,
                "nx": grid_res.nx,
                "ny": grid_res.ny,
                "summary": _compute_grid_stats(grid_res.values.reshape(-1)) | summary_contract.to_dict(),
            }
        )
        if primary_grid is None:
            primary_grid = grid_res

    for plane in project.vertical_planes:
        if getattr(plane, "host_surface_id", None):
            host = next((s for s in project.geometry.surfaces if s.id == plane.host_surface_id), None)
            if host is None:
                raise RunnerError(f"Vertical plane host surface not found: {plane.host_surface_id}")
            geo = build_vertical_grid_on_wall(
                host,
                rows=plane.ny,
                cols=plane.nx,
                openings=(project.geometry.openings if bool(getattr(plane, "mask_openings", True)) else ()),
                subrect_u0=getattr(plane, "subrect_u0", None),
                subrect_u1=getattr(plane, "subrect_u1", None),
                subrect_v0=getattr(plane, "subrect_v0", None),
                subrect_v1=getattr(plane, "subrect_v1", None),
            )
            pts_in = np.asarray([p for p, keep in zip(geo.points_xyz, geo.mask) if keep], dtype=float)
            normal = Vector3(*geo.normal).normalize()
            out = run_direct_points(
                points=pts_in,
                surface_normal=normal,
                luminaires=luminaires,
                occlusion=occlusion,
                use_occlusion=use_occlusion,
                occlusion_epsilon=occlusion_epsilon,
            )
            vals = np.full((geo.rows * geo.cols,), np.nan, dtype=float)
            src = 0
            for i, keep in enumerate(geo.mask):
                if keep:
                    vals[i] = float(out.values[src])
                    src += 1
            points_all = np.asarray(geo.points_xyz, dtype=float)
            aggregate_values.append(vals.reshape(-1))
            calc_objects.append(
                {
                    "type": "vertical_plane",
                    "id": plane.id,
                    "name": plane.name,
                    "points": points_all,
                    "values": vals,
                    "nx": geo.cols,
                    "ny": geo.rows,
                    "summary": _compute_grid_stats(vals.reshape(-1)),
                }
            )
        else:
            from luxera.project.schema import VerticalPlaneSpec

            sp = VerticalPlaneSpec(
                id=plane.id,
                name=plane.name,
                origin=tuple(float(x) * length_scale for x in plane.origin),
                width=float(plane.width) * length_scale,
                height=float(plane.height) * length_scale,
                nx=plane.nx,
                ny=plane.ny,
                azimuth_deg=plane.azimuth_deg,
                room_id=plane.room_id,
                zone_id=plane.zone_id,
            )
            plane_res = run_direct_vertical_plane(
                sp,
                luminaires,
                occlusion=occlusion,
                use_occlusion=use_occlusion,
                occlusion_epsilon=occlusion_epsilon,
            )
            aggregate_values.append(plane_res.values.reshape(-1))
            calc_objects.append(
                {
                    "type": "vertical_plane",
                    "id": plane.id,
                    "name": plane.name,
                    "points": plane_res.points,
                    "values": plane_res.values,
                    "nx": plane_res.nx,
                    "ny": plane_res.ny,
                    "summary": _compute_grid_stats(plane_res.values.reshape(-1)),
                }
            )

    for point_set in project.point_sets:
        from luxera.project.schema import PointSetSpec
        sps = PointSetSpec(
            id=point_set.id,
            name=point_set.name,
            points=[tuple(float(x) * length_scale for x in p) for p in point_set.points],
            room_id=point_set.room_id,
            zone_id=point_set.zone_id,
        )
        ps_res = run_direct_point_set(
            sps,
            luminaires,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )
        aggregate_values.append(ps_res.values.reshape(-1))
        calc_objects.append(
            {
                "type": "point_set",
                "id": point_set.id,
                "name": point_set.name,
                "points": ps_res.points,
                "values": ps_res.values,
                "summary": _compute_grid_stats(ps_res.values.reshape(-1)),
            }
        )

    for plane in project.arbitrary_planes:
        from luxera.project.schema import ArbitraryPlaneSpec
        ap = ArbitraryPlaneSpec(
            id=plane.id,
            name=plane.name,
            origin=tuple(float(x) * length_scale for x in plane.origin),
            axis_u=plane.axis_u,
            axis_v=plane.axis_v,
            width=float(plane.width) * length_scale,
            height=float(plane.height) * length_scale,
            nx=plane.nx,
            ny=plane.ny,
            room_id=plane.room_id,
            zone_id=plane.zone_id,
            evaluation_height_offset=float(getattr(plane, "evaluation_height_offset", 0.0)) * length_scale,
            metric_set=list(getattr(plane, "metric_set", [])),
        )
        plane_res = run_direct_arbitrary_plane(
            ap,
            luminaires,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )
        aggregate_values.append(plane_res.values.reshape(-1))
        calc_objects.append(
            {
                "type": "arbitrary_plane",
                "id": plane.id,
                "name": plane.name,
                "points": plane_res.points,
                "values": plane_res.values,
                "nx": plane_res.nx,
                "ny": plane_res.ny,
                "summary": _compute_grid_stats(plane_res.values.reshape(-1)),
            }
        )

    for line in project.line_grids:
        from luxera.project.schema import LineGridSpec
        lg = LineGridSpec(
            id=line.id,
            name=line.name,
            polyline=[tuple(float(x) * length_scale for x in p) for p in line.polyline],
            spacing=float(line.spacing) * length_scale,
            room_id=line.room_id,
            zone_id=line.zone_id,
            metric_set=list(getattr(line, "metric_set", [])),
        )
        line_res = run_direct_line_grid(
            lg,
            luminaires,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )
        aggregate_values.append(line_res.values.reshape(-1))
        calc_objects.append(
            {
                "type": "line_grid",
                "id": line.id,
                "name": line.name,
                "points": line_res.points,
                "values": line_res.values,
                "summary": _compute_grid_stats(line_res.values.reshape(-1)),
            }
        )

    if not aggregate_values:
        raise RunnerError("Direct job has no calculation objects to evaluate")

    all_values = np.concatenate([x.reshape(-1) for x in aggregate_values if x.size], axis=0) if any(x.size for x in aggregate_values) else np.zeros((0,), dtype=float)
    overall = _compute_grid_stats(all_values)
    worst_min = min(float(np.min(x)) if x.size else 0.0 for x in aggregate_values)
    mean_of_means = float(np.mean([float(np.mean(x)) if x.size else 0.0 for x in aggregate_values])) if aggregate_values else 0.0
    worst_uniformity = min(
        (_compute_grid_stats(x.reshape(-1)).get("uniformity_ratio", 0.0) if x.size else 0.0)
        for x in aggregate_values
    ) if aggregate_values else 0.0
    highest_ugr = max(
        (
            float(o.get("summary", {}).get("ugr_worst_case"))  # type: ignore[arg-type]
            for o in calc_objects
            if isinstance(o.get("summary", {}), dict) and isinstance(o.get("summary", {}).get("ugr_worst_case"), (int, float))
        ),
        default=0.0,
    )
    summary = {
        **overall,
        "worst_min_lux": worst_min,
        "worst_uniformity_ratio": worst_uniformity,
        "highest_ugr": highest_ugr,
        "global_worst_min_lux": worst_min,
        "global_worst_uniformity_ratio": worst_uniformity,
        "global_highest_ugr": highest_ugr,
        "mean_of_means_lux": mean_of_means,
        "calc_object_count": len(calc_objects),
        "calc_objects": [
            {
                "type": str(o.get("type")),
                "id": str(o.get("id")),
                "name": str(o.get("name", "")),
                "summary": dict(o.get("summary", {})),
            }
            for o in calc_objects
        ],
        "occlusion_enabled": use_occlusion,
        "occluder_count": len(occlusion.triangles),
    }

    compliance = None
    if project.geometry.rooms:
        room_spec = project.geometry.rooms[0]
        if room_spec.activity_type:
            try:
                activity = ActivityType[room_spec.activity_type]
                compliance = check_compliance_from_grid(
                    room_name=room_spec.name,
                    activity_type=activity,
                    grid_values_lux=all_values.reshape(-1).tolist(),
                    maintenance_factor=1.0,
                )
            except KeyError:
                compliance = {"error": f"Unknown activity_type: {room_spec.activity_type}"}
    summary["compliance"] = compliance.summary() if hasattr(compliance, "summary") else compliance
    profile = _resolve_compliance_profile(project, "indoor", (job.settings or {}).get("compliance_profile_id"))
    if profile is not None:
        summary["compliance_profile"] = _evaluate_profile_thresholds(summary, profile)

    payload: Dict[str, object] = {
        "summary": summary,
        "calc_objects": calc_objects,
        "assets": asset_hashes,
    }
    if primary_grid is not None:
        payload.update(
            {
                "grid_points": primary_grid.points,
                "grid_values": primary_grid.values,
                "grid_nx": primary_grid.nx,
                "grid_ny": primary_grid.ny,
            }
        )
    return payload


def _run_radiosity(project: Project, job: JobSpec) -> Dict[str, object]:
    if not project.geometry.rooms:
        raise RunnerError("Project has no rooms for radiosity")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    room_spec = project.geometry.rooms[0]
    room = build_room_from_spec(room_spec, length_scale=project_scale_to_meters(project))
    luminaires, asset_hashes = _load_luminaires_and_hashes(project)

    effective = _effective_job_settings(job)
    settings = RadiositySettings(
        max_iterations=int(effective["max_iterations"]),
        convergence_threshold=float(effective["convergence_threshold"]),
        damping=float(effective["damping"]),
        patch_max_area=float(effective["patch_max_area"]),
        method=RadiosityMethod[str(effective["method"])],
        use_visibility=bool(effective["use_visibility"]),
        ambient_light=float(effective["ambient_light"]),
        seed=job.seed,
        monte_carlo_samples=int(effective["monte_carlo_samples"]),
    )

    result = run_radiosity(room, luminaires, settings)

    compliance = None
    ugr_value = None
    ugr_grid_spacing = float(effective["ugr_grid_spacing"])
    ugr_eye_heights = list(effective["ugr_eye_heights"])
    ugr_occluder_bvh = build_bvh(triangulate_surfaces(room.get_surfaces()))
    ugr_analysis = compute_ugr_default(
        room,
        luminaires,
        grid_spacing=ugr_grid_spacing,
        eye_heights=ugr_eye_heights,
        occluder_bvh=ugr_occluder_bvh,
    )
    if ugr_analysis is not None:
        ugr_value = ugr_analysis.worst_case_ugr
    ugr_views_payload = None
    if project.glare_views:
        view_analysis = compute_ugr_for_views(room, luminaires, project.glare_views, occluder_bvh=ugr_occluder_bvh)
        if view_analysis is not None:
            ugr_value = max(ugr_value or 0.0, view_analysis.worst_case_ugr)
            ugr_views_payload = [
                {
                    "name": r.observer.name,
                    "observer": r.observer.eye_position.to_tuple(),
                    "view_dir": r.observer.view_direction.to_tuple(),
                    "ugr": r.ugr_value,
                }
                for r in view_analysis.results
            ]

    if room_spec.activity_type:
        try:
            activity = ActivityType[room_spec.activity_type]
            if result.floor_values:
                compliance = check_compliance_from_grid(
                    room_name=room_spec.name,
                    activity_type=activity,
                    grid_values_lux=result.floor_values,
                    maintenance_factor=1.0,
                    ugr=ugr_value,
                )
        except KeyError:
            compliance = {"error": f"Unknown activity_type: {room_spec.activity_type}"}

    summary = {
        "avg_illuminance": result.avg_illuminance,
        "total_flux": result.total_flux,
        "iterations": result.iterations,
        "converged": result.converged,
        "stop_reason": result.stop_reason,
        "residuals": result.residuals,
        "solver_status": result.solver_status,
        "energy": result.energy,
        "compliance": compliance.summary() if hasattr(compliance, "summary") else compliance,
        "ugr_worst_case": ugr_value,
        "ugr_views": ugr_views_payload,
    }

    return {
        "summary": summary,
        "assets": asset_hashes,
        "residuals": result.residuals,
        "surface_illuminance": result.surface_illuminance,
        "room": room,
        "luminaires": luminaires,
    }


def _build_run_assumptions(job: JobSpec, result: Dict[str, object]) -> List[str]:
    a: List[str] = []
    a.append("Coordinate convention: local luminaire frame +Z up, nadir -Z; Type C C=0 toward +X, C=90 toward +Y.")
    a.append("Supported photometric types: Type C only.")
    a.append("TILT factors are applied against gamma (vertical) angle; out-of-range tilt angles are clamped.")
    if job.type == "direct":
        if result.get("summary", {}).get("occlusion_enabled"):
            a.append("Direct occlusion uses hard-shadow binary ray blocking.")
        else:
            a.append("Direct calculation excludes geometry occlusion unless enabled.")
        a.append("Luminaire tilt is applied when photometry includes tilt data; otherwise tilt has no effect.")
        a.append("Direct solver uses no inter-reflection reflectance model (direct-only irradiance).")
    if job.type == "radiosity":
        a.append("Radiosity uses diffuse reflectance model with iterative convergence.")
        a.append("Specular reflectance is treated in direct-only pathways; radiosity secondary bounce is diffuse-only.")
        a.append("Material transmittance is currently not included in radiosity energy exchange.")
        if result.get("summary", {}).get("ugr_views"):
            a.append("UGR view results use explicit observer/view definitions from glare_views.")
        else:
            a.append("UGR uses default observer grid and eye heights when glare_views are absent.")
    if job.backend == "radiance":
        a.append("Radiance backend currently uses luminaire rectangle proxy emitters.")
    if job.type == "roadway":
        a.append("Roadway metrics are computed on roadway grid centerline/lane samples from project settings.")
    if job.type == "emergency":
        a.append("Emergency evaluation includes battery output decay over configured duration.")
    if job.type == "daylight":
        a.append("Daylight metrics support daylight-factor, radiance point mode, and annual (sDA/ASE/UDI) workflows.")
    return a


def _build_unsupported_features(job: JobSpec) -> List[str]:
    u: List[str] = []
    if job.type == "direct":
        u.append("Penumbra/area-light soft shadowing is not implemented in CPU direct backend.")
    if job.backend == "radiance":
        u.append("IES-native Radiance source mapping is approximated via proxy emitters.")
    if job.type == "roadway":
        u.append("Roadway glare/discomfort metrics are not yet implemented.")
    if job.type == "emergency":
        u.append("Emergency luminaire-level battery heterogeneity is not yet modeled.")
    if job.type == "daylight":
        u.append("Annual daylight currently uses deterministic Radiance-contract proxy sampling for reproducible metrics.")
    return u


def _compute_grid_stats(values: np.ndarray) -> Dict[str, float]:
    vals = values.reshape(-1)
    m = compute_basic_metrics(vals.tolist())
    return {
        "min_lux": float(m.E_min),
        "max_lux": float(m.E_max),
        "mean_lux": float(m.E_avg),
        "uniformity_ratio": float(m.U0),
        "uniformity_diversity": float(m.U1),
        "p50_lux": float(m.P50),
        "p90_lux": float(m.P90),
    }


def _evaluate_profile_thresholds(summary: Dict[str, float], profile: Dict[str, object]) -> Dict[str, object]:
    th = profile.get("thresholds", {}) if isinstance(profile, dict) else {}
    avg_min = float(th.get("avg_min_lux", 0.0))
    umin = float(th.get("uniformity_min", 0.0))
    ugr_max = float(th.get("ugr_max", 999.0))
    ugr_val = summary.get("ugr_worst_case")
    ugr_ok = True
    if isinstance(ugr_val, (int, float)):
        ugr_ok = float(ugr_val) <= ugr_max
    status = "PASS" if (summary["mean_lux"] >= avg_min and summary["uniformity_ratio"] >= umin and ugr_ok) else "FAIL"
    return {
        "profile_id": profile.get("id"),
        "standard": profile.get("standard_ref"),
        "status": status,
        "avg_ok": summary["mean_lux"] >= avg_min,
        "uniformity_ok": summary["uniformity_ratio"] >= umin,
        "ugr_ok": ugr_ok,
        "thresholds": {
            "avg_min_lux": avg_min,
            "uniformity_min": umin,
            "ugr_max": ugr_max,
        },
    }


def _resolve_compliance_profile(project: Project, domain: str, profile_id: Optional[str]) -> Optional[Dict[str, object]]:
    if profile_id:
        p = next((x for x in project.compliance_profiles if x.id == profile_id), None)
        return p.__dict__ if p is not None else None
    p = next((x for x in project.compliance_profiles if x.domain == domain), None)
    return p.__dict__ if p is not None else None


def _load_luminaires_and_hashes(project: Project):
    try:
        root = _resolve_project_root(project)
        return load_luminaires(project, lambda asset: _hash_photometry_asset(asset, root))
    except ValueError as e:
        raise RunnerError(str(e)) from e


def _run_roadway(project: Project, job: JobSpec) -> Dict[str, object]:
    if not project.roadway_grids:
        raise RunnerError("Project has no roadway grids")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    rg = project.roadway_grids[0]
    roadway = next((rw for rw in project.roadways if rw.id == rg.roadway_id), None) if getattr(rg, "roadway_id", None) else None
    settings = _effective_job_settings(job)
    settings["length_scale_to_m"] = project_scale_to_meters(project)
    if settings.get("observer_height_m") is None:
        settings["observer_height_m"] = float(getattr(rg, "observer_height_m", 1.5))
    luminaires, asset_hashes = _load_luminaires_and_hashes(project)

    road = run_road_illuminance(roadway, rg, luminaires, settings)
    summary = dict(road.summary)
    summary["road_class"] = str(settings.get("road_class", "M3"))

    profile = _resolve_compliance_profile(project, "roadway", settings.get("compliance_profile_id"))
    if profile is not None:
        th = profile.get("thresholds", {}) if isinstance(profile, dict) else {}
        avg_min = float(th.get("avg_min_lux", 0.0))
        uo_min = float(th.get("uo_min", 0.0))
        ul_min = float(th.get("ul_min", 0.0))
        lmin = float(th.get("luminance_min_cd_m2", 0.0))
        ti_max = float(th.get("ti_max_percent", 999.0))
        sr_min = float(th.get("surround_ratio_min", 0.0))
        summary["compliance"] = {
            "profile_id": profile.get("id"),
            "standard": profile.get("standard_ref"),
            "avg_ok": summary["mean_lux"] >= avg_min,
            "uo_ok": summary["uniformity_ratio"] >= uo_min,
            "ul_ok": summary["ul_longitudinal"] >= ul_min,
            "luminance_ok": summary["road_luminance_mean_cd_m2"] >= lmin,
            "ti_ok": summary["threshold_increment_ti_proxy_percent"] <= ti_max,
            "surround_ratio_ok": summary["surround_ratio_proxy"] >= sr_min,
            "thresholds": {
                "avg_min_lux": avg_min,
                "uo_min": uo_min,
                "ul_min": ul_min,
                "luminance_min_cd_m2": lmin,
                "ti_max_percent": ti_max,
                "surround_ratio_min": sr_min,
            },
        }

    return {
        "summary": summary,
        "grid_points": road.points,
        "grid_values": road.values,
        "grid_nx": road.nx,
        "grid_ny": road.ny,
        "lane_grids": road.lane_grids,
        "assets": asset_hashes,
    }


def _run_emergency(project: Project, job: JobSpec) -> Dict[str, object]:
    if job.emergency is not None or job.routes or job.open_area_targets:
        if not project.luminaires:
            raise RunnerError("Emergency job requires at least one luminaire")
        length_scale = project_scale_to_meters(project)
        luminaires, asset_hashes = _load_luminaires_and_hashes(project)
        effective = _effective_job_settings(job)
        use_occlusion = bool(effective.get("use_occlusion", False))
        occlusion_epsilon = float(effective.get("occlusion_epsilon", 1e-6))
        occlusion = build_direct_occlusion_context(
            project,
            include_room_shell=bool(effective.get("occlusion_include_room_shell", False)),
            occlusion_epsilon=occlusion_epsilon,
        )
        mode = job.mode
        emergency_factor = float(mode.emergency_factor) if mode is not None else 1.0
        include_ids = set(mode.include_luminaires) if mode is not None else set()
        include_ids |= set(mode.include_luminaire_ids) if mode is not None else set()
        exclude_ids = set(mode.exclude_luminaires) if mode is not None else set()
        include_tags = set(mode.include_tags) if mode is not None else set()
        if mode is not None and mode.include_tag:
            include_tags.add(str(mode.include_tag))
        selected_lums: List = []
        for runtime_lum, spec_lum in zip(luminaires, project.luminaires):
            if include_ids and spec_lum.id not in include_ids:
                continue
            if include_tags and not set(getattr(spec_lum, "tags", []) or []).intersection(include_tags):
                continue
            if spec_lum.id in exclude_ids:
                continue
            selected_lums.append(runtime_lum)
        if not selected_lums:
            raise RunnerError("Emergency luminaire selection resolved to empty set")

        route_map = {r.id: r for r in project.escape_routes}
        routes = [route_map[rid] for rid in job.routes if rid in route_map]
        route_results = run_escape_routes(
            routes,
            selected_lums,
            emergency_factor=emergency_factor,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
            length_scale=length_scale,
        )

        grid_ids = set(job.open_area_targets or [])
        grids = [g for g in project.grids if (not grid_ids or g.id in grid_ids)]
        scaled_grids = [_scale_grid_spec(g, length_scale) for g in grids]
        open_results = run_open_area(
            scaled_grids,
            selected_lums,
            emergency_factor=emergency_factor,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )

        spec = job.emergency
        standard = (spec.standard if spec is not None else "EN1838")
        profile = get_standard_profile(standard, category="default")
        route_min_lux = float(spec.route_min_lux) if spec is not None else float(profile["route_min_lux"])
        route_u0_min = float(spec.route_u0_min) if spec is not None else float(profile["route_u0_min"])
        open_min_lux = float(spec.open_area_min_lux) if spec is not None else float(profile["open_area_min_lux"])
        open_u0_min = float(spec.open_area_u0_min) if spec is not None else float(profile["open_area_u0_min"])
        route_stats = []
        for rr in route_results:
            s = dict(rr.summary)
            s["route_id"] = rr.route_id
            s["pass"] = bool(s["min_lux"] >= route_min_lux and s["u0"] >= route_u0_min)
            route_stats.append(s)
        open_stats = []
        for orr in open_results:
            s = dict(orr.summary)
            s["grid_id"] = orr.target_id
            s["pass"] = bool(s["min_lux"] >= open_min_lux and s["u0"] >= open_u0_min)
            open_stats.append(s)
        route_pass = all(bool(x.get("pass", False)) for x in route_stats) if route_stats else True
        open_pass = all(bool(x.get("pass", False)) for x in open_stats) if open_stats else True
        reasons: List[str] = []
        for row in route_stats:
            if not bool(row.get("pass", False)):
                reasons.append(
                    f"Route {row.get('route_id')} failed: min {float(row.get('min_lux', 0.0)):.3f} < {route_min_lux:.3f} lux or U0 {float(row.get('u0', 0.0)):.3f} < {route_u0_min:.3f}"
                )
        for row in open_stats:
            if not bool(row.get("pass", False)):
                reasons.append(
                    f"Open area {row.get('grid_id')} failed: min {float(row.get('min_lux', 0.0)):.3f} < {open_min_lux:.3f} lux or U0 {float(row.get('u0', 0.0)):.3f} < {open_u0_min:.3f}"
                )
        summary = {
            "mode": "emergency_v1",
            "standard": standard,
            "emergency_factor": emergency_factor,
            "luminaire_count": len(selected_lums),
            "route_results": route_stats,
            "open_area_results": open_stats,
            "compliance": {
                "route_pass": route_pass,
                "open_area_pass": open_pass,
                "status": "PASS" if (route_pass and open_pass) else "FAIL",
                "thresholds": {
                    "route_min_lux": route_min_lux,
                    "route_u0_min": route_u0_min,
                    "open_area_min_lux": open_min_lux,
                    "open_area_u0_min": open_u0_min,
                },
                "reasons": reasons,
            },
        }
        calc_objects: List[Dict[str, object]] = []
        for rr in route_results:
            calc_objects.append(
                {
                    "type": "escape_route",
                    "id": rr.route_id,
                    "name": rr.route_id,
                    "points": rr.points,
                    "values": rr.values,
                    "summary": rr.summary,
                }
            )
        for gr, orr in zip(grids, open_results):
            calc_objects.append(
                {
                    "type": "grid",
                    "id": gr.id,
                    "name": gr.name,
                    "points": orr.points,
                    "values": orr.values,
                    "nx": orr.nx,
                    "ny": orr.ny,
                    "summary": orr.summary,
                }
            )
        return {
            "summary": summary,
            "calc_objects": calc_objects,
            "assets": asset_hashes,
        }

    base = _run_direct(project, JobSpec(id=f"{job.id}:direct", type="direct", backend=job.backend, settings=job.settings, seed=job.seed))
    vals = np.array(base["grid_values"], dtype=float)
    summary = dict(_compute_grid_stats(vals))
    settings = _effective_job_settings(job)
    target_min = float(settings["target_min_lux"])
    target_u0 = float(settings["target_uniformity"])
    duration = float(settings["battery_duration_min"])
    end_factor = float(settings["battery_end_factor"])
    curve = str(settings["battery_curve"])
    steps = max(2, int(settings["battery_steps"]))

    tvals = np.linspace(0.0, duration, steps)
    profile_rows: List[Dict[str, float]] = []
    worst_min = float("inf")
    worst_u0 = float("inf")
    for t in tvals:
        tt = 0.0 if duration <= 1e-9 else (t / duration)
        if curve == "exponential":
            f = float(end_factor ** tt)
        else:
            f = float(1.0 - (1.0 - end_factor) * tt)
        f = max(0.0, min(1.0, f))
        st = _compute_grid_stats(vals * f)
        worst_min = min(worst_min, st["min_lux"])
        worst_u0 = min(worst_u0, st["uniformity_ratio"])
        profile_rows.append(
            {
                "time_min": float(t),
                "factor": f,
                "min_lux": st["min_lux"],
                "mean_lux": st["mean_lux"],
                "uniformity_ratio": st["uniformity_ratio"],
            }
        )
    summary.update(
        {
            "mode": str(settings["mode"]),
            "emergency_target_min_lux": target_min,
            "emergency_target_uniformity": target_u0,
            "battery_duration_min": duration,
            "battery_end_factor": end_factor,
            "battery_curve": curve,
            "battery_profile": profile_rows,
            "compliance": {
                "min_lux_ok": worst_min >= target_min,
                "uniformity_ok": worst_u0 >= target_u0,
                "worst_min_lux": worst_min,
                "worst_uniformity_ratio": worst_u0,
                "thresholds": {"min_lux": target_min, "uniformity_ratio": target_u0},
            },
        }
    )
    profile = _resolve_compliance_profile(project, "emergency", (job.settings or {}).get("compliance_profile_id"))
    if profile is not None:
        summary["compliance"]["profile_id"] = profile.get("id")
        summary["compliance"]["standard"] = profile.get("standard_ref")
    return {
        "summary": summary,
        "grid_points": base["grid_points"],
        "grid_values": base["grid_values"],
        "grid_nx": base["grid_nx"],
        "grid_ny": base["grid_ny"],
        "assets": base["assets"],
    }


def _run_daylight(project: Project, job: JobSpec) -> Dict[str, object]:
    if job.daylight is not None or job.targets or job.backend in {"df", "radiance"}:
        mode = (job.daylight.mode if job.daylight is not None else ("radiance" if job.backend == "radiance" else "df")).lower()
        if mode == "annual":
            out = run_daylight_annual_radiance(project, job, scene=None)
        elif mode == "radiance":
            out = run_daylight_radiance(project, job, scene=None)
        else:
            out = run_daylight_df(project, job, scene=None)
        calc_objects: List[Dict[str, object]] = []
        aggregate: List[np.ndarray] = []
        for tr in out.targets:
            aggregate.append(tr.values.reshape(-1))
            calc_objects.append(
                {
                    "type": tr.target_type,
                    "id": tr.target_id,
                    "name": tr.target_id,
                    "points": tr.points,
                    "values": tr.values,
                    "nx": tr.nx,
                    "ny": tr.ny,
                    "summary": {
                        "min_df_percent": float(np.min(tr.values)) if tr.values.size else 0.0,
                        "mean_df_percent": float(np.mean(tr.values)) if tr.values.size else 0.0,
                        "max_df_percent": float(np.max(tr.values)) if tr.values.size else 0.0,
                    },
                }
            )
        flat = np.concatenate([x.reshape(-1) for x in aggregate], axis=0) if aggregate else np.zeros((0,), dtype=float)
        summary = dict(out.summary)
        summary.setdefault("min_df_percent", float(np.min(flat)) if flat.size else 0.0)
        summary.setdefault("mean_df_percent", float(np.mean(flat)) if flat.size else 0.0)
        summary.setdefault("max_df_percent", float(np.max(flat)) if flat.size else 0.0)
        summary["calc_object_count"] = len(calc_objects)
        if isinstance(out.summary.get("annual_metrics"), list):
            summary["annual_metrics"] = out.summary["annual_metrics"]
        primary = calc_objects[0] if calc_objects else None
        result: Dict[str, object] = {
            "summary": summary,
            "calc_objects": calc_objects,
            "assets": {},
            "daylight_backend": mode,
        }
        if isinstance(primary, dict):
            result["grid_points"] = primary.get("points", np.zeros((0, 3), dtype=float))
            result["grid_values"] = primary.get("values", np.zeros((0,), dtype=float))
            result["grid_nx"] = int(primary.get("nx", 0))
            result["grid_ny"] = int(primary.get("ny", 0))
        return result

    if not project.grids:
        raise RunnerError("Project has no grids")
    grid_spec = _scale_grid_spec(project.grids[0], project_scale_to_meters(project))
    grid = build_grid_from_spec(grid_spec)
    pts = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
    settings = _effective_job_settings(job)
    mode = str(settings["mode"])
    ext = float(settings["exterior_horizontal_illuminance_lux"])
    df = float(settings["daylight_factor_percent"])
    target = float(settings["target_lux"])
    if mode == "annual_proxy":
        ext_hourly = settings.get("exterior_hourly_lux")
        if isinstance(ext_hourly, list) and ext_hourly:
            ext_vals = np.array([float(v) for v in ext_hourly], dtype=float)
        else:
            hours = int(settings["annual_hours"])
            ext_generated: List[float] = []
            for h in range(hours):
                hod = h % 24
                day_angle = (hod - 6.0) / 12.0
                sun = max(0.0, math.sin(math.pi * day_angle))
                season = 0.6 + 0.4 * math.sin(2.0 * math.pi * ((h / 24.0) / 365.0 - 0.25))
                ext_generated.append(100000.0 * max(0.0, season) * sun)
            ext_vals = np.array(ext_generated, dtype=float)
        if pts.shape[0] == 0:
            point_factor = np.zeros((0,), dtype=float)
        else:
            x = pts[:, 0]
            x0 = float(np.min(x))
            depth = x - x0
            depth_scale = max(grid.width, 1e-9)
            attenuation = float(settings["daylight_depth_attenuation"])
            point_factor = np.exp(-attenuation * depth / depth_scale)
        interior = (ext_vals[:, None] * (df * 0.01)) * point_factor[None, :]
        da_per_point = np.mean(interior >= target, axis=0) if interior.size else np.zeros((pts.shape[0],), dtype=float)
        sda_thr = float(settings["sda_threshold_ratio"])
        sda = float(np.mean(da_per_point >= sda_thr)) if da_per_point.size else 0.0
        udi_low = float(settings["udi_low_lux"])
        udi_high = float(settings["udi_high_lux"])
        udi_per_point = np.mean((interior >= udi_low) & (interior <= udi_high), axis=0) if interior.size else np.zeros((pts.shape[0],), dtype=float)
        mean_point_lux = np.mean(interior, axis=0) if interior.size else np.zeros((pts.shape[0],), dtype=float)
        stats = _compute_grid_stats(mean_point_lux)
        summary = {
            **stats,
            "mode": "annual",
            "annual_hours": int(ext_vals.shape[0]),
            "target_lux": target,
            "daylight_factor_percent": df,
            "da_mean_ratio": float(np.mean(da_per_point)) if da_per_point.size else 0.0,
            "sda_ratio": sda,
            "udi_mean_ratio": float(np.mean(udi_per_point)) if udi_per_point.size else 0.0,
            "sda_threshold_ratio": sda_thr,
            "udi_low_lux": udi_low,
            "udi_high_lux": udi_high,
            "daylight_target_area_ratio": float(np.mean(mean_point_lux >= target)) if mean_point_lux.size else 0.0,
        }
        daylight_lux = mean_point_lux
    else:
        daylight_lux = np.full((pts.shape[0],), ext * df * 0.01, dtype=float)
        stats = _compute_grid_stats(daylight_lux)
        da_ratio = float(np.mean(daylight_lux >= target)) if daylight_lux.size else 0.0
        summary = {
            **stats,
            "mode": mode,
            "exterior_horizontal_illuminance_lux": ext,
            "daylight_factor_percent": df,
            "target_lux": target,
            "daylight_target_area_ratio": da_ratio,
        }
    return {
        "summary": summary,
        "grid_points": pts,
        "grid_values": daylight_lux,
        "grid_nx": grid.nx,
        "grid_ny": grid.ny,
        "assets": {},
    }
