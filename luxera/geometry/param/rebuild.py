from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from luxera.geometry.materials import encode_wall_side_material_tags
from luxera.geometry.curves.arc import Arc
from luxera.geometry.openings.opening_uv import opening_uv_polygon
from luxera.geometry.openings.project_uv import lift_uv_to_3d, project_points_to_uv, wall_basis
from luxera.geometry.openings.subtract import UVPolygon, subtract_openings
from luxera.geometry.openings.triangulate_wall import wall_mesh_from_uv
from luxera.geometry.param.identity import (
    surface_id_for_ceiling,
    surface_id_for_floor,
    surface_id_for_shared_wall,
    surface_id_for_wall_side,
)
from luxera.geometry.param.graph import build_param_graph
from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, SharedWallParam, WallParam
from luxera.geometry.spatial import point_in_polygon
from luxera.geometry.selection_sets import remap_selection_sets
from luxera.geometry.zones import obstacle_polygons_for_room, resolve_zone_polygon, room_polygon
from luxera.calcs.masks import apply_obstacle_masks, apply_opening_proximity_mask
from luxera.project.schema import OpeningSpec, Project, SurfaceSpec


@dataclass(frozen=True)
class DerivedRoomGeometry:
    room_id: str
    floor: SurfaceSpec
    ceiling: SurfaceSpec
    walls: List[SurfaceSpec] = field(default_factory=list)

    @property
    def surfaces(self) -> List[SurfaceSpec]:
        return [self.floor, self.ceiling, *self.walls]


@dataclass(frozen=True)
class RebuildResult:
    regenerated: set[str]
    stable_id_map: Dict[str, List[str]]
    attachment_remap: Dict[str, str]


def _edge_key(i0: int, i1: int) -> str:
    return f"{int(i0)}:{int(i1)}"


def _edge_bulge(fp: FootprintParam, i0: int, i1: int) -> float:
    if fp.edge_ids and 0 <= int(i0) < len(fp.edge_ids):
        eid = str(fp.edge_ids[int(i0)])
        if eid in fp.edge_bulges:
            return float(fp.edge_bulges[eid])
    return float(fp.edge_bulges.get(_edge_key(i0, i1), 0.0))


def _sample_bulge_edge(a: Tuple[float, float], b: Tuple[float, float], bulge: float, seg_len: float = 0.5) -> List[Tuple[float, float]]:
    if abs(float(bulge)) <= 1e-12:
        return [a, b]
    arc = Arc.from_bulge(a, b, float(bulge))
    sweep = max(arc.sweep(), 1e-9)
    arc_len = abs(float(arc.radius) * sweep)
    n = max(2, int(math.ceil(arc_len / max(float(seg_len), 0.05))) + 1)
    return [arc.point_at(i / float(n - 1)) for i in range(n)]


def _outer_with_bulges(fp: FootprintParam) -> List[Tuple[float, float]]:
    poly = [(float(x), float(y)) for x, y in fp.polygon2d]
    if len(poly) < 3:
        return poly
    out: List[Tuple[float, float]] = []
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        seg = _sample_bulge_edge(poly[i], poly[j], _edge_bulge(fp, i, j))
        if not out:
            out.extend(seg)
        else:
            out.extend(seg[1:])
    return out


def _room(project: Project, room_id: str) -> RoomParam:
    for r in project.param.rooms:
        if r.id == room_id:
            return r
    raise ValueError(f"Param room not found: {room_id}")


def _footprint(project: Project, footprint_id: str) -> FootprintParam:
    for fp in project.param.footprints:
        if fp.id == footprint_id:
            return fp
    raise ValueError(f"Footprint not found: {footprint_id}")


def _walls_for_room(project: Project, room_id: str, n_edges: int) -> List[WallParam]:
    walls = [w for w in project.param.walls if w.room_id == room_id]
    if walls:
        return walls
    out: List[WallParam] = []
    for i in range(n_edges):
        out.append(
            WallParam(
                id=f"{room_id}:wall:{i}",
                room_id=room_id,
                edge_ref=(i, (i + 1) % n_edges),
            )
        )
    return out


def _shared_walls_for_room(project: Project, room_id: str) -> List[SharedWallParam]:
    return [w for w in project.param.shared_walls if w.room_a == room_id or w.room_b == room_id]


