from pathlib import Path

import pytest

from luxera.export.client_bundle import export_client_bundle
from luxera.export.debug_bundle import export_debug_bundle
from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.export.en12464_report import build_en12464_report_model
from luxera.project.presets import default_compliance_profiles
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)
from luxera.runner import run_job_in_memory as run_job

pytestmark = pytest.mark.slow


def test_indoor_workflow_e2e(tmp_path: Path):
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1500 1 5 1 1 2 0.5 0.5 0.2
0 22.5 45 67.5 90
0
600 550 400 200 50
""",
        encoding="utf-8",
    )

    p = Project(name="IndoorE2E", root_dir=str(tmp_path))
    p.compliance_profiles.extend(default_compliance_profiles())
    p.geometry.rooms.append(
        RoomSpec(
            id="r1",
            name="Office",
            width=6.0,
            length=8.0,
            height=3.0,
            activity_type="OFFICE_GENERAL",
        )
    )
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Panel-1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=rot),
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l2",
            name="Panel-2",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(4.0, 6.0, 2.8), rotation=rot),
        )
    )
    p.grids.append(
        CalcGrid(
            id="g1",
            name="Workplane",
            origin=(0.0, 0.0, 0.0),
            width=6.0,
            height=8.0,
            elevation=0.8,
            nx=9,
            ny=11,
            room_id="r1",
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": True, "occlusion_include_room_shell": True}, seed=7))

    ref = run_job(p, "j1")
    assert "mean_lux" in ref.summary
    assert "compliance" in ref.summary

    model = build_en12464_report_model(p, ref)
    pdf_path = render_en12464_pdf(model, tmp_path / "office_en12464.pdf")
    assert pdf_path.exists() and pdf_path.stat().st_size > 0

    client = export_client_bundle(p, ref, tmp_path / "client_bundle.zip")
    audit = export_debug_bundle(p, ref, tmp_path / "audit_bundle.zip")
    assert client.exists() and client.stat().st_size > 0
    assert audit.exists() and audit.stat().st_size > 0
