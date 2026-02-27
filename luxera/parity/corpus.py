from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping

import numpy as np

from luxera.parity.arrays import array_sha256
from luxera.parity.expected import ParityComparison, compare_expected, load_expected_file
from luxera.parity.invariance import run_invariance_for_scene
from luxera.parity.packs import Pack, PackScene, load_pack, select_scenes
from luxera.project.io import load_project_schema
from luxera.runner import run_job


def _scene_expected_path(
    parity_root: Path,
    pack: Pack,
    scene: PackScene,
    baseline: str,
) -> Path:
    if scene.expected:
        return (pack.pack_dir / scene.expected).resolve()
    return (
        Path(parity_root).resolve()
        / "packs"
        / pack.id
        / "expected"
        / baseline
        / "v1"
        / f"{scene.id}.expected.json"
    )


def _default_run_scene(scene_path: Path, pack: Pack, scene: PackScene) -> Dict[str, Any]:
    project = load_project_schema(scene_path)
    job_ids = list(pack.engines) if pack.engines else [j.id for j in project.jobs]
    if not job_ids:
        raise ValueError(f"No jobs available to run for scene: {scene_path}")

    def _array_summary(arr: np.ndarray) -> Dict[str, float]:
        aa = np.asarray(arr, dtype=float)
        return {
            "min": float(np.min(aa)),
            "max": float(np.max(aa)),
            "mean": float(np.mean(aa)),
            "p95": float(np.percentile(aa, 95)),
            "p99": float(np.percentile(aa, 99)),
        }

    def _extract_job_arrays(result_dir: Path, nx: int | None, ny: int | None) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        csv_files = sorted(result_dir.glob("grid*.csv"), key=lambda p: p.name)
        for idx, csv_path in enumerate(csv_files):
            try:
                raw = np.loadtxt(csv_path, delimiter=",", skiprows=1, dtype=float)
            except Exception:
                continue
            arr = np.asarray(raw, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.shape[1] < 4:
                continue
            lux = arr[:, 3]
            if nx is not None and ny is not None and nx * ny == lux.size:
                grid = lux.reshape((int(ny), int(nx)))
            else:
                grid = lux.reshape((lux.size, 1))
            grid_id = f"grid_{idx + 1}"
            out[grid_id] = {
                "grid_values_lux": grid.tolist(),
                "shape": [int(grid.shape[0]), int(grid.shape[1])],
                "hash": array_sha256(grid),
                "summary": _array_summary(grid),
            }
        return out

    nx = int(project.grids[0].nx) if getattr(project, "grids", None) else None
    ny = int(project.grids[0].ny) if getattr(project, "grids", None) else None
    summaries: Dict[str, Any] = {}
    arrays_by_job: Dict[str, Any] = {}
    for job_id in job_ids:
        ref = run_job(scene_path, job_id)
        summary = dict(ref.summary) if isinstance(ref.summary, Mapping) else {}
        heal_path = Path(ref.result_dir) / "geometry_heal_report.json"
        if heal_path.exists():
            try:
                heal_payload = json.loads(heal_path.read_text(encoding="utf-8"))
                if isinstance(heal_payload, Mapping):
                    counts = heal_payload.get("counts")
                    if isinstance(counts, Mapping):
                        summary["geometry_heal_counts"] = {str(k): int(v) for k, v in counts.items() if isinstance(v, (int, float))}
                        for k, v in counts.items():
                            if isinstance(v, (int, float)):
                                summary[f"geometry_heal_{str(k)}"] = int(v)
                    cleaned_hash = heal_payload.get("cleaned_mesh_hash")
                    if isinstance(cleaned_hash, str):
                        summary["geometry_heal_hash"] = cleaned_hash
            except Exception:
                pass
        arrays = _extract_job_arrays(Path(ref.result_dir), nx, ny)
        if arrays:
            summary["parity_arrays"] = arrays
            arrays_by_job[job_id] = arrays
        summaries[job_id] = summary

    if len(summaries) == 1:
        only = next(iter(summaries.values()))
        return {"results": only}
    return {"results": summaries, "parity_arrays": arrays_by_job}


def _write_failure_bundle(
    base: Path,
    scene_id: str,
    comparison,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    dst = base / "failures" / scene_id
    dst.mkdir(parents=True, exist_ok=True)

    diff_payload = {
        "passed": comparison.passed,
        "checked_metrics": comparison.checked_metrics,
        "mismatches": [
            {
                "path": m.path,
                "reason": m.reason,
                "expected": m.expected,
                "actual": m.actual,
                "abs_tol": m.abs_tol,
                "rel_tol": m.rel_tol,
            }
            for m in comparison.mismatches
        ],
    }
    (dst / "diff.json").write_text(json.dumps(diff_payload, indent=2, sort_keys=True), encoding="utf-8")
    (dst / "actual.json").write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
    (dst / "expected.json").write_text(json.dumps(expected, indent=2, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _expected_from_actual(actual: Mapping[str, Any], scene: PackScene, baseline: str) -> Dict[str, Any]:
    # Keep update output deterministic and schema-valid; prefer v2 wrapper.
    schema = str(actual.get("schema_version", "")).strip()
    if schema == "parity_expected_v1":
        return dict(actual)
    if schema == "parity_expected_v2":
        out = dict(actual)
        out.setdefault("scene_id", scene.id)
        out.setdefault("baseline", baseline)
        out.setdefault("baseline_version", "v1")
        out.setdefault("results", dict(actual.get("results", {})) if isinstance(actual.get("results"), Mapping) else {})
        out.setdefault("tags", list(scene.tags))
        return out

    results_obj: Mapping[str, Any]
    raw_results = actual.get("results")
    if isinstance(raw_results, Mapping):
        results_obj = raw_results
    elif isinstance(actual, Mapping):
        results_obj = dict(actual)
    else:
        results_obj = {}
    return {
        "schema_version": "parity_expected_v2",
        "scene_id": scene.id,
        "baseline": baseline,
        "baseline_version": "v1",
        "results": dict(results_obj),
        "tags": list(scene.tags),
    }


def _summary_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Parity Corpus Summary",
        "",
        "| Scene | Pack | Baseline | Status | Checked | Mismatches | Invariance |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['scene_id']} | {r['pack_id']} | {r['baseline']} | {r['status']} | {r['checked_metrics']} | {r['mismatches']} | {r.get('invariance_failures', 0)} |"
        )
    lines.append("")
    lines.append("## Invariance Failures")
    lines.append("")
    lines.append("| Scene | Transform | Metric | Abs Error | Rel Error | Tolerance | Reason |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    wrote = False
    for r in rows:
        inv = r.get("invariance_mismatches", [])
        if not isinstance(inv, list):
            continue
        for mm in inv:
            if not isinstance(mm, Mapping):
                continue
            wrote = True
            tol = mm.get("abs_tol")
            if mm.get("rel_tol") is not None:
                tol = f"{tol} / rel {mm.get('rel_tol')}"
            lines.append(
                f"| {r['scene_id']} | {mm.get('transform', '-')} | {mm.get('metric', '-')} | {mm.get('abs_error', '-')} | {mm.get('rel_error', '-')} | {tol if tol is not None else '-'} | {mm.get('reason', '-')} |"
            )
    if not wrote:
        lines.append("| - | - | - | - | - | - | none |")
    lines.append("")
    return "\n".join(lines)


def run_corpus(
    parity_root: Path,
    selector: dict,
    baseline: str,
    out_dir: Path,
    update_goldens: bool = False,
    run_scene: Callable[[Path], Mapping[str, Any]] | None = None,
) -> dict:
    root = Path(parity_root).expanduser().resolve()
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    selected = select_scenes(root, selector)
    rows: List[Dict[str, Any]] = []
    updates: List[Dict[str, Any]] = []

    for pack, scene in selected:
        scene_path = (pack.pack_dir / scene.path).resolve()
        expected_path = _scene_expected_path(root, pack, scene, baseline)

        if run_scene is not None:
            actual = dict(run_scene(scene_path))
        else:
            actual = _default_run_scene(scene_path, pack, scene)

        if expected_path.exists() and not (update_goldens and str(baseline) == "luxera"):
            expected_payload = load_expected_file(expected_path)
            comparison = compare_expected(
                actual,
                expected_payload,
                scene_tags=list(scene.tags),
                expected_root=expected_path.parent,
            )
            status = "PASS" if comparison.passed else "FAIL"
            if not comparison.passed:
                _write_failure_bundle(out, scene.id, comparison, actual, expected_payload)
        else:
            if update_goldens and str(baseline) == "luxera":
                expected_path.parent.mkdir(parents=True, exist_ok=True)
                old_hash = _sha256_file(expected_path) if expected_path.exists() else None
                to_write = _expected_from_actual(actual, scene, baseline)
                expected_path.write_text(json.dumps(to_write, indent=2, sort_keys=True), encoding="utf-8")
                new_hash = _sha256_file(expected_path)
                updates.append(
                    {
                        "pack_id": pack.id,
                        "scene_id": scene.id,
                        "expected_path": str(expected_path),
                        "old_hash": old_hash,
                        "new_hash": new_hash,
                    }
                )

                expected_payload = load_expected_file(expected_path)
                comparison = compare_expected(
                    actual,
                    expected_payload,
                    scene_tags=list(scene.tags),
                    expected_root=expected_path.parent,
                )
                status = "PASS" if comparison.passed else "FAIL"
                if not comparison.passed:
                    _write_failure_bundle(out, scene.id, comparison, actual, expected_payload)
            else:
                status = "FAIL"
                comparison = ParityComparison(passed=False, checked_metrics=0, mismatches=[])
                missing_expected = {
                    "schema_version": "parity_expected_v2",
                    "scene_id": scene.id,
                    "baseline": baseline,
                    "baseline_version": "v1",
                    "results": {},
                    "tags": list(scene.tags),
                }
                diff = {
                    "passed": False,
                    "checked_metrics": 0,
                    "mismatches": [
                        {
                            "path": "expected_file",
                            "reason": "missing_expected_file",
                            "expected": str(expected_path),
                            "actual": None,
                            "abs_tol": None,
                            "rel_tol": None,
                        }
                    ],
                }
                dst = out / "failures" / scene.id
                dst.mkdir(parents=True, exist_ok=True)
                (dst / "diff.json").write_text(json.dumps(diff, indent=2, sort_keys=True), encoding="utf-8")
                (dst / "actual.json").write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
                (dst / "expected.json").write_text(json.dumps(missing_expected, indent=2, sort_keys=True), encoding="utf-8")

        invariance_failures = 0
        invariance_mismatches: List[Dict[str, Any]] = []
        invariance_cfg = pack.global_config.get("invariance")
        do_invariance = False
        transforms = ("translate_large", "rotate_z_90", "unit_mm")
        scalar_abs_tol = 1e-4
        scalar_rel_tol = 1e-5
        array_thr: Dict[str, float] = {"max_abs": 1e-3, "rmse": 1e-4, "p95_abs": 1e-3}
        if isinstance(invariance_cfg, bool):
            do_invariance = invariance_cfg
        elif isinstance(invariance_cfg, Mapping):
            do_invariance = bool(invariance_cfg.get("enabled", True))
            trs = invariance_cfg.get("transforms")
            if isinstance(trs, list) and trs:
                transforms = tuple(str(x) for x in trs if str(x).strip())
            if invariance_cfg.get("scalar_abs_tol") is not None:
                scalar_abs_tol = float(invariance_cfg.get("scalar_abs_tol"))
            if invariance_cfg.get("scalar_rel_tol") is not None:
                scalar_rel_tol = float(invariance_cfg.get("scalar_rel_tol"))
            ath = invariance_cfg.get("array_thresholds")
            if isinstance(ath, Mapping):
                for k, v in ath.items():
                    try:
                        array_thr[str(k)] = float(v)
                    except Exception:
                        pass

        if do_invariance:
            inv_out = out / "invariance" / pack.id / scene.id
            inv_out.mkdir(parents=True, exist_ok=True)
            scene_job_ids = list(pack.engines)
            inv = run_invariance_for_scene(
                scene_path,
                job_ids=scene_job_ids,
                out_dir=inv_out,
                transforms=transforms,
                scalar_abs_tol=scalar_abs_tol,
                scalar_rel_tol=scalar_rel_tol,
                array_thresholds=array_thr,
            )
            invariance_failures = len(inv.mismatches)
            invariance_mismatches = [
                {
                    "transform": m.transform,
                    "metric": m.metric,
                    "baseline": m.baseline,
                    "variant": m.variant,
                    "abs_error": m.abs_error,
                    "rel_error": m.rel_error,
                    "abs_tol": m.abs_tol,
                    "rel_tol": m.rel_tol,
                    "reason": m.reason,
                }
                for m in inv.mismatches
            ]
            (inv_out / "details.json").write_text(json.dumps(inv.details, indent=2, sort_keys=True), encoding="utf-8")
            if invariance_failures > 0:
                status = "FAIL"

        rows.append(
            {
                "scene_id": scene.id,
                "pack_id": pack.id,
                "baseline": baseline,
                "expected_path": str(expected_path),
                "status": status,
                "checked_metrics": int(getattr(comparison, "checked_metrics", 0)),
                "mismatches": len(getattr(comparison, "mismatches", [])),
                "invariance_failures": invariance_failures,
                "invariance_mismatches": invariance_mismatches,
            }
        )

    passed = sum(1 for r in rows if r["status"] == "PASS")
    failed = len(rows) - passed
    summary = {
        "selected_scenes": len(rows),
        "passed": passed,
        "failed": failed,
        "baseline": baseline,
        "update_goldens": bool(update_goldens),
        "scenes": rows,
    }

    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (out / "summary.md").write_text(_summary_markdown(rows), encoding="utf-8")
    if update_goldens:
        (out / "golden_updates.json").write_text(
            json.dumps({"baseline": baseline, "updated": updates}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return summary
