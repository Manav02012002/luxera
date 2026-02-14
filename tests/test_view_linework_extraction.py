from __future__ import annotations

from luxera.geometry.drafting import view_linework_from_meshes
from luxera.geometry.mesh import extrusion_to_trimesh
from luxera.geometry.primitives import Extrusion, Polygon2D
from luxera.geometry.views.cutplane import ElevationView, PlanView, SectionView


def test_view_linework_extraction_plan_section_elevation() -> None:
    mesh = extrusion_to_trimesh(
        Extrusion(profile2d=Polygon2D(points=[(0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)]), height=3.0)
    )
    plan = view_linework_from_meshes([mesh], PlanView(cut_z=1.0, range_zmin=0.0, range_zmax=3.0), layer="CUT")
    sec = view_linework_from_meshes([mesh], SectionView(plane_origin=(1.5, 0.0, 0.0), plane_normal=(1.0, 0.0, 0.0), thickness=0.1), layer="SEC")
    elev = view_linework_from_meshes([mesh], ElevationView(plane_origin=(0.0, 0.0, 0.0), plane_normal=(0.0, 1.0, 0.0), direction=(0.0, 1.0, 0.0), depth=0.2), layer="ELEV")
    assert plan and sec and elev
    assert all(p.layer == "CUT" for p in plan)
    assert all(p.layer == "SEC" for p in sec)
    assert all(p.layer == "ELEV" for p in elev)
