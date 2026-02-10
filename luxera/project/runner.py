from __future__ import annotations

import base64
import json
import math
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
    write_named_json,
    write_result_json,
    write_residuals_csv,
    write_surface_illuminance_csv,
    write_surface_grid_csv,
    write_manifest,
)
from luxera.results.heatmaps import write_surface_heatmaps
from luxera.results.grid_viz import write_grid_heatmap_and_isolux
from luxera.results.surface_grids import compute_surface_grids
import luxera
from luxera.engine.radiosity_engine import RadiosityMethod, RadiositySettings, run_radiosity
from luxera.engine.ugr_engine import compute_ugr_default, compute_ugr_for_views
from luxera.engine.direct_illuminance import (
    build_direct_occluders,
    build_grid_from_spec,
    build_room_from_spec,
    load_luminaires,
    run_direct_grid,
)
from luxera.compliance import ActivityType, check_compliance_from_grid
from luxera.photometry.verify import verify_photometry_file
from luxera.agent.audit import append_audit_event
from luxera.backends.radiance import build_radiance_run_manifest, get_radiance_version, run_radiance_direct


class RunnerError(Exception):
    pass


def run_job(project_path: str | Path, job_id: str) -> JobResultRef:
    """
    Path-based runner contract:
    load project -> execute -> persist updated project -> return result ref.
    """
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
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


def _hash_photometry_asset(asset: PhotometryAsset) -> str:
    if asset.embedded_b64:
        return sha256_bytes(base64.b64decode(asset.embedded_b64.encode("utf-8")))
    if asset.path:
        return sha256_file(Path(asset.path).expanduser())
    raise RunnerError(f"Photometry asset {asset.id} has no data")


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
            "convergence_threshold": 0.001,
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
        if job.type != "direct":
            raise RunnerError("Radiance backend currently supports direct jobs only")
        try:
            rr = run_radiance_direct(project, job, out_dir)
        except RuntimeError as e:
            raise RunnerError(str(e)) from e
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
    if "backend_artifacts" in result:
        result_meta["backend_artifacts"] = result["backend_artifacts"]

    verification = _build_photometry_verification(project, result.get("assets", {}))
    result_meta["photometry_verification"] = verification
    if job.backend == "radiance":
        result_meta["backend_manifest"] = build_radiance_run_manifest(project, job)
        result_meta["solver"]["radiance"] = get_radiance_version()

    write_result_json(out_dir, result_meta)
    write_named_json(out_dir, "photometry_verify.json", verification)

    if "grid_points" in result and "grid_values" in result:
        write_grid_csv(out_dir, result["grid_points"], result["grid_values"])
        nx = int(result.get("grid_nx", 0))
        ny = int(result.get("grid_ny", 0))
        if nx > 0 and ny > 0:
            write_grid_heatmap_and_isolux(out_dir, result["grid_points"], result["grid_values"], nx=nx, ny=ny)
    if "residuals" in result:
        write_residuals_csv(out_dir, result["residuals"])
    if "surface_illuminance" in result:
        write_surface_illuminance_csv(out_dir, result["surface_illuminance"])
        write_surface_heatmaps(out_dir, result["surface_illuminance"])
    if "room" in result and "luminaires" in result:
        grids = compute_surface_grids(result["room"].get_surfaces(), result["luminaires"], resolution=10)
        for sid, grid in grids.items():
            write_surface_grid_csv(out_dir, sid, grid.points, grid.values)
    write_manifest(
        out_dir,
        metadata={
            "job_id": job.id,
            "job_hash": job_hash,
            "seed": job.seed,
            "solver": result_meta.get("solver", {}),
            "backend": result_meta.get("backend", {}),
            "assets": result_meta.get("assets", {}),
            "settings": result_meta.get("settings_dump", {}),
            "coordinate_convention": result_meta.get("coordinate_convention"),
            "units": result_meta.get("units", {}),
        },
    )
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
    if not project.grids:
        raise RunnerError("Project has no grids")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    grid_spec = project.grids[0]
    try:
        luminaires, asset_hashes = load_luminaires(project, _hash_photometry_asset)
    except ValueError as e:
        raise RunnerError(str(e)) from e

    effective = _effective_job_settings(job)
    occluders = build_direct_occluders(project, include_room_shell=bool(effective.get("occlusion_include_room_shell", False)))
    grid_res = run_direct_grid(
        grid_spec,
        luminaires,
        occluders=occluders,
        use_occlusion=bool(effective.get("use_occlusion", False)),
        occlusion_epsilon=float(effective.get("occlusion_epsilon", 1e-6)),
    )
    result = grid_res.result

    compliance = None
    if project.geometry.rooms:
        room_spec = project.geometry.rooms[0]
        if room_spec.activity_type:
            try:
                activity = ActivityType[room_spec.activity_type]
                compliance = check_compliance_from_grid(
                    room_name=room_spec.name,
                    activity_type=activity,
                    grid_values_lux=result.values.reshape(-1).tolist(),
                    maintenance_factor=1.0,
                )
            except KeyError:
                compliance = {"error": f"Unknown activity_type: {room_spec.activity_type}"}

    summary = {
        "min_lux": result.min_lux,
        "max_lux": result.max_lux,
        "mean_lux": result.mean_lux,
        "uniformity_ratio": result.uniformity_ratio,
        "uniformity_diversity": result.uniformity_diversity,
        "occlusion_enabled": bool(effective.get("use_occlusion", False)),
        "occluder_count": len(occluders),
        "compliance": compliance.summary() if hasattr(compliance, "summary") else compliance,
    }
    profile = _resolve_compliance_profile(project, "indoor", (job.settings or {}).get("compliance_profile_id"))
    if profile is not None:
        summary["compliance_profile"] = _evaluate_profile_thresholds(summary, profile)

    return {
        "summary": summary,
        "grid_points": grid_res.points,
        "grid_values": grid_res.values,
        "grid_nx": grid_res.nx,
        "grid_ny": grid_res.ny,
        "assets": asset_hashes,
    }


