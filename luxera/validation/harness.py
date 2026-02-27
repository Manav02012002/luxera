from __future__ import annotations

import csv
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

from luxera.project.io import load_project_schema
from luxera.runner import run_job


CASE_SCHEMA_VERSION = "validation_case_v1"
RUN_SCHEMA_VERSION = "validation_run_v1"
SUMMARY_SCHEMA_VERSION = "validation_summary_v1"


@dataclass(frozen=True)
class ValidationCaseRef:
    suite: str
    case_id: str
    case_dir: Path


@dataclass(frozen=True)
class MetricResult:
    kind: str
    metric_id: str
    passed: bool
    skipped: bool
    details: Dict[str, Any]


@dataclass(frozen=True)
class CaseRunResult:
    suite: str
    case_id: str
    passed: bool
    metrics: List[MetricResult]
    output_dir: Path
    comparison_path: Path


def _stable_float(v: float) -> float:
    return float(f"{float(v):.12g}")


def _list_dir(path: Path) -> List[Path]:
    return sorted([p for p in path.iterdir() if p.is_dir()], key=lambda p: p.name)


def discover_cases(root: Path | None = None) -> Dict[str, List[ValidationCaseRef]]:
    base = (root or Path("tests/validation")).expanduser().resolve()
    suites: Dict[str, List[ValidationCaseRef]] = {}
    if not base.exists():
        return suites

    for suite_dir in _list_dir(base):
        suite = suite_dir.name
        if suite.startswith("__") or suite == "scenes":
            continue
        cases: List[ValidationCaseRef] = []
        for case_dir in _list_dir(suite_dir):
            if (case_dir / "scene.lux.json").exists() and (case_dir / "expected.json").exists():
                cases.append(ValidationCaseRef(suite=suite, case_id=case_dir.name, case_dir=case_dir))
        if cases:
            suites[suite] = sorted(cases, key=lambda c: c.case_id)
    return dict(sorted(suites.items(), key=lambda kv: kv[0]))


def parse_target(target: str, suites: Mapping[str, Sequence[ValidationCaseRef]]) -> List[ValidationCaseRef]:
    if "/" in target:
        suite, case_id = target.split("/", 1)
        cases = list(suites.get(suite, []))
        selected = [c for c in cases if c.case_id == case_id]
        if not selected:
            raise ValueError(f"Validation case not found: {target}")
        return selected

    cases = list(suites.get(target, []))
    if not cases:
        raise ValueError(f"Validation suite not found: {target}")
    return cases


