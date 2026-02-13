from __future__ import annotations

from typing import Any, Dict, List

from luxera.project.schema import Project


def build_luminaire_schedule(project: Project, asset_hashes: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
    asset_hashes = dict(asset_hashes or {})
    by_asset = {a.id: a for a in project.photometry_assets}
    rows: Dict[tuple, Dict[str, Any]] = {}
    for lum in project.luminaires:
        key = (
            lum.photometry_asset_id,
            lum.mounting_height_m,
            lum.tilt_deg,
            lum.maintenance_factor,
            lum.flux_multiplier,
        )
        asset = by_asset.get(lum.photometry_asset_id)
        filename = (asset.path if asset is not None else None) or (asset.metadata.get("filename") if asset is not None and isinstance(asset.metadata, dict) else None)
        row = rows.setdefault(
            key,
            {
                "asset_id": lum.photometry_asset_id,
                "photometry_hash": asset_hashes.get(lum.photometry_asset_id),
                "manufacturer": (asset.metadata.get("manufacturer") if asset and isinstance(asset.metadata, dict) else None),
                "file_name": filename,
                "count": 0,
                "mounting_height_m": lum.mounting_height_m,
                "tilt_deg": lum.tilt_deg,
                "maintenance_factor": lum.maintenance_factor,
                "flux_multiplier": lum.flux_multiplier,
            },
        )
        row["count"] = int(row["count"]) + 1
    return list(rows.values())

