from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema
from luxera.project.schema import (
    JobSpec,
    LuminaireInstance,
    OpeningSpec,
    PhotometryAsset,
    Project,
    RoadwayGridSpec,
    RotationSpec,
    TransformSpec,
)
from luxera.project.io import save_project_schema
from luxera.runner import run_job_in_memory as run_job


def test_cli_add_roadway_grid_and_profile_and_job(tmp_path: Path):
    project = tmp_path / "p.json"
    assert main(["init", str(project), "--name", "WF"]) == 0
    assert (
        main(
            [
                "add-roadway",
                str(project),
                "--id",
                "rw1",
                "--start-x",
                "0",
                "--start-y",
                "0",
                "--end-x",
                "30",
                "--end-y",
                "0",
                "--num-lanes",
                "2",
                "--lane-width",
                "3.5",
            ]
        )
        == 0
    )
    assert main(
        [
            "add-compliance-profile",
            str(project),
            "--id",
            "cp1",
            "--name",
            "Road profile",
            "--domain",
            "roadway",
            "--standard-ref",
            "EN 13201",
            "--thresholds",
            '{"avg_min_lux": 0.1, "uo_min": 0.01, "ul_min": 0.01}',
        ]
    ) == 0
    assert (
        main(
            [
                "add-roadway-grid",
                str(project),
                "--id",
                "rg1",
                "--lane-width",
                "3.5",
                "--road-length",
                "30",
                "--nx",
                "12",
                "--ny",
                "3",
                "--roadway-id",
                "rw1",
                "--longitudinal-points",
                "12",
                "--transverse-points-per-lane",
                "2",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "add-job",
                str(project),
                "--id",
                "j_road",
                "--type",
                "roadway",
                "--road-class",
                "M3",
                "--compliance-profile-id",
                "cp1",
            ]
        )
        == 0
    )
    p = load_project_schema(project)
    assert any(j.id == "j_road" and j.type == "roadway" for j in p.jobs)
    assert any(rw.id == "rw1" for rw in p.roadways)
    assert any(rg.id == "rg1" for rg in p.roadway_grids)
    assert any(cp.id == "cp1" for cp in p.compliance_profiles)


def test_cli_add_profile_presets(tmp_path: Path):
    project = tmp_path / "p2.json"
    assert main(["init", str(project), "--name", "WF2"]) == 0
    assert main(["add-profile-presets", str(project)]) == 0
    p = load_project_schema(project)
    ids = {cp.id for cp in p.compliance_profiles}
    assert "office_en12464" in ids
    assert "road_m3_en13201" in ids
    assert "em_escape_en1838" in ids


def test_cli_add_daylight_annual_job_with_weather_file(tmp_path: Path):
    project = tmp_path / "p3.json"
    weather = tmp_path / "weather.csv"
    weather.write_text("0,10000,20000,30000\n", encoding="utf-8")
    assert main(["init", str(project), "--name", "WF3"]) == 0
    assert (
        main(
            [
                "add-job",
                str(project),
                "--id",
                "j_day",
                "--type",
                "daylight",
                "--daylight-mode",
                "annual_proxy",
                "--weather-hourly-lux-file",
                str(weather),
            ]
        )
        == 0
    )
    p = load_project_schema(project)
    job = next(j for j in p.jobs if j.id == "j_day")
    assert job.settings["mode"] == "annual_proxy"
    assert job.settings["exterior_hourly_lux"] == [0.0, 10000.0, 20000.0, 30000.0]


