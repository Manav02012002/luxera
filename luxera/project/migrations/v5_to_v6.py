from __future__ import annotations

from typing import Any, Dict


def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("schema_version", 5) != 5:
        return data

    data.setdefault("control_groups", [])
    data.setdefault("light_scenes", [])
    data["schema_version"] = 6
    return data

