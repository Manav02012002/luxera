from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from luxera.geometry.id import stable_id
from luxera.geometry.param.model import FootprintParam, RoomParam, SharedWallParam
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
                shared_edge_id=e.id,
                edge_geom=e.overlap_segment,
                room_a=e.room_a,
                room_b=e.room_b,
                thickness=float(thickness),
            )
        )
    return out


def _near(a: Tuple[float, float], b: Tuple[float, float], eps: float = 1e-6) -> bool:
    return abs(float(a[0]) - float(b[0])) <= eps and abs(float(a[1]) - float(b[1])) <= eps


def _replace_edge_points(poly: List[Tuple[float, float]], old_seg: Tuple[Tuple[float, float], Tuple[float, float]], new_seg: Tuple[Tuple[float, float], Tuple[float, float]]) -> bool:
    changed = False
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if _near(a, old_seg[0]) and _near(b, old_seg[1]):
            poly[i] = (float(new_seg[0][0]), float(new_seg[0][1]))
            poly[(i + 1) % n] = (float(new_seg[1][0]), float(new_seg[1][1]))
            changed = True
        elif _near(a, old_seg[1]) and _near(b, old_seg[0]):
            poly[i] = (float(new_seg[1][0]), float(new_seg[1][1]))
            poly[(i + 1) % n] = (float(new_seg[0][0]), float(new_seg[0][1]))
            changed = True
    return changed


def edit_shared_edge(
    footprints: List[FootprintParam],
    rooms: List[RoomParam],
    shared_walls: List[SharedWallParam],
    *,
    shared_wall_id: str,
    new_start: Tuple[float, float],
    new_end: Tuple[float, float],
) -> SharedWallParam:
    sw = next(w for w in shared_walls if w.id == shared_wall_id)
    old_seg = ((float(sw.edge_geom[0][0]), float(sw.edge_geom[0][1])), (float(sw.edge_geom[1][0]), float(sw.edge_geom[1][1])))
    new_seg = ((float(new_start[0]), float(new_start[1])), (float(new_end[0]), float(new_end[1])))
    sw.edge_geom = new_seg

    fp_by_id: Dict[str, FootprintParam] = {fp.id: fp for fp in footprints}
    for room_id in [sw.room_a, sw.room_b]:
        if room_id is None:
            continue
        room = next((r for r in rooms if r.id == room_id), None)
        if room is None:
            continue
        fp = fp_by_id.get(room.footprint_id)
        if fp is None:
            continue
        poly = [(float(x), float(y)) for x, y in fp.polygon2d]
        if _replace_edge_points(poly, old_seg, new_seg):
            fp.polygon2d = poly
            room.polygon2d = list(poly)
    return sw


def reconcile_shared_walls(
    rooms: List[RoomParam],
    footprints: List[FootprintParam],
    shared_walls: List[SharedWallParam],
    *,
    default_thickness: float = 0.2,
    delete_orphans: bool = False,
) -> List[SharedWallParam]:
    fp_by_id: Dict[str, FootprintParam] = {fp.id: fp for fp in footprints}
    enriched: List[RoomParam] = []
    for r in rooms:
        rr = RoomParam(
            id=r.id,
            footprint_id=r.footprint_id,
            height=r.height,
            wall_thickness=r.wall_thickness,
            wall_thickness_policy=r.wall_thickness_policy,
            wall_align_mode=r.wall_align_mode,
            name=r.name,
            origin_z=r.origin_z,
            floor_slab_thickness=r.floor_slab_thickness,
            ceiling_slab_thickness=r.ceiling_slab_thickness,
            floor_offset=r.floor_offset,
            ceiling_offset=r.ceiling_offset,
            polygon2d=list(r.polygon2d),
        )
        if not rr.polygon2d:
            fp = fp_by_id.get(rr.footprint_id)
            rr.polygon2d = list(fp.polygon2d) if fp is not None else []
        enriched.append(rr)

    detected = find_shared_edges(enriched)
    by_edge_id: Dict[str, SharedWallParam] = {str(w.shared_edge_id): w for w in shared_walls if w.shared_edge_id}
    out: List[SharedWallParam] = []

    seen_ids: set[str] = set()
    for e in detected:
        seen_ids.add(e.id)
        existing = by_edge_id.get(e.id)
        if existing is None:
            wall_id = stable_id("shared_wall", {"shared_edge_id": e.id, "room_a": e.room_a, "room_b": e.room_b})
            existing = SharedWallParam(
                id=wall_id,
                shared_edge_id=e.id,
                edge_geom=e.geom,
                room_a=e.room_a,
                room_b=e.room_b,
                thickness=float(default_thickness),
            )
        else:
            existing.edge_geom = e.geom
            existing.room_a = e.room_a
            existing.room_b = e.room_b
        out.append(existing)

    for w in shared_walls:
        if w.shared_edge_id and str(w.shared_edge_id) in seen_ids:
            continue
        # Lost adjacency: keep as exterior wall when at least one room still exists.
        room_exists_a = any(r.id == w.room_a for r in rooms)
        room_exists_b = w.room_b is not None and any(r.id == w.room_b for r in rooms)
        if room_exists_a and room_exists_b:
            w.room_b = None
            out.append(w)
        elif room_exists_a or room_exists_b:
            if not room_exists_a and room_exists_b and w.room_b is not None:
                w.room_a = w.room_b
            w.room_b = None
            out.append(w)
        elif not delete_orphans:
            out.append(w)

    return out
