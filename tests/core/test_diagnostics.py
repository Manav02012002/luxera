from __future__ import annotations

from luxera.core.diagnostics import ProjectDiagnostics
from luxera.core.errors import ERROR_CODES
from luxera.project.schema import CalcGrid, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _project_base() -> Project:
    p = Project(name="diag", root_dir=".")
    p.geometry.rooms.append(
        RoomSpec(
            id="r1",
            name="Room",
            width=6.0,
            length=8.0,
            height=3.0,
            origin=(0.0, 0.0, 0.0),
            floor_reflectance=0.2,
            wall_reflectance=0.5,
            ceiling_reflectance=0.7,
        )
    )
    return p


def _add_asset_and_luminaire(project: Project, z: float = 2.8) -> None:
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES"))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(
                position=(3.0, 4.0, z),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)),
            ),
            maintenance_factor=0.8,
            flux_multiplier=1.0,
        )
    )


def _add_grid(project: Project) -> None:
    project.grids.append(
        CalcGrid(
            id="g1",
            name="Grid",
            origin=(1.0, 1.0, 0.8),
            width=4.0,
            height=6.0,
            elevation=0.8,
            nx=5,
            ny=7,
            room_id="r1",
        )
    )


def test_missing_luminaire_warning() -> None:
    p = _project_base()
    _add_grid(p)
    issues = ProjectDiagnostics().check(p)
    errs = [i for i in issues if i.severity == "error"]
    assert any(i.code == "CAL-001" for i in errs)


def test_missing_grid_warning() -> None:
    p = _project_base()
    _add_asset_and_luminaire(p)
    issues = ProjectDiagnostics().check(p)
    errs = [i for i in issues if i.severity == "error"]
    assert any(i.code == "CAL-002" for i in errs)


def test_reflectance_out_of_range() -> None:
    p = _project_base()
    p.geometry.rooms[0].ceiling_reflectance = 1.5
    _add_asset_and_luminaire(p)
    _add_grid(p)
    issues = ProjectDiagnostics().check(p)
    assert any(i.severity == "warning" and "reflectance" in i.message for i in issues)


def test_mounting_height_above_ceiling() -> None:
    p = _project_base()
    _add_asset_and_luminaire(p, z=4.0)
    _add_grid(p)
    issues = ProjectDiagnostics().check(p)
    assert any(i.severity == "warning" and "above the room ceiling" in i.message for i in issues)


def test_valid_project_no_issues() -> None:
    p = _project_base()
    _add_asset_and_luminaire(p)
    _add_grid(p)
    issues = ProjectDiagnostics().check(p)
    assert issues == []


def test_error_codes_all_documented() -> None:
    assert ERROR_CODES
    assert all(str(k).strip() for k in ERROR_CODES.keys())
    assert all(str(v).strip() for v in ERROR_CODES.values())
