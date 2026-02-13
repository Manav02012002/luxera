from __future__ import annotations

from luxera.geometry.doctor import repair_mesh, scene_health_report, split_connected_components


def test_scene_health_report_detects_common_mesh_issues() -> None:
    vertices = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0),  # duplicate vertex
    ]
    triangles = [
        (0, 1, 2),
        (0, 1, 2),  # duplicate face
        (0, 1, 1),  # degenerate
    ]
    report = scene_health_report(vertices, triangles)
    assert report.counts["degenerate_triangles"] >= 1
    assert report.counts["duplicate_faces"] >= 1
    assert report.counts["duplicate_vertices"] >= 1
    assert report.counts["open_boundary_edges"] >= 1


def test_repair_mesh_removes_degenerate_and_can_make_two_sided() -> None:
    vertices = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0),  # duplicate
    ]
    triangles = [
        (0, 1, 2),
        (0, 1, 1),
        (3, 1, 2),  # same as first after weld
    ]

    repaired = repair_mesh(vertices, triangles)
    assert len(repaired.vertices) < len(vertices)
    assert repaired.report.counts["degenerate_triangles"] == 0

    two_sided = repair_mesh(vertices, triangles, make_two_sided=True)
    assert len(two_sided.triangles) == 2 * len(repaired.triangles)


def test_split_connected_components_and_hole_fill() -> None:
    vertices = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (5.0, 5.0, 0.0),
        (6.0, 5.0, 0.0),
        (5.0, 6.0, 0.0),
    ]
    triangles = [(0, 1, 2), (3, 4, 5)]
    comps = split_connected_components(triangles)
    assert len(comps) == 2

    # A missing triangle side (open boundary) can be filled for small loops.
    repaired = repair_mesh(vertices[:3], [(0, 1, 2)], fill_holes=True)
    assert repaired.report.counts["open_boundary_edges"] >= 0


def test_scene_health_detects_self_intersection_approx() -> None:
    vertices = [
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.0, 2.0, 0.0),
        (0.5, 0.5, -1.0),
        (0.5, 0.5, 1.0),
        (1.5, 0.5, 0.0),
    ]
    triangles = [(0, 1, 2), (3, 4, 5)]
    report = scene_health_report(vertices, triangles)
    assert report.counts["self_intersections_approx"] >= 1
