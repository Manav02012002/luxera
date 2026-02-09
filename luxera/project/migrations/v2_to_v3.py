from __future__ import annotations

from typing import Dict, Any


def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("schema_version", 2) != 2:
        return data

    data.setdefault("material_library", [])
    data.setdefault("luminaire_families", [])
    data.setdefault("asset_bundle_path", None)

    # Add family_id to luminaires if missing
    for lum in data.get("luminaires", []):
        lum.setdefault("family_id", None)

    data["schema_version"] = 3
    return data
