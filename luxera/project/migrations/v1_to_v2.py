from __future__ import annotations

from typing import Dict, Any


def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("schema_version", 1) != 1:
        return data

    # In v2, rooms include activity_type; default None.
    geometry = data.get("geometry", {})
    rooms = geometry.get("rooms", [])
    for r in rooms:
        r.setdefault("activity_type", None)

    data["schema_version"] = 2
    data["geometry"] = geometry
    return data
