from __future__ import annotations

from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.ops.delta import apply_delta, invert
from luxera.ops.diff import diff_project
from luxera.ops.scene_ops import create_room_from_footprint, create_walls_from_footprint, edit_wall_and_propagate_adjacency, place_opening_on_wall
from luxera.project.io import _project_from_dict  # type: ignore[attr-defined]
from luxera.project.schema import Project


def _clone(p: Project) -> Project:
    return _project_from_dict(p.to_dict())


def _state_geometry_and_calc(p: Project) -> dict:
    rooms = sorted([r.__dict__.copy() for r in p.geometry.rooms], key=lambda x: str(x.get("id", "")))
    surfaces = sorted([s.__dict__.copy() for s in p.geometry.surfaces], key=lambda x: str(x.get("id", "")))
    openings = sorted([o.__dict__.copy() for o in p.geometry.openings], key=lambda x: str(x.get("id", "")))
    grids = sorted([g.__dict__.copy() for g in p.grids], key=lambda x: str(x.get("id", "")))
    return {
        "rooms": rooms,
        "surfaces": surfaces,
        "openings": openings,
        "grids": grids,
    }


def test_delta_invert_restores_room_edit() -> None:
    p = Project(name="delta-room")
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], height=3.0)
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    wall = walls[0]

    before_full = p.to_dict()
    before = _state_geometry_and_calc(p)
    edit_wall_and_propagate_adjacency(p, wall_id=wall.id, new_start=(0.0, 0.0, 0.0), new_end=(5.0, 0.0, 0.0))
    after = p.to_dict()

    d = diff_project(before_full, after)
    q = _clone(p)
    apply_delta(q, invert(d))
    assert _state_geometry_and_calc(q) == before


def test_delta_invert_restores_opening_edit() -> None:
    p = Project(name="delta-opening")
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], height=3.0)
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)

    before_full = p.to_dict()
    before = _state_geometry_and_calc(p)
    place_opening_on_wall(
        p,
        opening_id="o1",
        host_surface_id=walls[0].id,
        width=1.0,
        height=1.2,
        sill_height=0.8,
        distance_from_corner=0.5,
        opening_type="window",
        glazing_material_id="glass",
    )
    after = p.to_dict()

    d = diff_project(before_full, after)
    q = _clone(p)
    apply_delta(q, invert(d))
    assert _state_geometry_and_calc(q) == before


def test_delta_invert_restores_calc_grid_edit() -> None:
    p = Project(name="delta-grid")
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], height=3.0)
    before_full = p.to_dict()
    before = _state_geometry_and_calc(p)
    create_calc_grid_from_room(p, grid_id="g1", name="G1", room_id="r1", elevation=0.8, spacing=1.0)
    after = _state_geometry_and_calc(p)

    d = diff_project(before_full, p.to_dict())
    q = _clone(p)
    apply_delta(q, invert(d))
    assert _state_geometry_and_calc(q) == before
    apply_delta(q, d)
    assert _state_geometry_and_calc(q) == after
