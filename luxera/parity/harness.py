from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.export.en12464_report import build_en12464_report_model
from luxera.export.pdf_report import build_project_pdf_report
from luxera.parity.expected import (
    ParityComparison,
    compare_results_to_expected,
    load_expected_file,
)
from luxera.project.io import load_project_schema
from luxera.runner import run_job


@dataclass(frozen=True)
class EngineRunSpec:
    engine_id: str
    job_id: str


@dataclass(frozen=True)
class ParityRunOutput:
    pack_dir: Path
    out_dir: Path
    results_json: Path
    manifest_json: Path
    report_pdf: Path
    engines: List[EngineRunSpec]


def _load_scene_payload(scene_path: Path) -> Dict[str, Any]:
    data = json.loads(scene_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("scene.lux.json must be a JSON object")
    return data


def _engine_specs_from_scene(scene_payload: Mapping[str, Any], project) -> List[EngineRunSpec]:
    parity_cfg = scene_payload.get("parity", {})
    engines_cfg = parity_cfg.get("engines", []) if isinstance(parity_cfg, Mapping) else []

    specs: List[EngineRunSpec] = []
    if isinstance(engines_cfg, list) and engines_cfg:
        for row in engines_cfg:
            if not isinstance(row, Mapping):
                raise ValueError("scene parity.engines entries must be objects")
            engine_id = str(row.get("id", "")).strip()
            job_id = str(row.get("job_id", "")).strip()
            if not engine_id or not job_id:
                raise ValueError("scene parity.engines entries require id and job_id")
            specs.append(EngineRunSpec(engine_id=engine_id, job_id=job_id))
    else:
        specs = [EngineRunSpec(engine_id=j.id, job_id=j.id) for j in project.jobs]

    if not specs:
        raise ValueError("scene pack has no configured engines/jobs")
    return specs


def _report_engine_id(scene_payload: Mapping[str, Any], specs: List[EngineRunSpec]) -> str:
    parity_cfg = scene_payload.get("parity", {}) if isinstance(scene_payload.get("parity", {}), Mapping) else {}
    preferred = str(parity_cfg.get("report_engine", "")).strip()
    if preferred:
        return preferred
    return specs[0].engine_id


def _copy_grid_csvs(result_dir: Path, out_grids_dir: Path, engine_id: str) -> List[str]:
    out_grids_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for src in sorted(result_dir.glob("*.csv")):
        if "grid" not in src.name.lower():
            continue
        dst_name = f"{engine_id}__{src.name}"
        dst = out_grids_dir / dst_name
        shutil.copyfile(src, dst)
        copied.append(dst_name)
    return copied


def _write_project_report(project, job_ref, out_pdf: Path) -> None:
    job = next((j for j in project.jobs if j.id == job_ref.job_id), None)
    if job is None:
        raise ValueError(f"Job not found while building report: {job_ref.job_id}")
    if job.type in {"roadway", "daylight", "emergency"}:
        build_project_pdf_report(project, job_ref, out_pdf)
    else:
        model = build_en12464_report_model(project, job_ref)
        render_en12464_pdf(model, out_pdf)


def run_pack(pack_dir: str | Path, out_dir: str | Path) -> ParityRunOutput:
    pack_path = Path(pack_dir).expanduser().resolve()
    out_path = Path(out_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    source_scene_path = pack_path / "scene.lux.json"
    expected_path = pack_path / "expected" / "expected.json"
    if not source_scene_path.exists():
        raise ValueError(f"Missing scene file: {source_scene_path}")
    if not expected_path.exists():
        raise ValueError(f"Missing expected file: {expected_path}")

    # Run on an isolated copy so parity metadata in source scene is preserved.
    work_pack = out_path / "_pack_work"
    if work_pack.exists():
        shutil.rmtree(work_pack)
    shutil.copytree(
        pack_path,
        work_pack,
        ignore=shutil.ignore_patterns(".luxera", "expected/last_failed_run"),
    )

    scene_path = work_pack / "scene.lux.json"
    scene_payload = _load_scene_payload(source_scene_path)
    project = load_project_schema(scene_path)
    specs = _engine_specs_from_scene(scene_payload, project)
    report_engine_id = _report_engine_id(scene_payload, specs)

    engines_by_id = {s.engine_id: s for s in specs}
    if report_engine_id not in engines_by_id:
        raise ValueError(f"report_engine '{report_engine_id}' is not in configured engines")

    engine_results: Dict[str, Dict[str, Any]] = {}
    manifest_engines: List[Dict[str, Any]] = []
    grids_dir = out_path / "grids"
    report_source_job_id = engines_by_id[report_engine_id].job_id

    for spec in specs:
        ref = run_job(scene_path, spec.job_id)
        project_after = load_project_schema(scene_path)
        job = next((j for j in project_after.jobs if j.id == spec.job_id), None)
        if job is None:
            raise ValueError(f"Configured job not found after run: {spec.job_id}")

        engine_results[spec.engine_id] = {
            "job_id": spec.job_id,
            "job_type": job.type,
            "backend": job.backend,
            "summary": ref.summary,
        }

        result_dir = Path(ref.result_dir)
        copied_grids = _copy_grid_csvs(result_dir, grids_dir, spec.engine_id)
        manifest_engines.append(
            {
                "engine_id": spec.engine_id,
                "job_id": spec.job_id,
                "result_dir": str(result_dir),
                "grid_csv": copied_grids,
            }
        )

    project_final = load_project_schema(scene_path)
    report_ref = next((r for r in project_final.results if r.job_id == report_source_job_id), None)
    if report_ref is None:
        raise ValueError(f"No result found for report engine job: {report_source_job_id}")

    report_pdf = out_path / "report.pdf"
    _write_project_report(project_final, report_ref, report_pdf)

    results_payload = {
        "schema_version": "parity_results_v1",
        "pack_name": pack_path.name,
        "scene_file": "scene.lux.json",
        "engines": engine_results,
    }
    results_json = out_path / "results.json"
    results_json.write_text(json.dumps(results_payload, indent=2, sort_keys=True), encoding="utf-8")

    manifest_payload = {
        "schema_version": "parity_manifest_v1",
        "pack_name": pack_path.name,
        "pack_dir": str(pack_path),
        "work_pack_dir": str(work_pack),
        "scene_path": str(scene_path),
        "out_dir": str(out_path),
        "engines": manifest_engines,
        "report_pdf": "report.pdf",
        "results_json": "results.json",
        "expected_json": str(expected_path),
    }
    manifest_json = out_path / "manifest.json"
    manifest_json.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

    return ParityRunOutput(
        pack_dir=pack_path,
        out_dir=out_path,
        results_json=results_json,
        manifest_json=manifest_json,
        report_pdf=report_pdf,
        engines=specs,
    )


def test_pack(pack_dir: str | Path) -> tuple[ParityRunOutput, ParityComparison]:
    pack_path = Path(pack_dir).expanduser().resolve()
    expected_path = pack_path / "expected" / "expected.json"
    expected = load_expected_file(expected_path)

    with tempfile.TemporaryDirectory(prefix="luxera_parity_") as tmp:
        out = run_pack(pack_path, Path(tmp))
        results = json.loads(out.results_json.read_text(encoding="utf-8"))
        comparison = compare_results_to_expected(results, expected)

        # Preserve result artifacts for debugging only when failed.
        if not comparison.passed:
            fail_out = pack_path / "expected" / "last_failed_run"
            if fail_out.exists():
                shutil.rmtree(fail_out)
            shutil.copytree(out.out_dir, fail_out)

        return out, comparison


# Prevent pytest from treating this helper as a test function.
test_pack.__test__ = False
