from pathlib import Path

from luxera.project.schema import Project, PhotometryAsset, LuminaireInstance, CalcGrid, JobSpec, TransformSpec, RotationSpec
from luxera.project.io import save_project_schema, load_project_schema
from luxera.runner import run_job_in_memory as run_job


def test_gate_determinism(tmp_path: Path):
    project_path = tmp_path / "proj.json"
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )

    project = Project(name="Gate", root_dir=str(tmp_path))
    asset = PhotometryAsset(id="a1", format="IES", path=str(ies_path))
    project.photometry_assets.append(asset)
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    lum = LuminaireInstance(
        id="l1",
        name="L1",
        photometry_asset_id="a1",
        transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
    )
    project.luminaires.append(lum)
    grid = CalcGrid(id="g1", name="grid", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3)
    project.grids.append(grid)
    job = JobSpec(id="j1", type="direct", seed=123)
    project.jobs.append(job)

    save_project_schema(project, project_path)
    p1 = load_project_schema(project_path)
    r1 = run_job(p1, "j1")
    p2 = load_project_schema(project_path)
    r2 = run_job(p2, "j1")

    assert r1.job_hash == r2.job_hash
    assert r1.result_dir == r2.result_dir
