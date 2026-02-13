from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from luxera.geometry.materials import encode_wall_side_material_tags
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
from luxera.geometry.param.model import FootprintParam, OpeningParam, RoomParam, SharedWallParam, WallParam
from luxera.project.schema import Project, SurfaceSpec


@dataclass(frozen=True)
class DerivedRoomGeometry:
    room_id: str
    floor: SurfaceSpec
    ceiling: SurfaceSpec
    walls: List[SurfaceSpec] = field(default_factory=list)

    @property
    def surfaces(self) -> List[SurfaceSpec]:
        return [self.floor, self.ceiling, *self.walls]


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
    op_uvs = [opening_uv_polygon(op, surface) for op in opening_params]
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
    verts = _wall_vertices(poly[i0], poly[i1], z0, z1)
    base = SurfaceSpec(
        id=surface_id_for_wall_side(wall.id, "A"),
        name=wall.name or wall.id,
        kind="wall",
        room_id=room.id,
        vertices=verts,
    )
    opening_params = [o for o in project.param.openings if o.wall_id == wall.id]
    return _surface_parts_with_openings(base, opening_params)


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
    poly = [(float(x), float(y)) for x, y in fp.polygon2d]
    if len(poly) < 3:
        raise ValueError(f"Footprint has fewer than 3 points: {fp.id}")
    z0 = float(room.origin_z)
    z1 = z0 + float(room.height)

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
    for w in _walls_for_room(project, room.id, len(poly)):
        walls.extend(rebuild_wall(w.id, project) if any(pw.id == w.id for pw in project.param.walls) else [
            SurfaceSpec(
                id=surface_id_for_wall_side(w.id, "A"),
                name=w.name or w.id,
                kind="wall",
                room_id=room.id,
                vertices=_wall_vertices(poly[w.edge_ref[0]], poly[w.edge_ref[1]], z0, z1),
            )
        ])
    for sw in _shared_walls_for_room(project, room.id):
        walls.extend(rebuild_shared_wall(sw.id, project))

    return DerivedRoomGeometry(room_id=room.id, floor=floor, ceiling=ceiling, walls=walls)


def rebuild_surfaces_for_room(room_id: str, project: Project) -> DerivedRoomGeometry:
    derived = rebuild_room(room_id, project)
    new_surfaces = derived.surfaces
    new_ids = {s.id for s in new_surfaces}
    old_by_id = {s.id: s for s in project.geometry.surfaces}
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

    retained: List[SurfaceSpec] = []
    for s in project.geometry.surfaces:
        if s.id in new_ids:
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

    project.geometry.surfaces = retained + new_surfaces
    return derived
