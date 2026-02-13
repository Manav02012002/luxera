from __future__ import annotations

from luxera.ops.scene_ops import (
    create_room_from_footprint,
    create_walls_from_footprint,
    edit_wall_and_propagate_adjacency,
    place_opening_on_wall,
)
from luxera.project.schema import Project, SurfaceSpec


def test_create_room_and_walls_shared_adjacency() -> None:
    p = Project(name="authoring")
    create_room_from_footprint(
        p,
        room_id="r1",
        name="R1",
        footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        height=3.0,
    )
    create_room_from_footprint(
        p,
        room_id="r2",
        name="R2",
        footprint=[(4.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0)],
        height=3.0,
    )
    w1 = create_walls_from_footprint(p, room_id="r1", thickness=0.2, shared_walls=True)
    w2 = create_walls_from_footprint(p, room_id="r2", thickness=0.2, shared_walls=True)
    assert len(w1) == 4
    # Shared boundary should avoid one duplicate wall.
    assert len(w2) == 3


def test_place_window_opening_subtracts_wall_and_adds_glazing() -> None:
    p = Project(name="openings")
    create_room_from_footprint(
        p,
        room_id="r1",
        name="R1",
        footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        height=3.0,
    )
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    host = walls[0]
    opening, glazing = place_opening_on_wall(
        p,
        opening_id="w1",
        host_surface_id=host.id,
        width=1.0,
        height=1.2,
        sill_height=0.8,
        distance_from_corner=0.5,
        opening_type="window",
        glazing_material_id="glass",
    )
    assert opening.host_surface_id == host.id
    assert glazing is not None
    assert any(s.id.startswith(host.id) for s in p.geometry.surfaces)
    assert any(s.id == "w1:glazing" for s in p.geometry.surfaces)


def test_edit_wall_propagates_to_adjacent_room_footprints() -> None:
    p = Project(name="adj")
    create_room_from_footprint(
        p,
        room_id="r1",
        name="R1",
        footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        height=3.0,
    )
    create_room_from_footprint(
        p,
        room_id="r2",
        name="R2",
        footprint=[(4.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0)],
        height=3.0,
    )
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    shared = next(w for w in walls if w.vertices[1][0] == 4.0 and w.vertices[0][0] == 4.0)
    edit_wall_and_propagate_adjacency(
        p,
        wall_id=shared.id,
        new_start=(4.2, 0.0, 0.0),
        new_end=(4.2, 4.0, 0.0),
    )
    r1 = next(r for r in p.geometry.rooms if r.id == "r1")
    r2 = next(r for r in p.geometry.rooms if r.id == "r2")
    assert any(abs(x - 4.2) < 1e-9 for x, _y in r1.footprint or [])
    assert any(abs(x - 4.2) < 1e-9 for x, _y in r2.footprint or [])


def test_place_opening_on_non_axis_aligned_wall() -> None:
    p = Project(name="diag")
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="wall_diag",
            name="Diag Wall",
            kind="wall",
            vertices=[(0.0, 0.0, 0.0), (2.0, 2.0, 0.0), (2.0, 2.0, 3.0), (0.0, 0.0, 3.0)],
        )
    )
    op, glazing = place_opening_on_wall(
        p,
        opening_id="diag_w1",
        host_surface_id="wall_diag",
        width=0.8,
        height=1.0,
        sill_height=0.9,
        distance_from_corner=0.4,
        opening_type="window",
        glazing_material_id="glass",
    )
    assert op.host_surface_id == "wall_diag"
    assert glazing is not None
    # Host wall replaced by strips.
    assert any(s.id.startswith("wall_diag") for s in p.geometry.surfaces)
