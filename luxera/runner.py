from __future__ import annotations

import base64
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from luxera.calculation.illuminance import CalculationGrid, Luminaire, calculate_grid_illuminance
from luxera.core.hashing import hash_job_spec, sha256_bytes, sha256_file
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.project.schema import Project, JobSpec, JobResultRef, PhotometryAsset, RoomSpec
from luxera.results.store import (
    ensure_result_dir,
    write_grid_csv,
    write_result_json,
    write_residuals_csv,
    write_surface_illuminance_csv,
    write_surface_grid_csv,
    write_manifest,
)
from luxera.results.heatmaps import write_surface_heatmaps
from luxera.results.surface_grids import compute_surface_grids
from luxera.geometry.core import Vector3
import luxera
from luxera.engine.radiosity_engine import run_radiosity
from luxera.engine.ugr_engine import compute_ugr_default
from luxera.calculation.radiosity import RadiositySettings, RadiosityMethod
from luxera.geometry.core import Room, Material
from luxera.compliance import ActivityType, check_compliance_from_grid


class RunnerError(Exception):
    pass


def _resolve_project_root(project: Project) -> Path:
    if project.root_dir:
        return Path(project.root_dir).expanduser().resolve()
    return Path.cwd()


def _load_photometry_asset(asset: PhotometryAsset) -> str:
    if asset.embedded_b64:
        return base64.b64decode(asset.embedded_b64.encode("utf-8")).decode("utf-8", errors="replace")
    if asset.path:
        return Path(asset.path).expanduser().read_text(encoding="utf-8", errors="replace")
    raise RunnerError(f"Photometry asset {asset.id} has no data")


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


def run_job(project: Project, job_id: str) -> JobResultRef:
    job = _get_job(project, job_id)
    job_hash = hash_job_spec(project, asdict(job))

    project_root = _resolve_project_root(project)
    out_dir = ensure_result_dir(project_root, job_hash)
    result_json = out_dir / "result.json"
    if result_json.exists():
        return JobResultRef(job_id=job.id, job_hash=job_hash, result_dir=str(out_dir))

    if job.type == "direct":
        result = _run_direct(project, job)
    elif job.type == "radiosity":
        result = _run_radiosity(project, job)
    else:
        raise RunnerError(f"Unsupported job type: {job.type}")

    result_meta = {
        "job_id": job.id,
        "job_hash": job_hash,
        "job": asdict(job),
        "summary": result["summary"],
        "assets": result["assets"],
        "solver": _solver_info(project_root),
        "coordinate_convention": "Local luminaire frame: +Z up, nadir is -Z; C=0 toward +X, C=90 toward +Y",
    }

    write_result_json(out_dir, result_meta)

    if "grid_points" in result and "grid_values" in result:
        write_grid_csv(out_dir, result["grid_points"], result["grid_values"])
    if "residuals" in result:
        write_residuals_csv(out_dir, result["residuals"])
    if "surface_illuminance" in result:
        write_surface_illuminance_csv(out_dir, result["surface_illuminance"])
        write_surface_heatmaps(out_dir, result["surface_illuminance"])
    if "room" in result and "luminaires" in result:
        grids = compute_surface_grids(result["room"].get_surfaces(), result["luminaires"], resolution=10)
        for sid, grid in grids.items():
            write_surface_grid_csv(out_dir, sid, grid.points, grid.values)
    write_manifest(out_dir)

    ref = JobResultRef(job_id=job.id, job_hash=job_hash, result_dir=str(out_dir), summary=result_meta["summary"])
    project.results.append(ref)
    return ref


