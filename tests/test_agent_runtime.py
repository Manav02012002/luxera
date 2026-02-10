from pathlib import Path

from luxera.agent.runtime import AgentRuntime
from luxera.project.io import load_project_schema, save_project_schema
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
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=4, height=4, elevation=0.8, nx=3, ny=3, room_id="r1"))
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
    p = load_project_schema(project_path)
    assert len(p.grids) >= 2


def test_runtime_diff_preview_has_keys(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    res = rt.execute(str(project_path), "/place panels target 500 lux")
    assert res.diff_preview["count"] > 0
    assert all("key" in op for op in res.diff_preview["ops"])
    assert all("payload_fields" in op for op in res.diff_preview["ops"])
    assert all("payload_summary" in op for op in res.diff_preview["ops"])


def test_runtime_apply_selected_diff_ops_only(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    before = load_project_schema(project_path)
    before_lum_ids = [x.id for x in before.luminaires]

    # Approve apply, but with explicit empty selection.
    rt.execute(
        str(project_path),
        "/place panels target 500 lux",
        approvals={"apply_diff": True, "selected_diff_ops": []},
    )
    after = load_project_schema(project_path)
    after_lum_ids = [x.id for x in after.luminaires]
    assert after_lum_ids == before_lum_ids


def test_runtime_workflow_hit_lux_uniformity_adds_layout_actions(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    res = rt.execute(str(project_path), "hit 500 lux uniformity")
    kinds = [a.kind for a in res.actions]
    assert "apply_diff" in kinds


def test_runtime_workflow_generate_client_and_audit_reports(tmp_path: Path):
    project_path = _make_project(tmp_path)
    p = load_project_schema(project_path)
    from luxera.runner import run_job_in_memory as run_job

    run_job(p, "j1")
    save_project_schema(p, project_path)

    rt = AgentRuntime()
    res = rt.execute(str(project_path), "generate client report and audit bundle")
    artifacts = set(res.produced_artifacts)
    assert any(a.endswith("_client_bundle.zip") for a in artifacts)
    assert any(a.endswith("_debug_bundle.zip") for a in artifacts)


def test_runtime_workflow_import_detect_grid(tmp_path: Path):
    project_path = _make_project(tmp_path)
    obj = tmp_path / "box.obj"
    obj.write_text(
        """v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
""",
        encoding="utf-8",
    )
    rt = AgentRuntime()
    rt.execute(str(project_path), f"import {obj} detect rooms create grid")
    p = load_project_schema(project_path)
    assert len(p.grids) >= 2
