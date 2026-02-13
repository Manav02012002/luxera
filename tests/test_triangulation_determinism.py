from __future__ import annotations

import hashlib
from pathlib import Path

from luxera.geometry.bvh import BVHNode, build_bvh
from luxera.io.mesh_import import import_mesh_file


def _triangles_hash(triangles: list[tuple[int, int, int]]) -> str:
    h = hashlib.sha256()
    for a, b, c in triangles:
        h.update(f"{a},{b},{c};".encode("utf-8"))
    return h.hexdigest()


def _bvh_hash(node: BVHNode | None) -> str:
    h = hashlib.sha256()

    def walk(n: BVHNode | None) -> None:
        if n is None:
            h.update(b"none")
            return
        h.update(
            (
                f"{n.aabb.min.x:.12f},{n.aabb.min.y:.12f},{n.aabb.min.z:.12f}|"
                f"{n.aabb.max.x:.12f},{n.aabb.max.y:.12f},{n.aabb.max.z:.12f}"
            ).encode("utf-8")
        )
        if n.triangles is not None:
            h.update(f"leaf:{len(n.triangles)}".encode("utf-8"))
            for tri in n.triangles:
                h.update(
                    (
                        f"{tri.a.x:.12f},{tri.a.y:.12f},{tri.a.z:.12f}|"
                        f"{tri.b.x:.12f},{tri.b.y:.12f},{tri.b.z:.12f}|"
                        f"{tri.c.x:.12f},{tri.c.y:.12f},{tri.c.z:.12f}"
                    ).encode("utf-8")
                )
        walk(n.left)
        walk(n.right)

    walk(node)
    return h.hexdigest()


def test_import_same_obj_twice_produces_same_triangle_and_bvh_hash(tmp_path: Path) -> None:
    obj = tmp_path / "repeat.obj"
    obj.write_text(
        """v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
f 1 2 3 4
f 1 2 5
""",
        encoding="utf-8",
    )

    m1 = import_mesh_file(str(obj), fmt="OBJ")
    m2 = import_mesh_file(str(obj), fmt="OBJ")

    assert m1.vertices == m2.vertices
    assert m1.faces == m2.faces
    assert _triangles_hash(m1.triangles) == _triangles_hash(m2.triangles)

    from luxera.geometry.bvh import Triangle
    from luxera.geometry.core import Vector3

    t1 = [
        Triangle(a=Vector3(*m1.vertices[a]), b=Vector3(*m1.vertices[b]), c=Vector3(*m1.vertices[c]))
        for (a, b, c) in m1.triangles
    ]
    t2 = [
        Triangle(a=Vector3(*m2.vertices[a]), b=Vector3(*m2.vertices[b]), c=Vector3(*m2.vertices[c]))
        for (a, b, c) in m2.triangles
    ]

    assert _bvh_hash(build_bvh(t1)) == _bvh_hash(build_bvh(t2))


def test_vertex_merge_is_deterministic_with_epsilon(tmp_path: Path) -> None:
    obj = tmp_path / "near_dupes.obj"
    obj.write_text(
        """v 0 0 0
v 1 0 0
v 1.0000000001 0 0
v 0 1 0
f 1 2 4
f 1 3 4
""",
        encoding="utf-8",
    )

    m = import_mesh_file(str(obj), fmt="OBJ")
    # v2 and v3 collapse under default epsilon merge.
    assert len(m.vertices) == 3
    assert len(m.triangles) == 2
