from __future__ import annotations

from pathlib import Path

from luxera.ops.calc_ops import create_calc_grid_from_room, create_point_set, create_vertical_plane, create_workplane
from luxera.ops.scene_ops import (
    add_opening,
    assign_material_to_surface_set,
    create_room,
    create_wall_polygon,
    ensure_material,
    extrude_room_to_surfaces,
)
from luxera.project.io import save_project_schema
from luxera.project.schema import JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.runner import run_job


def test_scene_ops_can_build_room_and_run_calc(tmp_path: Path) -> None:
    project = Project(name="ops-room", root_dir=str(tmp_path))
    room = create_room(project, room_id="r1", name="Room", width=4.0, length=5.0, height=3.0)
    surfaces = extrude_room_to_surfaces(project, room.id, replace_existing=True)
    mat = ensure_material(
        project,
        material_id="mat_wall",
        name="Wall",
        reflectance=0.5,
        diffuse_reflectance_rgb=(0.5, 0.5, 0.5),
        specular_reflectance=0.05,
        transmittance=0.0,
    )
    assigned = assign_material_to_surface_set(project, surface_ids=[s.id for s in surfaces if s.kind == "wall"], material_id=mat.id)
    assert assigned >= 1
    assert create_wall_polygon(
        project,
        surface_id="w_extra",
        name="Divider",
        vertices=[(2.0, 1.0, 0.0), (2.0, 4.0, 0.0), (2.0, 4.0, 2.4), (2.0, 1.0, 2.4)],
        room_id="r1",
        material_id=mat.id,
    ).id == "w_extra"
    assert add_opening(
        project,
        opening_id="o1",
        name="Window",
        host_surface_id=f"{room.id}_wall_south",
        vertices=[(1.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.0), (1.0, 0.0, 2.0)],
        opening_type="window",
        visible_transmittance=0.6,
    ).id == "o1"

    create_workplane(project, workplane_id="wp1", name="WP", elevation=0.8, margin=0.3, spacing=0.5, room_id="r1")
    create_calc_grid_from_room(project, grid_id="g1", name="Grid", room_id="r1", elevation=0.8, spacing=1.0, margin=0.5)
    create_vertical_plane(project, plane_id="vp1", name="VP", origin=(0.0, 0.0, 0.0), width=2.0, height=2.0, nx=3, ny=3, room_id="r1")
    create_point_set(project, point_set_id="ps1", name="PS", points=[(1.0, 1.0, 0.8), (2.0, 2.0, 0.8)], room_id="r1")

    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.5, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    project.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", settings={"use_occlusion": True}, seed=0))
    p = tmp_path / "p.json"
    save_project_schema(project, p)
    ref = run_job(p, "j1")
    assert ref.summary.get("mean_lux", 0.0) >= 0.0

