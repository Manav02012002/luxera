from __future__ import annotations

import json
import math
import hashlib
from dataclasses import is_dataclass, asdict
from typing import Any, Dict


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize(obj: Any) -> Any:
    if is_dataclass(obj):
        return _normalize(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("NaN/Inf not allowed in stable JSON")
        return float(f"{obj:.12g}")
    return obj


def stable_json_dumps(obj: Any) -> str:
    normalized = _normalize(obj)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_job_spec(project: Any, job_spec: Any) -> str:
    project_dict = project.to_dict() if hasattr(project, "to_dict") else project
    if isinstance(project_dict, dict):
        project_dict = dict(project_dict)
        project_dict.pop("results", None)
        project_dict.pop("jobs", None)
        project_dict.pop("root_dir", None)
        project_dict.pop("agent_history", None)
    payload = {
        "schema_version": getattr(project, "schema_version", None),
        "project": project_dict,
        "job_spec": job_spec,
    }
    data = stable_json_dumps(payload).encode("utf-8")
    return sha256_bytes(data)
