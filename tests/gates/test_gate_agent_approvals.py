from pathlib import Path

from luxera.agent.runtime import AgentRuntime
from luxera.project.io import save_project_schema
from luxera.project.schema import Project, RoomSpec, PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec, JobSpec, CalcGrid


def _mk(tmp_path: Path) -> Path:
    p = Project(name="GateAgent", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=6, length=8, height=3))
    ies = tmp_path / "a.ies"
    ies.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec(position=(1, 1, 2.8), rotation=rot)))
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=4, height=4, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    path = tmp_path / "p.json"
    save_project_schema(p, path)
    return path


def test_gate_agent_diff_preview_and_approval(tmp_path: Path):
    path = _mk(tmp_path)
    rt = AgentRuntime()
    res = rt.execute(str(path), "/place panels target 500 lux run")
    assert res.diff_preview["count"] >= 0
    # Requires explicit approvals; artifacts should not be produced by default.
    assert res.produced_artifacts == []
