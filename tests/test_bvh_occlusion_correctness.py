from __future__ import annotations

from pathlib import Path

from luxera.engine.direct_illuminance import (
    build_direct_occlusion_context,
    load_luminaires,
    run_direct_grid,
)
from luxera.project.schema import (
    CalcGrid,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RotationSpec,
    SurfaceSpec,
    TransformSpec,
)


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


def _base_project(tmp_path: Path) -> Project:
    ies = _ies_fixture(tmp_path / "bvh_test.ies")
    p = Project(name="BVH Occlusion", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, 2.0), rotation=rot),
        )
    )
    return p


def test_blocker_plane_occludes_center_point(tmp_path: Path):
    p = _base_project(tmp_path)
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="blocker",
            name="Blocker",
            kind="custom",
            vertices=[
                (-0.6, -0.6, 1.0),
                (0.6, -0.6, 1.0),
                (0.6, 0.6, 1.0),
                (-0.6, 0.6, 1.0),
            ],
        )
    )
    luminaires, _ = load_luminaires(p, lambda a: "hash")
    occlusion = build_direct_occlusion_context(p, include_room_shell=False, occlusion_epsilon=1e-6)
    assert occlusion.bvh is not None

    grid = CalcGrid(id="g1", name="g1", origin=(0.0, 0.0, 0.0), width=0.0, height=0.0, elevation=0.0, nx=1, ny=1)
    blocked = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=True, occlusion_epsilon=1e-6)
    open_res = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=False, occlusion_epsilon=1e-6)
    assert blocked.values[0] == 0.0
    assert open_res.values[0] > 0.0


def test_point_outside_blocker_is_not_occluded(tmp_path: Path):
    p = _base_project(tmp_path)
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="blocker",
            name="Blocker",
            kind="custom",
            vertices=[
                (-0.4, -0.4, 1.0),
                (0.4, -0.4, 1.0),
                (0.4, 0.4, 1.0),
                (-0.4, 0.4, 1.0),
            ],
        )
    )
    luminaires, _ = load_luminaires(p, lambda a: "hash")
    occlusion = build_direct_occlusion_context(p, include_room_shell=False, occlusion_epsilon=1e-6)

    grid = CalcGrid(id="g1", name="g1", origin=(2.0, 0.0, 0.0), width=0.0, height=0.0, elevation=0.0, nx=1, ny=1)
    blocked = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=True, occlusion_epsilon=1e-6)
    open_res = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=False, occlusion_epsilon=1e-6)
    assert blocked.values[0] > 0.0
    assert abs(blocked.values[0] - open_res.values[0]) / max(open_res.values[0], 1e-9) < 1e-9


def test_grazing_ray_epsilon_stability(tmp_path: Path):
    p = _base_project(tmp_path)
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="blocker",
            name="Blocker",
            kind="custom",
            vertices=[
                (0.0, -0.5, 1.0),
                (0.0, 0.5, 1.0),
                (0.0, 0.5, 2.0),
                (0.0, -0.5, 2.0),
            ],
        )
    )
    luminaires, _ = load_luminaires(p, lambda a: "hash")
    occlusion = build_direct_occlusion_context(p, include_room_shell=False, occlusion_epsilon=1e-6)
    grid = CalcGrid(id="g1", name="g1", origin=(1.0, 0.51, 1.0), width=0.0, height=0.0, elevation=1.0, nx=1, ny=1)
    v1 = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=True, occlusion_epsilon=1e-9).values[0]
    v2 = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=True, occlusion_epsilon=1e-5).values[0]
    assert v1 >= 0.0 and v2 >= 0.0
    if max(v1, v2) > 1e-9:
        assert abs(v1 - v2) / max(v1, v2) < 1e-3


def test_point_on_blocker_surface_no_self_hit(tmp_path: Path):
    p = _base_project(tmp_path)
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="blocker",
            name="Blocker",
            kind="custom",
            vertices=[
                (-0.8, -0.8, 1.0),
                (0.8, -0.8, 1.0),
                (0.8, 0.8, 1.0),
                (-0.8, 0.8, 1.0),
            ],
        )
    )
    luminaires, _ = load_luminaires(p, lambda a: "hash")
    occlusion = build_direct_occlusion_context(p, include_room_shell=False, occlusion_epsilon=1e-6)
    # Point lies on blocker plane; endpoint intersection should not be treated as occluded.
    grid = CalcGrid(id="g1", name="g1", origin=(0.0, 0.0, 1.0), width=0.0, height=0.0, elevation=1.0, nx=1, ny=1)
    blocked = run_direct_grid(grid, luminaires, occlusion=occlusion, use_occlusion=True, occlusion_epsilon=1e-6).values[0]
    assert blocked > 0.0
