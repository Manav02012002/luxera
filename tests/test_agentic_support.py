from luxera.project.schema import Project, RoomSpec
from luxera.project.schema import PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec
from luxera.ai.agent import propose_layout, apply_proposal


def test_agent_proposal_applied(tmp_path):
    project = Project(name="Agent")
    project.geometry.rooms.append(
        RoomSpec(id="r1", name="Room", width=6, length=8, height=3)
    )

    ies_path = tmp_path / "a.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )

    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    project.luminaires.append(
        LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec(position=(1, 1, 2.8), rotation=rot))
    )

    proposal = propose_layout(project, target_lux=500.0, constraints={"max_rows": 1, "max_cols": 1})
    apply_proposal(project, proposal)

    assert project.agent_history
