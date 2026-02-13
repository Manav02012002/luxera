from __future__ import annotations

from pathlib import Path

from luxera.geometry.drafting import make_dimension_annotation, make_leader_annotation, project_plan_view
from luxera.io.dxf_export import export_plan_to_dxf
from luxera.ops.scene_ops import create_room_from_footprint, create_walls_from_footprint
from luxera.project.schema import CalcGrid, LuminaireInstance, Project, RotationSpec, TransformSpec


def test_plan_projection_extracts_edges_cut_and_silhouette() -> None:
    p = Project(name="draft")
    create_room_from_footprint(
        p,
        room_id="r1",
        name="R1",
        footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
        height=3.0,
    )
    create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    proj = project_plan_view(p.geometry.surfaces, cut_z=1.2, include_below=True)
    assert proj.edges
    assert proj.cut_segments
    assert proj.silhouettes


def test_dimension_and_leader_annotations_geometry() -> None:
    d = make_dimension_annotation(ann_id="d1", start=(0.0, 0.0), end=(3.0, 0.0), offset=0.4)
    assert abs(d.value - 3.0) < 1e-9
    l = make_leader_annotation(ann_id="l1", anchor=(1.0, 1.0), elbow=(1.5, 1.5), text_anchor=(2.0, 1.8))
    assert len(l.points) == 3
    assert l.text_anchor == (2.0, 1.8)


def test_export_plan_dxf_contains_expected_entities(tmp_path: Path) -> None:
    p = Project(name="dxf")
    create_room_from_footprint(
        p,
        room_id="r1",
        name="R1",
        footprint=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)],
        height=3.0,
    )
    create_walls_from_footprint(p, room_id="r1", thickness=0.2)
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.2, 0.2, 0.0), width=4.6, height=3.6, elevation=0.8, nx=3, ny=3))
    p.luminaires.append(
        LuminaireInstance(
            id="L1",
            name="Lum 1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.5, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0, 0, 0))),
        )
    )
    out = export_plan_to_dxf(p, tmp_path / "plan.dxf", cut_z=1.0)
    text = out.read_text(encoding="utf-8")
    assert "SECTION" in text
    assert "LUM_SYMBOL" in text
    assert "LINE" in text
    assert "INSERT" in text

