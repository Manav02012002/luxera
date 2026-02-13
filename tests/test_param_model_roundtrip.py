from __future__ import annotations

from pathlib import Path

from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, SlabParam, WallParam, ZoneParam
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import Project


def test_param_model_roundtrip(tmp_path: Path) -> None:
    project = Project(name="param-roundtrip")
    project.param.footprints.append(FootprintParam(id="fp1", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]))
    project.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.0, wall_thickness=0.2, name="Room 1"))
    project.param.walls.append(WallParam(id="w1", room_id="r1", edge_ref=(0, 1), thickness=0.2))
    project.param.openings.append(OpeningParam(id="o1", wall_id="w1", anchor=0.5, width=1.2, height=1.5, sill=0.9, type="window"))
    project.param.slabs.append(SlabParam(id="s1", room_id="r1", thickness=0.2, elevation=0.0))
    project.param.zones.append(ZoneParam(id="z1", room_id="r1", polygon2d=[(0.0, 0.0), (2.0, 0.0), (2.0, 1.5), (0.0, 1.5)], rule_pack_id="office"))

    p = tmp_path / "project.luxera.json"
    save_project_schema(project, p)
    loaded = load_project_schema(p)

    assert len(loaded.param.footprints) == 1
    assert len(loaded.param.rooms) == 1
    assert len(loaded.param.walls) == 1
    assert len(loaded.param.openings) == 1
    assert len(loaded.param.slabs) == 1
    assert len(loaded.param.zones) == 1
    assert loaded.param.rooms[0].footprint_id == "fp1"
    assert loaded.param.walls[0].edge_ref == (0, 1)

