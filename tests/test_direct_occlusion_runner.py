from pathlib import Path

from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
    SurfaceSpec,
)
from luxera.runner import run_job_in_memory as run_job


def test_runner_direct_occlusion_changes_result(tmp_path: Path):
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 600 200
""",
        encoding="utf-8",
    )

    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))

    p_open = Project(name="open", root_dir=str(tmp_path))
    p_open.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    p_open.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, 3.0), rotation=rot),
        )
    )
    p_open.grids.append(CalcGrid(id="g1", name="g", origin=(0.0, 0.0, 0.0), width=0.01, height=0.01, elevation=0.0, nx=1, ny=1))
    p_open.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": False}))
    r_open = run_job(p_open, "j1")
    open_mean = r_open.summary["mean_lux"]

    p_blk = Project(name="blocked", root_dir=str(tmp_path))
    p_blk.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    p_blk.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, 3.0), rotation=rot),
        )
    )
    p_blk.grids.append(CalcGrid(id="g1", name="g", origin=(0.0, 0.0, 0.0), width=0.01, height=0.01, elevation=0.0, nx=1, ny=1))
    p_blk.geometry.surfaces.append(
        SurfaceSpec(
            id="blk",
            name="Blocker",
            kind="custom",
            vertices=[(-0.5, -0.5, 1.5), (0.5, -0.5, 1.5), (0.5, 0.5, 1.5), (-0.5, 0.5, 1.5)],
        )
    )
    p_blk.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": True}))
    r_blk = run_job(p_blk, "j1")
    blocked_mean = r_blk.summary["mean_lux"]

    assert open_mean > blocked_mean
    assert r_blk.summary["occlusion_enabled"] is True
    assert r_blk.summary["occluder_count"] >= 1
