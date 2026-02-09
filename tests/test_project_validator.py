import pytest

from luxera.project.schema import Project, JobSpec, PhotometryAsset
from luxera.project.validator import validate_project_for_job, ProjectValidationError


def test_validate_project_for_job_blocks_ambiguous_direct() -> None:
    project = Project(name="Invalid")
    job = JobSpec(id="j1", type="direct")

    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)

    assert "Direct job requires at least one grid" in str(exc.value)
    assert "Direct job requires at least one luminaire" in str(exc.value)


def test_validate_project_for_job_rejects_duplicate_ids() -> None:
    project = Project(name="Invalid")
    project.photometry_assets.append(PhotometryAsset(id="dup", format="IES"))
    project.photometry_assets.append(PhotometryAsset(id="dup", format="IES"))
    job = JobSpec(id="j1", type="direct")

    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)

    assert "Duplicate photometry asset id: dup" in str(exc.value)


def test_validate_project_for_roadway_requires_roadway_grid() -> None:
    project = Project(name="RoadInvalid")
    job = JobSpec(id="j1", type="roadway")
    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)
    assert "Roadway job requires at least one roadway grid" in str(exc.value)


def test_validate_project_for_daylight_requires_grid() -> None:
    project = Project(name="DayInvalid")
    job = JobSpec(id="j1", type="daylight")
    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)
    assert "Daylight job requires at least one grid" in str(exc.value)
