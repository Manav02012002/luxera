from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import json


def load_audit_metadata(result_dir: str | Path) -> Dict[str, Any]:
    p = Path(result_dir).expanduser().resolve() / "result.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {
        "solver": data.get("solver", {}),
        "backend": data.get("backend", {}),
        "units": data.get("units", {}),
        "coordinate_convention": data.get("coordinate_convention"),
        "assumptions": data.get("assumptions", []),
        "unsupported_features": data.get("unsupported_features", []),
        "seed": data.get("seed"),
        "job_hash": data.get("job_hash"),
        "job_id": data.get("job_id"),
    }