def _wall_vertices(a: Tuple[float, float], b: Tuple[float, float], z0: float, z1: float) -> List[Tuple[float, float, float]]:
    return [
        (float(a[0]), float(a[1]), float(z0)),
        (float(b[0]), float(b[1]), float(z0)),
        (float(b[0]), float(b[1]), float(z1)),
        (float(a[0]), float(a[1]), float(z1)),
    ]


def _surface_parts_with_openings(
    surface: SurfaceSpec,
    opening_params: List[OpeningParam],
) -> List[SurfaceSpec]:
    if not opening_params:
        return [surface]
    origin, u, v, _n = wall_basis(surface)
    wall_uv = project_points_to_uv(surface.vertices, origin, u, v)
    wu = [float(p[0]) for p in wall_uv]
    wv = [float(p[1]) for p in wall_uv]
    wu0, wu1 = min(wu), max(wu)
    wv0, wv1 = min(wv), max(wv)
    op_uvs: List[List[Tuple[float, float]]] = []
    for op in opening_params:
        try:
            uv = opening_uv_polygon(op, surface, peer_openings=opening_params)
        except ValueError:
            continue
        us = [float(p[0]) for p in uv]
        vs = [float(p[1]) for p in uv]
        if max(us) <= wu0 or min(us) >= wu1 or max(vs) <= wv0 or min(vs) >= wv1:
            continue
        op_uvs.append(uv)
    if not op_uvs:
        return [surface]
    cut = subtract_openings(UVPolygon(outer=wall_uv), op_uvs)
    polygons = [cut] if isinstance(cut, UVPolygon) else list(cut.polygons)
    if not polygons:
        return [surface]

    out: List[SurfaceSpec] = []
    k = 0
    for poly in polygons:
        if poly.holes:
            mesh = wall_mesh_from_uv(poly, origin, u, v)
            for a, b, c in mesh.faces:
                sid = surface.id if k == 0 else f"{surface.id}:tri{k}"
                out.append(
                    SurfaceSpec(
                        id=sid,
                        name=surface.name,
                        kind=surface.kind,
                        room_id=surface.room_id,
                        material_id=surface.material_id,
                        vertices=[mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]],
                        layer=surface.layer,
                        tags=list(surface.tags),
                        two_sided=surface.two_sided,
                        wall_room_side_a=surface.wall_room_side_a,
                        wall_room_side_b=surface.wall_room_side_b,
                        wall_material_side_a=surface.wall_material_side_a,
                        wall_material_side_b=surface.wall_material_side_b,
                    )
                )
                k += 1
            continue
        sid = surface.id if k == 0 else f"{surface.id}:part{k}"
        out.append(
            SurfaceSpec(
                id=sid,
                name=surface.name,
                kind=surface.kind,
                room_id=surface.room_id,
                material_id=surface.material_id,
                vertices=lift_uv_to_3d(poly.outer, origin, u, v),
                layer=surface.layer,
                tags=list(surface.tags),
                two_sided=surface.two_sided,
                wall_room_side_a=surface.wall_room_side_a,
                wall_room_side_b=surface.wall_room_side_b,
                wall_material_side_a=surface.wall_material_side_a,
                wall_material_side_b=surface.wall_material_side_b,
            )
        )
        k += 1
    return out


def _wall_surface_prefix_for_opening(project: Project, opening: OpeningParam) -> Optional[str]:
    if any(w.id == opening.wall_id for w in project.param.walls):
        return surface_id_for_wall_side(opening.wall_id, "A")
    shared = next((w for w in project.param.shared_walls if w.id == opening.wall_id), None)
    if shared is not None:
        return surface_id_for_shared_wall(shared.id)
    return None


def _opening_geometry_for_surface(
    opening: OpeningParam,
    surface: SurfaceSpec,
    peer_openings: Sequence[OpeningParam],
) -> Optional[List[Tuple[float, float, float]]]:
    try:
        uv = opening_uv_polygon(opening, surface, peer_openings=peer_openings)
    except ValueError:
        return None
    origin, u, v, _n = wall_basis(surface)
    return lift_uv_to_3d(uv, origin, u, v)


