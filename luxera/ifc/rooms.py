from __future__ import annotations

from typing import Dict, List

from luxera.project.schema import RoomSpec, SurfaceSpec
from luxera.scene.scene_graph import Room


def room_boundary_from_spec(room: RoomSpec) -> List[tuple[float, float]]:
    x0, y0, _ = room.origin
    x1 = x0 + float(room.width)
    y1 = y0 + float(room.length)
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def build_scene_rooms(rooms: List[RoomSpec], surfaces: List[SurfaceSpec]) -> List[Room]:
    surface_map: Dict[str, List[str]] = {}
    for s in surfaces:
        if s.room_id:
            surface_map.setdefault(s.room_id, []).append(s.id)
    out: List[Room] = []
    for r in rooms:
        out.append(
            Room(
                id=r.id,
                name=r.name,
                boundary_polygon=room_boundary_from_spec(r),
                height=float(r.height),
                surface_refs=sorted(surface_map.get(r.id, [])),
            )
        )
    return out

