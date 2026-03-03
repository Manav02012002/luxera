from __future__ import annotations

import numpy as np

from luxera.engine.radiosity.adaptive_mesh import AdaptiveRadiosityMesh
from luxera.engine.radiosity.solver import RadiosityConfig, solve_radiosity
from luxera.geometry.core import Material, Room, Vector3


def _room_surfaces(width: float = 4.0, length: float = 4.0, height: float = 3.0):
    room = Room.rectangular(
        name="adaptive_room",
        width=width,
        length=length,
        height=height,
        origin=Vector3(0.0, 0.0, 0.0),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.75),
    )
    return room.get_surfaces()


def test_proximity_refinement() -> None:
    surfaces = _room_surfaces(4.0, 4.0, 3.0)
    lum = np.array([2.0, 2.0, 2.9], dtype=float)
    mesher = AdaptiveRadiosityMesh(
        initial_max_area=1.0,
        refined_max_area=0.1,
        luminaire_proximity_m=2.0,
        gradient_threshold=0.3,
        max_refinement_passes=2,
    )

    adaptive = mesher.create_adaptive_mesh(surfaces, [lum])
    uniform_count = sum(len(s.polygon.subdivide(1.0)) if s.area > 1.0 else 1 for s in surfaces)

    assert len(adaptive) > uniform_count

    dists = np.array([np.linalg.norm(np.array(p.centroid.to_tuple(), dtype=float) - lum) for p in adaptive], dtype=float)
    areas = np.array([float(p.area) for p in adaptive], dtype=float)
    near = areas[dists < 1.25]
    far = areas[dists > 2.5]
    assert near.size > 0 and far.size > 0
    assert float(np.mean(near)) < float(np.mean(far))


def test_gradient_refinement() -> None:
    surfaces = _room_surfaces(4.0, 4.0, 3.0)
    mesher = AdaptiveRadiosityMesh(initial_max_area=1.0, refined_max_area=0.2, gradient_threshold=0.2)
    patches = mesher.create_adaptive_mesh(surfaces, [np.array([2.0, 2.0, 2.9], dtype=float)])

    centers = np.array([p.centroid.to_tuple() for p in patches], dtype=float)
    radiosity = 1.0 + 2.0 * centers[:, 0]

    refined, warm = mesher.refine_by_gradient(patches, radiosity)
    assert len(refined) > len(patches)
    assert warm.shape[0] == len(refined)


def test_adaptive_vs_uniform_accuracy() -> None:
    surfaces = _room_surfaces(4.0, 4.0, 3.0)
    direct = {s.id: 180.0 for s in surfaces}

    adaptive = solve_radiosity(
        surfaces,
        direct,
        config=RadiosityConfig(
            patch_max_area=0.3,
            max_iters=80,
            tol=1e-5,
            use_visibility=False,
            form_factor_method="analytic",
            adaptive_meshing=True,
            adaptive_luminaire_positions=[(2.0, 2.0, 2.9)],
            seed=7,
        ),
    )
    uniform = solve_radiosity(
        surfaces,
        direct,
        config=RadiosityConfig(
            patch_max_area=0.16,
            max_iters=80,
            tol=1e-5,
            use_visibility=False,
            form_factor_method="analytic",
            adaptive_meshing=False,
            seed=7,
        ),
    )

    e_ad = float(np.mean(adaptive.irradiance))
    e_un = float(np.mean(uniform.irradiance))
    assert e_un > 1e-9
    assert abs(e_ad - e_un) / e_un < 0.10
    assert len(adaptive.patches) < len(uniform.patches)


def test_total_area_preserved() -> None:
    surfaces = _room_surfaces(4.0, 4.0, 3.0)
    mesher = AdaptiveRadiosityMesh(initial_max_area=1.0, refined_max_area=0.1, luminaire_proximity_m=2.0)
    patches = mesher.create_adaptive_mesh(surfaces, [np.array([2.0, 2.0, 2.9], dtype=float)])

    area_src = sum(float(s.area) for s in surfaces)
    area_patch = sum(float(p.area) for p in patches)
    assert abs(area_src - area_patch) <= 1e-6 * max(1.0, area_src)


def test_parent_tracking() -> None:
    surfaces = _room_surfaces(4.0, 4.0, 3.0)
    mesher = AdaptiveRadiosityMesh(initial_max_area=1.0, refined_max_area=0.1, luminaire_proximity_m=2.0)
    patches = mesher.create_adaptive_mesh(surfaces, [np.array([2.0, 2.0, 2.9], dtype=float)])

    source_ids = {s.id for s in surfaces}
    assert patches
    for p in patches:
        parent = str(p.id).split("__patch_", 1)[0]
        assert parent in source_ids