def _run_direct(project: Project, job: JobSpec) -> Dict[str, object]:
    if not project.grids:
        raise RunnerError("Project has no grids")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    grid_spec = project.grids[0]
    grid = CalculationGrid(
        origin=Vector3(*grid_spec.origin),
        width=grid_spec.width,
        height=grid_spec.height,
        elevation=grid_spec.elevation,
        nx=grid_spec.nx,
        ny=grid_spec.ny,
        normal=Vector3(*grid_spec.normal),
    )

    assets_by_id = {a.id: a for a in project.photometry_assets}
    luminaires: List[Luminaire] = []
    asset_hashes: Dict[str, str] = {}

    for inst in project.luminaires:
        asset = assets_by_id.get(inst.photometry_asset_id)
        if asset is None:
            raise RunnerError(f"Missing photometry asset: {inst.photometry_asset_id}")
        text = _load_photometry_asset(asset)
        if asset.format == "IES":
            parsed = parse_ies_text(text)
            phot = photometry_from_parsed_ies(parsed)
        elif asset.format == "LDT":
            parsed = parse_ldt_text(text)
            phot = photometry_from_parsed_ldt(parsed)
        else:
            raise RunnerError(f"Unsupported photometry format: {asset.format}")

        t = inst.transform.to_transform()
        lum = Luminaire(
            photometry=phot,
            transform=t,
            flux_multiplier=inst.flux_multiplier,
            tilt_deg=inst.tilt_deg,
        )
        luminaires.append(lum)
        asset_hashes[asset.id] = asset.content_hash or _hash_photometry_asset(asset)

    result = calculate_grid_illuminance(grid, luminaires)
    points = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)

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
        "compliance": compliance.summary() if hasattr(compliance, "summary") else compliance,
    }

    return {
        "summary": summary,
        "grid_points": points,
        "grid_values": result.values.reshape(-1),
        "assets": asset_hashes,
    }


def _build_room_from_spec(spec: RoomSpec) -> Room:
    floor_mat = Material(name="floor", reflectance=spec.floor_reflectance)
    wall_mat = Material(name="wall", reflectance=spec.wall_reflectance)
    ceiling_mat = Material(name="ceiling", reflectance=spec.ceiling_reflectance)
    origin = Vector3(*spec.origin)
    return Room.rectangular(
        name=spec.name,
        width=spec.width,
        length=spec.length,
        height=spec.height,
        origin=origin,
        floor_material=floor_mat,
        wall_material=wall_mat,
        ceiling_material=ceiling_mat,
    )


def _run_radiosity(project: Project, job: JobSpec) -> Dict[str, object]:
    if not project.geometry.rooms:
        raise RunnerError("Project has no rooms for radiosity")
    if not project.luminaires:
        raise RunnerError("Project has no luminaires")

    room_spec = project.geometry.rooms[0]
    room = _build_room_from_spec(room_spec)

    assets_by_id = {a.id: a for a in project.photometry_assets}
    luminaires: List[Luminaire] = []
    asset_hashes: Dict[str, str] = {}

    for inst in project.luminaires:
        asset = assets_by_id.get(inst.photometry_asset_id)
        if asset is None:
            raise RunnerError(f"Missing photometry asset: {inst.photometry_asset_id}")
        text = _load_photometry_asset(asset)
        if asset.format == "IES":
            phot = photometry_from_parsed_ies(parse_ies_text(text))
        elif asset.format == "LDT":
            phot = photometry_from_parsed_ldt(parse_ldt_text(text))
        else:
            raise RunnerError(f"Unsupported photometry format: {asset.format}")

        t = inst.transform.to_transform()
        lum = Luminaire(
            photometry=phot,
            transform=t,
            flux_multiplier=inst.flux_multiplier,
            tilt_deg=inst.tilt_deg,
        )
        luminaires.append(lum)
        asset_hashes[asset.id] = asset.content_hash or _hash_photometry_asset(asset)

    settings = RadiositySettings(
        max_iterations=job.settings.get("max_iterations", 100),
        convergence_threshold=job.settings.get("convergence_threshold", 0.001),
        patch_max_area=job.settings.get("patch_max_area", 0.5),
        method=RadiosityMethod[job.settings.get("method", "GATHERING")],
        use_visibility=job.settings.get("use_visibility", True),
        ambient_light=job.settings.get("ambient_light", 0.0),
        seed=job.seed,
        monte_carlo_samples=job.settings.get("monte_carlo_samples", 16),
    )

    result = run_radiosity(room, luminaires, settings)

    compliance = None
    ugr_value = None
    ugr_grid_spacing = job.settings.get("ugr_grid_spacing", 2.0)
    ugr_eye_heights = job.settings.get("ugr_eye_heights", [1.2, 1.7])
    ugr_analysis = compute_ugr_default(
        room,
        luminaires,
        grid_spacing=ugr_grid_spacing,
        eye_heights=ugr_eye_heights,
    )
    if ugr_analysis is not None:
        ugr_value = ugr_analysis.worst_case_ugr

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
    }

    return {
        "summary": summary,
        "assets": asset_hashes,
        "residuals": result.residuals,
        "surface_illuminance": result.surface_illuminance,
        "room": room,
        "luminaires": luminaires,
    }
