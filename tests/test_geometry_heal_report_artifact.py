from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import load_project_schema
from luxera.runner import run_job


def test_run_always_writes_geometry_heal_report(tmp_path: Path) -> None:
    src = Path("tests/golden/projects/box_room/project.json").resolve()
    dst = tmp_path / "project.json"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    project = load_project_schema(dst)
    project.root_dir = str(src.parent)
    for asset in project.photometry_assets:
        if asset.path:
            asset.path = str((src.parent / asset.path).resolve())
    from luxera.project.io import save_project_schema

    save_project_schema(project, dst)
    job_id = project.jobs[0].id
    ref = run_job(dst, job_id)
    p = Path(ref.result_dir) / "geometry_heal_report.json"
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert "counts" in payload
    assert "cleaned_mesh_hash" in payload
    assert "actions" in payload
