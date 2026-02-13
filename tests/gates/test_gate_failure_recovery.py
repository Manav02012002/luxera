from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.project.runner import run_job, RunnerError


def _project_with_missing_asset(tmp_path: Path) -> Path:
    p = Project(name="FailSafe", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(tmp_path / "missing.ies")))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0, 0, 0), width=4, height=4, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    project_path = tmp_path / "p.json"
    save_project_schema(p, project_path)
    return project_path


def test_gate_runner_missing_asset_fails_cleanly(tmp_path: Path):
    project_path = _project_with_missing_asset(tmp_path)
    try:
        run_job(project_path, "j1")
        assert False, "Expected RunnerError for missing asset file"
    except RunnerError as e:
        msg = str(e).lower()
        assert "missing" in msg or "no such file" in msg or "not found" in msg


def test_gate_run_all_does_not_emit_report_on_failure(tmp_path: Path):
    project_path = _project_with_missing_asset(tmp_path)
    rc = main(["run-all", str(project_path), "--job", "j1", "--report", "--bundle"])
    assert rc != 0
    p = load_project_schema(project_path)
    assert len(p.results) == 0
