from __future__ import annotations

from luxera.geometry.param.model import RoomParam
from luxera.geometry.topology.adjacency import find_shared_edges


def test_find_shared_edges_tolerance_aware_with_coordinate_noise() -> None:
    room_a = RoomParam(
        id="A",
        footprint_id="fa",
        height=3.0,
        polygon2d=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
    )
    room_b = RoomParam(
        id="B",
        footprint_id="fb",
        height=3.0,
        polygon2d=[(4.0000004, 0.0), (8.0, 0.0000003), (8.0, 3.0), (3.9999997, 3.0)],
    )
    shared = find_shared_edges([room_a, room_b])
    assert len(shared) >= 1
    e = shared[0]
    assert {e.room_a, e.room_b} == {"A", "B"}
    p0, p1 = e.overlap_segment
    assert abs(p0[0] - 4.0) < 1e-3
    assert abs(p1[0] - 4.0) < 1e-3
    assert e.id
    assert e.geom == e.overlap_segment
    assert e.segment_a_local != e.segment_b_local


def test_shared_edge_resolver_handles_one_big_edge_against_two_small_edges() -> None:
    room_a = RoomParam(
        id="A",
        footprint_id="fa",
        height=3.0,
        polygon2d=[(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
    )
    room_b = RoomParam(
        id="B",
        footprint_id="fb",
        height=3.0,
        polygon2d=[(6.0, 0.0), (9.0, 0.0), (9.0, 2.0), (6.0, 2.0)],
    )
    room_c = RoomParam(
        id="C",
        footprint_id="fc",
        height=3.0,
        polygon2d=[(6.0, 2.0), (9.0, 2.0), (9.0, 4.0), (6.0, 4.0)],
    )
    shared = find_shared_edges([room_a, room_b, room_c])
    ac = [e for e in shared if {e.room_a, e.room_b} in [{"A", "B"}, {"A", "C"}]]
    assert len(ac) >= 2