def _build_param_openings_for_room(
    room_id: str,
    project: Project,
    wall_surfaces: Sequence[SurfaceSpec],
    old_surfaces_by_id: Dict[str, SurfaceSpec],
) -> Tuple[List[OpeningSpec], List[SurfaceSpec], Set[str]]:
    room_wall_ids = {w.id for w in project.param.walls if w.room_id == room_id}
    room_wall_ids.update({w.id for w in project.param.shared_walls if w.room_a == room_id or w.room_b == room_id})
    param_openings = [o for o in project.param.openings if o.wall_id in room_wall_ids]
    by_wall: Dict[str, List[OpeningParam]] = {}
    for op in param_openings:
        by_wall.setdefault(op.wall_id, []).append(op)

    out_openings: List[OpeningSpec] = []
    out_glazing: List[SurfaceSpec] = []
    opening_ids: Set[str] = set()
    for op in param_openings:
        prefix = _wall_surface_prefix_for_opening(project, op)
        if prefix is None:
            continue
        peers = by_wall.get(op.wall_id, [op])
        candidates = [s for s in wall_surfaces if s.id == prefix or s.id.startswith(f"{prefix}:")]
        verts: Optional[List[Tuple[float, float, float]]] = None
        host_id: Optional[str] = None
        for s in candidates:
            ov = _opening_geometry_for_surface(op, s, peers)
            if ov is None:
                continue
            verts = ov
            host_id = s.id
            break
        if not verts or host_id is None:
            continue
        kind = str(op.type)
        out_openings.append(
            OpeningSpec(
                id=op.id,
                name=op.id,
                opening_type=kind,  # type: ignore[arg-type]
                kind=kind,  # type: ignore[arg-type]
                host_surface_id=host_id,
                vertices=verts,
                is_daylight_aperture=(kind == "window"),
                visible_transmittance=op.visible_transmittance,
                vt=op.visible_transmittance,
            )
        )
        opening_ids.add(op.id)
        if kind == "window":
            gid = f"{op.id}:glazing"
            out_glazing.append(
                SurfaceSpec(
                    id=gid,
                    name=f"{op.id} Glazing",
                    kind="custom",
                    room_id=room_id,
                    material_id=(
                        op.glazing_material_id
                        if op.glazing_material_id is not None
                        else (old_surfaces_by_id.get(gid).material_id if gid in old_surfaces_by_id else None)
                    ),
                    vertices=verts,
                )
            )
    return out_openings, out_glazing, opening_ids


def rebuild_wall(wall_id: str, project: Project) -> List[SurfaceSpec]:
    wall = next((w for w in project.param.walls if w.id == wall_id), None)
    if wall is None:
        raise ValueError(f"Wall not found: {wall_id}")
    room = _room(project, wall.room_id)
    fp = _footprint(project, room.footprint_id)
    poly = list(fp.polygon2d)
    if len(poly) < 3:
        raise ValueError(f"Footprint has fewer than 3 points: {fp.id}")
    i0, i1 = int(wall.edge_ref[0]), int(wall.edge_ref[1])
    if not (0 <= i0 < len(poly) and 0 <= i1 < len(poly)):
        raise ValueError(f"Wall edge_ref out of range for wall {wall.id}: {wall.edge_ref}")
    z0 = float(room.origin_z)
    z1 = z0 + float(wall.height if wall.height is not None else room.height)
    bulge = _edge_bulge(fp, i0, i1)
    base_id = surface_id_for_wall_side(wall.id, "A")
    faceted = _sample_bulge_edge(poly[i0], poly[i1], bulge)
    wall_surfaces: List[SurfaceSpec] = []
    for k in range(len(faceted) - 1):
        sid = base_id if k == 0 else f"{base_id}:seg{k}"
        wall_surfaces.append(
            SurfaceSpec(
                id=sid,
                name=wall.name or wall.id,
                kind="wall",
                room_id=room.id,
                vertices=_wall_vertices(faceted[k], faceted[k + 1], z0, z1),
            )
        )
    opening_params = [o for o in project.param.openings if o.wall_id == wall.id]
    if not opening_params:
        return wall_surfaces
    out: List[SurfaceSpec] = []
    for s in wall_surfaces:
        out.extend(_surface_parts_with_openings(s, opening_params))
    return out


