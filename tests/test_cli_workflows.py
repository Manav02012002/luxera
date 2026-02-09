from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema


def test_cli_add_roadway_grid_and_profile_and_job(tmp_path: Path):
    project = tmp_path / "p.json"
    assert main(["init", str(project), "--name", "WF"]) == 0
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
