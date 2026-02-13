from __future__ import annotations

import json
from pathlib import Path

from luxera.backends.radiance import RadianceTooling
from luxera.project.schema import CalcGrid, DaylightAnnualSpec, DaylightSpec, JobSpec, OpeningSpec, Project
from luxera.runner import run_job_in_memory as run_job


def _write_fake_epw(path: Path) -> Path:
    header = [
        "LOCATION,Test,TS,USA,TMY3,000000,0.0,0.0,0.0,0.0",
        "DESIGN CONDITIONS,0",
        "TYPICAL/EXTREME PERIODS,0",
        "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        "COMMENTS 1,synthetic",
        "COMMENTS 2,synthetic",
        "DATA PERIODS,1,1,Data,Sunday,1/1,12/31",
    ]
    rows = [
        "2024,1,1,1,60,0,20,10,50,101325,0,0,0,0,0,0",
        "2024,1,1,2,60,0,20,10,50,101325,0,0,0,10,30,20",
        "2024,1,1,3,60,0,20,10,50,101325,0,0,0,200,400,150",
        "2024,1,1,4,60,0,20,10,50,101325,0,0,0,300,600,180",
    ]
    path.write_text("\n".join(header + rows) + "\n", encoding="utf-8")
    return path


def test_daylight_annual_contract_artifacts(tmp_path: Path, monkeypatch) -> None:
    tools = RadianceTooling(available=True, paths={"oconv": "/usr/bin/oconv", "rtrace": "/usr/bin/rtrace"}, missing=[])
    monkeypatch.setattr("luxera.project.validator.detect_radiance_tools", lambda: tools)
    monkeypatch.setattr("luxera.engine.daylight_annual_radiance.detect_radiance_tools", lambda: tools)

    epw = _write_fake_epw(tmp_path / "tiny.epw")

    p = Project(name="AnnualDaylight", root_dir=str(tmp_path))
    p.geometry.openings.append(
        OpeningSpec(
            id="op1",
            name="Window",
            kind="window",
            opening_type="window",
            vertices=[(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.5), (0.0, 0.0, 2.5)],
            is_daylight_aperture=True,
            vt=0.62,
            visible_transmittance=0.62,
        )
    )
    p.grids.append(CalcGrid(id="g1", name="Grid", origin=(0.0, 0.0, 0.0), width=4.0, height=3.0, elevation=0.8, nx=4, ny=3))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            backend="radiance",
            daylight=DaylightSpec(
                mode="annual",
                annual=DaylightAnnualSpec(weather_file=str(epw), grid_targets=["g1"]),
            ),
            targets=["g1"],
        )
    )

    ref = run_job(p, "j1")
    out_dir = Path(ref.result_dir)

    assert (out_dir / "daylight_summary.json").exists()
    assert (out_dir / "annual_summary.json").exists()
    assert (out_dir / "sda_g1.csv").exists()
    assert (out_dir / "ase_g1.csv").exists()
    assert (out_dir / "udi_g1.csv").exists()
    assert (out_dir / "sda_g1.png").exists()
    assert (out_dir / "ase_g1.png").exists()
    assert (out_dir / "udi_g1.png").exists()

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    daylight = manifest.get("metadata", {}).get("daylight", {})
    assert daylight.get("mode") == "annual"
    assert daylight.get("weather_file")
    assert isinstance(daylight.get("thresholds"), dict)
    summary = json.loads((out_dir / "daylight_summary.json").read_text(encoding="utf-8"))
    assert summary.get("annual_method") in {
        "radiance_full_matrix_dctimestep",
        "radiance_epw_gendaylit_df_transfer",
        "epw_proxy_df_transfer",
    }


def test_daylight_annual_matrix_preference_records_audit(tmp_path: Path, monkeypatch) -> None:
    tools = RadianceTooling(available=True, paths={"oconv": "/usr/bin/oconv", "rtrace": "/usr/bin/rtrace"}, missing=[])
    monkeypatch.setattr("luxera.project.validator.detect_radiance_tools", lambda: tools)
    monkeypatch.setattr("luxera.engine.daylight_annual_radiance.detect_radiance_tools", lambda: tools)
    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"epw2wea", "gendaymtx", "dctimestep", "rfluxmtx", "gendaylit", "oconv", "rtrace"} else None,
    )
    monkeypatch.setattr(
        "luxera.engine.daylight_annual_radiance._try_full_matrix_transfer",
        lambda project, targets, weather_path, spec: (
            {t.target_id: __import__("numpy").ones((4, int(t.points.shape[0])), dtype=float) * 150.0 for t in targets},
            {"status": "ok", "mode": "full_matrix"},
        ),
    )

    epw = _write_fake_epw(tmp_path / "tiny2.epw")
    p = Project(name="AnnualDaylightMatrix", root_dir=str(tmp_path))
    p.geometry.openings.append(
        OpeningSpec(
            id="op1",
            name="Window",
            kind="window",
            opening_type="window",
            vertices=[(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.5), (0.0, 0.0, 2.5)],
            is_daylight_aperture=True,
            vt=0.62,
            visible_transmittance=0.62,
        )
    )
    p.grids.append(CalcGrid(id="g1", name="Grid", origin=(0.0, 0.0, 0.0), width=4.0, height=3.0, elevation=0.8, nx=4, ny=3))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            backend="radiance",
            daylight=DaylightSpec(
                mode="annual",
                annual=DaylightAnnualSpec(weather_file=str(epw), grid_targets=["g1"], annual_method_preference="matrix"),
            ),
            targets=["g1"],
        )
    )
    ref = run_job(p, "j1")
    out_dir = Path(ref.result_dir)
    summary = json.loads((out_dir / "daylight_summary.json").read_text(encoding="utf-8"))
    assert summary.get("annual_method") == "radiance_full_matrix_dctimestep"
    assert isinstance(summary.get("matrix_artifacts"), dict)
