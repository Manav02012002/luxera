from __future__ import annotations

from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.project.schema import OpeningSpec, Project, RoomSpec, SurfaceSpec


def test_calc_grid_optional_near_opening_mask() -> None:
    p = Project(name="grid-opening-mask")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=4.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="w1",
            name="Wall",
            kind="wall",
            room_id="r1",
            vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
        )
    )
    p.geometry.openings.append(
        OpeningSpec(
            id="o1",
            name="Win",
            opening_type="window",
            kind="window",
            host_surface_id="w1",
            vertices=[(1.5, 0.0, 1.0), (2.5, 0.0, 1.0), (2.5, 0.0, 2.0), (1.5, 0.0, 2.0)],
        )
    )

    g0 = create_calc_grid_from_room(
        p,
        grid_id="g0",
        name="NoMask",
        room_id="r1",
        elevation=0.8,
        spacing=0.5,
        margin=0.0,
        mask_near_openings=False,
        opening_mask_margin=0.4,
    )
    g1 = create_calc_grid_from_room(
        p,
        grid_id="g1",
        name="Mask",
        room_id="r1",
        elevation=0.8,
        spacing=0.5,
        margin=0.0,
        mask_near_openings=True,
        opening_mask_margin=0.4,
    )
    assert len(g1.sample_points) < len(g0.sample_points)