def _validate_case_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if payload.get("schema_version") != CASE_SCHEMA_VERSION:
        raise ValueError(f"expected.schema_version must be '{CASE_SCHEMA_VERSION}'")

    run = payload.get("run", {})
    if run is None:
        run = {}
    if not isinstance(run, Mapping):
        raise ValueError("expected.run must be an object")
    jobs = run.get("jobs", [])
    if jobs is None:
        jobs = []
    if not isinstance(jobs, list) or any(not isinstance(j, str) for j in jobs):
        raise ValueError("expected.run.jobs must be a list of strings")

    skip_payload = payload.get("skip", {})
    if skip_payload is None:
        skip_payload = {}
    if not isinstance(skip_payload, Mapping):
        raise ValueError("expected.skip must be an object")
    skip_scalars = skip_payload.get("scalars", {})
    if skip_scalars is None:
        skip_scalars = {}
    if not isinstance(skip_scalars, Mapping):
        raise ValueError("expected.skip.scalars must be an object")
    skip_grids = skip_payload.get("grids", {})
    if skip_grids is None:
        skip_grids = {}
    if not isinstance(skip_grids, Mapping):
        raise ValueError("expected.skip.grids must be an object")
    for name, obj in (("scalars", skip_scalars), ("grids", skip_grids)):
        for key, val in obj.items():
            if not isinstance(val, Mapping) or not str(val.get("reason", "")).strip():
                raise ValueError(f"expected.skip.{name}.{key}.reason is required")

    scalars = payload.get("scalars", [])
    if not isinstance(scalars, list):
        raise ValueError("expected.scalars must be a list")
    for i, row in enumerate(scalars):
        if not isinstance(row, Mapping):
            raise ValueError(f"expected.scalars[{i}] must be an object")
        if "id" not in row:
            raise ValueError(f"expected.scalars[{i}] missing key: id")
        metric_id = str(row.get("id", "")).strip()
        top_skip = skip_scalars.get(metric_id)
        if "skip" in row or top_skip is not None:
            skip = row.get("skip", top_skip)
            if top_skip is not None and "skip" not in row:
                skip = top_skip
            if not isinstance(skip, Mapping) or not str(skip.get("reason", "")).strip():
                raise ValueError(f"expected.scalars[{i}] skip.reason is required when skip is present")
        else:
            for key in ("job_id", "path", "expected", "tolerance"):
                if key not in row:
                    raise ValueError(f"expected.scalars[{i}] missing key: {key}")
            tol = row["tolerance"]
            if not isinstance(tol, Mapping) or "abs" not in tol or "rel" not in tol:
                raise ValueError(f"expected.scalars[{i}].tolerance must contain abs and rel")

    grids = payload.get("grids", [])
    if not isinstance(grids, list):
        raise ValueError("expected.grids must be a list")
    for i, row in enumerate(grids):
        if not isinstance(row, Mapping):
            raise ValueError(f"expected.grids[{i}] must be an object")
        if "id" not in row:
            raise ValueError(f"expected.grids[{i}] missing key: id")
        metric_id = str(row.get("id", "")).strip()
        top_skip = skip_grids.get(metric_id)
        if "skip" in row or top_skip is not None:
            skip = row.get("skip", top_skip)
            if top_skip is not None and "skip" not in row:
                skip = top_skip
            if not isinstance(skip, Mapping) or not str(skip.get("reason", "")).strip():
                raise ValueError(f"expected.grids[{i}] skip.reason is required when skip is present")
        else:
            for key in ("job_id", "actual", "reference", "tolerance"):
                if key not in row:
                    raise ValueError(f"expected.grids[{i}] missing key: {key}")
            tol = row["tolerance"]
            if not isinstance(tol, Mapping):
                raise ValueError(f"expected.grids[{i}].tolerance must be an object")

    return {
        "schema_version": CASE_SCHEMA_VERSION,
        "run": {"jobs": [str(j) for j in jobs]},
        "reference_source": payload.get("reference_source", {}),
        "skip": {
            "scalars": {str(k): dict(v) for k, v in skip_scalars.items()},
            "grids": {str(k): dict(v) for k, v in skip_grids.items()},
        },
        "scalars": scalars,
        "grids": grids,
        "notes": str(payload.get("notes", "")),
    }


def _json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _value_at_path(payload: Mapping[str, Any], path: str) -> Any:
    cur: Any = payload
    for token in path.split("."):
        if not token:
            continue
        if not isinstance(cur, Mapping) or token not in cur:
            raise KeyError(path)
        cur = cur[token]
    return cur


def _read_series(path: Path) -> np.ndarray:
    ext = path.suffix.lower()
    if ext == ".npy":
        return np.asarray(np.load(path), dtype=float).reshape(-1)

    if ext != ".csv":
        raise ValueError(f"Unsupported grid format: {path}")

    values: List[float] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        first = True
        for row in reader:
            if not row:
                continue
            if first:
                first = False
                try:
                    float(row[-1])
                except ValueError:
                    continue
            try:
                values.append(float(row[-1]))
            except ValueError:
                continue
    return np.asarray(values, dtype=float).reshape(-1)


