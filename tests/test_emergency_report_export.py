from __future__ import annotations

from pathlib import Path

from luxera.export.pdf_report import build_project_pdf_report
from luxera.project.schema import CalcGrid, EmergencyModeSpec, EmergencySpec, EscapeRouteSpec, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.runner import run_job_in_memory as run_job


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    return path


def test_emergency_report_export(tmp_path: Path) -> None:
    ies = _ies_fixture(tmp_path / "em.ies")
    p = Project(name="EReport", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    p.luminaires.append(LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec(position=(2, 1, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0, 0, 0)))))
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0, 0, 0), width=4, height=2, elevation=0.0, nx=4, ny=3))
    p.escape_routes.append(EscapeRouteSpec(id="r1", name="R", polyline=[(0, 1, 0), (4, 1, 0)], width_m=1.0, spacing_m=0.5))
    p.jobs.append(JobSpec(id="j1", type="emergency", emergency=EmergencySpec(standard="EN1838"), mode=EmergencyModeSpec(emergency_factor=0.5), routes=["r1"], open_area_targets=["g1"]))

    ref = run_job(p, "j1")
    out = tmp_path / "emergency_report.pdf"
    build_project_pdf_report(p, ref, out)
    assert out.exists()
    assert out.stat().st_size > 1000
