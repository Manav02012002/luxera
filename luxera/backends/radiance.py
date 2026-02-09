from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np

from luxera.backends.interface import BackendRunResult
from luxera.calculation.illuminance import CalculationGrid, Luminaire, calculate_grid_illuminance
from luxera.core.hashing import sha256_file
from luxera.geometry.core import Vector3, Polygon, Surface, Material, Room
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.photometry.sample import sample_intensity_cd
from luxera.project.schema import Project, JobSpec


REQUIRED_TOOLS = ["oconv", "rtrace"]


@dataclass(frozen=True)
class RadianceTooling:
    available: bool
    paths: Dict[str, str]
    missing: List[str]


def detect_radiance_tools() -> RadianceTooling:
    paths: Dict[str, str] = {}
    missing: List[str] = []
    for tool in REQUIRED_TOOLS:
        p = shutil.which(tool)
        if p:
            paths[tool] = p
        else:
            missing.append(tool)
    return RadianceTooling(available=not missing, paths=paths, missing=missing)


def get_radiance_version() -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    tool = shutil.which("rtrace")
    if not tool:
        return {"installed": False}
    try:
        out = subprocess.check_output([tool, "-version"], stderr=subprocess.STDOUT, text=True).strip()
        info["installed"] = True
        info["rtrace_version"] = out
    except Exception as e:
        info["installed"] = True
        info["error"] = str(e)
    return info


def build_radiance_run_manifest(project: Project, job: JobSpec) -> Dict[str, Any]:
    tools = detect_radiance_tools()
    return {
        "backend": "radiance",
        "job_id": job.id,
        "job_type": job.type,
        "tools": {"available": tools.available, "paths": tools.paths, "missing": tools.missing},
        "version": get_radiance_version(),
        "notes": [
            "Radiance direct-grid path enabled.",
            "Uses luminaire proxy emitters and rtrace illuminance sampling.",
        ],
    }


def _load_luminaires(project: Project) -> Tuple[List[Luminaire], Dict[str, str]]:
    assets_by_id = {a.id: a for a in project.photometry_assets}
    luminaires: List[Luminaire] = []
    asset_hashes: Dict[str, str] = {}
    for inst in project.luminaires:
        asset = assets_by_id.get(inst.photometry_asset_id)
        if asset is None:
            raise RuntimeError(f"Missing photometry asset: {inst.photometry_asset_id}")
        if not asset.path:
            raise RuntimeError(f"Radiance backend requires file-backed asset path for {asset.id}")
        text = Path(asset.path).read_text(encoding="utf-8", errors="replace")
        if asset.format == "IES":
            phot = photometry_from_parsed_ies(parse_ies_text(text))
        elif asset.format == "LDT":
            phot = photometry_from_parsed_ldt(parse_ldt_text(text))
        else:
            raise RuntimeError(f"Unsupported photometry format: {asset.format}")
        lum = Luminaire(
            photometry=phot,
            transform=inst.transform.to_transform(),
            flux_multiplier=inst.flux_multiplier,
            tilt_deg=inst.tilt_deg,
        )
        luminaires.append(lum)
        asset_hashes[asset.id] = asset.content_hash or sha256_file(asset.path)
    return luminaires, asset_hashes


def _build_room_surfaces(project: Project) -> List[Surface]:
    surfaces: List[Surface] = []
    if project.geometry.rooms:
        room = project.geometry.rooms[0]
        rm = Room.rectangular(
            name=room.name,
            width=room.width,
            length=room.length,
            height=room.height,
            origin=Vector3(*room.origin),
            floor_material=Material("floor", reflectance=room.floor_reflectance),
            wall_material=Material("wall", reflectance=room.wall_reflectance),
            ceiling_material=Material("ceiling", reflectance=room.ceiling_reflectance),
        )
        surfaces.extend(rm.get_surfaces())
    for s in project.geometry.surfaces:
        if len(s.vertices) < 3:
            continue
        poly = Polygon([Vector3(*p) for p in s.vertices])
        surfaces.append(Surface(id=s.id, polygon=poly, material=Material(name=s.name or s.id, reflectance=0.5)))
    return surfaces