def _scalar_metric(row: Mapping[str, Any], by_job_summary: Mapping[str, Mapping[str, Any]]) -> MetricResult:
    metric_id = str(row["id"])
    if "skip" in row:
        reason = str((row.get("skip") or {}).get("reason", "")).strip() or "unspecified"
        return MetricResult(
            kind="scalar",
            metric_id=metric_id,
            passed=True,
            skipped=True,
            details={"reason": reason, "notes": str(row.get("notes", ""))},
        )

    job_id = str(row["job_id"])
    path = str(row["path"])
    expected_value = float(row["expected"])
    tol = row["tolerance"]
    abs_tol = float(tol.get("abs", 0.0))
    rel_tol = float(tol.get("rel", 0.0))

    summary = by_job_summary.get(job_id)
    if summary is None:
        return MetricResult(
            kind="scalar",
            metric_id=metric_id,
            passed=False,
            skipped=False,
            details={"reason": "missing_job", "job_id": job_id},
        )

    try:
        actual_value = float(_value_at_path(summary, path))
    except Exception:
        return MetricResult(
            kind="scalar",
            metric_id=metric_id,
            passed=False,
            skipped=False,
            details={"reason": "missing_path", "job_id": job_id, "path": path},
        )

    abs_error = abs(actual_value - expected_value)
    rel_error = abs_error / max(abs(expected_value), 1e-12)
    rel_error_pct = rel_error * 100.0
    passed = math.isclose(actual_value, expected_value, rel_tol=rel_tol, abs_tol=abs_tol)

    return MetricResult(
        kind="scalar",
        metric_id=metric_id,
        passed=passed,
        skipped=False,
        details={
            "job_id": job_id,
            "path": path,
            "expected": _stable_float(expected_value),
            "actual": _stable_float(actual_value),
            "abs_error": _stable_float(abs_error),
            "rel_error_pct": _stable_float(rel_error_pct),
            "abs_tol": _stable_float(abs_tol),
            "rel_tol": _stable_float(rel_tol),
            "notes": str(row.get("notes", "")),
            "reference_source": row.get("reference_source"),
        },
    )


def _grid_metric(row: Mapping[str, Any], result_dirs: Mapping[str, Path], case_dir: Path) -> MetricResult:
    metric_id = str(row["id"])
    if "skip" in row:
        reason = str((row.get("skip") or {}).get("reason", "")).strip() or "unspecified"
        return MetricResult(
            kind="grid",
            metric_id=metric_id,
            passed=True,
            skipped=True,
            details={"reason": reason, "notes": str(row.get("notes", ""))},
        )

    job_id = str(row["job_id"])
    actual_rel = str(row["actual"])
    reference_rel = str(row["reference"])
    tol = row["tolerance"]

    result_dir = result_dirs.get(job_id)
    if result_dir is None:
        return MetricResult(
            kind="grid",
            metric_id=metric_id,
            passed=False,
            skipped=False,
            details={"reason": "missing_job", "job_id": job_id},
        )

    actual_path = (result_dir / actual_rel).resolve()
    reference_path = (case_dir / reference_rel).resolve()
    if not actual_path.exists():
        return MetricResult(
            kind="grid",
            metric_id=metric_id,
            passed=False,
            skipped=False,
            details={"reason": "missing_actual", "path": str(actual_path)},
        )
    if not reference_path.exists():
        return MetricResult(
            kind="grid",
            metric_id=metric_id,
            passed=False,
            skipped=False,
            details={"reason": "missing_reference", "path": str(reference_path)},
        )

    actual = _read_series(actual_path)
    reference = _read_series(reference_path)
    if actual.shape != reference.shape:
        return MetricResult(
            kind="grid",
            metric_id=metric_id,
            passed=False,
            skipped=False,
            details={
                "reason": "shape_mismatch",
                "actual_count": int(actual.shape[0]),
                "reference_count": int(reference.shape[0]),
            },
        )

    diff = np.abs(actual - reference)
    rel = diff / np.maximum(np.abs(reference), 1e-12)

    max_abs = float(np.max(diff)) if diff.size else 0.0
    mean_abs = float(np.mean(diff)) if diff.size else 0.0
    p95_abs = float(np.percentile(diff, 95.0)) if diff.size else 0.0
    max_rel_pct = float(np.max(rel) * 100.0) if rel.size else 0.0
    mean_rel_pct = float(np.mean(rel) * 100.0) if rel.size else 0.0

    lim_max_abs = float(tol.get("max_abs", float("inf")))
    lim_mean_abs = float(tol.get("mean_abs", float("inf")))
    lim_p95_abs = float(tol.get("p95_abs", float("inf")))

    passed = max_abs <= lim_max_abs and mean_abs <= lim_mean_abs and p95_abs <= lim_p95_abs

    return MetricResult(
        kind="grid",
        metric_id=metric_id,
        passed=passed,
        skipped=False,
        details={
            "job_id": job_id,
            "actual": str(actual_path),
            "reference": str(reference_path),
            "count": int(diff.size),
            "max_abs": _stable_float(max_abs),
            "mean_abs": _stable_float(mean_abs),
            "p95_abs": _stable_float(p95_abs),
            "max_rel_pct": _stable_float(max_rel_pct),
            "mean_rel_pct": _stable_float(mean_rel_pct),
            "tol": {
                "max_abs": _stable_float(lim_max_abs),
                "mean_abs": _stable_float(lim_mean_abs),
                "p95_abs": _stable_float(lim_p95_abs),
            },
            "notes": str(row.get("notes", "")),
            "reference_source": row.get("reference_source"),
        },
    )


