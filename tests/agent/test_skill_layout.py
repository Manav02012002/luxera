from __future__ import annotations

import shutil
from pathlib import Path

from luxera.agent.skills.layout import build_layout_skill
from luxera.project.io import load_project_schema
from luxera.project.validator import validate_project_for_job


def test_skill_layout_diff_and_apply(tmp_path: Path) -> None:
    src = Path("examples/indoor_office").resolve()
    dst = tmp_path / "indoor_office"
    shutil.copytree(src, dst)
    project_path = dst / "office.luxera.json"
    out = build_layout_skill(str(project_path), target_lux=500.0, uniformity_min=0.5)
    assert out.diff.ops

    project = load_project_schema(project_path)
    out.diff.apply(project)
    for job in project.jobs:
        validate_project_for_job(project, job)
