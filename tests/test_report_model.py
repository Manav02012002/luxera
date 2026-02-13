import json
from pathlib import Path

from luxera.export.report_model import build_en13032_report_model, build_report_model
from luxera.project.schema import Project, JobResultRef, PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec


def test_report_model_build(tmp_path: Path):
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "job_hash": "hash1",
                "job": {"id": "job1", "type": "direct"},
                "summary": {"mean_lux": 500},
                "assets": {"asset1": "h1"},
                "solver": {"package_version": "0.2.0"},
            }
        ),
        encoding="utf-8",
    )

    project = Project(name="Test")
    project.photometry_assets.append(
        PhotometryAsset(id="asset1", format="IES", path="/tmp/a.ies", content_hash="h1", metadata={"filename": "a.ies"})
    )

    ref = JobResultRef(job_id="job1", job_hash="hash1", result_dir=str(result_dir))
    model = build_en13032_report_model(project, ref)

    assert model.audit.job_id == "job1"
    assert model.audit.job_hash == "hash1"
    assert model.photometry[0].asset_id == "asset1"
    assert model.summary["mean_lux"] == 500
    assert "rooms" in model.geometry
    assert "job" in model.method


def test_unified_report_model_build(tmp_path: Path):
    result_dir = tmp_path / "result2"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "job_hash": "hash1",
                "job": {"id": "job1", "type": "direct"},
                "summary": {"mean_lux": 500, "calc_objects": []},
                "assets": {"asset1": "h1"},
                "solver": {"package_version": "0.2.0"},
                "assumptions": ["occlusion disabled", "Coordinate convention: ..."],
                "coordinate_convention": "Type C",
                "units": {"illuminance": "lux"},
            }
        ),
        encoding="utf-8",
    )
    project = Project(name="Test")
    project.photometry_assets.append(PhotometryAsset(id="asset1", format="IES", path="/tmp/a.ies", content_hash="h1", metadata={"filename": "a.ies"}))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="asset1",
            transform=TransformSpec(position=(1.0, 2.0, 3.0), rotation=rot),
        )
    )
    ref = JobResultRef(job_id="job1", job_hash="hash1", result_dir=str(result_dir))
    model = build_report_model(project, "job1", ref)
    assert model["job_id"] == "job1"
    assert model["luminaire_schedule"]
    assert "worst_case_summary" in model
    assert "assumptions" in model["audit"]


def test_unified_report_model_includes_daylight_section(tmp_path: Path):
    result_dir = tmp_path / "result_daylight"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job_d",
                "job_hash": "hash_d",
                "job": {"id": "job_d", "type": "daylight"},
                "summary": {
                    "mode": "df",
                    "sky": "CIE_overcast",
                    "external_horizontal_illuminance_lux": 10000.0,
                    "calc_objects": [
                        {"id": "g1", "type": "grid", "summary": {"min_df_percent": 1.0, "mean_df_percent": 2.0, "max_df_percent": 3.0}}
                    ],
                },
                "assets": {},
                "solver": {"package_version": "0.2.0"},
            }
        ),
        encoding="utf-8",
    )
    project = Project(name="DayReport")
    ref = JobResultRef(job_id="job_d", job_hash="hash_d", result_dir=str(result_dir))
    model = build_report_model(project, "job_d", ref)
    daylight = model.get("daylight")
    assert isinstance(daylight, dict)
    assert daylight.get("mode") == "df"
    assert daylight.get("sky") == "CIE_overcast"


def test_unified_report_model_includes_emergency_section(tmp_path: Path):
    result_dir = tmp_path / "result_emergency"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job_e",
                "job_hash": "hash_e",
                "job": {"id": "job_e", "type": "emergency"},
                "summary": {
                    "mode": "emergency_v1",
                    "standard": "EN1838",
                    "emergency_factor": 0.5,
                    "route_results": [{"route_id": "r1", "min_lux": 1.0, "mean_lux": 2.0, "u0": 0.5, "pass": True}],
                    "open_area_results": [{"grid_id": "g1", "min_lux": 0.8, "mean_lux": 1.5, "u0": 0.53, "pass": True}],
                    "compliance": {"status": "PASS"},
                },
                "assets": {},
                "solver": {"package_version": "0.2.0"},
            }
        ),
        encoding="utf-8",
    )
    project = Project(name="EmReport")
    ref = JobResultRef(job_id="job_e", job_hash="hash_e", result_dir=str(result_dir))
    model = build_report_model(project, "job_e", ref)
    emergency = model.get("emergency")
    assert isinstance(emergency, dict)
    assert emergency.get("standard") == "EN1838"
    assert isinstance(emergency.get("route_table"), list)


def test_unified_report_model_includes_roadway_section(tmp_path: Path):
    result_dir = tmp_path / "result_roadway"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job_r",
                "job_hash": "hash_r",
                "job": {"id": "job_r", "type": "roadway"},
                "summary": {
                    "road_class": "M3",
                    "lane_width_m": 3.5,
                    "num_lanes": 2,
                    "road_length_m": 60.0,
                    "overall": {"avg_lux": 1.2, "u0": 0.45},
                    "lane_metrics": [{"lane_number": 1, "mean_lux": 1.1, "luminance_mean_cd_m2": 0.08}],
                    "observer_luminance_views": [{"observer_index": 0, "luminance_cd_m2": 0.09}],
                    "road_luminance_mean_cd_m2": 0.08,
                    "observer_luminance_max_cd_m2": 0.09,
                    "threshold_increment_ti_proxy_percent": 2.0,
                    "surround_ratio_proxy": 0.6,
                    "compliance": {"status": "PASS", "thresholds": {"uo_min": 0.4}},
                },
                "assets": {},
                "solver": {"package_version": "0.2.0"},
            }
        ),
        encoding="utf-8",
    )
    project = Project(name="RoadReport")
    ref = JobResultRef(job_id="job_r", job_hash="hash_r", result_dir=str(result_dir))
    model = build_report_model(project, "job_r", ref)
    roadway = model.get("roadway")
    assert isinstance(roadway, dict)
    assert roadway.get("road_class") == "M3"
    assert isinstance(roadway.get("lane_metrics"), list)
    assert isinstance(roadway.get("observer_luminance_views"), list)
    assert isinstance(roadway.get("luminance_metrics"), dict)
