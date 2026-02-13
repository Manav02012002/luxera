from __future__ import annotations

from luxera.agent.summarize import summarize_project
from luxera.project.schema import (
    CalcGrid,
    JobResultRef,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)


def test_summarize_project_context_shape() -> None:
    project = Project(name="Ctx")
    project.geometry.rooms.append(RoomSpec(id="r1", name="Office", width=6.0, length=8.0, height=3.0))
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES"))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1.0, 1.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    project.grids.append(CalcGrid(id="g1", name="G1", origin=(0, 0, 0), width=4.0, height=5.0, elevation=0.8, nx=3, ny=4))
    project.jobs.append(JobSpec(id="j1", type="direct", settings={"target_lux": 500.0, "uniformity_min": 0.4}))
    project.results.append(JobResultRef(job_id="j1", job_hash="h", result_dir="out", summary={"compliance": "PASS"}))

    ctx = summarize_project(project).to_dict()
    assert ctx["project_name"] == "Ctx"
    assert ctx["rooms"] and ctx["rooms"][0]["id"] == "r1"
    assert ctx["luminaires"] and ctx["luminaires"][0]["photometry_asset_id"] == "a1"
    assert any(c["id"] == "g1" and c["kind"] == "HorizontalGrid" for c in ctx["calc_objects"])
    assert float(ctx["constraints"]["target_lux"]) == 500.0