def _grid_from_project(project: Project) -> CalculationGrid:
    if not project.grids:
        raise RuntimeError("Project has no grids")
    g = project.grids[0]
    return CalculationGrid(
        origin=Vector3(*g.origin),
        width=g.width,
        height=g.height,
        elevation=g.elevation,
        nx=g.nx,
        ny=g.ny,
        normal=Vector3(*g.normal),
    )


def _radiance_material_and_geometry_lines(surfaces: List[Surface]) -> List[str]:
    lines: List[str] = []
    for i, s in enumerate(surfaces):
        mat = f"mat_{i}"
        poly = f"poly_{i}"
        r = max(0.0, min(1.0, s.material.reflectance))
        lines.append(f"void plastic {mat}")
        lines.append("0")
        lines.append("0")
        lines.append(f"5 {r:.6f} {r:.6f} {r:.6f} 0 0")
        lines.append("")
        v = s.polygon.vertices
        lines.append(f"{mat} polygon {poly}")
        lines.append("0")
        lines.append("0")
        coords = " ".join(f"{p.x:.6f} {p.y:.6f} {p.z:.6f}" for p in v)
        lines.append(f"{len(v) * 3} {coords}")
        lines.append("")
    return lines


def _radiance_luminaire_proxy_lines(luminaires: List[Luminaire], intensity_scale: float) -> List[str]:
    lines: List[str] = []
    for i, lum in enumerate(luminaires):
        # Proxy luminous rectangle with output proportional to nadir candela and area.
        cd_down = float(sample_intensity_cd(lum.photometry, Vector3(0, 0, -1), tilt_deg=lum.tilt_deg)) * lum.flux_multiplier
        width = float(lum.photometry.luminous_width_m or 0.6)
        length = float(lum.photometry.luminous_length_m or 0.6)
        area = max(width * length, 1e-6)
        rgb = max((cd_down / area) * intensity_scale, 0.0)
        mat = f"lum_mat_{i}"
        geo = f"lum_rect_{i}"
        p = lum.transform.position
        R = lum.transform.get_rotation_matrix()
        ux = Vector3.from_array(R @ np.array([1.0, 0.0, 0.0], dtype=float)).normalize()
        uy = Vector3.from_array(R @ np.array([0.0, 1.0, 0.0], dtype=float)).normalize()
        hdx = ux * (width * 0.5)
        hdy = uy * (length * 0.5)
        v0 = p - hdx - hdy
        v1 = p + hdx - hdy
        v2 = p + hdx + hdy
        v3 = p - hdx + hdy
        lines.append(f"void light {mat}")
        lines.append("0")
        lines.append("0")
        lines.append(f"3 {rgb:.6f} {rgb:.6f} {rgb:.6f}")
        lines.append("")
        lines.append(f"{mat} polygon {geo}")
        lines.append("0")
        lines.append("0")
        lines.append(
            "12 "
            f"{v0.x:.6f} {v0.y:.6f} {v0.z:.6f} "
            f"{v1.x:.6f} {v1.y:.6f} {v1.z:.6f} "
            f"{v2.x:.6f} {v2.y:.6f} {v2.z:.6f} "
            f"{v3.x:.6f} {v3.y:.6f} {v3.z:.6f}"
        )
        lines.append("")
    return lines


