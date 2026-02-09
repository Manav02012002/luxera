from luxera.project.migrations import migrate_project


def test_migrate_v2_to_v3_adds_fields():
    data = {
        "schema_version": 2,
        "name": "Test",
        "geometry": {"rooms": []},
        "materials": [],
        "photometry_assets": [],
        "luminaires": [],
        "grids": [],
        "jobs": [],
        "results": [],
    }
    migrated = migrate_project(data)
    assert migrated["schema_version"] == 4
    assert "material_library" in migrated
    assert "luminaire_families" in migrated
    assert "asset_bundle_path" in migrated
    assert "agent_history" in migrated
