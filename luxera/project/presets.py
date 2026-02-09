from __future__ import annotations

from luxera.project.schema import JobSpec


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
