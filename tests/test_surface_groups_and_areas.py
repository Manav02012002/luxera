from __future__ import annotations

from luxera.geometry.areas import area_by_kind, area_by_room, area_by_surface_group, surface_area
from luxera.project.schema import Project, RoomSpec, SurfaceSpec
from luxera.scene.surface_groups import (
    resolve_surface_set,
    select_all_ceilings_on_storey,
    select_all_walls_in_room,
    select_by_tag_layer_material,
)


def test_surface_group_selectors() -> None:
    p = Project(name="sel")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=4.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0), level_id="L1"))
    p.geometry.rooms.append(RoomSpec(id="r2", name="R2", width=4.0, length=4.0, height=3.0, origin=(4.0, 0.0, 0.0), level_id="L1"))
    p.geometry.surfaces.extend(
        [
            SurfaceSpec(id="w1", name="W1", kind="wall", room_id="r1", material_id="m1", layer="WALL", tags=["north"], vertices=[(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)]),
            SurfaceSpec(id="c1", name="C1", kind="ceiling", room_id="r1", material_id="m2", layer="CEIL", tags=["A"], vertices=[(0, 0, 3), (4, 0, 3), (4, 4, 3), (0, 4, 3)]),
            SurfaceSpec(id="c2", name="C2", kind="ceiling", room_id="r2", material_id="m2", layer="CEIL", tags=["B"], vertices=[(4, 0, 3), (8, 0, 3), (8, 4, 3), (4, 4, 3)]),
        ]
    )
    s1 = select_all_walls_in_room(p, "r1")
    s2 = select_all_ceilings_on_storey(p, "L1")
    s3 = select_by_tag_layer_material(p, tags_any=["north"], layer="WALL", material_id="m1")
    merged = resolve_surface_set(p, [s1, s2, s3])
    assert "w1" in s1.ids
    assert "c1" in s2.ids and "c2" in s2.ids
    assert s3.ids == ["w1"]
    assert sorted(merged.ids) == ["c1", "c2", "w1"]


def test_surface_area_group_and_room_totals() -> None:
    p = Project(name="areas")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R1", width=2.0, length=2.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    s = SurfaceSpec(id="f1", name="F", kind="floor", room_id="r1", vertices=[(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    p.geometry.surfaces.append(s)
    assert abs(surface_area(s) - 4.0) < 1e-9
    assert abs(area_by_surface_group(p, ["f1"]) - 4.0) < 1e-9
    by_room = area_by_room(p)
    assert abs(by_room["r1"] - 4.0) < 1e-9
    by_kind = area_by_kind(p, room_id="r1")
    assert abs(by_kind["floor"] - 4.0) < 1e-9

