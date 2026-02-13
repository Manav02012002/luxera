from __future__ import annotations

from pathlib import Path

from luxera.agent.skills.emergency import build_emergency_skill
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, Project


def test_emergency_skill_builds_diff_and_manifest(tmp_path: Path) -> None:
    p = Project(name="EmSkill", root_dir=str(tmp_path))
    p.grids.append(CalcGrid(id="g1", name="g1", origin=(0.0, 0.0, 0.0), width=4.0, height=2.0, elevation=0.0, nx=5, ny=3))
    path = tmp_path / "p.json"
    save_project_schema(p, path)
    out = build_emergency_skill(
        str(path),
        route_polyline=[(0.0, 1.0, 0.0), (4.0, 1.0, 0.0)],
        route_id="r1",
        standard="EN1838",
        emergency_factor=0.6,
    )
    assert out.diff.ops
    assert out.run_manifest.get("skill") == "emergency"
    assert out.run_manifest.get("job_id")
