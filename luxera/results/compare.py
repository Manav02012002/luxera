from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from luxera.project.schema import Project


def _load_result_summary(result_dir: str) -> Dict[str, Any]:
    p = Path(result_dir) / "result.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("summary", {}) if isinstance(data, dict) else {}


def compare_job_results(project: Project, job_id_a: str, job_id_b: str) -> Dict[str, Any]:
    ra = next((r for r in project.results if r.job_id == job_id_a), None)
    rb = next((r for r in project.results if r.job_id == job_id_b), None)
    if ra is None or rb is None:
        raise ValueError("Both job results must exist in project")

    sa = _load_result_summary(ra.result_dir)
    sb = _load_result_summary(rb.result_dir)
    keys = sorted(set(sa.keys()) | set(sb.keys()))
    delta: Dict[str, Any] = {}
    for k in keys:
        va = sa.get(k)
        vb = sb.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta[k] = {"a": va, "b": vb, "delta": vb - va}
        else:
            delta[k] = {"a": va, "b": vb}
    return {
        "job_a": job_id_a,
        "job_b": job_id_b,
        "delta": delta,
    }
