from __future__ import annotations

from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import (
    CalcGrid,
    DaylightSpec,
    EmergencyModeSpec,
    EmergencySpec,
    EscapeRouteSpec,
    JobSpec,
    LuminaireInstance,
    OpeningSpec,
    PhotometryAsset,
    Project,
    RotationSpec,
    TransformSpec,
)


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


def test_run_all_daylight_generates_report_pdf(tmp_path: Path) -> None:
    p = Project(name="cli_daylight", root_dir=str(tmp_path))
    p.geometry.openings.append(
        OpeningSpec(
            id="o1",
            name="Window",
            opening_type="window",
            kind="window",
            vertices=[(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.0), (0.0, 0.0, 2.0)],
            is_daylight_aperture=True,
            vt=0.65,
            visible_transmittance=0.65,
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=4.0, height=3.0, elevation=0.8, nx=3, ny=3))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            backend="df",
            daylight=DaylightSpec(mode="df", external_horizontal_illuminance_lux=10000.0),
            targets=["g1"],
        )
    )
    project_path = tmp_path / "p_daylight.json"
    save_project_schema(p, project_path)

    assert main(["run-all", str(project_path), "--job", "j1", "--report"]) == 0
    proj = load_project_schema(project_path)
    ref = next(r for r in proj.results if r.job_id == "j1")
    assert (Path(ref.result_dir) / "report.pdf").exists()


def test_run_all_emergency_generates_report_pdf(tmp_path: Path) -> None:
    ies = _ies_fixture(tmp_path / "e.ies")
    p = Project(name="cli_emergency", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 1.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=4.0, height=2.0, elevation=0.0, nx=4, ny=3))
    p.escape_routes.append(EscapeRouteSpec(id="r1", name="R", polyline=[(0.0, 1.0, 0.0), (4.0, 1.0, 0.0)], width_m=1.0, spacing_m=0.5))
    p.jobs.append(JobSpec(id="j1", type="emergency", emergency=EmergencySpec(standard="EN1838"), mode=EmergencyModeSpec(emergency_factor=0.5), routes=["r1"], open_area_targets=["g1"]))
    project_path = tmp_path / "p_emergency.json"
    save_project_schema(p, project_path)

    assert main(["run-all", str(project_path), "--job", "j1", "--report"]) == 0
    proj = load_project_schema(project_path)
    ref = next(r for r in proj.results if r.job_id == "j1")
    assert (Path(ref.result_dir) / "report.pdf").exists()