def _write_scene_rad(path: Path, surfaces: List[Surface], luminaires: List[Luminaire], intensity_scale: float) -> None:
    lines: List[str] = []
    lines.extend(_radiance_material_and_geometry_lines(surfaces))
    lines.extend(_radiance_luminaire_proxy_lines(luminaires, intensity_scale=intensity_scale))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_points(path: Path, grid: CalculationGrid) -> np.ndarray:
    pts = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
    n = grid.normal
    rows = [f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {n.x:.6f} {n.y:.6f} {n.z:.6f}" for p in pts]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return pts


def _radiance_rgb_to_lux(rgb: np.ndarray) -> np.ndarray:
    # Radiance convention conversion to photopic lux.
    return 179.0 * (0.265 * rgb[:, 0] + 0.670 * rgb[:, 1] + 0.065 * rgb[:, 2])


def _run_radiance_tools(
    out_dir: Path,
    oct_path: Path,
    rad_path: Path,
    pts_path: Path,
    settings: Dict[str, Any],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    oconv = shutil.which("oconv")
    rtrace = shutil.which("rtrace")
    if not oconv or not rtrace:
        missing = [name for name, p in [("oconv", oconv), ("rtrace", rtrace)] if not p]
        raise RuntimeError(f"Radiance tools not available: {', '.join(missing)}")

    oconv_cmd = [oconv, str(rad_path)]
    with oct_path.open("wb") as f:
        subprocess.check_call(oconv_cmd, stdout=f, stderr=subprocess.STDOUT)

    # Minimal deterministic-ish command options.
    ab = int(settings.get("radiance_ab", 1))
    ad = int(settings.get("radiance_ad", 256))
    asamp = int(settings.get("radiance_as", 64))
    aa = float(settings.get("radiance_aa", 0.15))
    rtrace_cmd = [rtrace, "-h", "-I+", "-ab", str(ab), "-ad", str(ad), "-as", str(asamp), "-aa", str(aa), str(oct_path)]
    pts_data = pts_path.read_bytes()
    out = subprocess.check_output(rtrace_cmd, input=pts_data)
    lines = out.decode("utf-8", errors="replace").strip().splitlines()
    rgb_rows: List[List[float]] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        toks = s.split()
        if len(toks) < 3:
            continue
        rgb_rows.append([float(toks[0]), float(toks[1]), float(toks[2])])
    if not rgb_rows:
        raise RuntimeError("Radiance rtrace returned no RGB data")
    return np.array(rgb_rows, dtype=float), {
        "oconv_cmd": oconv_cmd,
        "rtrace_cmd": rtrace_cmd,
        "settings": {
            "radiance_ab": ab,
            "radiance_ad": ad,
            "radiance_as": asamp,
            "radiance_aa": aa,
        },
        "workdir": str(out_dir),
    }


def _write_delta_csv(path: Path, cpu_lux: np.ndarray, rad_lux: np.ndarray) -> Dict[str, float]:
    n = min(cpu_lux.shape[0], rad_lux.shape[0])
    c = cpu_lux[:n]
    r = rad_lux[:n]
    diff = r - c
    rel = np.where(np.abs(c) > 1e-9, diff / c, 0.0)
    rows = ["idx,cpu_lux,radiance_lux,delta_lux,delta_rel"] + [
        f"{i},{c[i]:.6f},{r[i]:.6f},{diff[i]:.6f},{rel[i]:.6f}" for i in range(n)
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return {
        "delta_mean_lux": float(np.mean(diff)),
        "delta_max_abs_lux": float(np.max(np.abs(diff))),
        "delta_mean_rel": float(np.mean(np.abs(rel))),
        "delta_p95_abs_lux": float(np.percentile(np.abs(diff), 95)),
    }


def _build_comparison_report(
    stats: Dict[str, float],
    settings: Dict[str, Any],
    points: int,
) -> Dict[str, Any]:
    max_mean_rel = float(settings.get("radiance_max_mean_rel_error", 0.50))
    max_abs_lux = float(settings.get("radiance_max_abs_lux_error", 150.0))
    passed = (stats["delta_mean_rel"] <= max_mean_rel) and (stats["delta_max_abs_lux"] <= max_abs_lux)
    return {
        "points_compared": points,
        "thresholds": {
            "max_mean_rel_error": max_mean_rel,
            "max_abs_lux_error": max_abs_lux,
        },
        "stats": stats,
        "pass": passed,
    }


def run_radiance_direct(project: Project, job: JobSpec, out_dir: Path) -> BackendRunResult:
    manifest = build_radiance_run_manifest(project, job)
    manifest_path = out_dir / "radiance_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    tools = manifest["tools"]
    if not tools.get("available", False):
        missing = ", ".join(tools.get("missing", []))
        raise RuntimeError(f"Radiance tools not available: {missing}")

    grid = _grid_from_project(project)
    luminaires, asset_hashes = _load_luminaires(project)
    surfaces = _build_room_surfaces(project)

    scene_rad = out_dir / "scene.rad"
    scene_oct = out_dir / "scene.oct"
    points_file = out_dir / "grid_points.pts"
    rtrace_rgb_csv = out_dir / "radiance_rgb.csv"
    delta_csv = out_dir / "cpu_radiance_delta.csv"
    comparison_json = out_dir / "backend_comparison.json"

    intensity_scale = float(job.settings.get("radiance_intensity_scale", 0.005))
    _write_scene_rad(scene_rad, surfaces, luminaires, intensity_scale=intensity_scale)
    grid_points = _write_points(points_file, grid)
    rgb, exec_meta = _run_radiance_tools(out_dir, scene_oct, scene_rad, points_file, settings=job.settings or {})
    lux = _radiance_rgb_to_lux(rgb).reshape(-1)

    rgb_rows = ["R,G,B"] + [f"{row[0]:.8f},{row[1]:.8f},{row[2]:.8f}" for row in rgb]
    rtrace_rgb_csv.write_text("\n".join(rgb_rows) + "\n", encoding="utf-8")

    cpu_result = calculate_grid_illuminance(grid, luminaires)
    cpu_lux = cpu_result.values.reshape(-1)
    delta_stats = _write_delta_csv(delta_csv, cpu_lux=cpu_lux, rad_lux=lux)
    comparison = _build_comparison_report(delta_stats, settings=job.settings or {}, points=int(min(cpu_lux.shape[0], lux.shape[0])))
    comparison_json.write_text(json.dumps(comparison, indent=2, sort_keys=True), encoding="utf-8")
    execution_json = out_dir / "radiance_execution.json"
    execution_json.write_text(json.dumps(exec_meta, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "min_lux": float(np.min(lux)) if lux.size else 0.0,
        "max_lux": float(np.max(lux)) if lux.size else 0.0,
        "mean_lux": float(np.mean(lux)) if lux.size else 0.0,
        "uniformity_ratio": (float(np.min(lux)) / float(np.mean(lux))) if lux.size and float(np.mean(lux)) > 1e-9 else 0.0,
        "uniformity_diversity": (float(np.min(lux)) / float(np.max(lux))) if lux.size and float(np.max(lux)) > 1e-9 else 0.0,
        "radiance_points": int(lux.size),
        "radiance_intensity_scale": intensity_scale,
        "cpu_delta": delta_stats,
        "backend_comparison_pass": bool(comparison["pass"]),
    }

    artifacts = {
        "radiance_manifest": str(manifest_path),
        "radiance_execution": str(execution_json),
        "scene_rad": str(scene_rad),
        "scene_oct": str(scene_oct),
        "points": str(points_file),
        "radiance_rgb_csv": str(rtrace_rgb_csv),
        "cpu_radiance_delta_csv": str(delta_csv),
        "backend_comparison_json": str(comparison_json),
    }

    return BackendRunResult(
        summary=summary,
        assets=asset_hashes,
        artifacts=artifacts,
        result_data={
            "grid_points": grid_points,
            "grid_values": lux,
            "grid_nx": grid.nx,
            "grid_ny": grid.ny,
            "radiance_artifacts": artifacts,
        },
    )
