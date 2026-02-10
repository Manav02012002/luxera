from __future__ import annotations

from luxera.project.schema import JobSpec, ComplianceProfile


def en12464_direct_job(job_id: str = "en12464_direct") -> JobSpec:
    return JobSpec(id=job_id, type="direct", seed=0, settings={})


def en13032_radiosity_job(job_id: str = "en13032_radiosity") -> JobSpec:
    return JobSpec(
        id=job_id,
        type="radiosity",
        seed=0,
        settings={
            "max_iterations": 200,
            "convergence_threshold": 0.0005,
            "patch_max_area": 0.25,
            "method": "GATHERING",
            "use_visibility": True,
            "ambient_light": 0.0,
            "monte_carlo_samples": 24,
            "ugr_grid_spacing": 2.0,
            "ugr_eye_heights": [1.2, 1.7],
        },
    )


def default_compliance_profiles() -> list[ComplianceProfile]:
    return [
        ComplianceProfile(
            id="office_en12464",
            name="Office (EN 12464)",
            domain="indoor",
            standard_ref="EN 12464-1:2021",
            thresholds={"avg_min_lux": 500.0, "uniformity_min": 0.6, "ugr_max": 19.0},
        ),
        ComplianceProfile(
            id="classroom_en12464",
            name="Classroom (EN 12464)",
            domain="indoor",
            standard_ref="EN 12464-1:2021",
            thresholds={"avg_min_lux": 300.0, "uniformity_min": 0.6, "ugr_max": 19.0},
        ),
        ComplianceProfile(
            id="corridor_en12464",
            name="Corridor (EN 12464)",
            domain="indoor",
            standard_ref="EN 12464-1:2021",
            thresholds={"avg_min_lux": 100.0, "uniformity_min": 0.4, "ugr_max": 28.0},
        ),
        ComplianceProfile(
            id="road_m3_en13201",
            name="Roadway M3 (EN 13201 proxy)",
            domain="roadway",
            standard_ref="EN 13201",
            thresholds={
                "avg_min_lux": 1.0,
                "uo_min": 0.35,
                "ul_min": 0.4,
                "luminance_min_cd_m2": 0.5,
                "ti_max_percent": 15.0,
                "surround_ratio_min": 0.5,
            },
        ),
        ComplianceProfile(
            id="road_p2_en13201",
            name="Roadway P2 (EN 13201 proxy)",
            domain="roadway",
            standard_ref="EN 13201",
            thresholds={
                "avg_min_lux": 5.0,
                "uo_min": 0.4,
                "ul_min": 0.4,
                "luminance_min_cd_m2": 1.0,
                "ti_max_percent": 20.0,
                "surround_ratio_min": 0.5,
            },
        ),
        ComplianceProfile(
            id="em_escape_en1838",
            name="Emergency Escape Route (EN 1838)",
            domain="emergency",
            standard_ref="EN 1838",
            thresholds={"min_lux": 1.0, "uniformity_ratio_min": 0.1},
        ),
    ]
