from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import List

from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.export.en12464_report import build_en12464_report_model
from luxera.export.en13032_pdf import render_en13032_pdf
from luxera.export.report_model import build_en13032_report_model
from luxera.project.schema import JobResultRef, Project


def export_client_bundle(project: Project, job_ref: JobResultRef, out_path: Path) -> Path:
    """
    Build a client-facing bundle (PDF + key tables/images), excluding heavy audit internals.
    """
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result_dir = Path(job_ref.result_dir)
    staging = out_path.parent / f".client_bundle_{job_ref.job_hash}"
    staging.mkdir(parents=True, exist_ok=True)

    en13032_pdf = render_en13032_pdf(build_en13032_report_model(project, job_ref), staging / "report_en13032.pdf")
    en12464_pdf = render_en12464_pdf(build_en12464_report_model(project, job_ref), staging / "report_en12464.pdf")

    include_names = [
        "result.json",
        "grid.csv",
        "grid_heatmap.png",
        "grid_isolux.png",
        "surface_illuminance.csv",
    ]
    files: List[Path] = [en13032_pdf, en12464_pdf]
    for name in include_names:
        p = result_dir / name
        if p.exists() and p.is_file():
            files.append(p)

    summary_txt = staging / "summary.txt"
    try:
        meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
        summary = meta.get("summary", {})
        summary_txt.write_text(
            "Luxera Client Summary\n"
            f"Project: {project.name}\n"
            f"Job: {job_ref.job_id}\n"
            f"Job Hash: {job_ref.job_hash}\n"
            f"Summary: {json.dumps(summary, sort_keys=True)}\n",
            encoding="utf-8",
        )
        files.append(summary_txt)
    except Exception:
        pass

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)

    return out_path
