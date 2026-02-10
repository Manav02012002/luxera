from pathlib import Path
import zipfile

from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
)
from luxera.runner import run_job_in_memory as run_job
from luxera.export.client_bundle import export_client_bundle


def test_export_client_bundle(tmp_path: Path):
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

    project = Project(name="ClientBundle", root_dir=str(tmp_path))
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    project.grids.append(CalcGrid(id="g1", name="grid", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3))
    project.jobs.append(JobSpec(id="j1", type="direct", seed=1))
    ref = run_job(project, "j1")

    out = export_client_bundle(project, ref, tmp_path / "client.zip")
    assert out.exists()
    with zipfile.ZipFile(out, "r") as zf:
        names = set(zf.namelist())
        assert "report_en13032.pdf" in names
        assert "report_en12464.pdf" in names
        assert "result.json" in names
