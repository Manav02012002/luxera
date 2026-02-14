from __future__ import annotations

from pathlib import Path

from luxera.geometry.param.model import (
    FootprintHoleParam,
    FootprintParam,
    InstanceParam,
    OpeningParam,
    RoomParam,
    SlabParam,
    WallParam,
    ZoneParam,
)
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import Project


def test_param_model_roundtrip(tmp_path: Path) -> None:
    project = Project(name="param-roundtrip")
    project.param.footprints.append(
        FootprintParam(
            id="fp1",
            polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
            vertex_ids=["v0", "v1", "v2", "v3"],
            edge_ids=["e0", "e1", "e2", "e3"],
            holes=[FootprintHoleParam(id="h1", polygon2d=[(1.0, 1.0), (1.5, 1.0), (1.5, 1.5), (1.0, 1.5)])],
            edge_bulges={"e1": 0.25},
        )
    )
    project.param.rooms.append(
        RoomParam(
            id="r1",
            footprint_id="fp1",
            height=3.0,
            wall_thickness=0.2,
            wall_thickness_policy="inside",
            floor_slab_thickness=0.15,
            ceiling_slab_thickness=0.12,
            floor_offset=0.02,
            ceiling_offset=-0.01,
            name="Room 1",
        )
    )
    project.param.walls.append(WallParam(id="w1", room_id="r1", edge_ref=(0, 1), edge_id="e0", thickness=0.2, finish_thickness=0.01))
    project.param.openings.append(
        OpeningParam(
            id="o1",
            wall_id="w1",
            host_wall_id="w1",
            anchor=0.5,
            anchor_mode="from_start_distance",
            from_start_distance=0.4,
            width=1.2,
            height=1.5,
            sill=0.9,
            polygon2d=[],
            type="window",
            glazing_material_id="glass_a",
            visible_transmittance=0.62,
        )
    )
    project.param.slabs.append(SlabParam(id="s1", room_id="r1", thickness=0.2, elevation=0.0))
    project.param.zones.append(
        ZoneParam(
            id="z1",
            room_id="r1",
            polygon2d=[(0.0, 0.0), (2.0, 0.0), (2.0, 1.5), (0.0, 1.5)],
            holes2d=[[(0.2, 0.2), (0.4, 0.2), (0.4, 0.4), (0.2, 0.4)]],
            rule_pack_id="office",
        )
    )
    project.param.instances.append(InstanceParam(id="i1", symbol_id="chair", position=(1.0, 1.0, 0.0), rotation_deg=(0.0, 0.0, 45.0), scale=(1.0, 1.0, 1.0)))

    p = tmp_path / "project.luxera.json"
    save_project_schema(project, p)
    loaded = load_project_schema(p)

    assert len(loaded.param.footprints) == 1
    assert len(loaded.param.rooms) == 1
    assert len(loaded.param.walls) == 1
    assert len(loaded.param.openings) == 1
    assert len(loaded.param.slabs) == 1
    assert len(loaded.param.zones) == 1
    assert len(loaded.param.instances) == 1
    assert loaded.param.rooms[0].footprint_id == "fp1"
    assert loaded.param.walls[0].edge_ref == (0, 1)
    assert loaded.param.footprints[0].edge_bulges["e1"] == 0.25
    assert loaded.param.rooms[0].wall_thickness_policy == "inside"
    assert loaded.param.openings[0].anchor_mode == "from_start_distance"
    assert loaded.param.openings[0].glazing_material_id == "glass_a"
    assert loaded.param.openings[0].visible_transmittance == 0.62
