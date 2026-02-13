from __future__ import annotations

from math import isclose
from typing import List, Optional, Sequence, Tuple

from luxera.calcs.masks import apply_obstacle_masks
from luxera.geometry.zones import obstacle_polygons_for_room, resolve_zone_polygon, room_polygon
from luxera.ops.base import OpContext, execute_op
from luxera.geometry.spatial import clip_polyline_to_polygon, snap_polyline_to_segments
from luxera.project.schema import CalcGrid, LineGridSpec, PointSetSpec, Project, VerticalPlaneSpec, WorkplaneSpec


def create_workplane(
    project: Project,
    *,
    workplane_id: str,
    name: str,
    elevation: float,
    margin: float,
    spacing: float,
    room_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    ctx: Optional[OpContext] = None,
) -> WorkplaneSpec:
    def _validate() -> None:
        if spacing <= 0.0:
            raise ValueError("spacing must be > 0")
        if any(w.id == workplane_id for w in project.workplanes):
            raise ValueError(f"Workplane already exists: {workplane_id}")

    def _mutate() -> WorkplaneSpec:
        wp = WorkplaneSpec(
            id=workplane_id,
            name=name,
            elevation=float(elevation),
            margin=float(margin),
            spacing=float(spacing),
            room_id=room_id,
            zone_id=zone_id,
        )
        project.workplanes.append(wp)
        return wp

    return execute_op(
        project,
        op_name="create_workplane",
        args={"workplane_id": workplane_id, "name": name, "elevation": elevation, "spacing": spacing},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def _point_in_polygon(point: tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if isclose(y1, y2):
            continue
        intersects = ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        if intersects:
            inside = not inside
    return inside


def create_calc_grid_from_room(
    project: Project,
    *,
    grid_id: str,
    name: str,
    room_id: str,
    elevation: float,
    spacing: float,
    margin: float = 0.0,
    zone_id: Optional[str] = None,
    ctx: Optional[OpContext] = None,
) -> CalcGrid:
    def _validate() -> None:
        _ = next(r for r in project.geometry.rooms if r.id == room_id)
        if zone_id is not None:
            _ = next(z for z in project.geometry.zones if z.id == zone_id)
        if spacing <= 0.0:
            raise ValueError("spacing must be > 0")
        if any(g.id == grid_id for g in project.grids):
            raise ValueError(f"Grid already exists: {grid_id}")

    def _mutate() -> CalcGrid:
        room = next(r for r in project.geometry.rooms if r.id == room_id)
        width = max(float(room.width) - 2.0 * float(margin), float(spacing))
        height = max(float(room.length) - 2.0 * float(margin), float(spacing))
        nx = max(2, int(round(width / float(spacing))) + 1)
        ny = max(2, int(round(height / float(spacing))) + 1)
        x0, y0, z0 = room.origin
        origin = (x0 + float(margin), y0 + float(margin), z0)
        sample_mask: List[bool] = []
        sample_points: List[Tuple[float, float, float]] = []

        footprint = room_polygon(room)
        if zone_id is not None:
            rooms_by_id = {r.id: r for r in project.geometry.rooms}
            zone = next(z for z in project.geometry.zones if z.id == zone_id)
            footprint = resolve_zone_polygon(zone, rooms_by_id)

        dx = width / max(nx - 1, 1)
        dy = height / max(ny - 1, 1)
        points_xy: List[Tuple[float, float]] = []
        for j in range(ny):
            for i in range(nx):
                px = origin[0] + i * dx
                py = origin[1] + j * dy
                points_xy.append((float(px), float(py)))
                inside = _point_in_polygon((px, py), footprint)
                sample_mask.append(bool(inside))
        obstacles = obstacle_polygons_for_room(project.geometry.no_go_zones, room_id)
        sample_mask = apply_obstacle_masks(sample_mask, points_xy, obstacles)
        for i, inside in enumerate(sample_mask):
            if inside:
                px, py = points_xy[i]
                sample_points.append((float(px), float(py), float(z0 + float(elevation))))

        grid = CalcGrid(
            id=grid_id,
            name=name,
            origin=origin,
            width=width,
            height=height,
            elevation=float(z0 + float(elevation)),
            nx=nx,
            ny=ny,
            room_id=room_id,
            zone_id=zone_id,
            sample_points=sample_points,
            sample_mask=sample_mask,
        )
        project.grids.append(grid)
        return grid

    return execute_op(
        project,
        op_name="create_calc_grid_from_room",
        args={
            "grid_id": grid_id,
            "name": name,
            "room_id": room_id,
            "zone_id": zone_id,
            "elevation": elevation,
            "spacing": spacing,
            "margin": margin,
        },
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def create_vertical_plane(
    project: Project,
    *,
    plane_id: str,
    name: str,
    origin: Tuple[float, float, float],
    width: float,
    height: float,
    nx: int,
    ny: int,
    azimuth_deg: float = 0.0,
    host_surface_id: Optional[str] = None,
    mask_openings: bool = True,
    subrect_u0: Optional[float] = None,
    subrect_u1: Optional[float] = None,
    subrect_v0: Optional[float] = None,
    subrect_v1: Optional[float] = None,
    room_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    ctx: Optional[OpContext] = None,
) -> VerticalPlaneSpec:
    def _validate() -> None:
        if width <= 0.0 or height <= 0.0:
            raise ValueError("Plane dimensions must be > 0")
        if int(nx) < 1 or int(ny) < 1:
            raise ValueError("Plane resolution must be >= 1")

    def _mutate() -> VerticalPlaneSpec:
        plane = VerticalPlaneSpec(
            id=plane_id,
            name=name,
            origin=tuple(float(v) for v in origin),
            width=float(width),
            height=float(height),
            nx=int(nx),
            ny=int(ny),
            azimuth_deg=float(azimuth_deg),
            host_surface_id=host_surface_id,
            mask_openings=bool(mask_openings),
            subrect_u0=(float(subrect_u0) if subrect_u0 is not None else None),
            subrect_u1=(float(subrect_u1) if subrect_u1 is not None else None),
            subrect_v0=(float(subrect_v0) if subrect_v0 is not None else None),
            subrect_v1=(float(subrect_v1) if subrect_v1 is not None else None),
            room_id=room_id,
            zone_id=zone_id,
        )
        project.vertical_planes.append(plane)
        return plane

    return execute_op(
        project,
        op_name="create_vertical_plane",
        args={
            "plane_id": plane_id,
            "name": name,
            "width": width,
            "height": height,
            "nx": nx,
            "ny": ny,
            "host_surface_id": host_surface_id,
            "mask_openings": bool(mask_openings),
        },
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def create_point_set(
    project: Project,
    *,
    point_set_id: str,
    name: str,
    points: Sequence[Tuple[float, float, float]],
    room_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    ctx: Optional[OpContext] = None,
) -> PointSetSpec:
    def _validate() -> None:
        if len(points) == 0:
            raise ValueError("Point set requires at least one point")

    def _mutate() -> PointSetSpec:
        ps = PointSetSpec(
            id=point_set_id,
            name=name,
            points=[tuple(float(v) for v in p) for p in points],
            room_id=room_id,
            zone_id=zone_id,
        )
        project.point_sets.append(ps)
        return ps

    return execute_op(
        project,
        op_name="create_point_set",
        args={"point_set_id": point_set_id, "name": name, "count": len(points)},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )


def create_line_grid(
    project: Project,
    *,
    line_id: str,
    name: str,
    polyline: Sequence[Tuple[float, float, float]],
    spacing: float,
    room_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    snap_segments_xy: Optional[Sequence[Tuple[Tuple[float, float], Tuple[float, float]]]] = None,
    clip_boundary_xy: Optional[Sequence[Tuple[float, float]]] = None,
    ctx: Optional[OpContext] = None,
) -> LineGridSpec:
    def _validate() -> None:
        if len(polyline) < 2:
            raise ValueError("line grid polyline requires at least two points")
        if spacing <= 0.0:
            raise ValueError("line grid spacing must be > 0")

    def _mutate() -> LineGridSpec:
        pts2 = [(float(p[0]), float(p[1])) for p in polyline]
        if snap_segments_xy:
            pts2 = snap_polyline_to_segments(pts2, list(snap_segments_xy))
        if clip_boundary_xy:
            pts2 = clip_polyline_to_polygon(pts2, list(clip_boundary_xy))
        if len(pts2) < 2:
            raise ValueError("line grid collapsed after snapping/clipping")
        z = float(polyline[0][2]) if polyline else 0.0
        lg = LineGridSpec(
            id=line_id,
            name=name,
            polyline=[(float(x), float(y), z) for x, y in pts2],
            spacing=float(spacing),
            room_id=room_id,
            zone_id=zone_id,
        )
        project.line_grids.append(lg)
        return lg

    return execute_op(
        project,
        op_name="create_line_grid",
        args={"line_id": line_id, "name": name, "count": len(polyline), "spacing": spacing},
        ctx=ctx,
        validate=_validate,
        mutate=_mutate,
    )
