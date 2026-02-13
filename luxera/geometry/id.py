from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, float):
        # Keep float payload deterministic while avoiding noisy binary tails.
        return round(float(value), 12)
    return value


def _hash_payload(payload: Dict[str, Any]) -> str:
    norm = _normalize(payload)
    raw = json.dumps(norm, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def stable_id(prefix: str, payload: Dict[str, Any]) -> str:
    h = _hash_payload(dict(payload))
    return f"{prefix}:{h[:12]}"


def derived_id(parent_id: str, kind: str, params: Dict[str, Any]) -> str:
    return stable_id(f"{parent_id}:{kind}", {"parent_id": parent_id, "kind": kind, "params": dict(params)})