def _run_radiosity(project: Project, job: JobSpec) -> Dict[str, object]:
    if not project.geometry.rooms:
        raise RunnerError("Project has no rooms for radiosity")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    room_spec = project.geometry.rooms[0]
    room = build_room_from_spec(room_spec)
    try:
        luminaires, asset_hashes = load_luminaires(project, _hash_photometry_asset)
    except ValueError as e:
        raise RunnerError(str(e)) from e

    effective = _effective_job_settings(job)
    settings = RadiositySettings(
        max_iterations=int(effective["max_iterations"]),
        convergence_threshold=float(effective["convergence_threshold"]),
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
    ugr_analysis = compute_ugr_default(
        room,
        luminaires,
        grid_spacing=ugr_grid_spacing,
        eye_heights=ugr_eye_heights,
    )
    if ugr_analysis is not None:
        ugr_value = ugr_analysis.worst_case_ugr
    ugr_views_payload = None
    if project.glare_views:
        view_analysis = compute_ugr_for_views(room, luminaires, project.glare_views)
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
    if job.type == "direct":
        if result.get("summary", {}).get("occlusion_enabled"):
            a.append("Direct occlusion uses hard-shadow binary ray blocking.")
        else:
            a.append("Direct calculation excludes geometry occlusion unless enabled.")
    if job.type == "radiosity":
        a.append("Radiosity uses diffuse reflectance model with iterative convergence.")
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
        a.append("Daylight metrics support daylight-factor and annual proxy workflows from configured schedules/settings.")
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
        u.append("EPW/weather-file driven climate simulation is not yet implemented (annual proxy only).")
    return u


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
        return load_luminaires(project, _hash_photometry_asset)
    except ValueError as e:
        raise RunnerError(str(e)) from e


def _roadway_observer_luminance(
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


def _run_roadway(project: Project, job: JobSpec) -> Dict[str, object]:
    if not project.roadway_grids:
        raise RunnerError("Project has no roadway grids")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    rg = project.roadway_grids[0]

    settings = _effective_job_settings(job)
    if settings.get("observer_height_m") is None:
        settings["observer_height_m"] = float(getattr(rg, "observer_height_m", 1.5))
    luminaires, asset_hashes = _load_luminaires_and_hashes(project)

    road_grid_spec = CalcGrid(
        id=rg.id,
        name=rg.name,
        origin=rg.origin,
        width=rg.road_length,
        height=rg.lane_width,
        elevation=rg.origin[2],
        nx=rg.nx,
        ny=rg.ny,
        normal=(0.0, 0.0, 1.0),
    )
    road = run_direct_grid(
        road_grid_spec,
        luminaires,
        occluders=None,
        use_occlusion=False,
        occlusion_epsilon=1e-6,
    )
    vals = np.array(road.result.values, dtype=float).reshape(rg.ny, rg.nx)
    points = road.points
    centerline = vals[rg.ny // 2, :]
    ul = float(np.min(centerline) / np.max(centerline)) if centerline.size and float(np.max(centerline)) > 1e-9 else 0.0
    rho = float(settings.get("road_surface_reflectance", 0.07))
    luminance = np.array(road.result.values, dtype=float).reshape(-1) * rho / math.pi
    views = _roadway_observer_luminance(points, luminance, rg.origin, rg.lane_width, settings)
    mean_lum = float(np.mean(luminance)) if luminance.size else 0.0
    max_view_lum = max((float(v.get("luminance_cd_m2", 0.0)) for v in views), default=0.0)
    # Deterministic glare proxy for roadway v1.5 reporting.
    ti_proxy = 65.0 * max_view_lum / max(mean_lum + 1.0, 1.0)
    # Surround ratio proxy from edge-vs-center lane strips (road-surface proxy only).
    if rg.ny >= 3:
        edge = np.concatenate([vals[0, :], vals[-1, :]])
        center = vals[rg.ny // 2, :]
        surround_ratio_proxy = float(np.mean(edge) / np.mean(center)) if center.size and float(np.mean(center)) > 1e-9 else 0.0
    else:
        surround_ratio_proxy = 0.0

    summary = dict(_compute_grid_stats(vals))
    summary.update(
        {
            "road_class": str(settings.get("road_class", "M3")),
            "ul_longitudinal": ul,
            "lane_width_m": rg.lane_width,
            "num_lanes": rg.num_lanes,
            "road_length_m": rg.road_length,
            "pole_spacing_m": rg.pole_spacing_m,
            "mounting_height_m": rg.mounting_height_m,
            "setback_m": rg.setback_m,
            "road_surface_reflectance": rho,
            "road_luminance_mean_cd_m2": mean_lum,
            "observer_luminance_views": views,
            "observer_luminance_max_cd_m2": max_view_lum,
            "threshold_increment_ti_proxy_percent": float(ti_proxy),
            "surround_ratio_proxy": surround_ratio_proxy,
        }
    )

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
        "grid_points": points,
        "grid_values": road.values,
        "grid_nx": rg.nx,
        "grid_ny": rg.ny,
        "assets": asset_hashes,
    }


def _run_emergency(project: Project, job: JobSpec) -> Dict[str, object]:
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
    if not project.grids:
        raise RunnerError("Project has no grids")
    grid_spec = project.grids[0]
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
            "mode": mode,
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
