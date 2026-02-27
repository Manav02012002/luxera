from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _parse_scalar(raw: str) -> Any:
    v = raw.strip()
    if not v:
        return ""
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        return v[1:-1]
    if v.startswith("'") and v.endswith("'") and len(v) >= 2:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [str(_parse_scalar(tok.strip())) for tok in inner.split(",")]
    if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
        return int(v)
    try:
        return float(v)
    except ValueError:
        return v


def _load_yaml_fallback(text: str) -> Dict[str, Any]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    out: Dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("default:"):
            default: Dict[str, Any] = {}
            i += 1
            while i < len(lines) and lines[i].startswith("  ") and not lines[i].startswith("  - "):
                k, v = lines[i].strip().split(":", 1)
                default[k.strip()] = _parse_scalar(v)
                i += 1
            out["default"] = default
            i -= 1
        elif line.startswith("profiles:"):
            profiles: List[Dict[str, Any]] = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                item: Dict[str, Any] = {}
                first = lines[i][4:]
                if ":" in first:
                    k, v = first.split(":", 1)
                    item[k.strip()] = _parse_scalar(v)
                i += 1
                while i < len(lines) and lines[i].startswith("    "):
                    inner = lines[i].strip()
                    if inner.endswith(":"):
                        key = inner[:-1]
                        block: Dict[str, Any] = {}
                        i += 1
                        while i < len(lines) and lines[i].startswith("      "):
                            bk, bv = lines[i].strip().split(":", 1)
                            block[bk.strip()] = _parse_scalar(bv)
                            i += 1
                        item[key] = block
                        continue
                    k, v = inner.split(":", 1)
                    item[k.strip()] = _parse_scalar(v)
                    i += 1
                profiles.append(item)
            out["profiles"] = profiles
            i -= 1
        else:
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = _parse_scalar(v)
        i += 1
    return out


def load_tolerance_file(path: Path) -> dict:
    p = Path(path)
    text = p.read_text(encoding="utf-8")

    # JSON is valid YAML 1.2; keep deterministic fallback behavior even without PyYAML.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    data = _load_yaml_fallback(text)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid tolerance file at {p}: expected mapping")
    return data


def _matches_tags(rule: Mapping[str, Any], scene_tags: Set[str]) -> bool:
    any_tags: Set[str] = set()
    all_tags: Set[str] = set()

    if "when_tags_any" in rule:
        raw = rule.get("when_tags_any")
        if isinstance(raw, list):
            any_tags = {str(x) for x in raw}
    if "when_tags_all" in rule:
        raw = rule.get("when_tags_all")
        if isinstance(raw, list):
            all_tags = {str(x) for x in raw}
    if not any_tags and not all_tags and "when_tags" in rule:
        raw = rule.get("when_tags")
        if isinstance(raw, list):
            any_tags = {str(x) for x in raw}

    if any_tags and not (scene_tags & any_tags):
        return False
    if all_tags and not all_tags.issubset(scene_tags):
        return False
    return True


def _iter_profile_entries(profiles: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in ("profiles", "overrides"):
        raw = profiles.get(key)
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, Mapping):
                    yield entry


def resolve_profile(metric: str, profiles: dict, scene_tags: set[str]) -> dict:
    default = profiles.get("default", {})
    if not isinstance(default, Mapping):
        default = {}

    merged: Dict[str, Any] = dict(default)
    metric_norm = str(metric)

    for entry in _iter_profile_entries(profiles):
        metric_filter = entry.get("metric")
        if isinstance(metric_filter, str) and metric_filter and metric_filter != metric_norm:
            continue
        if not _matches_tags(entry, scene_tags):
            continue

        overlay = {
            k: v
            for k, v in entry.items()
            if k
            not in {
                "name",
                "id",
                "metric",
                "when_tags",
                "when_tags_any",
                "when_tags_all",
            }
        }
        merged = _deep_merge(merged, overlay)

    return merged


def _lookup_metric_override(overrides: Mapping[str, Any], metric_path: str) -> Mapping[str, Any] | None:
    if metric_path in overrides and isinstance(overrides[metric_path], Mapping):
        return overrides[metric_path]
    # prefix fallback for nested metric paths
    best: Mapping[str, Any] | None = None
    best_len = -1
    for key, val in overrides.items():
        if not isinstance(key, str) or not isinstance(val, Mapping):
            continue
        if metric_path == key or metric_path.startswith(key + "."):
            if len(key) > best_len:
                best = val
                best_len = len(key)
    return best


def scalar_tolerance(profile: Mapping[str, Any], metric_path: str) -> dict:
    scalar = profile.get("scalar", {}) if isinstance(profile.get("scalar"), Mapping) else {}
    if not scalar and any(k in profile for k in ("abs", "rel", "near_zero_abs", "metrics")):
        scalar = {
            "abs": profile.get("abs", 1e-6),
            "rel": profile.get("rel", 1e-6),
            "near_zero_abs": profile.get("near_zero_abs", profile.get("abs", 1e-6)),
            "metrics": profile.get("metrics", {}),
        }
    metrics = scalar.get("metrics", {}) if isinstance(scalar.get("metrics"), Mapping) else {}

    abs_tol = float(scalar.get("abs", 1e-6))
    rel_tol = float(scalar.get("rel", 1e-6))
    near_zero_abs = float(scalar.get("near_zero_abs", abs_tol))

    metric_override = _lookup_metric_override(metrics, metric_path)
    if metric_override is not None:
        abs_tol = float(metric_override.get("abs", abs_tol))
        rel_tol = float(metric_override.get("rel", rel_tol))
        near_zero_abs = float(metric_override.get("near_zero_abs", near_zero_abs))

    return {
        "abs": abs_tol,
        "rel": rel_tol,
        "near_zero_abs": near_zero_abs,
    }


def array_thresholds(profile: Mapping[str, Any], array_id: str) -> dict:
    arrays = profile.get("arrays", {}) if isinstance(profile.get("arrays"), Mapping) else {}
    defaults = arrays.get("default", {}) if isinstance(arrays.get("default"), Mapping) else {}
    by_id = arrays.get("by_id", {}) if isinstance(arrays.get("by_id"), Mapping) else {}

    out = {
        "max_abs": float(defaults.get("max_abs", 1e-6)),
        "rmse_abs": float(defaults.get("rmse_abs", defaults.get("rmse", 1e-6))),
        "p95_abs": float(defaults.get("p95_abs", 1e-6)),
        "p99_abs": float(defaults.get("p99_abs", 1e-6)),
    }

    metric_override = _lookup_metric_override(by_id, array_id)
    if metric_override is not None:
        for key in ("max_abs", "rmse_abs", "p95_abs", "p99_abs"):
            if key in metric_override:
                out[key] = float(metric_override[key])
        if "rmse" in metric_override:
            out["rmse_abs"] = float(metric_override["rmse"])

    return out
