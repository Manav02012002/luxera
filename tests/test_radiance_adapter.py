from pathlib import Path

import pytest

from luxera.backends.radiance import build_radiance_run_manifest, detect_radiance_tools
from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
)
from luxera.runner import run_job_in_memory as run_job, RunnerError

pytestmark = pytest.mark.radiance


def test_detect_radiance_tools_shape():
    tools = detect_radiance_tools()
    assert isinstance(tools.available, bool)
    assert isinstance(tools.paths, dict)
    assert isinstance(tools.missing, list)


def test_radiance_manifest_builds():
    project = Project(name="Rad")
    job = JobSpec(id="j1", type="direct", backend="radiance")
    manifest = build_radiance_run_manifest(project, job)
    assert manifest["backend"] == "radiance"
    assert manifest["job_type"] == "direct"
    assert "tools" in manifest


def test_runner_radiance_missing_tools_fails_cleanly(tmp_path: Path):
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
    project = Project(name="RadRun", root_dir=str(tmp_path))
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, 3.0), rotation=rot),
        )
    )
    project.grids.append(CalcGrid(id="g1", name="g", origin=(0.0, 0.0, 0.0), width=1.0, height=1.0, elevation=0.8, nx=2, ny=2))
    project.jobs.append(JobSpec(id="j1", type="direct", backend="radiance"))

    with pytest.raises(RunnerError):
        run_job(project, "j1")
