from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    author: str
    description: str
    plugin_type: str
    entry_point: str
    dependencies: List[str] = field(default_factory=list)
    min_luxera_version: str = "0.3.0"

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "PluginManifest":
        required = ["name", "version", "author", "description", "plugin_type", "entry_point"]
        missing = [k for k in required if not payload.get(k)]
        if missing:
            raise ValueError(f"Manifest missing required fields: {', '.join(missing)}")
        deps = payload.get("dependencies", [])
        if deps is None:
            deps = []
        if not isinstance(deps, list):
            raise ValueError("dependencies must be a list")

        return PluginManifest(
            name=str(payload["name"]),
            version=str(payload["version"]),
            author=str(payload["author"]),
            description=str(payload["description"]),
            plugin_type=str(payload["plugin_type"]),
            entry_point=str(payload["entry_point"]),
            dependencies=[str(x) for x in deps],
            min_luxera_version=str(payload.get("min_luxera_version", "0.3.0")),
        )

    @staticmethod
    def from_json_file(path: Path) -> "PluginManifest":
        p = Path(path).expanduser().resolve()
        payload = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Manifest JSON must be an object")
        return PluginManifest.from_dict(payload)
