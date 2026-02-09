from __future__ import annotations

from typing import Dict, Any


def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("schema_version", 3) != 3:
        return data

    data.setdefault("agent_history", [])
    data["schema_version"] = 4
    return data
