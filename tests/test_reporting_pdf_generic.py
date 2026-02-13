from __future__ import annotations

from pathlib import Path

from luxera.export.pdf_report import build_project_pdf_report
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec
from luxera.runner import run_job


def test_build_project_pdf_report_generic_direct(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="generic-report", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=4.0, height=3.0))
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=4, ny=4, room_id="r1"))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=0))
    pp = tmp_path / "p.json"
    save_project_schema(p, pp)
    ref = run_job(pp, "j1")
    out = tmp_path / "generic.pdf"
    build_project_pdf_report(p, ref, out)
    assert out.exists()
    assert out.stat().st_size > 0

