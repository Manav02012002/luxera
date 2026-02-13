from __future__ import annotations

import copy
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from luxera.core.hashing import sha256_bytes
from luxera.project.diff import DiffOp, ProjectDiff
from luxera.project.io import load_project_schema
from luxera.project.schema import Project, ProjectVariant
from luxera.results.store import results_root


@dataclass(frozen=True)
class VariantCompareResult:
    out_dir: str
    compare_json: str
    compare_csv: str
    rows: List[Dict[str, Any]]


def _variant_to_diff(variant: ProjectVariant) -> ProjectDiff:
    ops: List[DiffOp] = []
    for raw in variant.diff_ops:
        if not isinstance(raw, dict):
            continue
        op = str(raw.get("op", ""))
        kind = str(raw.get("kind", ""))
        item_id = str(raw.get("id", ""))
        payload = raw.get("payload", {})
        if op not in {"add", "update", "remove"}:
            continue
        if kind not in {
            "room",
            "surface",
            "opening",
            "obstruction",
            "level",
            "escape_route",
            "luminaire",
            "grid",
            "job",
            "material",
            "asset",
            "family",
        }:
            continue
        ops.append(DiffOp(op=op, kind=kind, id=item_id, payload=payload if isinstance(payload, dict) else {}))
    return ProjectDiff(ops=ops)


def _apply_variant(base: Project, variant: ProjectVariant) -> Project:
    variant_project = copy.deepcopy(base)

    if variant.luminaire_overrides:
        by_id = {l.id: l for l in variant_project.luminaires}
        for lum_id, overrides in variant.luminaire_overrides.items():
            lum = by_id.get(lum_id)
            if lum is None:
                continue
            if "flux_multiplier" in overrides:
                lum.flux_multiplier = float(overrides["flux_multiplier"])
            if "maintenance_factor" in overrides:
                lum.maintenance_factor = float(overrides["maintenance_factor"])
            if "tilt_deg" in overrides:
                lum.tilt_deg = float(overrides["tilt_deg"])

    if variant.dimming_schemes:
        by_id = {l.id: l for l in variant_project.luminaires}
        for lum_id, factor in variant.dimming_schemes.items():
            lum = by_id.get(lum_id)
            if lum is not None:
                lum.flux_multiplier = float(lum.flux_multiplier) * float(factor)

    pdiff = _variant_to_diff(variant)
    pdiff.apply(variant_project)
    return variant_project


def _collect_metric_keys(rows: Sequence[Dict[str, Any]]) -> List[str]:
    keys: set[str] = set()
    for row in rows:
        for k, v in row.get("summary", {}).items():
            if isinstance(v, (int, float)):
                keys.add(str(k))
    return sorted(keys)


def run_job_for_variants(
    project_path: str | Path,
    job_id: str,
    variant_ids: Sequence[str],
    baseline_variant_id: str | None = None,
) -> VariantCompareResult:
    from luxera.project.runner import run_job_in_memory

    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    project.root_dir = str(ppath.parent)

    variant_by_id = {v.id: v for v in project.variants}
    missing = [vid for vid in variant_ids if vid not in variant_by_id]
    if missing:
        raise ValueError(f"Unknown variant ids: {', '.join(missing)}")
    if baseline_variant_id is not None and baseline_variant_id not in variant_ids:
        raise ValueError("baseline_variant_id must be one of variant_ids")

    token = f"{job_id}|{'|'.join(variant_ids)}".encode("utf-8")
    out_dir = results_root(ppath.parent) / f"variants_{sha256_bytes(token)[:16]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for vid in variant_ids:
        variant = variant_by_id[vid]
        vp = _apply_variant(project, variant)
        ref = run_job_in_memory(vp, job_id)
        rows.append(
            {
                "variant_id": variant.id,
                "variant_name": variant.name,
                "job_hash": ref.job_hash,
                "result_dir": ref.result_dir,
                "summary": dict(ref.summary),
            }
        )

    metric_keys = _collect_metric_keys(rows)
    baseline_id = baseline_variant_id or (variant_ids[0] if variant_ids else None)
    baseline_row = next((r for r in rows if r["variant_id"] == baseline_id), None)
    baseline_summary = baseline_row.get("summary", {}) if isinstance(baseline_row, dict) else {}
    table_rows: List[Dict[str, Any]] = []
    for row in rows:
        line: Dict[str, Any] = {
            "variant_id": row["variant_id"],
            "variant_name": row["variant_name"],
            "job_hash": row["job_hash"],
            "result_dir": row["result_dir"],
        }
        summary = row.get("summary", {})
        for key in metric_keys:
            value = summary.get(key)
            line[key] = value
            bval = baseline_summary.get(key)
            if isinstance(value, (int, float)) and isinstance(bval, (int, float)):
                line[f"delta_{key}"] = float(value) - float(bval)
        table_rows.append(line)

    out_json = out_dir / "variants_compare.json"
    out_json.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "variant_ids": list(variant_ids),
                "baseline_variant_id": baseline_id,
                "metrics": metric_keys,
                "rows": table_rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    out_csv = out_dir / "variants_compare.csv"
    delta_keys = [f"delta_{k}" for k in metric_keys]
    fieldnames = ["variant_id", "variant_name", "job_hash", "result_dir", *metric_keys, *delta_keys]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in table_rows:
            writer.writerow(row)

    return VariantCompareResult(
        out_dir=str(out_dir),
        compare_json=str(out_json),
        compare_csv=str(out_csv),
        rows=table_rows,
    )
