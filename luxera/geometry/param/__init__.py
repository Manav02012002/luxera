from __future__ import annotations

from typing import Any

from luxera.geometry.param.graph import ParamGraph
from luxera.geometry.param.identity import (
    surface_id_for_ceiling,
    surface_id_for_floor,
    surface_id_for_shared_wall,
    surface_id_for_wall_side,
)
from luxera.geometry.param.model import (
    FootprintParam,
    OpeningParam,
    ParamModel,
    RoomParam,
    SharedWallParam,
    SlabParam,
    WallParam,
    ZoneParam,
)

__all__ = [
    "FootprintParam",
    "RoomParam",
    "WallParam",
    "SharedWallParam",
    "OpeningParam",
    "SlabParam",
    "ZoneParam",
    "ParamModel",
    "ParamGraph",
    "DerivedRoomGeometry",
    "rebuild_room",
    "rebuild_wall",
    "rebuild_shared_wall",
    "rebuild_surfaces_for_room",
    "surface_id_for_wall_side",
    "surface_id_for_floor",
    "surface_id_for_ceiling",
    "surface_id_for_shared_wall",
]


def __getattr__(name: str) -> Any:
    if name in {"DerivedRoomGeometry", "rebuild_room", "rebuild_wall", "rebuild_shared_wall", "rebuild_surfaces_for_room"}:
        from luxera.geometry.param.rebuild import (
            DerivedRoomGeometry,
            rebuild_room,
            rebuild_shared_wall,
            rebuild_surfaces_for_room,
            rebuild_wall,
        )

        return {
            "DerivedRoomGeometry": DerivedRoomGeometry,
            "rebuild_room": rebuild_room,
            "rebuild_wall": rebuild_wall,
            "rebuild_shared_wall": rebuild_shared_wall,
            "rebuild_surfaces_for_room": rebuild_surfaces_for_room,
        }[name]
    raise AttributeError(name)

