from __future__ import annotations

import random

from luxera.geometry.param.graph import build_param_graph
from luxera.geometry.param.identity import surface_id_for_wall_side
from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, WallParam, ZoneParam
from luxera.geometry.param.rebuild import rebuild
from luxera.project.schema import CalcGrid, Project


def _project() -> Project:
    p = Project(name="param-pipeline")
    p.param.footprints.append(
        FootprintParam(
            id="fp1",
            polygon2d=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
            vertex_ids=["v0", "v1", "v2", "v3"],
            edge_ids=["e0", "e1", "e2", "e3"],
            edge_bulges={"e1": 0.4},
        )
    )
    p.param.rooms.append(RoomParam(id="r1", footprint_id="fp1", height=3.0, wall_thickness_policy="center"))
    p.param.walls.extend(
        [
            WallParam(id="w01", room_id="r1", edge_ref=(0, 1), edge_id="e0"),
            WallParam(id="w12", room_id="r1", edge_ref=(1, 2), edge_id="e1"),
            WallParam(id="w23", room_id="r1", edge_ref=(2, 3), edge_id="e2"),
            WallParam(id="w30", room_id="r1", edge_ref=(3, 0), edge_id="e3"),
        ]
    )
    p.param.openings.append(
        OpeningParam(
            id="o1",
            wall_id="w01",
            anchor_mode="center_at_fraction",
            center_at_fraction=0.4,
            width=1.1,
            height=1.3,
            sill=0.9,
            type="window",
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=6.0, height=4.0, elevation=0.8, nx=7, ny=5, room_id="r1"))
    return p


def test_incremental_rebuild_returns_stable_mapping_and_no_lost_refs() -> None:
    p = _project()
    # Initial build.
    r0 = rebuild(["footprint:fp1"], p)
    assert r0.regenerated

    wall_sid = surface_id_for_wall_side("w01", "A")
    target = next(s for s in p.geometry.surfaces if s.id == wall_sid)
    target.material_id = "mat_wall"

    # Editing one vertex should keep logical wall identity and remap split children.
    p.param.footprints[0].polygon2d[0] = (-0.5, 0.0)
    r1 = rebuild(["footprint:fp1"], p)

    assert wall_sid in r1.stable_id_map
    mapped = r1.stable_id_map[wall_sid]
    assert mapped
    mapped_surfs = [s for s in p.geometry.surfaces if s.id in mapped]
    assert mapped_surfs
    assert all(s.material_id == "mat_wall" for s in mapped_surfs)

    # Grid remains clipped and consistent.
    g = next(g for g in p.grids if g.id == "g1")
    assert len(g.sample_mask) == g.nx * g.ny
    assert len(g.sample_points) == sum(1 for m in g.sample_mask if m)


def test_randomized_param_edits_keep_references_attached() -> None:
    p = _project()
    rebuild(["footprint:fp1"], p)

    sid = surface_id_for_wall_side("w01", "A")
    s = next(x for x in p.geometry.surfaces if x.id == sid)
    s.material_id = "mat_wall"

    rng = random.Random(7)
    for _ in range(120):
        fp = p.param.footprints[0]
        i = rng.randrange(len(fp.polygon2d))
        x, y = fp.polygon2d[i]
        fp.polygon2d[i] = (x + rng.uniform(-0.03, 0.03), y + rng.uniform(-0.03, 0.03))

        op = p.param.openings[0]
        op.width = max(0.4, min(1.4, op.width + rng.uniform(-0.04, 0.04)))
        op.anchor = min(0.9, max(0.1, op.anchor + rng.uniform(-0.03, 0.03)))
        p.param.walls[0].thickness = max(0.1, min(0.6, p.param.walls[0].thickness + rng.uniform(-0.01, 0.01)))

        out = rebuild(["footprint:fp1", "opening:o1"], p)
        mapped = out.stable_id_map.get(sid, [sid])
        mats = [x.material_id for x in p.geometry.surfaces if x.id in mapped]
        assert mats and all(m == "mat_wall" for m in mats)

        g = p.grids[0]
        assert len(g.sample_points) == sum(1 for m in g.sample_mask if m)
        assert p.param.openings[0].wall_id == "w01"


def test_dag_contains_required_dependency_edges() -> None:
    p = _project()
    g = build_param_graph(p)
    affected = g.affected(["footprint:fp1"])
    assert "room:r1" in affected
    assert "wall:w01" in affected
    assert "opening:o1" in affected
    assert "grid:g1" in affected


def test_bulge_edges_create_faceted_wall_segments() -> None:
    p = _project()
    rebuild(["footprint:fp1"], p)
    base = surface_id_for_wall_side("w12", "A")
    segs = [s for s in p.geometry.surfaces if s.id == base or s.id.startswith(f"{base}:seg")]
    assert len(segs) >= 2


def test_zone_holes_clip_grids() -> None:
    p = _project()
    p.param.zones.append(
        ZoneParam(
            id="z1",
            room_id="r1",
            polygon2d=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
            holes2d=[[(2.5, 1.5), (3.5, 1.5), (3.5, 2.5), (2.5, 2.5)]],
        ),
    )
    p.grids[0].zone_id = "z1"
    rebuild(["zone:z1"], p)
    assert (3.0, 2.0, 0.8) not in p.grids[0].sample_points