def rebuild_shared_wall(shared_wall_id: str, project: Project) -> List[SurfaceSpec]:
    wall = next((w for w in project.param.shared_walls if w.id == shared_wall_id), None)
    if wall is None:
        raise ValueError(f"Shared wall not found: {shared_wall_id}")
    room = _room(project, wall.room_a)
    z0 = float(room.origin_z)
    z1 = z0 + float(wall.height if wall.height is not None else room.height)
    a, b = wall.edge_geom
    verts = _wall_vertices(a, b, z0, z1)
    s = SurfaceSpec(
        id=surface_id_for_shared_wall(wall.id),
        name=wall.name or wall.id,
        kind="wall",
        room_id=None,
        vertices=verts,
        material_id=wall.wall_material_side_a or wall.wall_material_side_b,
        wall_room_side_a=wall.room_a,
        wall_room_side_b=wall.room_b,
        wall_material_side_a=wall.wall_material_side_a,
        wall_material_side_b=wall.wall_material_side_b,
        tags=[f"room_a={wall.room_a}", f"room_b={wall.room_b or ''}"],
    )
    s.layer = "shared_wall"
    opening_params = [o for o in project.param.openings if o.wall_id == wall.id]
    return _surface_parts_with_openings(s, opening_params)


def rebuild_room(room_id: str, project: Project) -> DerivedRoomGeometry:
    room = _room(project, room_id)
    fp = _footprint(project, room.footprint_id)
    raw_poly = [(float(x), float(y)) for x, y in fp.polygon2d]
    if len(raw_poly) < 3:
        raise ValueError(f"Footprint has fewer than 3 points: {fp.id}")
    poly = _outer_with_bulges(fp)
    z0 = float(room.origin_z) + float(room.floor_offset)
    z1 = float(room.origin_z) + float(room.height) + float(room.ceiling_offset)

    floor = SurfaceSpec(
        id=surface_id_for_floor(room.id),
        name=f"{room.name or room.id} Floor",
        kind="floor",
        room_id=room.id,
        vertices=[(x, y, z0) for x, y in poly],
    )
    ceiling = SurfaceSpec(
        id=surface_id_for_ceiling(room.id),
        name=f"{room.name or room.id} Ceiling",
        kind="ceiling",
        room_id=room.id,
        vertices=[(x, y, z1) for x, y in reversed(poly)],
    )

    walls: List[SurfaceSpec] = []
    for w in _walls_for_room(project, room.id, len(raw_poly)):
        walls.extend(rebuild_wall(w.id, project) if any(pw.id == w.id for pw in project.param.walls) else [
            SurfaceSpec(
                id=surface_id_for_wall_side(w.id, "A"),
                name=w.name or w.id,
                kind="wall",
                room_id=room.id,
                vertices=_wall_vertices(raw_poly[w.edge_ref[0]], raw_poly[w.edge_ref[1]], z0, z1),
            )
        ])
    for sw in _shared_walls_for_room(project, room.id):
        walls.extend(rebuild_shared_wall(sw.id, project))

    return DerivedRoomGeometry(room_id=room.id, floor=floor, ceiling=ceiling, walls=walls)


def rebuild_surfaces_for_room(room_id: str, project: Project) -> DerivedRoomGeometry:
    derived = rebuild_room(room_id, project)
    new_surfaces = derived.surfaces
    new_ids = {s.id for s in new_surfaces}
    old_surfaces = [s for s in project.geometry.surfaces]
    old_by_id = {s.id: s for s in old_surfaces}
    for s in new_surfaces:
        old = old_by_id.get(s.id)
        if old is not None and s.material_id is None:
            s.material_id = old.material_id
        sw = next((x for x in project.param.shared_walls if surface_id_for_shared_wall(x.id) == s.id), None)
        if sw is not None:
            s.wall_room_side_a = sw.room_a
            s.wall_room_side_b = sw.room_b
            s.wall_material_side_a = sw.wall_material_side_a
            s.wall_material_side_b = sw.wall_material_side_b
            s.material_id = sw.wall_material_side_a or sw.wall_material_side_b or s.material_id
            s.tags = [f"room_a={sw.room_a}", f"room_b={sw.room_b or ''}"] + encode_wall_side_material_tags(
                sw.wall_material_side_a,
                sw.wall_material_side_b,
            )

    # Rebuild geometry.openings and glazing surfaces from param openings for this room.
    wall_surfaces = [s for s in new_surfaces if s.kind == "wall"]
    opening_specs, glazing_surfaces, opening_ids = _build_param_openings_for_room(room_id, project, wall_surfaces, old_by_id)
    glazing_ids = {s.id for s in glazing_surfaces}

    retained: List[SurfaceSpec] = []
    for s in project.geometry.surfaces:
        if s.id in new_ids:
            continue
        if s.id in glazing_ids:
            continue
        if s.room_id == room_id and s.kind in {"wall", "floor", "ceiling"}:
            continue
        if any(
            surface_id_for_shared_wall(sw.id) == s.id
            or s.id.startswith(f"{surface_id_for_shared_wall(sw.id)}:part")
            or s.id.startswith(f"{surface_id_for_shared_wall(sw.id)}:tri")
            for sw in _shared_walls_for_room(project, room_id)
        ):
            continue
        retained.append(s)

    # Attachment/material remap for split surfaces.
    for s in new_surfaces:
        if s.material_id is not None:
            continue
        parent_id = s.id.split(":part")[0].split(":tri")[0]
        old_parent = old_by_id.get(parent_id)
        if old_parent is not None and old_parent.material_id is not None:
            s.material_id = old_parent.material_id

    project.geometry.surfaces = retained + new_surfaces + glazing_surfaces
    if opening_ids:
        project.geometry.openings = [o for o in project.geometry.openings if o.id not in opening_ids] + opening_specs
    return derived


