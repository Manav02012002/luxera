from __future__ import annotations
"""Contract: docs/spec/report_contracts.md."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from luxera.project.schema import Project, JobResultRef, PhotometryAsset
from luxera.compliance.en13032 import evaluate_en13032


@dataclass(frozen=True)
class AuditHeader:
    project_name: str
    schema_version: int
    job_id: str
    job_hash: str
    solver: Dict[str, Any]
    settings: Dict[str, Any]
    asset_hashes: Dict[str, str]
    coordinate_convention: Optional[str] = None
    units: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    unsupported_features: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PhotometryEntry:
    asset_id: str
    format: str
    filename: Optional[str]
    content_hash: Optional[str]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class EN13032ReportModel:
    audit: AuditHeader
    photometry: List[PhotometryEntry]
    summary: Dict[str, Any]
    geometry: Dict[str, Any]
    method: Dict[str, Any]
    compliance: Optional[Dict[str, Any]] = None


def _load_result_meta(result_dir: Path) -> Dict[str, Any]:
    path = result_dir / "result.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_en13032_report_model(project: Project, job_ref: JobResultRef) -> EN13032ReportModel:
    result_dir = Path(job_ref.result_dir)
    meta = _load_result_meta(result_dir)

    asset_hashes = meta.get("assets", {})
    solver = meta.get("solver", {})
    settings = meta.get("job", {})

    photometry_entries: List[PhotometryEntry] = []
    for asset in project.photometry_assets:
        photometry_entries.append(
            PhotometryEntry(
                asset_id=asset.id,
                format=asset.format,
                filename=asset.metadata.get("filename") if asset.metadata else None,
                content_hash=asset.content_hash,
                metadata=asset.metadata or {},
            )
        )

    audit = AuditHeader(
        project_name=project.name,
        schema_version=project.schema_version,
        job_id=job_ref.job_id,
        job_hash=job_ref.job_hash,
        solver=solver,
        settings=settings,
        asset_hashes=asset_hashes,
        coordinate_convention=meta.get("coordinate_convention"),
        units=meta.get("units", {}),
        assumptions=meta.get("assumptions", []),
        unsupported_features=meta.get("unsupported_features", []),
    )

    summary = meta.get("summary", {})
    compliance = summary.get("compliance") if isinstance(summary, dict) else None
    en13032 = evaluate_en13032(summary).to_dict() if isinstance(summary, dict) else None

    geometry = {
        "rooms": [r.__dict__ for r in project.geometry.rooms],
        "grids": [g.__dict__ for g in project.grids],
    }
    method = {
        "job": meta.get("job", {}),
        "solver": meta.get("solver", {}),
        "coordinate_convention": meta.get("coordinate_convention"),
    }

    return EN13032ReportModel(
        audit=audit,
        photometry=photometry_entries,
        summary=summary,
        geometry=geometry,
        method=method,
        compliance={"en12464": compliance, "en13032": en13032},
    )


def build_report_model(project: Project, job_id: str, result_ref: JobResultRef) -> Dict[str, Any]:
    result_dir = Path(result_ref.result_dir).expanduser().resolve()
    meta = _load_result_meta(result_dir)
    summary = meta.get("summary", {}) if isinstance(meta, dict) else {}
    assets = meta.get("assets", {}) if isinstance(meta, dict) else {}

    assets_by_id: Dict[str, PhotometryAsset] = {a.id: a for a in project.photometry_assets}
    luminaire_schedule_by_key: Dict[str, Dict[str, Any]] = {}
    for lum in project.luminaires:
        asset = assets_by_id.get(lum.photometry_asset_id)
        rotation_payload = lum.transform.rotation.__dict__
        key = json.dumps(
            {
                "asset_id": lum.photometry_asset_id,
                "mounting": lum.mounting_type,
                "mounting_height_m": lum.mounting_height_m,
                "rotation": rotation_payload,
                "aim": lum.transform.rotation.aim,
                "tilt_deg": lum.tilt_deg,
                "flux_multiplier": lum.flux_multiplier,
                "maintenance_factor": lum.maintenance_factor,
            },
            sort_keys=True,
            default=str,
        )
        if key not in luminaire_schedule_by_key:
            luminaire_schedule_by_key[key] = {
                "id": lum.id,
                "name": lum.name,
                "count": 0,
                "asset_id": lum.photometry_asset_id,
                "asset_name": (asset.metadata.get("filename") if asset and asset.metadata else None) or lum.photometry_asset_id,
                "asset_hash": assets.get(lum.photometry_asset_id) if isinstance(assets, dict) else None,
                "mounting": lum.mounting_type,
                "mounting_height_m": lum.mounting_height_m,
                "position": lum.transform.position,
                "rotation": rotation_payload,
                "aim": lum.transform.rotation.aim,
                "tilt_deg": lum.tilt_deg,
                "flux_multiplier": lum.flux_multiplier,
                "maintenance_factor": lum.maintenance_factor,
                "llf": lum.maintenance_factor,
            }
        luminaire_schedule_by_key[key]["count"] = int(luminaire_schedule_by_key[key]["count"]) + 1
    luminaire_schedule: List[Dict[str, Any]] = list(luminaire_schedule_by_key.values())

    per_grid = summary.get("calc_objects", []) if isinstance(summary, dict) else []
    worst = {
        "global_worst_min_lux": summary.get("global_worst_min_lux", summary.get("worst_min_lux")) if isinstance(summary, dict) else None,
        "global_worst_uniformity_ratio": summary.get("global_worst_uniformity_ratio", summary.get("uniformity_ratio")) if isinstance(summary, dict) else None,
        "global_highest_ugr": summary.get("global_highest_ugr", summary.get("ugr_worst_case")) if isinstance(summary, dict) else None,
    }

    compliance = summary.get("compliance", {}) if isinstance(summary, dict) else {}
    pass_fail_reasons: List[str] = []
    thresholds = compliance.get("thresholds", {}) if isinstance(compliance, dict) else {}
    if isinstance(compliance, dict):
        for k, v in compliance.items():
            if k.endswith("_ok") and v is False:
                pass_fail_reasons.append(f"{k} failed")
            if k.endswith("_ok") and v is True:
                pass_fail_reasons.append(f"{k} passed")

    photo_assets = meta.get("photometry_assets", {}) if isinstance(meta, dict) else {}
    has_tilt = any(
        isinstance(v, dict) and str(v.get("tilt_mode", "")).upper() in {"INCLUDE", "FILE"}
        for v in (photo_assets.values() if isinstance(photo_assets, dict) else [])
    )
    assumptions = list(meta.get("assumptions", [])) if isinstance(meta.get("assumptions"), list) else []
    backend = meta.get("backend", {}) if isinstance(meta.get("backend"), dict) else {}
    units = meta.get("units", {}) if isinstance(meta.get("units"), dict) else {}
    summary_dict = summary if isinstance(summary, dict) else {}
    occlusion_enabled = summary_dict.get("occlusion_enabled")
    assumptions.extend(
        [
            f"TILT applied: {'yes' if has_tilt else 'no'}",
            "TILT application angle: gamma (vertical angle)",
            f"Units contract: {units or {'length': 'm', 'illuminance': 'lux'}}",
            f"Occlusion mode: {'enabled' if occlusion_enabled else 'disabled'}",
            "Supported photometric types: Type C only.",
            f"Backend version: {backend.get('name', 'cpu')}@{backend.get('version', 'unknown')}",
        ]
    )

    tables_json_path = result_dir / "tables.json"
    tables_payload: Dict[str, Any] = {}
    if tables_json_path.exists():
        try:
            tables_payload = json.loads(tables_json_path.read_text(encoding="utf-8"))
        except Exception:
            tables_payload = {}
    plot_refs = [p.name for p in [result_dir / "heatmap.png", result_dir / "isolux.png"] if p.exists()]

    daylight_section: Dict[str, Any] | None = None
    if isinstance(summary, dict) and str(summary.get("mode", "")).lower() in {"df", "radiance", "daylight_factor", "annual_proxy", "annual"}:
        entries: List[Dict[str, Any]] = []
        for obj in (per_grid if isinstance(per_grid, list) else []):
            if not isinstance(obj, dict):
                continue
            s = obj.get("summary", {})
            if not isinstance(s, dict):
                s = {}
            entries.append(
                {
                    "target_id": obj.get("id"),
                    "target_type": obj.get("type"),
                    "min_df_percent": s.get("min_df_percent"),
                    "mean_df_percent": s.get("mean_df_percent"),
                    "max_df_percent": s.get("max_df_percent"),
                    "min_lux": s.get("min_lux"),
                    "mean_lux": s.get("mean_lux"),
                    "max_lux": s.get("max_lux"),
                }
            )
        daylight_section = {
            "mode": summary.get("mode"),
            "sky": summary.get("sky"),
            "external_horizontal_illuminance_lux": summary.get("external_horizontal_illuminance_lux"),
            "radiance_quality": summary.get("radiance_quality"),
            "metric": summary.get("metric", "daylight_factor_percent"),
            "targets": entries,
            "assumptions": [
                f"Sky model: {summary.get('sky')}",
                "Aperture transmittance from opening metadata or DaylightSpec default.",
                f"Obstruction policy: {summary.get('obstruction_policy', 'engine_default')}",
            ],
        }

    emergency_section: Dict[str, Any] | None = None
    if isinstance(summary, dict) and (
        isinstance(summary.get("route_results"), list)
        or isinstance(summary.get("open_area_results"), list)
        or str(summary.get("mode", "")).lower().startswith("emergency")
    ):
        emergency_section = {
            "mode": summary.get("mode"),
            "standard": summary.get("standard"),
            "emergency_factor": summary.get("emergency_factor"),
            "route_table": summary.get("route_results", []),
            "open_area_table": summary.get("open_area_results", []),
            "compliance": summary.get("compliance", {}),
            "assumptions": [
                f"Emergency factor applied: {summary.get('emergency_factor')}",
                f"Luminaire subset count: {summary.get('luminaire_count')}",
            ],
        }

    roadway_section: Dict[str, Any] | None = None
    if isinstance(summary, dict) and (
        isinstance(summary.get("lane_metrics"), list)
        or str(summary.get("road_class", "")).strip()
        or isinstance(summary.get("observer_luminance_views"), list)
    ):
        compliance_obj = summary.get("compliance", {}) if isinstance(summary.get("compliance"), dict) else {}
        roadway_section = {
            "road_class": summary.get("road_class"),
            "overall": summary.get("overall", {}),
            "lane_metrics": summary.get("lane_metrics", []),
            "observer_luminance_views": summary.get("observer_luminance_views", []),
            "luminance_metrics": {
                "road_luminance_mean_cd_m2": summary.get("road_luminance_mean_cd_m2"),
                "observer_luminance_max_cd_m2": summary.get("observer_luminance_max_cd_m2"),
                "threshold_increment_ti_proxy_percent": summary.get("threshold_increment_ti_proxy_percent"),
                "surround_ratio_proxy": summary.get("surround_ratio_proxy"),
            },
            "compliance": compliance_obj,
            "thresholds": compliance_obj.get("thresholds", {}) if isinstance(compliance_obj, dict) else {},
            "assumptions": [
                f"Lane width (m): {summary.get('lane_width_m')}",
                f"Lane count: {summary.get('num_lanes')}",
                f"Road length (m): {summary.get('road_length_m')}",
                f"Road surface reflectance: {summary.get('road_surface_reflectance')}",
            ],
        }

    indoor_section: Dict[str, Any] | None = None
    if not roadway_section and not daylight_section and not emergency_section:
        indoor_section = {
            "tables": {
                "per_grid": per_grid if isinstance(per_grid, list) else [],
                "worst_case": worst,
            },
            "plots": plot_refs,
            "assumptions": assumptions,
            "compliance": {
                "raw": compliance if isinstance(compliance, dict) else {},
                "thresholds": thresholds if isinstance(thresholds, dict) else {},
                "reasons": pass_fail_reasons,
            },
        }

    return {
        "job_id": job_id,
        "job_hash": result_ref.job_hash,
        "result_dir": str(result_dir),
        "audit": {
            "solver": meta.get("solver", {}),
            "backend": meta.get("backend", {}),
            "settings": meta.get("job", {}),
            "asset_hashes": assets if isinstance(assets, dict) else {},
            "coordinate_convention": meta.get("coordinate_convention"),
            "units": meta.get("units", {}),
            "assumptions": assumptions,
            "unsupported_features": meta.get("unsupported_features", []),
        },
        "luminaire_schedule": luminaire_schedule,
        "per_grid_stats": per_grid if isinstance(per_grid, list) else [],
        "tables": tables_payload,
        "calc_tables": tables_payload,
        "plots": plot_refs,
        "worst_case_summary": worst,
        "compliance": {
            "raw": compliance if isinstance(compliance, dict) else {},
            "thresholds": thresholds if isinstance(thresholds, dict) else {},
            "reasons": pass_fail_reasons,
        },
        "indoor": indoor_section,
        "daylight": daylight_section,
        "emergency": emergency_section,
        "roadway": roadway_section,
    }


def build_structured_report_dict(project: Project, job_ref: JobResultRef) -> Dict[str, Any]:
    from luxera.export.en12464_report import build_en12464_report_model

    en12464 = build_en12464_report_model(project, job_ref)
    en13032 = build_en13032_report_model(project, job_ref)
    return {
        "project": {"name": project.name, "schema_version": project.schema_version},
        "job": {"job_id": job_ref.job_id, "job_hash": job_ref.job_hash, "result_dir": job_ref.result_dir},
        "inputs": en12464.inputs,
        "luminaire_schedule": en12464.luminaire_schedule,
        "per_grid_stats": en12464.per_grid_stats,
        "assumptions": en12464.assumptions,
        "audit": {
            "solver": en12464.audit.solver,
            "settings": en12464.audit.settings,
            "asset_hashes": en12464.audit.asset_hashes,
            "coordinate_convention": en12464.audit.coordinate_convention,
            "units": en12464.audit.units,
            "unsupported_features": en12464.audit.unsupported_features,
        },
        "compliance": {
            "en12464": en12464.compliance,
            "en13032": (en13032.compliance or {}).get("en13032"),
        },
    }
