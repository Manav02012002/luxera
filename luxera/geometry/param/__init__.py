from __future__ import annotations

from typing import Any

from luxera.geometry.param.graph import ParamGraph, build_param_graph
from luxera.geometry.param.identity import (
    surface_id_for_ceiling,
    surface_id_for_floor,
    surface_id_for_shared_wall,
    surface_id_for_wall_side,
)
from luxera.geometry.param.model import (
    FootprintHoleParam,
    FootprintParam,
    InstanceParam,
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
    "FootprintHoleParam",
    "RoomParam",
    "WallParam",
    "SharedWallParam",
    "OpeningParam",
    "SlabParam",
    "ZoneParam",
    "InstanceParam",
    "ParamModel",
    "ParamGraph",
    "build_param_graph",
    "DerivedRoomGeometry",
    "RebuildResult",
    "rebuild_room",
    "rebuild_wall",
    "rebuild_shared_wall",
    "rebuild_surfaces_for_room",
    "rebuild",
    "surface_id_for_wall_side",
    "surface_id_for_floor",
    "surface_id_for_ceiling",
    "surface_id_for_shared_wall",
]


def __getattr__(name: str) -> Any:
    if name in {"DerivedRoomGeometry", "RebuildResult", "rebuild_room", "rebuild_wall", "rebuild_shared_wall", "rebuild_surfaces_for_room", "rebuild"}:
        from luxera.geometry.param.rebuild import (
            DerivedRoomGeometry,
            RebuildResult,
            rebuild,
            rebuild_room,
            rebuild_shared_wall,
            rebuild_surfaces_for_room,
            rebuild_wall,
        )

        return {
            "DerivedRoomGeometry": DerivedRoomGeometry,
            "RebuildResult": RebuildResult,
            "rebuild_room": rebuild_room,
            "rebuild_wall": rebuild_wall,
            "rebuild_shared_wall": rebuild_shared_wall,
            "rebuild_surfaces_for_room": rebuild_surfaces_for_room,
            "rebuild": rebuild,
        }[name]
    raise AttributeError(name)
