from pathlib import Path

from luxera.project.schema import (
    CalcGrid,
    ComplianceProfile,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoadwayGridSpec,
    RotationSpec,
    TransformSpec,
)
from luxera.runner import run_job


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


def test_run_roadway_job(tmp_path: Path):
    ies = _ies_fixture(tmp_path / "road.ies")
    p = Project(name="Road", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Road Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(10.0, 2.0, 8.0), rotation=rot),
        )
    )
    p.roadway_grids.append(RoadwayGridSpec(id="rg1", name="R1", lane_width=4.0, road_length=20.0, nx=10, ny=3))
    p.compliance_profiles.append(
        ComplianceProfile(
            id="cp1",
            name="Road M",
            domain="roadway",
            standard_ref="EN 13201",
            thresholds={"avg_min_lux": 0.1, "uo_min": 0.01, "ul_min": 0.01, "luminance_min_cd_m2": 0.01},
        )
    )
    p.jobs.append(JobSpec(id="j1", type="roadway", settings={"road_class": "M3", "compliance_profile_id": "cp1"}))
    ref = run_job(p, "j1")
    assert ref.summary["road_class"] == "M3"
    assert "ul_longitudinal" in ref.summary
    assert "road_luminance_mean_cd_m2" in ref.summary
    assert "observer_luminance_views" in ref.summary
    assert len(ref.summary["observer_luminance_views"]) >= 1
    assert "compliance" in ref.summary
    assert "luminance_ok" in ref.summary["compliance"]


def test_run_emergency_job(tmp_path: Path):
    ies = _ies_fixture(tmp_path / "em.ies")
    p = Project(name="Emergency", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Emergency Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.0, nx=5, ny=5))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="emergency",
            settings={
                "target_min_lux": 0.1,
                "target_uniformity": 0.01,
                "battery_duration_min": 90.0,
                "battery_end_factor": 0.4,
                "battery_curve": "linear",
                "battery_steps": 4,
            },
        )
    )
    ref = run_job(p, "j1")
    assert ref.summary["mode"] == "escape_route"
    assert ref.summary["battery_duration_min"] == 90.0
    assert len(ref.summary["battery_profile"]) == 4
    assert "compliance" in ref.summary
    assert "min_lux_ok" in ref.summary["compliance"]
    assert "worst_min_lux" in ref.summary["compliance"]


def test_run_daylight_job(tmp_path: Path):
    p = Project(name="Daylight", root_dir=str(tmp_path))
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=5.0, height=5.0, elevation=0.8, nx=3, ny=3))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            settings={
                "exterior_horizontal_illuminance_lux": 12000.0,
                "daylight_factor_percent": 2.5,
                "target_lux": 300.0,
            },
        )
    )
    ref = run_job(p, "j1")
    assert ref.summary["mode"] == "daylight_factor"
    assert ref.summary["mean_lux"] == 300.0
    assert ref.summary["daylight_target_area_ratio"] == 1.0


def test_run_daylight_annual_proxy_metrics(tmp_path: Path):
    p = Project(name="DaylightAnnual", root_dir=str(tmp_path))
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=5.0, height=5.0, elevation=0.8, nx=3, ny=3))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            settings={
                "mode": "annual_proxy",
                "exterior_hourly_lux": [0.0, 10000.0, 20000.0, 30000.0],
                "daylight_factor_percent": 2.0,
                "target_lux": 300.0,
                "daylight_depth_attenuation": 0.0,
                "sda_threshold_ratio": 0.5,
                "udi_low_lux": 100.0,
                "udi_high_lux": 500.0,
            },
        )
    )
    ref = run_job(p, "j1")
    assert ref.summary["mode"] == "annual_proxy"
    assert ref.summary["annual_hours"] == 4
    assert ref.summary["da_mean_ratio"] == 0.5
    assert ref.summary["sda_ratio"] == 1.0
    assert ref.summary["udi_mean_ratio"] == 0.5


def test_run_direct_with_indoor_compliance_profile(tmp_path: Path):
    ies = _ies_fixture(tmp_path / "direct.ies")
    p = Project(name="DirectProfile", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=4, height=4, elevation=0.8, nx=3, ny=3))
    p.compliance_profiles.append(
        ComplianceProfile(
            id="office500",
            name="Office 500",
            domain="indoor",
            standard_ref="EN 12464-1:2021",
            thresholds={"avg_min_lux": 10.0, "uniformity_min": 0.1, "ugr_max": 19.0},
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", settings={"compliance_profile_id": "office500"}))
    ref = run_job(p, "j1")
    cp = ref.summary.get("compliance_profile")
    assert isinstance(cp, dict)
    assert cp["profile_id"] == "office500"
    assert cp["standard"] == "EN 12464-1:2021"
    assert cp["status"] in {"PASS", "FAIL"}