def _room_for_footprint(project: Project, footprint_id: str) -> List[str]:
    return [r.id for r in project.param.rooms if r.footprint_id == footprint_id]


def _grid_xy_points(grid: object) -> List[Tuple[float, float]]:
    ox, oy = float(grid.origin[0]), float(grid.origin[1])  # type: ignore[attr-defined]
    nx = max(1, int(grid.nx))  # type: ignore[attr-defined]
    ny = max(1, int(grid.ny))  # type: ignore[attr-defined]
    dx = float(grid.width) / max(nx - 1, 1)  # type: ignore[attr-defined]
    dy = float(grid.height) / max(ny - 1, 1)  # type: ignore[attr-defined]
    out: List[Tuple[float, float]] = []
    for j in range(ny):
        for i in range(nx):
            out.append((ox + i * dx, oy + j * dy))
    return out


def _reclip_grids_for_room(project: Project, room_id: str) -> List[str]:
    room_spec = next((r for r in project.geometry.rooms if r.id == room_id), None)
    param_room = next((r for r in project.param.rooms if r.id == room_id), None)
    base_poly: List[Tuple[float, float]] = []
    if room_spec is not None:
        base_poly = room_polygon(room_spec)
    elif param_room is not None:
        fp = next((f for f in project.param.footprints if f.id == param_room.footprint_id), None)
        if fp is not None:
            base_poly = [(float(x), float(y)) for x, y in fp.polygon2d]
    if len(base_poly) < 3:
        return []
    rooms_by_id = {r.id: r for r in project.geometry.rooms}
    changed: List[str] = []
    for grid in project.grids:
        if grid.room_id != room_id:
            continue
        poly = list(base_poly)
        zone_holes: List[List[Tuple[float, float]]] = []
        if grid.zone_id is not None:
            zone = next((z for z in project.geometry.zones if z.id == grid.zone_id), None)
            if zone is not None:
                poly = resolve_zone_polygon(zone, rooms_by_id)
            pz = next((z for z in project.param.zones if z.id == grid.zone_id), None)
            if pz is not None:
                zone_holes = [[(float(x), float(y)) for x, y in h] for h in pz.holes2d if len(h) >= 3]
        pts_xy = _grid_xy_points(grid)
        mask = [point_in_polygon(p, poly) for p in pts_xy]
        if zone_holes:
            for i, p in enumerate(pts_xy):
                if any(point_in_polygon(p, h) for h in zone_holes):
                    mask[i] = False
        obstacles = obstacle_polygons_for_room(project.geometry.no_go_zones, room_id)
        mask = apply_obstacle_masks(mask, pts_xy, obstacles)
        if bool(getattr(grid, "mask_near_openings", False)) and float(getattr(grid, "opening_mask_margin", 0.0)) > 0.0:
            room_wall_ids = {s.id for s in project.geometry.surfaces if s.kind == "wall" and s.room_id == room_id}
            opening_polys = [
                [(float(v[0]), float(v[1])) for v in o.vertices]
                for o in project.geometry.openings
                if o.host_surface_id in room_wall_ids and len(o.vertices) >= 2
            ]
            mask = apply_opening_proximity_mask(mask, pts_xy, opening_polys, float(getattr(grid, "opening_mask_margin", 0.0)))
        z = float(grid.elevation)
        grid.sample_mask = [bool(x) for x in mask]
        grid.sample_points = [(float(p[0]), float(p[1]), z) for i, p in enumerate(pts_xy) if grid.sample_mask[i]]
        changed.append(grid.id)
    return changed