def test_cli_daylight_convenience_command(tmp_path: Path):
    project_path = tmp_path / "daylight.json"
    p = Project(name="DayCli", root_dir=str(tmp_path))
    p.geometry.openings.append(
        OpeningSpec(
            id="op1",
            name="Window",
            kind="window",
            vertices=[(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.0), (0.0, 0.0, 2.0)],
            is_daylight_aperture=True,
            visible_transmittance=0.65,
        )
    )
    from luxera.project.schema import CalcGrid, DaylightSpec

    p.grids.append(CalcGrid(id="g1", name="g", origin=(0.0, 0.0, 0.0), width=4.0, height=3.0, elevation=0.8, nx=4, ny=3))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            backend="df",
            daylight=DaylightSpec(mode="df", external_horizontal_illuminance_lux=10000.0),
            targets=["g1"],
        )
    )
    save_project_schema(p, project_path)

    assert main(["daylight", str(project_path), "--job", "j1"]) == 0
    loaded = load_project_schema(project_path)
    ref = next(r for r in loaded.results if r.job_id == "j1")
    out_dir = Path(ref.result_dir)
    assert (out_dir / "daylight_g1.csv").exists()
    assert (out_dir / "daylight_summary.json").exists()


def test_cli_export_roadway_report(tmp_path: Path):
    project_path = tmp_path / "road.json"
    ies_path = tmp_path / "road.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    p = Project(name="RoadCli", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(10.0, 2.0, 8.0), rotation=rot),
        )
    )
    p.roadway_grids.append(RoadwayGridSpec(id="rg1", name="R1", lane_width=4.0, road_length=20.0, nx=10, ny=3))
    p.jobs.append(JobSpec(id="j1", type="roadway", settings={"road_class": "M3"}))
    save_project_schema(p, project_path)

    loaded = load_project_schema(project_path)
    run_job(loaded, "j1")
    save_project_schema(loaded, project_path)

    out_html = tmp_path / "roadway.html"
    assert main(["export-roadway-report", str(project_path), "j1", "--out", str(out_html)]) == 0
    assert out_html.exists()


def test_cli_run_all_roadway_generates_pdf_and_bundle(tmp_path: Path):
    project_path = tmp_path / "road_runall.json"
    ies_path = tmp_path / "road_runall.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    p = Project(name="RoadRunAll", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(10.0, 2.0, 8.0), rotation=rot),
        )
    )
    p.roadway_grids.append(RoadwayGridSpec(id="rg1", name="R1", lane_width=4.0, road_length=20.0, nx=10, ny=3))
    p.jobs.append(JobSpec(id="j1", type="roadway", settings={"road_class": "M3"}))
    save_project_schema(p, project_path)

    assert main(["run-all", str(project_path), "--job", "j1", "--report", "--bundle"]) == 0
    loaded = load_project_schema(project_path)
    ref = next(r for r in loaded.results if r.job_id == "j1")
    result_dir = Path(ref.result_dir)
    assert (result_dir / "report.pdf").exists()
    assert (result_dir / "audit_bundle.zip").exists()
    assert (result_dir / "road_grid.csv").exists()
    assert (result_dir / "road_summary.json").exists()
    assert (result_dir / "road_heatmap.png").exists()


def test_cli_add_escape_route_and_emergency_job_fields(tmp_path: Path):
    project = tmp_path / "em.json"
    assert main(["init", str(project), "--name", "EM"]) == 0
    assert (
        main(
            [
                "add-grid",
                str(project),
                "--id",
                "g1",
                "--width",
                "4",
                "--height",
                "2",
                "--elevation",
                "0",
                "--nx",
                "5",
                "--ny",
                "3",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "add-escape-route",
                str(project),
                "--id",
                "r1",
                "--polyline",
                "0,1,0;4,1,0",
                "--width-m",
                "1.0",
                "--spacing-m",
                "0.5",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "add-job",
                str(project),
                "--id",
                "j_em",
                "--type",
                "emergency",
                "--emergency-standard",
                "EN1838",
                "--routes",
                "r1",
                "--open-area-targets",
                "g1",
                "--emergency-factor",
                "0.6",
            ]
        )
        == 0
    )
    p = load_project_schema(project)
    assert any(r.id == "r1" for r in p.escape_routes)
    job = next(j for j in p.jobs if j.id == "j_em")
    assert job.emergency is not None
    assert job.mode is not None
    assert job.routes == ["r1"]
    assert job.open_area_targets == ["g1"]
