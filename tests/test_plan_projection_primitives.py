from __future__ import annotations

from luxera.geometry.views.cutplane import SectionView, view_basis
from luxera.geometry.views.intersect import Polyline3D
from luxera.geometry.views.project import polylines_to_primitives, project_polyline_to_view


def test_project_polyline_to_view_and_layered_primitives_are_deterministic() -> None:
    basis = view_basis(SectionView(plane_origin=(0.0, 0.0, 0.0), plane_normal=(1.0, 0.0, 0.0), thickness=0.1))
    p1 = Polyline3D(points=[(0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 2.0, 3.0)])
    p2 = Polyline3D(points=[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (1.0, 2.0, 3.0)])

    p2d = project_polyline_to_view(p1, basis)
    assert len(p2d.points) == 3

    a = polylines_to_primitives([p1, p2], basis, layer="WALL", style="solid", by_layer={"WALL": "A-WALL"})
    b = polylines_to_primitives([p1, p2], basis, layer="WALL", style="solid", by_layer={"WALL": "A-WALL"})
    assert [x.__dict__ for x in a] == [x.__dict__ for x in b]
    assert all(pr.layer == "A-WALL" for pr in a)
    assert all(pr.type == "polyline" for pr in a)
