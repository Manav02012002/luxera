from __future__ import annotations

import re
from pathlib import Path

from luxera.export.professional_pdf import ProfessionalReportBuilder
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec
from luxera.runner import run_job


def _build_project(tmp_path: Path) -> tuple[Project, dict]:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="professional-report", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="Open Office", width=10.0, length=8.0, height=3.0))
    p.grids.append(CalcGrid(id="g1", name="Main Grid", origin=(0.0, 0.0, 0.0), width=10.0, height=8.0, elevation=0.8, nx=10, ny=8, room_id="r1"))
    p.photometry_assets.append(
        PhotometryAsset(
            id="a1",
            format="IES",
            path=str(fixture),
            metadata={"manufacturer": "Luxera", "catalog": "LX-100", "lumens": 3600, "wattage": 32},
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.5, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
            maintenance_factor=0.8,
            mounting_height_m=2.8,
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l2",
            name="L2",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(7.5, 6.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
            maintenance_factor=0.8,
            mounting_height_m=2.8,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=0))
    pp = tmp_path / "p.json"
    save_project_schema(p, pp)
    ref = run_job(pp, "j1")
    results = {"summary": ref.summary, "result_dir": ref.result_dir, "job_id": ref.job_id, "job_hash": ref.job_hash}
    return p, results


def test_report_creates_file(tmp_path: Path) -> None:
    project, results = _build_project(tmp_path)
    out = tmp_path / "professional.pdf"
    ProfessionalReportBuilder(project, results).build(out)
    assert out.exists()
    assert out.stat().st_size > 10_000


def test_report_has_multiple_pages(tmp_path: Path) -> None:
    project, results = _build_project(tmp_path)
    out = tmp_path / "professional_pages.pdf"
    ProfessionalReportBuilder(project, results).build(out)
    data = out.read_bytes()
    page_count = len(re.findall(rb"/Type\s*/Page\b", data))
    assert page_count >= 5


def test_luminaire_schedule_content(tmp_path: Path) -> None:
    project, results = _build_project(tmp_path)
    out = tmp_path / "professional_schedule.pdf"
    ProfessionalReportBuilder(project, results).build(out)
    data = out.read_bytes()
    assert b"Luminaire Schedule" in data
    assert b"LX-100" in data
    assert b"a1" in data
