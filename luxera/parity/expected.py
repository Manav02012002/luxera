from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import numpy as np

from luxera.parity.arrays import array_sha256, compare_arrays, load_csv_grid
from luxera.parity.tolerances import (
    array_thresholds,
    load_tolerance_file,
    resolve_profile,
    scalar_tolerance,
)


@dataclass(frozen=True)
class ParityMismatch:
    path: str
    reason: str
    expected: Any = None
    actual: Any = None
    abs_tol: float | None = None
    rel_tol: float | None = None


@dataclass(frozen=True)
class ParityComparison:
    passed: bool
    checked_metrics: int
    mismatches: List[ParityMismatch]


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _flatten(payload: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(payload, Mapping):
        for k in sorted(payload.keys(), key=lambda x: str(x)):
            sk = str(k)
            p = f"{prefix}.{sk}" if prefix else sk
            out.update(_flatten(payload[k], p))
        return out
    if isinstance(payload, list):
        for i, item in enumerate(payload):
            p = f"{prefix}[{i}]"
            out.update(_flatten(item, p))
        return out
    out[prefix] = payload
    return out


def _matches_pattern(path: str, pattern: str) -> bool:
    if path == pattern:
        return True
    if path.startswith(pattern + "."):
        return True
    if path.startswith(pattern + "["):
        return True
    return False


def _is_ignored(path: str, ignore: Iterable[str]) -> bool:
    for pattern in ignore:
        if _matches_pattern(path, pattern):
            return True
    return False


def validate_expected_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("expected payload must be an object")

    schema_version = payload.get("schema_version")
    if schema_version == "parity_expected_v1":
        return validate_expected_v1(payload)
    if schema_version == "parity_expected_v2":
        return validate_expected_v2(payload)
    raise ValueError("expected.schema_version must be 'parity_expected_v1' or 'parity_expected_v2'")


def validate_expected_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("expected payload must be an object")

    schema_version = payload.get("schema_version")
    if schema_version != "parity_expected_v1":
        raise ValueError("expected.schema_version must be 'parity_expected_v1'")

    tolerances = payload.get("tolerances")
    if not isinstance(tolerances, Mapping):
        raise ValueError("expected.tolerances must be an object")

    default_tol = tolerances.get("default")
    if not isinstance(default_tol, Mapping):
        raise ValueError("expected.tolerances.default must be an object")
    if "abs" not in default_tol or "rel" not in default_tol:
        raise ValueError("expected.tolerances.default must include abs and rel")

    default_abs = float(default_tol["abs"])
    default_rel = float(default_tol["rel"])
    if default_abs < 0.0 or default_rel < 0.0:
        raise ValueError("expected.tolerances.default abs/rel must be >= 0")

    metric_tols_raw = tolerances.get("metrics", {})
    if not isinstance(metric_tols_raw, Mapping):
        raise ValueError("expected.tolerances.metrics must be an object")
    metric_tols: Dict[str, Dict[str, float]] = {}
    for path, tol in metric_tols_raw.items():
        if not isinstance(path, str) or not path:
            raise ValueError("expected.tolerances.metrics keys must be non-empty strings")
        if not isinstance(tol, Mapping):
            raise ValueError(f"expected.tolerances.metrics['{path}'] must be an object")
        if "abs" not in tol or "rel" not in tol:
            raise ValueError(f"expected.tolerances.metrics['{path}'] must include abs and rel")
        abs_tol = float(tol["abs"])
        rel_tol = float(tol["rel"])
        if abs_tol < 0.0 or rel_tol < 0.0:
            raise ValueError(f"expected.tolerances.metrics['{path}'] abs/rel must be >= 0")
        metric_tols[path] = {"abs": abs_tol, "rel": rel_tol}

    ignore = payload.get("ignore", [])
    if not isinstance(ignore, list) or any(not isinstance(x, str) for x in ignore):
        raise ValueError("expected.ignore must be a list of strings")

    expected = payload.get("expected")
    if not isinstance(expected, Mapping):
        raise ValueError("expected.expected must be an object")

    return {
        "schema_version": "parity_expected_v1",
        "tolerances": {
            "default": {"abs": default_abs, "rel": default_rel},
            "metrics": metric_tols,
        },
        "ignore": list(ignore),
        "expected": expected,
    }


def validate_expected_v2(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("expected payload must be an object")

    schema_version = payload.get("schema_version")
    if schema_version != "parity_expected_v2":
        raise ValueError("expected.schema_version must be 'parity_expected_v2'")

    scene_id = payload.get("scene_id")
    if not isinstance(scene_id, str) or not scene_id.strip():
        raise ValueError("expected.scene_id must be a non-empty string")

    baseline = payload.get("baseline")
    if not isinstance(baseline, str) or not baseline.strip():
        raise ValueError("expected.baseline must be a non-empty string")

    baseline_version = payload.get("baseline_version")
    if not isinstance(baseline_version, str) or not baseline_version.strip():
        raise ValueError("expected.baseline_version must be a non-empty string")

    generated_by = payload.get("generated_by")
    if generated_by is not None and not isinstance(generated_by, Mapping):
        raise ValueError("expected.generated_by must be an object when present")

    results = payload.get("results")
    if not isinstance(results, Mapping):
        raise ValueError("expected.results must be an object")

    normalized_results: Dict[str, Any] = {}
    for metric_id, metric_payload in results.items():
        if not isinstance(metric_id, str) or not metric_id.strip():
            raise ValueError("expected.results keys must be non-empty strings")
        if _is_number(metric_payload):
            normalized_results[metric_id] = float(metric_payload)
            continue
        if not isinstance(metric_payload, Mapping):
            raise ValueError(
                f"expected.results['{metric_id}'] must be numeric or object map for array/grid metrics"
            )

        per_object: Dict[str, Any] = {}
        for object_id, object_payload in metric_payload.items():
            if not isinstance(object_id, str) or not object_id.strip():
                raise ValueError(f"expected.results['{metric_id}'] keys must be non-empty strings")
            if not isinstance(object_payload, Mapping):
                raise ValueError(
                    f"expected.results['{metric_id}']['{object_id}'] must be an object"
                )
            obj_norm = dict(object_payload)
            grid_obj = obj_norm.get("grid_values_lux")
            if grid_obj is not None:
                if not isinstance(grid_obj, Mapping):
                    raise ValueError(
                        f"expected.results['{metric_id}']['{object_id}'].grid_values_lux must be an object"
                    )
                shape = grid_obj.get("shape")
                if (
                    not isinstance(shape, list)
                    or len(shape) != 2
                    or any((not isinstance(x, int) or isinstance(x, bool) or x <= 0) for x in shape)
                ):
                    raise ValueError(
                        f"expected.results['{metric_id}']['{object_id}'].grid_values_lux.shape must be [H,W] positive ints"
                    )
                hsh = grid_obj.get("hash")
                if not isinstance(hsh, str) or not hsh.startswith("sha256:"):
                    raise ValueError(
                        f"expected.results['{metric_id}']['{object_id}'].grid_values_lux.hash must be sha256:<hex>"
                    )
                summary = grid_obj.get("summary")
                if summary is not None and not isinstance(summary, Mapping):
                    raise ValueError(
                        f"expected.results['{metric_id}']['{object_id}'].grid_values_lux.summary must be an object"
                    )
                sidecar = grid_obj.get("sidecar")
                if sidecar is not None and (not isinstance(sidecar, str) or not sidecar.strip()):
                    raise ValueError(
                        f"expected.results['{metric_id}']['{object_id}'].grid_values_lux.sidecar must be a non-empty string when present"
                    )
                obj_norm["grid_values_lux"] = {
                    "shape": [int(shape[0]), int(shape[1])],
                    "hash": hsh,
                    "summary": dict(summary) if isinstance(summary, Mapping) else {},
                    **({"sidecar": sidecar.strip()} if isinstance(sidecar, str) else {}),
                }
            per_object[object_id] = obj_norm
        normalized_results[metric_id] = per_object

    tags = payload.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(x, str) for x in tags):
        raise ValueError("expected.tags must be a list of strings")

    out: Dict[str, Any] = {
        "schema_version": "parity_expected_v2",
        "scene_id": scene_id.strip(),
        "baseline": baseline.strip(),
        "baseline_version": baseline_version.strip(),
        "results": normalized_results,
        "tags": list(tags),
    }
    if generated_by is not None:
        out["generated_by"] = dict(generated_by)
    return out


def load_expected_file(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_expected_payload(data)


def _resolve_tolerance(path: str, validated_expected: Mapping[str, Any]) -> tuple[float, float]:
    metrics = validated_expected["tolerances"]["metrics"]
    if path in metrics:
        return float(metrics[path]["abs"]), float(metrics[path]["rel"])
    d = validated_expected["tolerances"]["default"]
    return float(d["abs"]), float(d["rel"])


def compare_results_to_expected(results: Mapping[str, Any], validated_expected: Mapping[str, Any]) -> ParityComparison:
    expected_subset = validated_expected["expected"]
    ignore = list(validated_expected.get("ignore", []))

    expected_flat = _flatten(expected_subset)
    results_flat = _flatten(results)

    mismatches: List[ParityMismatch] = []
    checked = 0

    for path in sorted(expected_flat.keys()):
        if _is_ignored(path, ignore):
            continue
        checked += 1
        expected_value = expected_flat[path]
        if path not in results_flat:
            mismatches.append(
                ParityMismatch(path=path, reason="missing_in_results", expected=expected_value, actual=None)
            )
            continue
        actual_value = results_flat[path]

        if _is_number(expected_value) and _is_number(actual_value):
            exp = float(expected_value)
            act = float(actual_value)
            abs_tol, rel_tol = _resolve_tolerance(path, validated_expected)
            if math.isnan(exp) and math.isnan(act):
                continue
            if not math.isclose(exp, act, rel_tol=rel_tol, abs_tol=abs_tol):
                mismatches.append(
                    ParityMismatch(
                        path=path,
                        reason="numeric_mismatch",
                        expected=exp,
                        actual=act,
                        abs_tol=abs_tol,
                        rel_tol=rel_tol,
                    )
                )
            continue

        if expected_value != actual_value:
            mismatches.append(
                ParityMismatch(
                    path=path,
                    reason="value_mismatch",
                    expected=expected_value,
                    actual=actual_value,
                )
            )

    return ParityComparison(passed=not mismatches, checked_metrics=checked, mismatches=mismatches)


def _repo_tolerance_root() -> Path:
    return Path(__file__).resolve().parents[2] / "parity" / "tolerances"


def _metric_tolerance_filename(metric_id: str) -> str:
    metric = str(metric_id).strip().lower()
    if not metric:
        return "indoor_illuminance.yaml"
    if "ugr" in metric:
        return "ugr.yaml"
    if "illuminance" in metric or "lux" in metric:
        return "indoor_illuminance.yaml"
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in metric)
    return f"{safe}.yaml"


def _load_metric_profile(
    metric_id: str,
    tolerance_model: Mapping[str, Any] | None,
    scene_tags: Sequence[str] | None,
    tolerances_root: Path | None = None,
) -> Dict[str, Any]:
    tags = set(scene_tags or [])
    if isinstance(tolerance_model, Mapping) and tolerance_model:
        # Allow direct profile payload injection for tests/callers.
        if "profiles" in tolerance_model or "overrides" in tolerance_model:
            return resolve_profile(metric_id, dict(tolerance_model), tags)
        if "default" in tolerance_model and isinstance(tolerance_model["default"], Mapping):
            d = tolerance_model["default"]
            # Legacy v2 tolerance object: {"default":{"abs","rel"}, "metrics":{...}}
            if "abs" in d or "rel" in d:
                legacy_profile = {
                    "scalar": {
                        "abs": float(d.get("abs", 1e-6)),
                        "rel": float(d.get("rel", 1e-6)),
                        "near_zero_abs": float(d.get("near_zero_abs", d.get("abs", 1e-6))),
                        "metrics": dict(tolerance_model.get("metrics", {})) if isinstance(tolerance_model.get("metrics"), Mapping) else {},
                    },
                    "arrays": dict(tolerance_model.get("arrays", {})) if isinstance(tolerance_model.get("arrays"), Mapping) else {},
                }
                return legacy_profile
            return resolve_profile(metric_id, dict(tolerance_model), tags)
        if "scalar" in tolerance_model or "arrays" in tolerance_model:
            return dict(tolerance_model)
        # Backward-compatible direct tolerance object.
        return {
            "scalar": {
                "abs": float(tolerance_model.get("abs", 1e-6)),
                "rel": float(tolerance_model.get("rel", 1e-6)),
                "near_zero_abs": float(tolerance_model.get("near_zero_abs", tolerance_model.get("abs", 1e-6))),
            },
            "arrays": {
                "default": {
                    "max_abs": float(tolerance_model.get("max_abs", 1e-6)),
                    "rmse_abs": float(tolerance_model.get("rmse_abs", tolerance_model.get("rmse", 1e-6))),
                    "p95_abs": float(tolerance_model.get("p95_abs", 1e-6)),
                    "p99_abs": float(tolerance_model.get("p99_abs", 1e-6)),
                }
            },
        }

    root = Path(tolerances_root) if tolerances_root is not None else _repo_tolerance_root()
    filename = _metric_tolerance_filename(metric_id)
    path = root / filename
    if not path.exists():
        # deterministic fallback baseline profile
        return {
            "scalar": {"abs": 1e-6, "rel": 1e-6, "near_zero_abs": 1e-6},
            "arrays": {
                "default": {"max_abs": 1e-6, "rmse_abs": 1e-6, "p95_abs": 1e-6, "p99_abs": 1e-6}
            },
        }
    profiles = load_tolerance_file(path)
    return resolve_profile(metric_id, profiles, tags)


def _coerce_grid_array(value: Any) -> np.ndarray | None:
    if isinstance(value, np.ndarray):
        return np.asarray(value, dtype=float)
    if isinstance(value, list):
        return np.asarray(value, dtype=float)
    if isinstance(value, Mapping):
        for k in ("values", "array", "data"):
            if k in value:
                return _coerce_grid_array(value[k])
    return None


def _load_expected_grid_from_descriptor(desc: Mapping[str, Any], expected_root: Path | None) -> np.ndarray | None:
    if "values" in desc:
        return _coerce_grid_array(desc["values"])
    sidecar = desc.get("sidecar")
    if not isinstance(sidecar, str) or not sidecar.strip():
        return None
    if expected_root is None:
        return None
    sidecar_path = (expected_root / sidecar).resolve()
    try:
        return load_csv_grid(sidecar_path)
    except Exception:
        return None


def _compare_v2_results(
    actual: Mapping[str, Any],
    expected_v2: Mapping[str, Any],
    tolerance_model: Mapping[str, Any] | None,
    scene_tags: Sequence[str] | None,
    expected_root: Path | None = None,
    tolerances_root: Path | None = None,
) -> ParityComparison:
    expected_metrics = expected_v2["results"]
    actual_metrics = actual.get("results")
    if not isinstance(actual_metrics, Mapping):
        actual_metrics = actual

    mismatches: List[ParityMismatch] = []
    checked = 0

    for metric_id in sorted(expected_metrics.keys()):
        checked += 1
        expected_value = expected_metrics[metric_id]
        if metric_id not in actual_metrics:
            mismatches.append(
                ParityMismatch(path=metric_id, reason="missing_in_results", expected=expected_value, actual=None)
            )
            continue
        actual_value = actual_metrics[metric_id]
        if _is_number(expected_value):
            if not _is_number(actual_value):
                mismatches.append(
                    ParityMismatch(path=metric_id, reason="value_mismatch", expected=expected_value, actual=actual_value)
                )
                continue
            exp = float(expected_value)
            act = float(actual_value)
            profile = _load_metric_profile(metric_id, tolerance_model, scene_tags, tolerances_root=tolerances_root)
            scalar_tol = scalar_tolerance(profile, metric_id)
            abs_tol = float(scalar_tol["abs"])
            rel_tol = float(scalar_tol["rel"])
            near_zero_abs = float(scalar_tol.get("near_zero_abs", abs_tol))
            if abs(exp) <= near_zero_abs:
                abs_tol = max(abs_tol, near_zero_abs)
            if math.isnan(exp) and math.isnan(act):
                continue
            if not math.isclose(exp, act, rel_tol=rel_tol, abs_tol=abs_tol):
                mismatches.append(
                    ParityMismatch(
                        path=metric_id,
                        reason="numeric_mismatch",
                        expected=exp,
                        actual=act,
                        abs_tol=abs_tol,
                        rel_tol=rel_tol,
                    )
                )
            continue

        if not isinstance(expected_value, Mapping) or not isinstance(actual_value, Mapping):
            mismatches.append(
                ParityMismatch(path=metric_id, reason="value_mismatch", expected=expected_value, actual=actual_value)
            )
            continue

        for object_id in sorted(expected_value.keys()):
            checked += 1
            path = f"{metric_id}.{object_id}"
            exp_obj = expected_value[object_id]
            if object_id not in actual_value:
                mismatches.append(
                    ParityMismatch(path=path, reason="missing_in_results", expected=exp_obj, actual=None)
                )
                continue
            act_obj = actual_value[object_id]
            if not isinstance(exp_obj, Mapping) or not isinstance(act_obj, Mapping):
                mismatches.append(
                    ParityMismatch(path=path, reason="value_mismatch", expected=exp_obj, actual=act_obj)
                )
                continue

            exp_grid = exp_obj.get("grid_values_lux")
            act_grid = act_obj.get("grid_values_lux")
            if isinstance(exp_grid, Mapping):
                actual_arr = _coerce_grid_array(act_grid)
                expected_arr = _load_expected_grid_from_descriptor(exp_grid, expected_root)
                if actual_arr is None:
                    mismatches.append(
                        ParityMismatch(
                            path=f"{path}.grid_values_lux",
                            reason="missing_in_results",
                            expected="numeric array",
                            actual=act_grid,
                        )
                    )
                    continue
                if expected_arr is None:
                    mismatches.append(
                        ParityMismatch(
                            path=f"{path}.grid_values_lux",
                            reason="missing_expected_sidecar",
                            expected=exp_grid,
                            actual=None,
                        )
                    )
                    continue

                expected_hash = str(exp_grid.get("hash", ""))
                expected_hash_actual = array_sha256(expected_arr)
                if expected_hash and expected_hash != expected_hash_actual:
                    mismatches.append(
                        ParityMismatch(
                            path=f"{path}.grid_values_lux.hash",
                            reason="value_mismatch",
                            expected=expected_hash,
                            actual=expected_hash_actual,
                        )
                    )
                    continue

                profile = _load_metric_profile(metric_id, tolerance_model, scene_tags, tolerances_root=tolerances_root)
                arr_tol = array_thresholds(profile, f"{metric_id}.{object_id}.grid_values_lux")
                thresholds = {
                    "max_abs": float(arr_tol.get("max_abs", 1e-6)),
                    "rmse": float(arr_tol.get("rmse_abs", 1e-6)),
                    "p95_abs": float(arr_tol.get("p95_abs", 1e-6)),
                    "p99_abs": float(arr_tol.get("p99_abs", 1e-6)),
                }
                ok, stats, failures = compare_arrays(actual_arr, expected_arr, thresholds)
                if not ok:
                    mismatches.append(
                        ParityMismatch(
                            path=f"{path}.grid_values_lux",
                            reason="array_mismatch",
                            expected=exp_grid.get("summary", {}),
                            actual={"stats": stats, "failures": failures},
                        )
                    )
                continue

            if exp_obj != act_obj:
                mismatches.append(
                    ParityMismatch(path=path, reason="value_mismatch", expected=exp_obj, actual=act_obj)
                )

    return ParityComparison(passed=not mismatches, checked_metrics=checked, mismatches=mismatches)


def compare_expected(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    tolerance_model: Mapping[str, Any] | None = None,
    scene_tags: Sequence[str] | None = None,
    expected_root: Path | None = None,
    tolerances_root: Path | None = None,
) -> ParityComparison:
    validated = validate_expected_payload(expected)
    schema_version = validated["schema_version"]
    if schema_version == "parity_expected_v1":
        return compare_results_to_expected(actual, validated)
    return _compare_v2_results(
        actual,
        validated,
        tolerance_model=tolerance_model,
        scene_tags=scene_tags if scene_tags is not None else validated.get("tags", []),
        expected_root=expected_root,
        tolerances_root=tolerances_root,
    )
