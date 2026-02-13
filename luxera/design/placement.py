from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

from luxera.project.schema import CalcGrid, LuminaireInstance, RotationSpec, SurfaceSpec, TransformSpec


RoomBounds = Tuple[float, float, float, float]
Polygon2D = Sequence[Tuple[float, float]]


def _rotation_from_inputs(aim, rotation) -> RotationSpec:
    if rotation is not None:
        yaw, pitch, roll = rotation
        return RotationSpec(type="euler_zyx", euler_deg=(float(yaw), float(pitch), float(roll)))
    if aim is not None:
        return RotationSpec(type="aim_up", aim=tuple(float(x) for x in aim), up=(0.0, 0.0, 1.0))
    return RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))


def _point_in_polygon_2d(x: float, y: float, polygon: Polygon2D) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = float(polygon[i][0]), float(polygon[i][1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / max((yj - yi), 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _position_blocked(x: float, y: float, no_go_polygons: Sequence[Polygon2D] | None) -> bool:
    if not no_go_polygons:
        return False
    return any(_point_in_polygon_2d(x, y, poly) for poly in no_go_polygons)


def place_rect_array(
    room_bounds: RoomBounds,
    nx: int,
    ny: int,
    margins: float | Tuple[float, float] = 0.0,
    mount_height: float = 2.8,
    rotation: Tuple[float, float, float] | None = None,
    aim: Tuple[float, float, float] | None = None,
    photometry_asset_id: str = "asset",
    no_go_polygons: Sequence[Polygon2D] | None = None,
) -> List[LuminaireInstance]:
    if isinstance(margins, tuple):
        margin_x, margin_y = float(margins[0]), float(margins[1])
    else:
        margin_x = margin_y = float(margins)
    return place_array_rect(
        room_bounds=room_bounds,
        nx=nx,
        ny=ny,
        margin_x=margin_x,
        margin_y=margin_y,
        z=mount_height,
        photometry_asset_id=photometry_asset_id,
        aim=aim,
        rotation=rotation,
        no_go_polygons=no_go_polygons,
    )


def place_array_rect(
    room_bounds: RoomBounds,
    nx: int,
    ny: int,
    margin_x: float,
    margin_y: float,
    z: float,
    photometry_asset_id: str,
    aim: Tuple[float, float, float] | None = None,
    rotation: Tuple[float, float, float] | None = None,
    no_go_polygons: Sequence[Polygon2D] | None = None,
) -> List[LuminaireInstance]:
    x_min, y_min, x_max, y_max = [float(v) for v in room_bounds]
    nx = max(1, int(nx))
    ny = max(1, int(ny))
    inner_x0 = x_min + float(margin_x)
    inner_x1 = x_max - float(margin_x)
    inner_y0 = y_min + float(margin_y)
    inner_y1 = y_max - float(margin_y)
    width = max(inner_x1 - inner_x0, 0.0)
    height = max(inner_y1 - inner_y0, 0.0)
    dx = width / max(nx - 1, 1)
    dy = height / max(ny - 1, 1)
    rot = _rotation_from_inputs(aim, rotation)
    out: List[LuminaireInstance] = []
    for j in range(ny):
        for i in range(nx):
            x = inner_x0 + i * dx
            y = inner_y0 + j * dy
            if _position_blocked(x, y, no_go_polygons):
                # Deterministic fallback: shift along x; if still blocked, drop fixture.
                step = max(dx, width / max(nx, 1), 0.25) * 0.25
                shifted = False
                for k in range(1, 17):
                    xn = min(inner_x1, x + k * step)
                    if not _position_blocked(xn, y, no_go_polygons):
                        x = xn
                        shifted = True
                        break
                if not shifted:
                    continue
            out.append(
                LuminaireInstance(
                    id=f"arr_{j+1}_{i+1}",
                    name=f"Array {j+1}-{i+1}",
                    photometry_asset_id=photometry_asset_id,
                    transform=TransformSpec(position=(x, y, float(z)), rotation=rot),
                )
            )
    return out


def place_along_polyline(
    polyline: Sequence[Tuple[float, float, float]],
    spacing: float,
    start_offset: float = 0.0,
    mount_height: float = 8.0,
    photometry_asset_id: str = "asset",
    aim: Tuple[float, float, float] | None = None,
    rotation: Tuple[float, float, float] | None = None,
) -> List[LuminaireInstance]:
    return place_along_line(
        polyline=polyline,
        spacing=spacing,
        offset=start_offset,
        z=mount_height,
        photometry_asset_id=photometry_asset_id,
        aim=aim,
        rotation=rotation,
    )


def place_along_line(
    polyline: Sequence[Tuple[float, float, float]],
    spacing: float,
    offset: float,
    z: float,
    photometry_asset_id: str,
    aim: Tuple[float, float, float] | None = None,
    rotation: Tuple[float, float, float] | None = None,
) -> List[LuminaireInstance]:
    pts = [(float(x), float(y), float(z0)) for x, y, z0 in polyline]
    if len(pts) < 2:
        return []
    spacing = max(float(spacing), 1e-6)
    dist_offset = max(float(offset), 0.0)
    rot = _rotation_from_inputs(aim, rotation)

    segments: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], float]] = []
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]
        d = math.dist(a, b)
        if d > 1e-9:
            segments.append((a, b, d))
    if not segments:
        return []
    total_len = sum(s[2] for s in segments)
    if dist_offset > total_len:
        return []

    out: List[LuminaireInstance] = []
    cursor = dist_offset
    idx = 0
    while cursor <= total_len + 1e-9:
        remain = cursor
        for a, b, d in segments:
            if remain <= d + 1e-9:
                t = 0.0 if d <= 1e-9 else remain / d
                x = a[0] + (b[0] - a[0]) * t
                y = a[1] + (b[1] - a[1]) * t
                out.append(
                    LuminaireInstance(
                        id=f"line_{idx+1}",
                        name=f"Line {idx+1}",
                        photometry_asset_id=photometry_asset_id,
                        transform=TransformSpec(position=(x, y, float(z)), rotation=rot),
                    )
                )
                idx += 1
                break
            remain -= d
        cursor += spacing
    return out


