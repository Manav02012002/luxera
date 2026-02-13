from __future__ import annotations

import json
from pathlib import Path

from luxera.geometry.drafting import plan_linework_from_meshes, project_plan_view
from luxera.geometry.mesh import extrusion_to_trimesh
from luxera.geometry.primitives import Extrusion, Polygon2D
from luxera.ops.scene_ops import create_room_from_footprint, create_walls_from_footprint
from luxera.project.schema import Project


def _load_case() -> dict:
    p = Path("tests/assets/geometry_cases/plan_view_extraction.json").resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def test_gate_plan_view_extraction_is_deterministic() -> None:
    case = _load_case()
    footprint = [(float(x), float(y)) for x, y in case["footprint"]]

    p = Project(name="gate-plan-view")
    create_room_from_footprint(p, room_id="r1", name="R1", footprint=footprint, height=float(case["height"]))
    create_walls_from_footprint(p, room_id="r1", thickness=0.2)

    proj = project_plan_view(p.geometry.surfaces, cut_z=float(case["cut_z"]), include_below=True)
    assert len(proj.cut_segments) >= int(case["expect"]["min_cut_segments"])
    assert len(proj.silhouettes) >= int(case["expect"]["min_silhouettes"])

    mesh = extrusion_to_trimesh(Extrusion(profile2d=Polygon2D(points=footprint), height=float(case["height"])))
    a = plan_linework_from_meshes(
        [mesh],
        cut_z=float(case["cut_z"]),
        range_zmin=float(case["range_zmin"]),
        range_zmax=float(case["range_zmax"]),
        layer=str(case["expect"]["linework_layer"]),
    )
    b = plan_linework_from_meshes(
        [mesh],
        cut_z=float(case["cut_z"]),
        range_zmin=float(case["range_zmin"]),
        range_zmax=float(case["range_zmax"]),
        layer=str(case["expect"]["linework_layer"]),
    )

    assert a
    assert [x.__dict__ for x in a] == [x.__dict__ for x in b]
    assert all(pr.layer == str(case["expect"]["linework_layer"]) for pr in a)
