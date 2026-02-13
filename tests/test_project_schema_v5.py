from pathlib import Path

from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import (
    ArbitraryPlaneSpec,
    LineGridSpec,
    Project,
    RoomSpec,
    RoadwaySpec,
    ZoneSpec,
    WorkplaneSpec,
    ComplianceProfile,
    ProjectVariant,
)


def test_project_schema_v5_round_trip(tmp_path: Path):
    project = Project(name="V5")
    project.geometry.rooms.append(RoomSpec(id="r1", name="Room", width=6, length=8, height=3))
    project.geometry.zones.append(ZoneSpec(id="z1", name="Zone 1", room_ids=["r1"]))
    project.workplanes.append(WorkplaneSpec(id="wp1", name="Desk", elevation=0.8, margin=0.5, spacing=0.25, zone_id="z1"))
    project.arbitrary_planes.append(
        ArbitraryPlaneSpec(
            id="ap1",
            name="Tilted",
            origin=(0.0, 0.0, 0.8),
            axis_u=(1.0, 0.0, 0.0),
            axis_v=(0.0, 0.8, 0.6),
            width=2.0,
            height=1.0,
            nx=3,
            ny=2,
            room_id="r1",
        )
    )
    project.line_grids.append(LineGridSpec(id="lg1", name="Line", polyline=[(0.0, 0.0, 0.8), (1.0, 1.0, 0.8)], room_id="r1"))
    project.roadways.append(RoadwaySpec(id="rw1", name="Road", start=(0.0, 0.0, 0.0), end=(20.0, 0.0, 0.0)))
    project.compliance_profiles.append(
        ComplianceProfile(
            id="cp1",
            name="Office",
            thresholds={"maintained_illuminance_lux": 500.0, "uniformity_min": 0.6},
        )
    )
    project.variants.append(ProjectVariant(id="var1", name="Baseline"))
    project.active_variant_id = "var1"

    p = tmp_path / "p.json"
    save_project_schema(project, p)
    loaded = load_project_schema(p)

    assert loaded.schema_version == 5
    assert loaded.geometry.zones[0].id == "z1"
    assert loaded.workplanes[0].spacing == 0.25
    assert loaded.arbitrary_planes[0].id == "ap1"
    assert loaded.line_grids[0].id == "lg1"
    assert loaded.roadways[0].id == "rw1"
    assert loaded.compliance_profiles[0].thresholds["uniformity_min"] == 0.6
    assert loaded.active_variant_id == "var1"