def _surface_normal(surface: SurfaceSpec) -> Tuple[float, float, float]:
    if surface.normal is not None:
        return tuple(float(v) for v in surface.normal)
    if len(surface.vertices) < 3:
        return (0.0, 0.0, -1.0)
    a = surface.vertices[0]
    b = surface.vertices[1]
    c = surface.vertices[2]
    ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    nlen = math.sqrt(nx * nx + ny * ny + nz * nz)
    if nlen < 1e-12:
        return (0.0, 0.0, -1.0)
    return (nx / nlen, ny / nlen, nz / nlen)


def snap_to_ceiling(surface_id: str, mount_offset: float, surfaces: Iterable[SurfaceSpec]) -> TransformSpec:
    target = next((s for s in surfaces if s.id == surface_id), None)
    if target is None:
        raise ValueError(f"Surface not found: {surface_id}")
    if not target.vertices:
        raise ValueError(f"Surface has no vertices: {surface_id}")
    cx = sum(v[0] for v in target.vertices) / len(target.vertices)
    cy = sum(v[1] for v in target.vertices) / len(target.vertices)
    cz = sum(v[2] for v in target.vertices) / len(target.vertices)
    nx, ny, nz = _surface_normal(target)
    # Mount luminaire below the ceiling into room space.
    px = cx - nx * float(mount_offset)
    py = cy - ny * float(mount_offset)
    pz = cz - nz * float(mount_offset)
    return TransformSpec(
        position=(px, py, pz),
        rotation=RotationSpec(type="aim_up", aim=(nx, ny, nz), up=(0.0, 0.0, 1.0)),
    )


def snap_to_mounting_plane(transform: TransformSpec, z_or_surface: float | SurfaceSpec, mount_offset: float = 0.0) -> TransformSpec:
    if isinstance(z_or_surface, SurfaceSpec):
        if not z_or_surface.vertices:
            raise ValueError(f"Surface has no vertices: {z_or_surface.id}")
        z = max(float(v[2]) for v in z_or_surface.vertices) - float(mount_offset)
    else:
        z = float(z_or_surface) - float(mount_offset)
    x, y, _ = transform.position
    return TransformSpec(position=(float(x), float(y), z), rotation=transform.rotation)


def snap_array_to_room_centerlines_bounds(
    transforms: Sequence[TransformSpec],
    room_bounds: RoomBounds,
    snap_centerlines: bool = True,
) -> List[TransformSpec]:
    x_min, y_min, x_max, y_max = [float(v) for v in room_bounds]
    cx = 0.5 * (x_min + x_max)
    cy = 0.5 * (y_min + y_max)
    out: List[TransformSpec] = []
    for t in transforms:
        x, y, z = [float(v) for v in t.position]
        x = max(x_min, min(x_max, x))
        y = max(y_min, min(y_max, y))
        if snap_centerlines:
            if abs(x - cx) <= abs(y - cy):
                x = cx
            else:
                y = cy
        out.append(TransformSpec(position=(x, y, z), rotation=t.rotation))
    return out


def snap_to_grid_intersections(grid_id: str, grids: Iterable[CalcGrid], z: float | None = None) -> List[TransformSpec]:
    grid = next((g for g in grids if g.id == grid_id), None)
    if grid is None:
        raise ValueError(f"Grid not found: {grid_id}")
    nx = max(1, int(grid.nx))
    ny = max(1, int(grid.ny))
    dx = float(grid.width) / max(nx - 1, 1)
    dy = float(grid.height) / max(ny - 1, 1)
    zz = float(z) if z is not None else float(grid.elevation)
    out: List[TransformSpec] = []
    for j in range(ny):
        for i in range(nx):
            x = float(grid.origin[0]) + i * dx
            y = float(grid.origin[1]) + j * dy
            out.append(
                TransformSpec(
                    position=(x, y, zz),
                    rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)),
                )
            )
    return out
