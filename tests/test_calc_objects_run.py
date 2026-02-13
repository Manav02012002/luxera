from __future__ import annotations

from pathlib import Path

from luxera.project.io import save_project_schema
from luxera.project.schema import (
    ArbitraryPlaneSpec,
    JobSpec,
    LineGridSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)
from luxera.runner import run_job


def test_direct_job_runs_arbitrary_and_line_objects(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="calc-objects", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=4.0, height=3.0))
    p.arbitrary_planes.append(
        ArbitraryPlaneSpec(
            id="ap1",
            name="AP",
            origin=(0.5, 0.5, 0.8),
            axis_u=(1.0, 0.0, 0.0),
            axis_v=(0.0, 0.8, 0.6),
            width=2.0,
            height=1.0,
            nx=4,
            ny=3,
            room_id="r1",
        )
    )
    p.line_grids.append(LineGridSpec(id="lg1", name="LG", polyline=[(0.0, 0.0, 0.8), (3.0, 3.0, 0.8)], spacing=0.5, room_id="r1"))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=0))
    pp = tmp_path / "p.json"
    save_project_schema(p, pp)
    ref = run_job(pp, "j1")
    assert int(ref.summary.get("calc_object_count", 0)) == 2

