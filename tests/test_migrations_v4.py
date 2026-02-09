from luxera.project.migrations import migrate_project


def test_migrate_v4_to_v5_adds_professional_workflow_fields():
    data = {
        "schema_version": 4,
        "name": "Test",
        "geometry": {"rooms": [{"id": "r1", "name": "R", "width": 6, "length": 8, "height": 3}]},
        "materials": [],
        "photometry_assets": [],
        "luminaires": [],
        "grids": [],
        "jobs": [],
        "results": [],
    }

    migrated = migrate_project(data)
    assert migrated["schema_version"] == 5
    assert "zones" in migrated["geometry"]
    assert "surfaces" in migrated["geometry"]
    assert "coordinate_systems" in migrated["geometry"]
    assert migrated["geometry"]["length_unit"] == "m"
    assert "workplanes" in migrated
    assert "vertical_planes" in migrated
    assert "point_sets" in migrated
    assert "glare_views" in migrated
    assert "roadway_grids" in migrated
    assert "compliance_profiles" in migrated
    assert "variants" in migrated
