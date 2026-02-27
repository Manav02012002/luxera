from __future__ import annotations

import json
from pathlib import Path

from luxera.parity.invariance import run_invariance_for_scene
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def test_invariance_runner_passes_on_simple_direct_scene(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="inv", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3, room_id="r1"))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=42, settings={"use_occlusion": False}))

    scene = tmp_path / "scene.lux.json"
    save_project_schema(p, scene)

    inv = run_invariance_for_scene(
        scene,
        job_ids=["j1"],
        out_dir=tmp_path / "inv_out",
        transforms=("translate_large", "rotate_z_90", "unit_mm"),
    )
    assert inv.transforms_checked == 3
    assert inv.passed
    assert not inv.mismatches


def test_invariance_report_contains_transform_details(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="inv2", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3, room_id="r1"))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=42, settings={"use_occlusion": False}))

    scene = tmp_path / "scene2.lux.json"
    save_project_schema(p, scene)

    inv = run_invariance_for_scene(scene, job_ids=["j1"], out_dir=tmp_path / "inv_out2")
    details_path = tmp_path / "details.json"
    details_path.write_text(json.dumps(inv.details, indent=2, sort_keys=True), encoding="utf-8")
    loaded = json.loads(details_path.read_text(encoding="utf-8"))
    assert "transforms" in loaded
    assert "translate_large" in loaded["transforms"]
    assert "rotate_z_90" in loaded["transforms"]
    assert "unit_mm" in loaded["transforms"]
