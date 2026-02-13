from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from luxera.geometry.spatial import point_in_polygon
from luxera.project.schema import NoGoZoneSpec, RoomSpec, ZoneSpec

Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]


def room_polygon(room: RoomSpec) -> List[Point2]:
    if room.footprint:
        return [(float(p[0]), float(p[1])) for p in room.footprint]
    x0, y0, _ = room.origin
    x1 = float(x0) + float(room.width)
    y1 = float(y0) + float(room.length)
    return [
        (float(x0), float(y0)),
        (x1, float(y0)),
        (x1, y1),
        (float(x0), y1),
    ]


def _zone_room_ids(zone: ZoneSpec) -> List[str]:
    ids = [str(x) for x in zone.room_ids]
    if zone.room_id:
        ids.append(str(zone.room_id))
    return ids


def zone_applies_to_room(zone: ZoneSpec, room_id: str) -> bool:
    room_ids = _zone_room_ids(zone)
    if not room_ids:
        return False
    return str(room_id) in room_ids


def zones_for_room(zones: Iterable[ZoneSpec], room_id: str) -> List[ZoneSpec]:
    return [z for z in zones if zone_applies_to_room(z, room_id)]


def resolve_zone_polygon(zone: ZoneSpec, rooms_by_id: Dict[str, RoomSpec]) -> List[Point2]:
    if zone.polygon2d:
        return [(float(p[0]), float(p[1])) for p in zone.polygon2d]
    room_ids = _zone_room_ids(zone)
    if not room_ids:
        raise ValueError(f"Zone '{zone.id}' is missing room assignment")
    rid = room_ids[0]
    room = rooms_by_id.get(rid)
    if room is None:
        raise ValueError(f"Zone '{zone.id}' references unknown room '{rid}'")
    return room_polygon(room)


def no_go_polygon(zone: NoGoZoneSpec) -> List[Point2]:
    return [(float(v[0]), float(v[1])) for v in zone.vertices if len(v) >= 2]


def obstacle_polygons_for_room(no_go_zones: Sequence[NoGoZoneSpec], room_id: Optional[str]) -> List[List[Point2]]:
    out: List[List[Point2]] = []
    for ng in no_go_zones:
        if ng.room_id is not None and room_id is not None and str(ng.room_id) != str(room_id):
            continue
        poly = no_go_polygon(ng)
        if len(poly) >= 3:
            out.append(poly)
    return out


def point_in_any_polygon(point: Point2, polygons: Sequence[Sequence[Point2]]) -> bool:
    for poly in polygons:
        if len(poly) >= 3 and point_in_polygon(point, poly):
            return True
    return False
