from __future__ import annotations

from pathlib import Path

from luxera.agent.skills.optimize import build_optimize_skill
from luxera.project.io import save_project_schema
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)


def _seed(tmp_path: Path) -> Path:
    ies_path = tmp_path / "opt_skill.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    p = Project(name="OptSkill", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=6.0, length=8.0, height=3.0))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0, 0, 0), width=6.0, height=8.0, elevation=0.8, nx=5, ny=7, room_id="r1"))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    path = tmp_path / "p.json"
    save_project_schema(p, path)
    return path


def test_optimize_skill_emits_diff_and_manifest(tmp_path: Path) -> None:
    project_path = _seed(tmp_path)
    out = build_optimize_skill(str(project_path), job_id="j1", candidate_limit=4)
    assert out.diff.ops
    assert out.run_manifest.get("skill") == "optimize"
    artifacts = out.run_manifest.get("artifacts", {})
    assert isinstance(artifacts, dict)
    assert "candidates_csv" in artifacts
