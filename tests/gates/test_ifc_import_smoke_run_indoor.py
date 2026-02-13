from __future__ import annotations

from pathlib import Path

from luxera.io.geometry_import import import_geometry_file
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.runner import run_job_in_memory as run_job


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


def test_ifc_import_smoke_run_indoor(tmp_path: Path) -> None:
    ifc_path = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    ies_path = _ies_fixture(tmp_path / "smoke.ies")
    res = import_geometry_file(str(ifc_path), fmt="IFC")

    p = Project(name="IFCSmoke", root_dir=str(tmp_path))
    p.geometry.rooms.extend(res.rooms)
    p.geometry.surfaces.extend(res.surfaces)
    p.geometry.openings.extend(res.openings)
    p.geometry.levels.extend(res.levels)
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    room = p.geometry.rooms[0]
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(room.origin[0] + room.width * 0.5, room.origin[1] + room.length * 0.5, room.origin[2] + room.height - 0.2), rotation=rot),
        )
    )
    p.grids.append(
        CalcGrid(
            id="g1",
            name="grid",
            origin=room.origin,
            width=room.width,
            height=room.length,
            elevation=room.origin[2] + 0.8,
            nx=4,
            ny=4,
            room_id=room.id,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": False}))
    save_project_schema(p, tmp_path / "p.json")

    ref = run_job(p, "j1")
    assert "mean_lux" in ref.summary