def rebuild(edited_ids: Sequence[str], project: Project) -> RebuildResult:
    """
    Incremental param rebuild from edited entity IDs.
    Returns regenerated IDs, stable old->new mapping, and attachment remaps.
    """
    graph = build_param_graph(project)
    affected = graph.affected(set(str(x) for x in edited_ids))

    room_ids: set[str] = set()
    for aid in affected:
        if aid.startswith("room:"):
            room_ids.add(aid.split(":", 1)[1])
        elif aid.startswith("wall:"):
            wid = aid.split(":", 1)[1]
            w = next((x for x in project.param.walls if x.id == wid), None)
            if w is not None:
                room_ids.add(w.room_id)
        elif aid.startswith("footprint:"):
            fid = aid.split(":", 1)[1]
            room_ids.update(_room_for_footprint(project, fid))
        elif aid.startswith("zone:"):
            zid = aid.split(":", 1)[1]
            z = next((x for x in project.param.zones if x.id == zid), None)
            if z is not None:
                room_ids.add(z.room_id)

    regenerated: set[str] = set()
    stable_id_map: Dict[str, List[str]] = {}
    attachment_remap: Dict[str, str] = {}

    for room_id in sorted(room_ids):
        old_room_surfaces = [s for s in project.geometry.surfaces if s.room_id == room_id and s.kind in {"wall", "floor", "ceiling"}]
        old_ids = {s.id for s in old_room_surfaces}
        rebuild_surfaces_for_room(room_id, project)
        new_room_surfaces = [s for s in project.geometry.surfaces if s.room_id == room_id and s.kind in {"wall", "floor", "ceiling"}]
        new_ids = {s.id for s in new_room_surfaces}
        regenerated.update(new_ids)
        for oid in sorted(old_ids):
            if oid in new_ids:
                stable_id_map[oid] = [oid]
                continue
            children = sorted([nid for nid in new_ids if nid.startswith(f"{oid}:part") or nid.startswith(f"{oid}:tri")])
            if children:
                stable_id_map[oid] = children
                for cid in children:
                    attachment_remap[cid] = oid
            else:
                # Overlap fallback: remap to best matching new surface by XY bbox overlap.
                old = next((s for s in old_room_surfaces if s.id == oid), None)
                if old is not None:
                    cands = [s for s in new_room_surfaces if s.kind == old.kind]
                    def _bbox_xy(vs: Sequence[Tuple[float, float, float]]) -> Tuple[float, float, float, float]:
                        xs = [float(v[0]) for v in vs]
                        ys = [float(v[1]) for v in vs]
                        return (min(xs), min(ys), max(xs), max(ys))
                    def _overlap(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
                        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
                        iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
                        return ix * iy
                    bo = _bbox_xy(old.vertices)
                    ranked = sorted(((s.id, _overlap(bo, _bbox_xy(s.vertices))) for s in cands), key=lambda x: (-x[1], x[0]))
                    if ranked and ranked[0][1] > 0.0:
                        stable_id_map[oid] = [ranked[0][0]]
                        attachment_remap[ranked[0][0]] = oid
                    else:
                        stable_id_map[oid] = []
                else:
                    stable_id_map[oid] = []

        # Remap host surface references for planes/openings after splits.
        for vp in project.vertical_planes:
            hs = vp.host_surface_id
            if hs and hs in stable_id_map and stable_id_map[hs]:
                vp.host_surface_id = stable_id_map[hs][0]
                attachment_remap[f"vertical_plane:{vp.id}"] = vp.host_surface_id
        for op in project.geometry.openings:
            hs = op.host_surface_id
            if hs and hs in stable_id_map and stable_id_map[hs]:
                op.host_surface_id = stable_id_map[hs][0]
                attachment_remap[f"opening:{op.id}"] = op.host_surface_id

        regenerated.update(f"grid:{gid}" for gid in _reclip_grids_for_room(project, room_id))

    remap_selection_sets(project, stable_id_map, attachment_remap)
    return RebuildResult(regenerated=regenerated, stable_id_map=stable_id_map, attachment_remap=attachment_remap)
