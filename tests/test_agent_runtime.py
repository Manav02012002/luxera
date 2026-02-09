from pathlib import Path

from luxera.agent.runtime import AgentRuntime
from luxera.project.io import save_project_schema
from luxera.project.schema import Project, RoomSpec, PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec, JobSpec, CalcGrid


def _make_project(tmp_path: Path) -> Path:
    p = Project(name="AgentRt", root_dir=str(tmp_path))
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


def test_runtime_requires_approval_for_apply_and_run(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    res = rt.execute(str(project_path), "/place panels target 500 lux and run")
    kinds = [a.kind for a in res.actions]
    assert "apply_diff" in kinds
    assert "run_job" in kinds
    assert not res.produced_artifacts


def test_runtime_determinism_same_intent(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    r1 = rt.execute(str(project_path), "/place panels target 500 lux")
    r2 = rt.execute(str(project_path), "/place panels target 500 lux")
    assert r1.run_manifest["runtime_id"] == r2.run_manifest["runtime_id"]
    assert r1.plan == r2.plan


def test_runtime_never_claims_compliance_without_run(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    res = rt.execute(str(project_path), "check compliance")
    assert res.compliance_claimed is False
    assert any("cannot be declared without running jobs" in w.lower() for w in res.warnings)


def test_runtime_grid_command_adds_grid(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    rt.execute(str(project_path), "/grid 0.8 0.5")
    from luxera.project.io import load_project_schema
    p = load_project_schema(project_path)
    assert len(p.grids) >= 2
