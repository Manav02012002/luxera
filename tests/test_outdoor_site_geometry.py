from __future__ import annotations

from luxera.outdoor.site import (
    GroundPlane,
    carriageway_polygon_from_edges,
    import_terrain_mesh,
    luminaire_positions_along_roadway,
    make_ground_surface,
    make_site_obstruction,
    observer_spacing_for_standard,
    roadway_edges_from_centerline,
    roadway_observer_positions,
)


def test_ground_plane_and_obstruction_generation() -> None:
    g = GroundPlane(polygon_xy=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], elevation_z=0.0, reflectance=0.2)
    s = make_ground_surface(g)
    assert s.id == "site_ground"
    assert len(s.vertices) == 4
    ob = make_site_obstruction(obstruction_id="b1", footprint_xy=[(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)], height=6.0)
    assert ob.height == 6.0


def test_roadway_geometry_helpers() -> None:
    center = [(0.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
    left, right = roadway_edges_from_centerline(center, lane_width=3.5, num_lanes=2)
    assert len(left) == 2 and len(right) == 2
    poly = carriageway_polygon_from_edges(left, right)
    assert len(poly) == 4
    obs = roadway_observer_positions(center, spacing_m=10.0, eye_height_m=1.5, standard="EN 13201", road_class="M3")
    assert len(obs) >= 2
    assert observer_spacing_for_standard("EN 13201", "M3") == 10.0
    poles = luminaire_positions_along_roadway(center, spacing_m=10.0, lateral_offset_m=4.0, mounting_height_m=8.0)
    assert len(poles) >= 2


def test_import_terrain_mesh(monkeypatch, tmp_path) -> None:
    p = tmp_path / "terrain.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    surfaces = import_terrain_mesh(str(p), fmt="OBJ")
    assert surfaces
    assert surfaces[0].layer == "SITE_TERRAIN"
