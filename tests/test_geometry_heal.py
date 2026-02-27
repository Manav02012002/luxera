from __future__ import annotations

from pathlib import Path

from luxera.geometry.heal import FaceRef, heal_mesh
from luxera.io.mesh_import import import_mesh_file


def test_heal_mesh_reports_expected_counts_and_hash_is_deterministic() -> None:
    vertices = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0),  # near-duplicate of vertex 0
    ]
    triangles = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 1, 2),  # duplicate coplanar face after vertex merge
        (0, 0, 1),  # degenerate
    ]
    refs = [FaceRef(object_id="obj", face_id=f"f{i+1}", triangle_index=i) for i in range(len(triangles))]

    r1 = heal_mesh(vertices, triangles, triangle_refs=refs, weld_epsilon=1e-8, area_epsilon=1e-12)
    r2 = heal_mesh(vertices, triangles, triangle_refs=refs, weld_epsilon=1e-8, area_epsilon=1e-12)

    assert r1.report.counts["degenerate_triangles"] == 1
    assert r1.report.counts["duplicate_coplanar_faces"] == 1
    assert r1.report.counts["open_shell_edges"] > 0
    assert r1.report.cleaned_mesh_hash == r2.report.cleaned_mesh_hash
    assert r1.triangles == r2.triangles
    assert r1.vertices == r2.vertices


def test_mesh_import_emits_deterministic_geometry_heal_report(tmp_path: Path) -> None:
    obj = tmp_path / "dirty.obj"
    obj.write_text(
        "\n".join(
            [
                "v 0 0 0",
                "v 1 0 0",
                "v 1 1 0",
                "v 0 1 0",
                "v 0 0 0",
                "f 1 2 3",
                "f 1 3 4",
                "f 5 2 3",
                "f 1 1 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    m1 = import_mesh_file(str(obj), fmt="OBJ")
    m2 = import_mesh_file(str(obj), fmt="OBJ")
    h1 = m1.geometry_heal_report
    h2 = m2.geometry_heal_report
    assert isinstance(h1, dict) and isinstance(h2, dict)
    assert h1["counts"]["degenerate_triangles"] == 1
    assert h1["counts"]["duplicate_coplanar_faces"] == 1
    assert h1["cleaned_mesh_hash"] == h2["cleaned_mesh_hash"]
