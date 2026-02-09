from luxera.geometry.scene_prep import clean_scene_surfaces, detect_room_volumes_from_surfaces, detect_non_manifold_edges
from luxera.project.schema import SurfaceSpec


def test_scene_prep_fixes_normals_and_snaps_vertices():
    surfaces = [
        SurfaceSpec(
            id="s1",
            name="S1",
            kind="floor",
            vertices=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
            normal=(0, 0, -1),
            room_id="r1",
        ),
        SurfaceSpec(
            id="s2",
            name="S2",
            kind="floor",
            vertices=[(1.0004, 0, 0), (2, 0, 0), (2, 1, 0), (1.0004, 1, 0)],
            room_id="r1",
        ),
    ]
    cleaned, report = clean_scene_surfaces(surfaces, snap_tolerance=1e-2, merge_coplanar=False)
    assert len(cleaned) == 2
    assert report.fixed_normals == 2
    assert report.non_manifold_edges == 0
    assert cleaned[0].normal is not None


def test_detect_room_volumes_from_surfaces():
    surfaces = [
        SurfaceSpec(id="f", name="floor", kind="floor", vertices=[(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 0)], room_id="roomA"),
        SurfaceSpec(id="c", name="ceil", kind="ceiling", vertices=[(0, 0, 3), (2, 0, 3), (2, 3, 3), (0, 3, 3)], room_id="roomA"),
    ]
    rooms = detect_room_volumes_from_surfaces(surfaces)
    assert len(rooms) == 1
    assert rooms[0].width == 2
    assert rooms[0].length == 3
    assert rooms[0].height == 3


def test_coplanar_merge_preserves_hole_like_topology_as_multiple_loops():
    # Ring around a center void (0,0)-(3,3) with hole (1,1)-(2,2)
    surfaces = [
        SurfaceSpec(id="s1", name="b", kind="floor", room_id="r1", vertices=[(0, 0, 0), (3, 0, 0), (3, 1, 0), (0, 1, 0)]),
        SurfaceSpec(id="s2", name="l", kind="floor", room_id="r1", vertices=[(0, 1, 0), (1, 1, 0), (1, 2, 0), (0, 2, 0)]),
        SurfaceSpec(id="s3", name="r", kind="floor", room_id="r1", vertices=[(2, 1, 0), (3, 1, 0), (3, 2, 0), (2, 2, 0)]),
        SurfaceSpec(id="s4", name="t", kind="floor", room_id="r1", vertices=[(0, 2, 0), (3, 2, 0), (3, 3, 0), (0, 3, 0)]),
    ]
    cleaned, report = clean_scene_surfaces(surfaces, merge_coplanar=True)
    # Outer + inner boundaries are preserved as separate loops/surfaces rather than convex-filled.
    assert len(cleaned) >= 2
    assert report.non_manifold_edges == 0


def test_detect_non_manifold_edges():
    surfaces = [
        SurfaceSpec(id="a", name="a", kind="custom", vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0)]),
        SurfaceSpec(id="b", name="b", kind="custom", vertices=[(1, 0, 0), (0, 0, 0), (0, 0, 1)]),
        SurfaceSpec(id="c", name="c", kind="custom", vertices=[(0, 0, 0), (1, 0, 0), (0, -1, 0)]),
    ]
    non_manifold = detect_non_manifold_edges(surfaces)
    assert len(non_manifold) >= 1
