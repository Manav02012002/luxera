from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from luxera.geometry.contracts import assert_surface, assert_valid_polygon
from luxera.geometry.openings.opening_uv import opening_uv_polygon
from luxera.geometry.openings.project_uv import lift_uv_to_3d, project_points_to_uv, wall_basis
from luxera.geometry.openings.subtract import UVPolygon, subtract_openings
from luxera.geometry.openings.triangulate_wall import wall_mesh_from_uv
from luxera.geometry.primitives import Polygon2D
from luxera.geometry.tolerance import EPS_PLANE, EPS_POS
from luxera.ops.base import OpContext, execute_op
from luxera.project.schema import MaterialSpec, OpeningSpec, Project, RoomSpec, SurfaceSpec
from luxera.scene.surfaces import room_footprint_from_spec, room_surfaces_from_footprint


def create_room(
    project: Project,
    *,
    room_id: str,
    name: str,
    width: float,
    length: float,
    height: float,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ctx: Optional[OpContext] = None,
) -> RoomSpec:
    def _validate() -> None:
        if width <= 0.0 or length <= 0.0 or height <= 0.0:
            raise ValueError("Room dimensions must be > 0")
        if any(r.id == room_id for r in project.geometry.rooms):
            raise ValueError(f"Room already exists: {room_id}")

    def _mutate() -> RoomSpec:
        room = RoomSpec(id=room_id, name=name, width=float(width), length=float(length), height=float(height), origin=origin)
        project.geometry.rooms.append(room)
        return room

    return execute_op(
        project,
        op_name="create_room",
        args={"room_id": room_id, "name": name, "width": width, "length": length, "height": height, "origin": origin},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def create_room_from_footprint(
    project: Project,
    *,
    room_id: str,
    name: str,
    footprint: Sequence[Tuple[float, float]],
    height: float,
    origin_z: float = 0.0,
    ctx: Optional[OpContext] = None,
) -> RoomSpec:
    fp = [(float(x), float(y)) for x, y in footprint]

    def _validate() -> None:
        if len(fp) < 3:
            raise ValueError("footprint must have at least 3 points")
        if height <= 0.0:
            raise ValueError("height must be > 0")
        if any(r.id == room_id for r in project.geometry.rooms):
            raise ValueError(f"Room already exists: {room_id}")
        assert_valid_polygon(Polygon2D(points=list(fp)))

    def _mutate() -> RoomSpec:
        xs = [p[0] for p in fp]
        ys = [p[1] for p in fp]
        room = RoomSpec(
            id=room_id,
            name=name,
            width=float(max(xs) - min(xs)),
            length=float(max(ys) - min(ys)),
            height=float(height),
            origin=(float(min(xs)), float(min(ys)), float(origin_z)),
            footprint=fp,
        )
        project.geometry.rooms.append(room)
        return room

    return execute_op(
        project,
        op_name="create_room_from_footprint",
        args={"room_id": room_id, "name": name, "footprint_points": len(fp), "height": height, "origin_z": origin_z},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def create_wall_polygon(
    project: Project,
    *,
    surface_id: str,
    name: str,
    vertices: Sequence[Tuple[float, float, float]],
    room_id: Optional[str] = None,
    material_id: Optional[str] = None,
    ctx: Optional[OpContext] = None,
) -> SurfaceSpec:
    def _validate() -> None:
        if len(vertices) < 3:
            raise ValueError("Wall polygon requires at least 3 vertices")
        if any(s.id == surface_id for s in project.geometry.surfaces):
            raise ValueError(f"Surface already exists: {surface_id}")
        assert_surface(type("SurfacePayload", (), {"vertices": list(vertices)})())

    def _mutate() -> SurfaceSpec:
        surface = SurfaceSpec(
            id=surface_id,
            name=name,
            kind="wall",
            vertices=[tuple(float(x) for x in v) for v in vertices],
            room_id=room_id,
            material_id=material_id,
        )
        project.geometry.surfaces.append(surface)
        return surface

    return execute_op(
        project,
        op_name="create_wall_polygon",
        args={"surface_id": surface_id, "name": name, "vertex_count": len(vertices), "room_id": room_id, "material_id": material_id},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def add_opening(
    project: Project,
    *,
    opening_id: str,
    name: str,
    host_surface_id: str,
    vertices: Sequence[Tuple[float, float, float]],
    opening_type: str = "window",
    visible_transmittance: Optional[float] = None,
    ctx: Optional[OpContext] = None,
) -> OpeningSpec:
    def _validate() -> None:
        if len(vertices) < 3:
            raise ValueError("Opening polygon requires at least 3 vertices")
        if any(o.id == opening_id for o in project.geometry.openings):
            raise ValueError(f"Opening already exists: {opening_id}")
        if not any(s.id == host_surface_id for s in project.geometry.surfaces):
            raise ValueError(f"Host surface not found: {host_surface_id}")
        assert_surface(type("SurfacePayload", (), {"vertices": list(vertices)})())

    def _mutate() -> OpeningSpec:
        opening = OpeningSpec(
            id=opening_id,
            name=name,
            opening_type=str(opening_type),  # type: ignore[arg-type]
            kind=str(opening_type),  # type: ignore[arg-type]
            host_surface_id=host_surface_id,
            vertices=[tuple(float(x) for x in v) for v in vertices],
            visible_transmittance=visible_transmittance,
            vt=visible_transmittance,
            is_daylight_aperture=(str(opening_type).lower() == "window"),
        )
        project.geometry.openings.append(opening)
        return opening

    return execute_op(
        project,
        op_name="add_opening",
        args={"opening_id": opening_id, "host_surface_id": host_surface_id, "opening_type": opening_type, "vertex_count": len(vertices)},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def _edge_key_2d(a: Tuple[float, float], b: Tuple[float, float], eps: float = EPS_PLANE) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    s = 1.0 / max(eps, EPS_POS)
    aa = (int(round(a[0] * s)), int(round(a[1] * s)))
    bb = (int(round(b[0] * s)), int(round(b[1] * s)))
    return (aa, bb) if aa <= bb else (bb, aa)


def create_walls_from_footprint(
    project: Project,
    *,
    room_id: str,
    thickness: float,
    alignment: str = "center",
    shared_walls: bool = True,
    ctx: Optional[OpContext] = None,
) -> List[SurfaceSpec]:
    def _validate() -> None:
        if thickness <= 0.0:
            raise ValueError("thickness must be > 0")
        if alignment not in {"inside", "outside", "center"}:
            raise ValueError("alignment must be inside|outside|center")
        _ = next(r for r in project.geometry.rooms if r.id == room_id)

    def _mutate() -> List[SurfaceSpec]:
        room = next(r for r in project.geometry.rooms if r.id == room_id)
        if room.footprint and len(room.footprint) >= 3:
            fp = [(float(x), float(y)) for x, y in room.footprint]
        else:
            ox, oy, _oz = room.origin
            fp = [(ox, oy), (ox + room.width, oy), (ox + room.width, oy + room.length), (ox, oy + room.length)]
        if alignment in {"inside", "outside"} and thickness > 0.0:
            try:
                from shapely.geometry import Polygon  # type: ignore

                poly = Polygon(fp)
                sign = -1.0 if alignment == "inside" else 1.0
                off = poly.buffer(sign * (float(thickness) * 0.5), join_style=2)
                if not off.is_empty:
                    fp2 = [(float(x), float(y)) for x, y in list(off.exterior.coords)[:-1]]
                    if len(fp2) >= 3:
                        fp = fp2
            except Exception:
                pass
        z0 = float(room.origin[2])
        z1 = z0 + float(room.height)
        existing_by_edge = {}
        if shared_walls:
            for s in project.geometry.surfaces:
                if s.kind != "wall" or len(s.vertices) < 2:
                    continue
                a = (float(s.vertices[0][0]), float(s.vertices[0][1]))
                b = (float(s.vertices[1][0]), float(s.vertices[1][1]))
                existing_by_edge[_edge_key_2d(a, b)] = s

        created: List[SurfaceSpec] = []
        for i in range(len(fp)):
            a = fp[i]
            b = fp[(i + 1) % len(fp)]
            ek = _edge_key_2d(a, b)
            if shared_walls and ek in existing_by_edge:
                continue
            sid = f"{room_id}_wall_{i+1}"
            if any(ss.id == sid for ss in project.geometry.surfaces):
                sid = f"{sid}_shared"
            s = SurfaceSpec(
                id=sid,
                name=f"{room.name} Wall {i+1}",
                kind="wall",
                room_id=room_id,
                vertices=[(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)],
            )
            project.geometry.surfaces.append(s)
            created.append(s)
        return created

    return execute_op(
        project,
        op_name="create_walls_from_footprint",
        args={"room_id": room_id, "thickness": thickness, "alignment": alignment, "shared_walls": shared_walls},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def place_opening_on_wall(
    project: Project,
    *,
    opening_id: str,
    host_surface_id: str,
    width: float,
    height: float,
    sill_height: float,
    head_height: Optional[float] = None,
    distance_from_corner: Optional[float] = None,
    click_point: Optional[Tuple[float, float, float]] = None,
    opening_type: str = "window",
    glazing_material_id: Optional[str] = None,
    ctx: Optional[OpContext] = None,
) -> Tuple[OpeningSpec, Optional[SurfaceSpec]]:
    def _validate() -> None:
        if width <= 0.0 or height <= 0.0:
            raise ValueError("opening width/height must be > 0")
        if any(o.id == opening_id for o in project.geometry.openings):
            raise ValueError(f"Opening already exists: {opening_id}")
        _ = next(s for s in project.geometry.surfaces if s.id == host_surface_id)
        if distance_from_corner is None and click_point is None:
            raise ValueError("provide distance_from_corner or click_point")

    def _mutate() -> Tuple[OpeningSpec, Optional[SurfaceSpec]]:
        wall = next(s for s in project.geometry.surfaces if s.id == host_surface_id)
        p0, u, v, _n = wall_basis(wall)
        wall_uv = project_points_to_uv(list(wall.vertices), p0, u, v)
        us = [t[0] for t in wall_uv]
        vs = [t[1] for t in wall_uv]
        u_min, u_max = min(us), max(us)
        v_min, v_max = min(vs), max(vs)

        ov0 = v_min + float(sill_height)
        ov1 = v_min + (float(head_height) if head_height is not None else (float(sill_height) + float(height)))
        ov1 = min(ov1, v_max - (EPS_PLANE * 100.0))
        if ov1 <= ov0:
            raise ValueError("invalid sill/head heights for host wall")
        if click_point is not None:
            uv_click = project_points_to_uv([click_point], p0, u, v)[0]
            uc = float(uv_click[0])
        else:
            uc = u_min + float(distance_from_corner or 0.0) + float(width) * 0.5
        ou0 = max(u_min, uc - float(width) * 0.5)
        ou1 = min(u_max, ou0 + float(width))
        opening_uv = [(ou0, ov0), (ou1, ov0), (ou1, ov1), (ou0, ov1)]
        verts = lift_uv_to_3d(opening_uv, p0, u, v)

        opening = OpeningSpec(
            id=opening_id,
            name=opening_id,
            opening_type=str(opening_type),  # type: ignore[arg-type]
            kind=str(opening_type),  # type: ignore[arg-type]
            host_surface_id=host_surface_id,
            vertices=verts,
            is_daylight_aperture=(str(opening_type).lower() == "window"),
        )
        assert_surface(type("SurfacePayload", (), {"vertices": list(verts)})())
        project.geometry.openings.append(opening)

        host_openings = [o for o in project.geometry.openings if o.host_surface_id == wall.id and len(o.vertices) >= 3]
        opening_polys_uv = [opening_uv_polygon(o, wall) for o in host_openings]
        wall_poly = UVPolygon(outer=wall_uv)
        cut = subtract_openings(wall_poly, opening_polys_uv)
        polygons = [cut] if isinstance(cut, UVPolygon) else list(cut.polygons)
        if not polygons:
            raise ValueError("opening fully removes host wall surface")

        wall_parts: List[SurfaceSpec] = []
        k = 0
        for poly in polygons:
            if poly.holes:
                mesh = wall_mesh_from_uv(poly, p0, u, v)
                for a, b, c in mesh.faces:
                    sid = wall.id if k == 0 else f"{wall.id}:tri{k}"
                    candidate = SurfaceSpec(
                        id=sid,
                        name=wall.name,
                        kind="wall",
                        room_id=wall.room_id,
                        material_id=wall.material_id,
                        vertices=[mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]],
                    )
                    assert_surface(candidate)
                    wall_parts.append(candidate)
                    k += 1
                continue
            sid = wall.id if k == 0 else f"{wall.id}:part{k}"
            candidate = SurfaceSpec(
                id=sid,
                name=wall.name,
                kind="wall",
                room_id=wall.room_id,
                material_id=wall.material_id,
                vertices=lift_uv_to_3d(poly.outer, p0, u, v),
            )
            assert_surface(candidate)
            wall_parts.append(candidate)
            k += 1
        project.geometry.surfaces = [
            s
            for s in project.geometry.surfaces
            if s.id != wall.id and not s.id.startswith(f"{wall.id}:part") and not s.id.startswith(f"{wall.id}:tri")
        ] + wall_parts

        glazing: Optional[SurfaceSpec] = None
        if str(opening_type).lower() == "window":
            gid = f"{opening_id}:glazing"
            glazing = SurfaceSpec(
                id=gid,
                name=f"{opening_id} Glazing",
                kind="custom",
                room_id=wall.room_id,
                material_id=glazing_material_id,
                vertices=list(verts),
            )
            assert_surface(glazing)
            project.geometry.surfaces.append(glazing)
        return opening, glazing

    return execute_op(
        project,
        op_name="place_opening_on_wall",
        args={
            "opening_id": opening_id,
            "host_surface_id": host_surface_id,
            "opening_type": opening_type,
            "width": width,
            "height": height,
            "sill_height": sill_height,
            "head_height": head_height,
            "distance_from_corner": distance_from_corner,
            "has_click_point": click_point is not None,
        },
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def edit_wall_and_propagate_adjacency(
    project: Project,
    *,
    wall_id: str,
    new_start: Tuple[float, float, float],
    new_end: Tuple[float, float, float],
    ctx: Optional[OpContext] = None,
) -> SurfaceSpec:
    def _validate() -> None:
        _ = next(s for s in project.geometry.surfaces if s.id == wall_id and s.kind == "wall")

    def _mutate() -> SurfaceSpec:
        wall = next(s for s in project.geometry.surfaces if s.id == wall_id and s.kind == "wall")
        old0 = (float(wall.vertices[0][0]), float(wall.vertices[0][1]))
        old1 = (float(wall.vertices[1][0]), float(wall.vertices[1][1]))
        z0 = float(min(v[2] for v in wall.vertices))
        z1 = float(max(v[2] for v in wall.vertices))
        ns = (float(new_start[0]), float(new_start[1]), z0)
        ne = (float(new_end[0]), float(new_end[1]), z0)
        wall.vertices = [ns, ne, (ne[0], ne[1], z1), (ns[0], ns[1], z1)]

        # Propagate changed edge endpoints into room footprints for all adjacent rooms.
        def _near(a: Tuple[float, float], b: Tuple[float, float], eps: float = EPS_PLANE) -> bool:
            return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps

        for room in project.geometry.rooms:
            if not room.footprint:
                continue
            fp = list(room.footprint)
            changed = False
            for i in range(len(fp)):
                a = fp[i]
                b = fp[(i + 1) % len(fp)]
                if _near(a, old0) and _near(b, old1):
                    fp[i] = (float(new_start[0]), float(new_start[1]))
                    fp[(i + 1) % len(fp)] = (float(new_end[0]), float(new_end[1]))
                    changed = True
                elif _near(a, old1) and _near(b, old0):
                    fp[i] = (float(new_end[0]), float(new_end[1]))
                    fp[(i + 1) % len(fp)] = (float(new_start[0]), float(new_start[1]))
                    changed = True
            if changed:
                room.footprint = fp
                xs = [p[0] for p in fp]
                ys = [p[1] for p in fp]
                room.origin = (float(min(xs)), float(min(ys)), room.origin[2])
                room.width = float(max(xs) - min(xs))
                room.length = float(max(ys) - min(ys))
        return wall

    return execute_op(
        project,
        op_name="edit_wall_and_propagate_adjacency",
        args={"wall_id": wall_id},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def extrude_room_to_surfaces(project: Project, room_id: str, *, replace_existing: bool = False, ctx: Optional[OpContext] = None) -> List[SurfaceSpec]:
    def _validate() -> None:
        _ = next(r for r in project.geometry.rooms if r.id == room_id)

    def _mutate() -> List[SurfaceSpec]:
        room = next(r for r in project.geometry.rooms if r.id == room_id)
        if replace_existing:
            project.geometry.surfaces = [s for s in project.geometry.surfaces if s.room_id != room_id]
        footprint = room_footprint_from_spec(room)
        assert_valid_polygon(footprint.outer)
        generated = room_surfaces_from_footprint(room, footprint)
        for s in generated:
            assert_surface(s)
        project.geometry.surfaces.extend(generated)
        return generated

    return execute_op(
        project,
        op_name="extrude_room_to_surfaces",
        args={"room_id": room_id, "replace_existing": bool(replace_existing)},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def assign_material_to_surface_set(project: Project, *, surface_ids: Iterable[str], material_id: str, ctx: Optional[OpContext] = None) -> int:
    sid = set(surface_ids)

    def _validate() -> None:
        _ = next(m for m in project.materials if m.id == material_id)
        missing = [s for s in sid if not any(sf.id == s for sf in project.geometry.surfaces)]
        if missing:
            raise ValueError(f"Unknown surfaces: {missing}")

    def _mutate() -> int:
        count = 0
        for s in project.geometry.surfaces:
            if s.id in sid:
                s.material_id = material_id
                count += 1
        return count

    return execute_op(
        project,
        op_name="assign_material_to_surface_set",
        args={"material_id": material_id, "surface_count": len(sid)},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def ensure_material(
    project: Project,
    *,
    material_id: str,
    name: str,
    reflectance: float,
    diffuse_reflectance_rgb: Optional[Tuple[float, float, float]] = None,
    specular_reflectance: Optional[float] = None,
    roughness: Optional[float] = None,
    transmittance: float = 0.0,
    ctx: Optional[OpContext] = None,
) -> MaterialSpec:
    def _validate() -> None:
        if reflectance < 0.0 or reflectance > 1.0:
            raise ValueError("reflectance must be in [0,1]")

    def _mutate() -> MaterialSpec:
        for m in project.materials:
            if m.id == material_id:
                return m
        mat = MaterialSpec(
            id=material_id,
            name=name,
            reflectance=float(reflectance),
            diffuse_reflectance_rgb=diffuse_reflectance_rgb,
            specular_reflectance=specular_reflectance,
            roughness=roughness,
            transmittance=float(transmittance),
        )
        project.materials.append(mat)
        return mat

    return execute_op(
        project,
        op_name="ensure_material",
        args={"material_id": material_id, "name": name, "reflectance": reflectance},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )
