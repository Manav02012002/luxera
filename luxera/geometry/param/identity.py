from __future__ import annotations

from luxera.geometry.id import derived_id


def surface_id_for_wall_side(wall_id: str, side: str) -> str:
    side_norm = str(side).upper()
    if side_norm not in {"A", "B"}:
        raise ValueError("side must be 'A' or 'B'")
    return derived_id(str(wall_id), "surface.wall.side", {"side": side_norm})


def surface_id_for_floor(room_id: str) -> str:
    return derived_id(str(room_id), "surface.floor", {})


def surface_id_for_ceiling(room_id: str) -> str:
    return derived_id(str(room_id), "surface.ceiling", {})


def surface_id_for_shared_wall(shared_wall_id: str) -> str:
    return derived_id(str(shared_wall_id), "surface.shared_wall", {})
