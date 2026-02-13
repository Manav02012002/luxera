from __future__ import annotations

from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, WallParam
from luxera.geometry.param.rebuild import rebuild_surfaces_for_room
from luxera.ops.scene_ops import place_opening_on_wall
from luxera.project.schema import Project, SurfaceSpec


def test_authored_opening_subtraction_on_rotated_wall_creates_real_void_parts() -> None:
    p = Project(name="authored-opening")
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="wall_diag",
            name="Diag Wall",
            kind="wall",
            vertices=[(0.0, 0.0, 0.0), (3.0, 2.0, 0.0), (3.0, 2.0, 3.0), (0.0, 0.0, 3.0)],
        )
    )

    opening, glazing = place_opening_on_wall(
        p,
        opening_id="o1",
        host_surface_id="wall_diag",
        width=1.0,
        height=1.2,
        sill_height=0.8,
        distance_from_corner=0.7,
        opening_type="window",
        glazing_material_id="glass",
    )

    assert opening.host_surface_id == "wall_diag"
    assert glazing is not None
    wall_parts = [s for s in p.geometry.surfaces if s.id == "wall_diag" or s.id.startswith("wall_diag:part") or s.id.startswith("wall_diag:tri")]
    assert len(wall_parts) >= 2


def test_authored_opening_subtraction_handles_hole_case_via_triangulation() -> None:
    p = Project(name="authored-opening-hole")
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="wall_poly",
            name="Poly Wall",
            kind="wall",
            vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 1.5, 0.0), (2.5, 3.0, 0.0), (0.0, 3.0, 0.0)],
        )
    )
    place_opening_on_wall(
        p,
        opening_id="o_hole",
        host_surface_id="wall_poly",
        width=1.0,
        height=1.0,
        sill_height=0.8,
        distance_from_corner=1.5,
        opening_type="window",
        glazing_material_id="glass",
    )
    wall_parts = [s for s in p.geometry.surfaces if s.id == "wall_poly" or s.id.startswith("wall_poly:tri") or s.id.startswith("wall_poly:part")]
    assert len(wall_parts) >= 3


def test_param_rebuild_opening_uses_same_subtraction_path() -> None:
    p = Project(name="param-opening")
    p.param.footprints.append(FootprintParam(id="fp1", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]))
    p.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.0))
    p.param.walls.append(WallParam(id="w01", room_id="r1", edge_ref=(0, 1)))
    p.param.openings.append(OpeningParam(id="o1", wall_id="w01", anchor=0.5, width=1.0, height=1.2, sill=0.8))

    rebuild_surfaces_for_room("r1", p)
    wall_parts = [s for s in p.geometry.surfaces if s.kind == "wall" and s.room_id == "r1"]
    assert len(wall_parts) >= 2
