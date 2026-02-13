from __future__ import annotations

from pathlib import Path

from luxera.agent.skills.daylight import build_daylight_skill
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, OpeningSpec, Project


def test_daylight_skill_builds_diff_and_manifest(tmp_path: Path) -> None:
    p = Project(name="DaySkill", root_dir=str(tmp_path))
    p.geometry.openings.append(
        OpeningSpec(
            id="op1",
            name="Window",
            kind="window",
            vertices=[(0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 0.0, 2.0), (0.0, 0.0, 2.0)],
        )
    )
    p.grids.append(CalcGrid(id="g1", name="g1", origin=(0.0, 0.0, 0.0), width=3.0, height=3.0, elevation=0.8, nx=3, ny=3))
    path = tmp_path / "p.json"
    save_project_schema(p, path)

    out = build_daylight_skill(str(path), mode="df", sky="CIE_overcast", e0=10000.0, vt=0.65)
    assert out.diff.ops
    assert out.run_manifest.get("skill") == "daylight"
    assert out.run_manifest.get("job_id")
