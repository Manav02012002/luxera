from __future__ import annotations

from pathlib import Path

from luxera.backends.radiance import RadianceTooling
from luxera.export.pdf_report import build_project_pdf_report
from luxera.project.schema import CalcGrid, DaylightAnnualSpec, DaylightSpec, JobSpec, OpeningSpec, Project
from luxera.runner import run_job_in_memory as run_job


def _write_fake_epw(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "LOCATION,Test,TS,USA,TMY3,000000,0.0,0.0,0.0,0.0",
                "DESIGN CONDITIONS,0",
                "TYPICAL/EXTREME PERIODS,0",
                "GROUND TEMPERATURES,0",
                "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
                "COMMENTS 1,synthetic",
                "COMMENTS 2,synthetic",
                "DATA PERIODS,1,1,Data,Sunday,1/1,12/31",
                "2024,1,1,1,60,0,20,10,50,101325,0,0,0,10,30,20",
                "2024,1,1,2,60,0,20,10,50,101325,0,0,0,200,400,150",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_daylight_report_export(tmp_path: Path, monkeypatch) -> None:
    tools = RadianceTooling(available=True, paths={"oconv": "/usr/bin/oconv", "rtrace": "/usr/bin/rtrace"}, missing=[])
    monkeypatch.setattr("luxera.project.validator.detect_radiance_tools", lambda: tools)
    monkeypatch.setattr("luxera.engine.daylight_annual_radiance.detect_radiance_tools", lambda: tools)

    epw = _write_fake_epw(tmp_path / "tiny.epw")
    p = Project(name="DReport", root_dir=str(tmp_path))
    p.geometry.openings.append(OpeningSpec(id="op1", name="W", opening_type="window", kind="window", vertices=[(0, 0, 1), (2, 0, 1), (2, 0, 2), (0, 0, 2)], is_daylight_aperture=True, vt=0.6, visible_transmittance=0.6))
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0, 0, 0), width=4, height=3, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="daylight", backend="radiance", daylight=DaylightSpec(mode="annual", annual=DaylightAnnualSpec(weather_file=str(epw), grid_targets=["g1"])), targets=["g1"]))

    ref = run_job(p, "j1")
    out = tmp_path / "daylight_report.pdf"
    build_project_pdf_report(p, ref, out)
    assert out.exists()
    assert out.stat().st_size > 1000
