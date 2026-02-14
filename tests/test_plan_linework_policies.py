from __future__ import annotations

from luxera.geometry.drafting import PlanLineworkPolicy, plan_view_primitives
from luxera.geometry.views.cutplane import PlanView
from luxera.project.schema import LuminaireInstance, OpeningSpec, Project, RotationSpec, SurfaceSpec, TransformSpec


def test_plan_linework_policy_layers_cut_below_openings_and_symbols() -> None:
    p = Project(name="plan-policy")
    p.geometry.surfaces.extend(
        [
            SurfaceSpec(
                id="wall_cut",
                name="Wall Cut",
                kind="wall",
                vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
            ),
            SurfaceSpec(
                id="wall_below",
                name="Wall Below",
                kind="wall",
                vertices=[(0.0, 2.0, 0.0), (4.0, 2.0, 0.0), (4.0, 2.0, 1.0), (0.0, 2.0, 1.0)],
            ),
        ]
    )
    p.geometry.openings.append(
        OpeningSpec(
            id="op1",
            name="Open",
            opening_type="window",
            kind="window",
            host_surface_id="wall_cut",
            vertices=[(1.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.0), (1.0, 0.0, 2.0)],
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="lum1",
            name="L1",
            photometry_asset_id="asset1",
            transform=TransformSpec(position=(1.5, 1.0, 1.2), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    view = PlanView(cut_z=1.5, range_zmin=0.0, range_zmax=3.0)
    prims = plan_view_primitives(p, view, policy=PlanLineworkPolicy())
    assert any(x.layer == "CUT" and x.type == "line" and x.style == "solid" for x in prims)
    assert any(x.layer == "WALLS_BELOW" and x.type == "line" and x.style == "dashed" for x in prims)
    assert any(x.layer == "OPENINGS" and x.type == "polyline" for x in prims)
    assert any(x.layer == "LUMINAIRES" and x.type == "text" and x.text == "lum1" for x in prims)
