from __future__ import annotations

import json
from pathlib import Path
from typing import List
import zipfile

from luxera.project.schema import Project, JobResultRef


def export_debug_bundle(project: Project, job_ref: JobResultRef, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result_dir = Path(job_ref.result_dir)
    files: List[Path] = []

    # Project file
    if project.root_dir:
        project_file = Path(project.root_dir) / "project.json"
        if project_file.exists():
            files.append(project_file)

    # Result artifacts
    for p in result_dir.glob("*"):
        if p.is_file():
            files.append(p)

    # Photometry assets
    for asset in project.photometry_assets:
        if asset.path:
            p = Path(asset.path)
            if p.exists():
                files.append(p)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arcname = f.name if f.parent == result_dir else f"assets/{f.name}"
            zf.write(f, arcname)

    return out_path
