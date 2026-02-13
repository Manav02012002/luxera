import pytest

from luxera.project.schema import JobSpec, MaterialSpec, PhotometryAsset, Project
from luxera.project.validator import validate_project_for_job, ProjectValidationError


def test_validate_project_for_job_blocks_ambiguous_direct() -> None:
    project = Project(name="Invalid")
    job = JobSpec(id="j1", type="direct")

    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)

    assert "Direct job requires at least one calculation object" in str(exc.value)
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


def test_validate_project_blocks_type_b_asset(tmp_path) -> None:
    ies = tmp_path / "type_b.ies"
    ies.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 2 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )
    project = Project(name="TypeB", root_dir=str(tmp_path))
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    job = JobSpec(id="j1", type="daylight")
    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)
    msg = str(exc.value)
    assert "Unsupported photometric type in asset a1" in msg
    assert "type=2 (B)" in msg


def test_validate_project_flags_missing_tilt_file(tmp_path) -> None:
    ies = tmp_path / "missing_tilt.ies"
    ies.write_text(
        """IESNA:LM-63-2019
TILT=FILE missing_tilt.dat
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )
    project = Project(name="MissingTilt", root_dir=str(tmp_path))
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    job = JobSpec(id="j1", type="daylight")
    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)
    assert "tilt_status=missing" in str(exc.value)


def test_validate_project_rejects_invalid_material_physics() -> None:
    project = Project(name="BadMaterial")
    project.materials.append(
        MaterialSpec(
            id="m1",
            name="Bad",
            reflectance=1.2,
            transmittance=-0.1,
            diffuse_reflectance_rgb=(0.5, 0.5, 1.2),
        )
    )
    job = JobSpec(id="j1", type="direct")
    with pytest.raises(ProjectValidationError) as exc:
        validate_project_for_job(project, job)
    msg = str(exc.value)
    assert "Material m1 reflectance must be in [0,1]" in msg
    assert "Material m1 transmittance must be in [0,1]" in msg
