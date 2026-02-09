from pathlib import Path

from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
)
from luxera.runner import run_job


def _seed_project(tmp_path: Path) -> Path:
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

    p = Project(name="Persist", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="grid", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct", seed=1))

    project_path = tmp_path / "project.json"
    save_project_schema(p, project_path)
    return project_path


def test_cached_artifact_run_still_updates_project_results(tmp_path: Path):
    project_path = _seed_project(tmp_path)

    p1 = load_project_schema(project_path)
    r1 = run_job(p1, "j1")
    save_project_schema(p1, project_path)
    assert len(p1.results) == 1

    # Simulate a caller with no in-memory results but same project/job state.
    p2 = load_project_schema(project_path)
    p2.results = []
    r2 = run_job(p2, "j1")

    assert r2.job_hash == r1.job_hash
    assert len(p2.results) == 1
    assert p2.results[0].job_hash == r1.job_hash