def _apply_top_level_skips(
    rows: Sequence[Mapping[str, Any]],
    skip_map: Mapping[str, Mapping[str, Any]],
) -> List[Mapping[str, Any]]:
    out: List[Mapping[str, Any]] = []
    for row in rows:
        metric_id = str(row.get("id", "")).strip()
        top_skip = skip_map.get(metric_id)
        if top_skip and "skip" not in row:
            merged = dict(row)
            merged["skip"] = dict(top_skip)
            out.append(merged)
            continue
        out.append(row)
    return out


def run_case(case: ValidationCaseRef, out_root: Path) -> CaseRunResult:
    case_out = (out_root / case.suite / case.case_id).resolve()
    case_out.mkdir(parents=True, exist_ok=True)

    work_dir = case_out / "_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(case.case_dir, work_dir, dirs_exist_ok=False)

    expected = _validate_case_payload(_json(work_dir / "expected.json"))
    scene_path = work_dir / "scene.lux.json"
    project = load_project_schema(scene_path)

    jobs = list(expected["run"]["jobs"])
    if not jobs:
        jobs = [j.id for j in project.jobs]
    if not jobs:
        raise ValueError(f"Case has no runnable jobs: {case.suite}/{case.case_id}")

    by_job_summary: Dict[str, Mapping[str, Any]] = {}
    result_dirs: Dict[str, Path] = {}
    for job_id in sorted(jobs):
        ref = run_job(scene_path, job_id)
        by_job_summary[job_id] = dict(ref.summary)
        result_dirs[job_id] = Path(ref.result_dir).resolve()

    scalar_rows = _apply_top_level_skips(expected["scalars"], expected.get("skip", {}).get("scalars", {}))
    grid_rows = _apply_top_level_skips(expected["grids"], expected.get("skip", {}).get("grids", {}))

    metrics: List[MetricResult] = []
    for row in scalar_rows:
        metrics.append(_scalar_metric(row, by_job_summary))
    for row in grid_rows:
        metrics.append(_grid_metric(row, result_dirs, work_dir))

    metrics_sorted = sorted(metrics, key=lambda m: (m.kind, m.metric_id))
    passed = all(m.passed for m in metrics_sorted)

    comparison_payload = {
        "schema_version": RUN_SCHEMA_VERSION,
        "suite": case.suite,
        "case_id": case.case_id,
        "passed": passed,
        "reference_source": expected.get("reference_source", {}),
        "jobs": sorted(jobs),
        "metrics": [
            {
                "kind": m.kind,
                "id": m.metric_id,
                "passed": m.passed,
                "skipped": m.skipped,
                "details": m.details,
            }
            for m in metrics_sorted
        ],
    }
    comparison_path = case_out / "comparison.json"
    comparison_path.write_text(json.dumps(comparison_payload, indent=2, sort_keys=True), encoding="utf-8")

    run_payload = {
        "schema_version": RUN_SCHEMA_VERSION,
        "suite": case.suite,
        "case_id": case.case_id,
        "jobs": {
            jid: {
                "summary": by_job_summary[jid],
                "result_dir": str(result_dirs[jid]),
            }
            for jid in sorted(by_job_summary.keys())
        },
    }
    (case_out / "run_results.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True), encoding="utf-8")

    return CaseRunResult(
        suite=case.suite,
        case_id=case.case_id,
        passed=passed,
        metrics=metrics_sorted,
        output_dir=case_out,
        comparison_path=comparison_path,
    )


def run_cases(cases: Sequence[ValidationCaseRef], out_root: Path) -> List[CaseRunResult]:
    return [run_case(case, out_root) for case in sorted(cases, key=lambda c: (c.suite, c.case_id))]


def _fmt(v: float) -> str:
    return f"{float(v):.6g}"


def _metric_expected_actual(m: MetricResult) -> Tuple[str, str, str, str]:
    d = m.details
    if m.skipped:
        return "-", "-", "-", "-"
    if m.kind == "scalar":
        exp = d.get("expected")
        act = d.get("actual")
        abs_err = d.get("abs_error")
        rel_pct = d.get("rel_error_pct")
        return (
            _fmt(exp) if isinstance(exp, (int, float)) else "-",
            _fmt(act) if isinstance(act, (int, float)) else "-",
            _fmt(abs_err) if isinstance(abs_err, (int, float)) else "-",
            _fmt(rel_pct) if isinstance(rel_pct, (int, float)) else "-",
        )
    exp = str(d.get("reference", "-"))
    act = str(d.get("actual", "-"))
    abs_err = d.get("mean_abs")
    rel_pct = d.get("mean_rel_pct")
    return (
        exp,
        act,
        _fmt(abs_err) if isinstance(abs_err, (int, float)) else "-",
        _fmt(rel_pct) if isinstance(rel_pct, (int, float)) else "-",
    )


def write_suite_report(suite: str, case_results: Sequence[CaseRunResult], out_root: Path) -> Tuple[Path, Path]:
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for cr in sorted(case_results, key=lambda c: c.case_id):
        for m in cr.metrics:
            d = m.details
            row = {
                "suite": cr.suite,
                "case_id": cr.case_id,
                "metric_kind": m.kind,
                "metric_id": m.metric_id,
                "passed": m.passed,
                "skipped": m.skipped,
                "expected": m.details.get("expected", m.details.get("reference")),
                "actual": m.details.get("actual"),
                "abs_error": d.get("abs_error", d.get("mean_abs")),
                "rel_error_pct": d.get("rel_error_pct", d.get("mean_rel_pct")),
                "max_abs": d.get("max_abs"),
                "p95_abs": d.get("p95_abs"),
                "skip_reason": d.get("reason", "") if m.skipped else "",
                "notes": d.get("notes", ""),
            }
            rows.append(row)

    payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "suite": suite,
        "passed": all(c.passed for c in case_results),
        "case_count": len(case_results),
        "cases": [
            {
                "case_id": c.case_id,
                "passed": c.passed,
                "metrics": [
                    {
                        "kind": m.kind,
                        "id": m.metric_id,
                        "passed": m.passed,
                        "skipped": m.skipped,
                        "details": m.details,
                    }
                    for m in c.metrics
                ],
            }
            for c in sorted(case_results, key=lambda x: x.case_id)
        ],
        "rows": rows,
    }

    json_path = out_root / f"{suite}_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    legacy_json_path = out_root / f"validation_{suite}_summary.json"
    legacy_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    md_path = out_root / f"{suite}_summary.md"
    lines: List[str] = []
    lines.append(f"# Validation Summary: {suite}")
    lines.append("")
    lines.append(f"- Cases: {len(case_results)}")
    lines.append(f"- Overall: {'PASS' if payload['passed'] else 'FAIL'}")
    lines.append("")
    for case in sorted(case_results, key=lambda x: x.case_id):
        lines.append(f"## Case: {case.case_id}")
        lines.append("")
        lines.append("| Metric | Expected | Actual | Abs Error | % Error | Status |")
        lines.append("|---|---|---|---:|---:|---:|")
        for m in sorted(case.metrics, key=lambda mm: (mm.kind, mm.metric_id)):
            expected_txt, actual_txt, abs_err_txt, rel_err_txt = _metric_expected_actual(m)
            status = "SKIPPED" if m.skipped else ("PASS" if m.passed else "FAIL")
            lines.append(
                f"| {m.metric_id} ({m.kind}) | {expected_txt} | {actual_txt} | {abs_err_txt} | {rel_err_txt} | {status} |"
            )
            if m.skipped:
                reason = str(m.details.get("reason", "")).strip()
                if reason:
                    lines.append(f"| reason | - | {reason} | - | - | SKIPPED |")
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    legacy_md_path = out_root / f"validation_{suite}_summary.md"
    legacy_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
