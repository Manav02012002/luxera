from __future__ import annotations

from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.ops.scene_ops import create_room_from_footprint, create_walls_from_footprint, edit_wall_and_propagate_adjacency, place_opening_on_wall
from luxera.ops.transactions import get_transaction_manager
from luxera.project.schema import Project


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


def test_scene_ops_create_one_transaction_per_op_and_undo_redo() -> None:
    p = Project(name="ops-tx")
    tx = get_transaction_manager(p)

    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], height=3.0)
    assert tx.undo_depth == 1

    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    assert tx.undo_depth == 2

    before = _state_geometry_and_calc(p)
    place_opening_on_wall(
        p,
        opening_id="o1",
        host_surface_id=walls[0].id,
        width=1.0,
        height=1.2,
        sill_height=0.8,
        distance_from_corner=0.5,
    )
    assert tx.undo_depth == 3
    assert tx.undo() is True
    assert _state_geometry_and_calc(p) == before
    assert tx.redo() is True
    assert any(o.id == "o1" for o in p.geometry.openings)


def test_vertex_drag_edit_is_single_transaction_and_restorable() -> None:
    p = Project(name="drag-tx")
    tx = get_transaction_manager(p)
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], height=3.0)
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    wall = walls[0]
    before = _state_geometry_and_calc(p)

    d0 = tx.undo_depth
    edit_wall_and_propagate_adjacency(p, wall_id=wall.id, new_start=(0.0, 0.0, 0.0), new_end=(5.0, 0.0, 0.0))
    assert tx.undo_depth == d0 + 1
    assert tx.undo() is True
    assert _state_geometry_and_calc(p) == before


def test_calc_ops_are_transactional() -> None:
    p = Project(name="calc-tx")
    tx = get_transaction_manager(p)
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], height=3.0)
    before = _state_geometry_and_calc(p)

    create_calc_grid_from_room(p, grid_id="g1", name="G1", room_id="r1", elevation=0.8, spacing=1.0)
    assert tx.undo_depth >= 2
    assert any(g.id == "g1" for g in p.grids)

    assert tx.undo() is True
    # Undo last op only (grid create).
    assert _state_geometry_and_calc(p) == before
