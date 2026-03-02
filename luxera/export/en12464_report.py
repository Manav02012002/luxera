from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict
import tempfile
import json
import math

import numpy as np

from luxera.calculation.illuminance import CalculationGrid, IlluminanceResult, Luminaire, calculate_grid_illuminance
from luxera.calculation.plots import plot_room_with_luminaires
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.photometry.model import photometry_from_parsed_ldt
from luxera.plotting.plots import plot_polar_photometric
from luxera.results.grid_viz import write_grid_heatmap_and_isolux

from luxera.export.report_model import AuditHeader, build_report_model
from luxera.project.schema import Project, JobResultRef


@dataclass(frozen=True)
class EN12464ReportModel:
    audit: AuditHeader
    compliance: Dict[str, Any]
    inputs: Dict[str, Any]
    luminaire_schedule: list[Dict[str, Any]]
    per_grid_stats: list[Dict[str, Any]]
    tables: Dict[str, Any]
    worst_case_summary: Dict[str, Any]
    assumptions: list[str]
    result_dir: str
    heatmap_paths: list[str] = field(default_factory=list)
    isolux_paths: list[str] = field(default_factory=list)
    layout_path: str | None = None
    polar_paths: list[str] = field(default_factory=list)
    image_temp_dir: str | None = None
    polar_meta: list[Dict[str, Any]] = field(default_factory=list)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
    except Exception:
        return default
    if not math.isfinite(v):
        return default
    return v


def _iter_grid_csv_paths(result_dir: Path) -> list[Path]:
    grids_dir = result_dir / "grids"
    if not grids_dir.exists():
        return []
    out: list[Path] = []
    for p in sorted(grids_dir.glob("*.csv")):
        name = p.name.lower()
        if "direct" not in name:
            continue
        if "grid" not in name:
            continue
        out.append(p)
    return out


