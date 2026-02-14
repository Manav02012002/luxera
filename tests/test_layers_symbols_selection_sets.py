from __future__ import annotations

from pathlib import Path

from luxera.geometry.drafting import PlanLineworkPolicy, plan_view_primitives
from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, WallParam
from luxera.geometry.param.identity import surface_id_for_wall_side
from luxera.geometry.param.rebuild import rebuild
from luxera.geometry.selection_sets import (
    query_all_walls_in_room,
    query_by_layer,
    query_by_material,
    query_by_tag,
    upsert_selection_set,
)
from luxera.geometry.symbols import all_symbol_placements
from luxera.geometry.views.cutplane import PlanView
from luxera.io.dxf_export_pro import export_plan_to_dxf_pro
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import (
    BlockInstanceSpec,
    LayerSpec,
    LuminaireInstance,
    Project,
    RotationSpec,
    SelectionSetSpec,
    SurfaceSpec,
    Symbol2DSpec,
    TransformSpec,
)


def test_layer_system_visibility_respected_by_plan_generation() -> None:
    p = Project(name="layers")
    p.layers.append(LayerSpec(id="hidden_wall", name="Hidden wall", visible=False, order=100))
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="w_hidden",
            name="W",
            kind="wall",
            layer_id="hidden_wall",
            vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
        )
    )
    prims = plan_view_primitives(p, PlanView(cut_z=1.2, range_zmin=0.0, range_zmax=3.0), policy=PlanLineworkPolicy())
    assert not prims


def test_symbol_blocks_and_luminaires_expand_to_placements_and_export(tmp_path: Path) -> None:
    p = Project(name="symbols")
    p.symbols_2d.append(Symbol2DSpec(id="B_EXIT", name="Exit", anchor=(0.1, -0.1), default_scale=1.2, layer_id="symbol"))
    p.block_instances.append(BlockInstanceSpec(id="bi1", symbol_id="B_EXIT", position=(5.0, 2.0), rotation_deg=30.0, scale=0.8))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1.0, 1.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(15.0, 0.0, 0.0))),
        )
    )
    placements = all_symbol_placements(p)
    ids = {x.id for x in placements}
    assert "lum:l1" in ids
    assert "block:bi1" in ids

    out = export_plan_to_dxf_pro(p, tmp_path / "symbols.dxf", cut_z=1.0, include_grids=False, include_luminaires=True)
    text = out.read_text(encoding="utf-8")
    assert "INSERT" in text
    assert "B_EXIT" in text or "LUM_SYMBOL" in text


def test_selection_set_queries_and_persistence_and_rebuild_remap(tmp_path: Path) -> None:
    p = Project(name="sel")
    p.geometry.surfaces.extend(
        [
            SurfaceSpec(id="w1", name="w1", kind="wall", room_id="r1", layer_id="wall", material_id="m1", tags=["perimeter"], vertices=[(0, 0, 0), (3, 0, 0), (3, 0, 3), (0, 0, 3)]),
            SurfaceSpec(id="c1", name="c1", kind="ceiling", room_id="r1", layer_id="ceiling_grid", material_id="m2", vertices=[(0, 0, 3), (3, 0, 3), (3, 3, 3), (0, 3, 3)]),
        ]
    )
    assert query_all_walls_in_room(p, "r1") == ["w1"]
    assert query_by_material(p, "m1") == ["w1"]
    assert query_by_tag(p, "perimeter") == ["w1"]
    assert query_by_layer(p, "wall") == ["w1"]

    upsert_selection_set(p, SelectionSetSpec(id="ss1", name="WallsR1", query="walls_in_room:r1"))
    assert p.selection_sets[0].object_ids == ["w1"]
    pj = tmp_path / "s.json"
    save_project_schema(p, pj)
    loaded = load_project_schema(pj)
    assert loaded.selection_sets[0].id == "ss1"
    assert loaded.selection_sets[0].object_ids == ["w1"]

    # Remap stability across rebuild split.
    q = Project(name="sel-remap")
    q.param.footprints.append(FootprintParam(id="fp1", polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]))
    q.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.0))
    q.param.walls.append(WallParam(id="w01", room_id="r1", edge_ref=(0, 1)))
    sid = surface_id_for_wall_side("w01", "A")
    q.selection_sets.append(SelectionSetSpec(id="ssw", name="Wall", object_ids=[sid]))
    rebuild(["footprint:fp1"], q)
    q.selection_sets[0].object_ids = [sid]
    q.param.openings.append(OpeningParam(id="o1", wall_id="w01", anchor=0.5, width=1.0, height=1.0, sill=0.8))
    rebuild(["opening:o1"], q)
    assert any(x == sid or x.startswith(f"{sid}:") for x in q.selection_sets[0].object_ids)
