from __future__ import annotations

from luxera.project.schema import LevelSpec, Project, RoomSpec, SurfaceSpec
from luxera.viewer.streaming import build_storey_chunks, filter_chunks_for_storeys


def test_build_storey_chunks_and_filter_visibility() -> None:
    p = Project(name="stream")
    p.geometry.levels.extend(
        [
            LevelSpec(id="L1", name="Level 1", elevation=0.0),
            LevelSpec(id="L2", name="Level 2", elevation=3.5),
        ]
    )
    p.geometry.rooms.extend(
        [
            RoomSpec(id="r1", name="R1", width=4.0, length=3.0, height=3.0, origin=(0.0, 0.0, 0.0), level_id="L1"),
            RoomSpec(id="r2", name="R2", width=4.0, length=3.0, height=3.0, origin=(0.0, 0.0, 3.5), level_id="L2"),
        ]
    )
    p.geometry.surfaces.extend(
        [
            SurfaceSpec(id="s1", name="S1", kind="wall", room_id="r1", vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)]),
            SurfaceSpec(id="s2", name="S2", kind="wall", room_id="r2", vertices=[(0.0, 0.0, 3.5), (4.0, 0.0, 3.5), (4.0, 0.0, 6.5), (0.0, 0.0, 6.5)]),
        ]
    )

    chunks = build_storey_chunks(p, viewport_ratio=0.5)
    assert len(chunks) == 2
    assert {c.storey_id for c in chunks} == {"L1", "L2"}

    for c in chunks:
        assert len(c.calc_mesh.faces) > 0
        assert c.viewport_mesh.indices.shape[0] <= len(c.calc_mesh.faces)

    only_l1 = filter_chunks_for_storeys(chunks, {"L1"})
    assert len(only_l1) == 1
    assert only_l1[0].storey_id == "L1"