def _load_grid_csv(path: Path) -> tuple[np.ndarray, np.ndarray, int, int]:
    arr = np.loadtxt(str(path), delimiter=",", skiprows=1, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[1] < 4:
        raise ValueError(f"Grid CSV missing expected columns: {path}")
    order = np.lexsort((arr[:, 0], arr[:, 1]))
    arr = arr[order]
    xs = np.unique(arr[:, 0])
    ys = np.unique(arr[:, 1])
    nx = int(xs.size)
    ny = int(ys.size)
    points = arr[:, :3]
    values = arr[:, 3]
    if nx * ny != len(values):
        raise ValueError(f"Grid CSV point count does not match nx*ny: {path}")
    return points, values, nx, ny


def _estimate_beam_angle(doc) -> float | None:
    angles = getattr(doc, "angles", None)
    candela = getattr(doc, "candela", None)
    if angles is None or candela is None:
        return None
    if not angles.vertical_deg or not angles.horizontal_deg:
        return None
    c_vals = [float(v) for v in angles.horizontal_deg]
    idx = int(min(range(len(c_vals)), key=lambda i: abs(c_vals[i] - 0.0)))
    curve = np.asarray(candela.values_cd_scaled[idx], dtype=float)
    gam = np.asarray(angles.vertical_deg, dtype=float)
    if curve.size == 0 or gam.size != curve.size:
        return None
    peak = float(np.max(curve))
    if peak <= 1e-9:
        return None
    target = peak * 0.5
    mask = np.where(curve <= target)[0]
    if mask.size == 0:
        return None
    g = float(gam[int(mask[0])])
    return max(0.0, min(180.0, g * 2.0))


def _generate_report_images(project: Project, result_dir: Path) -> tuple[list[str], list[str], str | None, list[str], list[Dict[str, Any]], str | None]:
    tmp_dir = Path(tempfile.mkdtemp(prefix="luxera_en12464_"))
    heatmap_paths: list[str] = []
    isolux_paths: list[str] = []
    polar_paths: list[str] = []
    polar_meta: list[Dict[str, Any]] = []
    layout_path: str | None = None

    grid_csvs = _iter_grid_csv_paths(result_dir)
    first_grid_data: tuple[np.ndarray, np.ndarray, int, int] | None = None
    for idx, grid_csv in enumerate(grid_csvs):
        try:
            points, values, nx, ny = _load_grid_csv(grid_csv)
        except Exception:
            continue
        if first_grid_data is None:
            first_grid_data = (points, values, nx, ny)
        generated = write_grid_heatmap_and_isolux(tmp_dir, points, values, nx, ny)
        heatmap_src = generated.get("heatmap")
        isolux_src = generated.get("isolux")
        if heatmap_src and heatmap_src.exists():
            dst = tmp_dir / f"grid_{idx+1}_heatmap.png"
            heatmap_src.replace(dst)
            heatmap_paths.append(str(dst))
        if isolux_src and isolux_src.exists():
            dst = tmp_dir / f"grid_{idx+1}_isolux.png"
            isolux_src.replace(dst)
            isolux_paths.append(str(dst))

    if first_grid_data is None and project.grids and project.luminaires:
        try:
            from luxera.geometry.core import Vector3

            first_grid = project.grids[0]
            calc_grid = CalculationGrid(
                origin=Vector3(float(first_grid.origin[0]), float(first_grid.origin[1]), float(first_grid.origin[2])),
                width=float(first_grid.width),
                height=float(first_grid.height),
                elevation=float(first_grid.elevation),
                nx=int(first_grid.nx),
                ny=int(first_grid.ny),
            )
            assets_by_id = {str(a.id): a for a in project.photometry_assets}
            photometry_cache: dict[str, Any] = {}
            luminaires: list[Luminaire] = []
            for lum in project.luminaires:
                aid = str(lum.photometry_asset_id)
                if aid not in photometry_cache:
                    asset = assets_by_id.get(aid)
                    if asset is None or not asset.path:
                        photometry_cache[aid] = None
                    else:
                        ppath = Path(asset.path).expanduser()
                        if not ppath.is_absolute():
                            ppath = (Path(project.root_dir).expanduser().resolve() / ppath).resolve()
                        if not ppath.exists():
                            photometry_cache[aid] = None
                        else:
                            text = ppath.read_text(encoding="utf-8", errors="replace")
                            if str(asset.format).upper() == "IES":
                                photometry_cache[aid] = photometry_from_parsed_ies(parse_ies_text(text, source_path=ppath))
                            elif str(asset.format).upper() == "LDT":
                                photometry_cache[aid] = photometry_from_parsed_ldt(parse_ldt_text(text))
                            else:
                                photometry_cache[aid] = None
                phot = photometry_cache.get(aid)
                if phot is None:
                    continue
                luminaires.append(
                    Luminaire(
                        photometry=phot,
                        transform=lum.transform.to_transform(),
                        flux_multiplier=float(lum.flux_multiplier),
                        tilt_deg=float(lum.tilt_deg),
                    )
                )
            if luminaires:
                result = calculate_grid_illuminance(calc_grid, luminaires)
                pts = np.array([[p.x, p.y, p.z] for p in calc_grid.get_points()], dtype=float)
                vals = np.asarray(result.values, dtype=float).reshape(-1)
                first_grid_data = (pts, vals, int(calc_grid.nx), int(calc_grid.ny))
                generated = write_grid_heatmap_and_isolux(tmp_dir, pts, vals, int(calc_grid.nx), int(calc_grid.ny))
                heatmap_src = generated.get("heatmap")
                isolux_src = generated.get("isolux")
                if heatmap_src and heatmap_src.exists():
                    dst = tmp_dir / "grid_1_heatmap.png"
                    heatmap_src.replace(dst)
                    heatmap_paths.append(str(dst))
                if isolux_src and isolux_src.exists():
                    dst = tmp_dir / "grid_1_isolux.png"
                    isolux_src.replace(dst)
                    isolux_paths.append(str(dst))
        except Exception:
            pass

    if first_grid_data is not None and project.geometry.rooms:
        points, values, nx, ny = first_grid_data
        room = project.geometry.rooms[0]
        origin_x = float(np.min(points[:, 0]))
        origin_y = float(np.min(points[:, 1]))
        elevation = float(np.mean(points[:, 2]))
        from luxera.geometry.core import Vector3

        grid = CalculationGrid(
            origin=Vector3(origin_x, origin_y, elevation),
            width=float(np.max(points[:, 0]) - np.min(points[:, 0])),
            height=float(np.max(points[:, 1]) - np.min(points[:, 1])),
            elevation=elevation,
            nx=nx,
            ny=ny,
        )
        result = IlluminanceResult(grid=grid, values=np.asarray(values, dtype=float).reshape(ny, nx))
        luminaire_positions = []
        for lum in project.luminaires:
            pos = getattr(lum.transform, "position", (0.0, 0.0, 0.0))
            luminaire_positions.append((_safe_float(pos[0]), _safe_float(pos[1])))
        layout_img = tmp_dir / "room_layout.png"
        plot_room_with_luminaires(
            result=result,
            luminaire_positions=luminaire_positions,
            outpath=layout_img,
            room_width=float(room.width),
            room_length=float(room.length),
        )
        if layout_img.exists():
            layout_path = str(layout_img)

    used_asset_ids = {str(l.photometry_asset_id) for l in project.luminaires}
    assets_by_id = {str(a.id): a for a in project.photometry_assets}
    for asset_id in sorted(used_asset_ids):
        asset = assets_by_id.get(asset_id)
        if asset is None or str(asset.format).upper() != "IES" or not asset.path:
            continue
        apath = Path(asset.path).expanduser()
        if not apath.is_absolute():
            apath = (Path(project.root_dir).expanduser().resolve() / apath).resolve()
        if not apath.exists():
            continue
        try:
            text = apath.read_text(encoding="utf-8", errors="replace")
            parsed = parse_ies_text(text, source_path=apath)
            phot = photometry_from_parsed_ies(parsed)
            out = tmp_dir / f"polar_{asset_id}.png"
            plot_polar_photometric(parsed, out)
            if out.exists():
                polar_paths.append(str(out))
                polar_meta.append(
                    {
                        "asset_id": asset_id,
                        "filename": apath.name,
                        "total_lumens": float(phot.luminous_flux_lm) if phot.luminous_flux_lm is not None else None,
                        "beam_angle": _estimate_beam_angle(parsed),
                    }
                )
        except Exception:
            continue

    return heatmap_paths, isolux_paths, layout_path, polar_paths, polar_meta, str(tmp_dir)


def build_en12464_report_model(project: Project, job_ref: JobResultRef) -> EN12464ReportModel:
    result_dir = Path(job_ref.result_dir)
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    unified = build_report_model(project, job_ref.job_id, job_ref)

    audit = AuditHeader(
        project_name=project.name,
        schema_version=project.schema_version,
        job_id=job_ref.job_id,
        job_hash=job_ref.job_hash,
        solver=meta.get("solver", {}),
        settings=meta.get("job", {}),
        asset_hashes=meta.get("assets", {}),
        coordinate_convention=meta.get("coordinate_convention"),
        units=meta.get("units", {}),
        assumptions=meta.get("assumptions", []),
        unsupported_features=meta.get("unsupported_features", []),
    )

    summary = meta.get("summary", {})
    compliance = summary.get("compliance", {}) if isinstance(summary, dict) else {}
    compliance_payload = unified.get("compliance", {}) if isinstance(unified, dict) else {}
    if isinstance(compliance_payload, dict) and isinstance(compliance_payload.get("reasons"), list):
        compliance = dict(compliance) if isinstance(compliance, dict) else {}
        compliance["pass_fail_reasons"] = list(compliance_payload.get("reasons", []))
    inputs = {
        "rooms": [r.__dict__ for r in project.geometry.rooms],
        "reflectances": [
            {
                "room_id": r.id,
                "floor_reflectance": r.floor_reflectance,
                "wall_reflectance": r.wall_reflectance,
                "ceiling_reflectance": r.ceiling_reflectance,
            }
            for r in project.geometry.rooms
        ],
        "grids": [g.__dict__ for g in project.grids],
        "vertical_planes": [vp.__dict__ for vp in project.vertical_planes],
        "point_sets": [ps.__dict__ for ps in project.point_sets],
        "photometry_assets": [a.__dict__ for a in project.photometry_assets],
    }
    luminaire_schedule = unified.get("luminaire_schedule", []) if isinstance(unified, dict) else []
    per_grid_stats = summary.get("calc_objects", []) if isinstance(summary, dict) else []
    tables = unified.get("tables", {}) if isinstance(unified, dict) else {}
    worst_case_summary = unified.get("worst_case_summary", {}) if isinstance(unified, dict) else {}
    audit_payload = unified.get("audit", {}) if isinstance(unified, dict) else {}
    assumptions = list(audit_payload.get("assumptions", [])) if isinstance(audit_payload, dict) else []
    heatmap_paths, isolux_paths, layout_path, polar_paths, polar_meta, image_temp_dir = _generate_report_images(project, result_dir)

    return EN12464ReportModel(
        audit=audit,
        compliance=compliance,
        inputs=inputs,
        luminaire_schedule=luminaire_schedule,
        per_grid_stats=per_grid_stats if isinstance(per_grid_stats, list) else [],
        tables=tables if isinstance(tables, dict) else {},
        worst_case_summary=worst_case_summary if isinstance(worst_case_summary, dict) else {},
        assumptions=assumptions,
        result_dir=str(result_dir),
        heatmap_paths=heatmap_paths,
        isolux_paths=isolux_paths,
        layout_path=layout_path,
        polar_paths=polar_paths,
        image_temp_dir=image_temp_dir,
        polar_meta=polar_meta,
    )
