from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import numpy as np

from luxera.geometry.primitives import Polygon2D, RoomFootprint2D
from luxera.project.schema import RoomSpec, SurfaceSpec


SurfaceKind = Literal["floor", "ceiling", "wall", "opening", "custom"]


@dataclass(frozen=True)
class Surface:
    id: str
    kind: SurfaceKind
    polygon3d: Optional[List[Tuple[float, float, float]]] = None
    mesh_ref: Optional[str] = None
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    area: float = 0.0
    material_id: Optional[str] = None
    room_id: Optional[str] = None


def _polygon_area_2d(poly: List[Tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _surface_area_3d(poly: List[Tuple[float, float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    p0 = np.array(poly[0], dtype=float)
    area = 0.0
    for i in range(1, len(poly) - 1):
        a = np.array(poly[i], dtype=float) - p0
        b = np.array(poly[i + 1], dtype=float) - p0
        area += 0.5 * np.linalg.norm(np.cross(a, b))
    return float(area)


def room_surfaces_from_footprint(room: RoomSpec, footprint: RoomFootprint2D, *, material_id: Optional[str] = None) -> List[SurfaceSpec]:
    x0, y0, z0 = room.origin
    z1 = z0 + float(room.height)
    outer = list(footprint.outer.points)
    floor = [(x0 + x, y0 + y, z0) for x, y in outer]
    ceil = [(x0 + x, y0 + y, z1) for x, y in reversed(outer)]
    out: List[SurfaceSpec] = [
        SurfaceSpec(id=f"{room.id}_floor", name=f"{room.name} Floor", kind="floor", room_id=room.id, material_id=material_id, vertices=floor),
        SurfaceSpec(id=f"{room.id}_ceiling", name=f"{room.name} Ceiling", kind="ceiling", room_id=room.id, material_id=material_id, vertices=ceil),
    ]
    rect_like = len(outer) == 4
    wall_ids = ["wall_south", "wall_east", "wall_north", "wall_west"] if rect_like else []
    wall_names = ["South Wall", "East Wall", "North Wall", "West Wall"] if rect_like else []
    for i in range(len(outer)):
        a = outer[i]
        b = outer[(i + 1) % len(outer)]
        wall = [
            (x0 + a[0], y0 + a[1], z0),
            (x0 + b[0], y0 + b[1], z0),
            (x0 + b[0], y0 + b[1], z1),
            (x0 + a[0], y0 + a[1], z1),
        ]
        suffix = wall_ids[i] if rect_like else f"wall_{i+1}"
        name = wall_names[i] if rect_like else f"Wall {i+1}"
        out.append(
            SurfaceSpec(
                id=f"{room.id}_{suffix}",
                name=f"{room.name} {name}",
                kind="wall",
                room_id=room.id,
                material_id=material_id,
                vertices=wall,
            )
        )
    return out


def room_footprint_from_spec(room: RoomSpec) -> RoomFootprint2D:
    if room.footprint:
        return RoomFootprint2D(outer=Polygon2D(points=[(float(x), float(y)) for x, y in room.footprint]))
    return RoomFootprint2D(
        outer=Polygon2D(
            points=[
                (0.0, 0.0),
                (float(room.width), 0.0),
                (float(room.width), float(room.length)),
                (0.0, float(room.length)),
            ]
        )
    )
