from __future__ import annotations

from typing import List

from luxera.geometry.id import stable_id
from luxera.geometry.param.model import RoomParam, SharedWallParam
from luxera.geometry.topology.adjacency import find_shared_edges


def build_shared_walls_from_rooms(rooms: list[RoomParam], thickness: float = 0.2) -> List[SharedWallParam]:
    shared = find_shared_edges(rooms)
    out: List[SharedWallParam] = []
    for e in shared:
        wall_id = stable_id(
            "shared_wall",
            {
                "room_a": e.room_a,
                "edge_a": e.edge_a,
                "room_b": e.room_b,
                "edge_b": e.edge_b,
                "segment": e.overlap_segment,
            },
        )
        out.append(
            SharedWallParam(
                id=wall_id,
                edge_geom=e.overlap_segment,
                room_a=e.room_a,
                room_b=e.room_b,
                thickness=float(thickness),
            )
        )
    return out

