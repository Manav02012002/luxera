from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional


@dataclass(frozen=True)
class ComplianceEvaluation:
    domain: str
    status: str
    failed_checks: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)


def _pick_source(summary: Mapping[str, Any]) -> Dict[str, Any]:
    for key in ("compliance_profile", "compliance"):
        value = summary.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _first_numeric(source: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _metric_detail(source: Mapping[str, Any], metric_name: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    actual_keys = (
        metric_name,
        f"{metric_name}_value",
        f"{metric_name}_lux",
        f"{metric_name}_cd_m2",
        f"worst_{metric_name}",
        f"min_{metric_name}",
        f"avg_{metric_name}",
    )
    threshold_keys = (
        f"{metric_name}_target",
        f"target_{metric_name}",
        f"target_{metric_name}_lux",
        f"{metric_name}_target_lux",
        f"{metric_name}_target_cd_m2",
        f"target_{metric_name}_cd_m2",
        f"{metric_name}_min",
        f"{metric_name}_max",
        f"required_{metric_name}",
    )
    direction: Optional[str] = None
    for k in threshold_keys:
        if k.endswith("_min") or k.startswith("required_") or k.startswith("target_"):
            direction = ">="
            break
        if k.endswith("_max"):
            direction = "<="
            break
    return _first_numeric(source, actual_keys), _first_numeric(source, threshold_keys), direction


def _build_explanations(source: Mapping[str, Any], failed_checks: list[str]) -> list[str]:
    lines: list[str] = []
    for check in failed_checks:
        if check == "status":
            continue
        metric = check[:-3] if check.endswith("_ok") else check
        actual, threshold, direction = _metric_detail(source, metric)
        if actual is not None and threshold is not None:
            cmp = direction or "vs"
            lines.append(f"{check} failed: actual={actual:.3f}, threshold {cmp} {threshold:.3f}.")
        elif actual is not None:
            lines.append(f"{check} failed: actual={actual:.3f}, threshold missing.")
        elif threshold is not None:
            lines.append(f"{check} failed: threshold={threshold:.3f}, actual missing.")
        else:
            lines.append(f"{check} failed: actual/threshold values not available in summary.")
    if not lines and str(source.get("status", "")).upper() == "FAIL":
        lines.append("status failed: project marked FAIL but no metric-level fields were provided.")
    return lines


def _evaluate(summary: Mapping[str, Any], domain: str) -> ComplianceEvaluation:
    source = _pick_source(summary)
    failed: list[str] = []
    for key, value in source.items():
        if key.endswith("_ok") and value is False:
            failed.append(str(key))
    if str(source.get("status", "")).upper() == "FAIL":
        failed.append("status")
    failed = sorted(set(failed))
    status = "FAIL" if failed else "PASS"
    explanations = _build_explanations(source, failed)
    return ComplianceEvaluation(domain=domain, status=status, failed_checks=failed, explanations=explanations, source=dict(source))


def evaluate_indoor(result: Mapping[str, Any], profile: Mapping[str, Any] | None = None) -> ComplianceEvaluation:
    summary = dict(result)
    if profile:
        summary.setdefault("compliance_profile", dict(profile))
    return _evaluate(summary, domain="indoor")


def evaluate_roadway(result: Mapping[str, Any], profile: Mapping[str, Any] | None = None) -> ComplianceEvaluation:
    summary = dict(result)
    if profile:
        summary.setdefault("compliance", dict(profile))
    return _evaluate(summary, domain="roadway")


def evaluate_emergency(result: Mapping[str, Any], standard: str | None = None) -> ComplianceEvaluation:
    summary = dict(result)
    if standard and isinstance(summary.get("compliance"), Mapping):
        src = dict(summary["compliance"])
        src.setdefault("standard", standard)
        # Normalize common emergency pass/fail booleans into *_ok keys
        if "route_pass" in src and "route_min_lux_ok" not in src:
            src["route_min_lux_ok"] = bool(src.get("route_pass"))
        if "open_area_pass" in src and "open_area_min_lux_ok" not in src:
            src["open_area_min_lux_ok"] = bool(src.get("open_area_pass"))
        if "route_min_lux" in src and "route_min_lux_target" in src:
            src.setdefault("route_min_lux_value", src.get("route_min_lux"))
        if "open_area_min_lux" in src and "open_area_min_lux_target" in src:
            src.setdefault("open_area_min_lux_value", src.get("open_area_min_lux"))
        summary["compliance"] = src
    return _evaluate(summary, domain="emergency")
