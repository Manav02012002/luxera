from __future__ import annotations

import json
from pathlib import Path

from luxera.geometry.bvh import Triangle, any_hit, build_bvh
from luxera.geometry.core import Polygon, Vector3
from luxera.geometry.polygon2d import validate_polygon_with_holes
from luxera.geometry.spatial import pick_nearest
from luxera.io.dxf_import import DXFArc, DXFInsert, load_dxf
from luxera.io.import_pipeline import run_import_pipeline
from luxera.ops.calc_ops import create_calc_grid_from_room
from luxera.ops.scene_ops import create_room_from_footprint, create_walls_from_footprint, place_opening_on_wall
from luxera.project.schema import Project


FIX = Path("tests/fixtures/geometry")


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_fixture_footprints_validate() -> None:
    simple = _load("simple_rectangle_room.json")
    lshape = _load("l_shaped_room.json")
    hole = _load("room_with_hole.json")
    r1 = validate_polygon_with_holes(simple["footprint"])
    r2 = validate_polygon_with_holes(lshape["footprint"])
    r3 = validate_polygon_with_holes(hole["outer"], hole["holes"])
    assert r1.valid and r2.valid and r3.valid


def test_wall_extrusion_surfaces_and_normals() -> None:
    d = _load("l_shaped_room.json")
    p = Project(name="geom")
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=d["footprint"], height=float(d["height"]))
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    assert len(walls) == len(d["footprint"])
    for w in walls:
        n = Polygon([Vector3(*v) for v in w.vertices]).get_normal()
        assert n.length() > 0.0


def test_openings_subtract_and_grid_clipping() -> None:
    d = _load("room_with_multiple_openings.json")
    p = Project(name="openings")
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=d["footprint"], height=float(d["height"]))
    walls = create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    host = walls[0]
    place_opening_on_wall(
        p,
        opening_id="w1",
        host_surface_id=host.id,
        width=1.2,
        height=1.5,
        sill_height=0.9,
        distance_from_corner=1.0,
        opening_type="window",
    )
    assert any(s.id.startswith(host.id) for s in p.geometry.surfaces)

    # L-shape grid clipping.
    lshape = _load("l_shaped_room.json")
    p2 = Project(name="grid")
    create_room_from_footprint(p2, room_id="r1", name="R1", footprint=lshape["footprint"], height=float(lshape["height"]))
    g = create_calc_grid_from_room(p2, grid_id="g1", name="G1", room_id="r1", elevation=0.8, spacing=1.0)
    assert g.sample_mask
    assert any(m is False for m in g.sample_mask)
    assert len(g.sample_points) == sum(1 for m in g.sample_mask if m)


def test_selection_picking_and_bvh_known_rays_stable() -> None:
    pk = pick_nearest((0.0, 0.0, 0.0), vertices=[("v1", (0.1, 0.0, 0.0))], radius=0.5)
    pk2 = pick_nearest((0.0, 0.0, 0.0), vertices=[("v1", (0.1, 0.0, 0.0))], radius=0.5)
    assert pk.kind == "vertex" and pk2.kind == "vertex" and pk.id == pk2.id

    tris = [
        Triangle(a=Vector3(0.0, 0.0, 0.0), b=Vector3(1.0, 0.0, 0.0), c=Vector3(0.0, 1.0, 0.0)),
        Triangle(a=Vector3(2.0, 0.0, 0.0), b=Vector3(3.0, 0.0, 0.0), c=Vector3(2.0, 1.0, 0.0)),
    ]
    bvh = build_bvh(tris)
    rays = [
        (Vector3(0.1, 0.1, 1.0), Vector3(0.0, 0.0, -1.0), True),
        (Vector3(2.1, 0.1, 1.0), Vector3(0.0, 0.0, -1.0), True),
        (Vector3(1.5, 0.5, 1.0), Vector3(0.0, 0.0, -1.0), False),
    ]
    for o, d, exp in rays:
        assert any_hit(bvh, o, d, t_min=1e-6, t_max=10.0) == exp


def test_imported_ifc_dirty_mesh_and_dxf_arcs_blocks_fixtures() -> None:
    ifc = Path("tests/fixtures/ifc/simple_office_boundaries_conflict.ifc").resolve()
    out = run_import_pipeline(str(ifc), fmt="IFC")
    assert out.geometry is not None
    assert "degenerate_triangles" in out.report.scene_health.get("counts", {})

    dxf = load_dxf((FIX / "imported_dxf_arcs_blocks.dxf").resolve())
    assert any(isinstance(e, DXFArc) for e in dxf.entities)
    assert any(isinstance(e, DXFInsert) for e in dxf.entities)

