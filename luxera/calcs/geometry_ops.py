from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from luxera.geometry.openings.opening_uv import opening_uv_polygon
from luxera.geometry.openings.project_uv import lift_uv_to_3d, project_points_to_uv, wall_basis
from luxera.geometry.spatial import point_in_polygon
from luxera.project.schema import OpeningSpec, SurfaceSpec


Point3 = Tuple[float, float, float]
Point2 = Tuple[float, float]


@dataclass(frozen=True)
class WorkplaneGridGeom:
    points_xyz: List[Point3]
    mask: List[bool]
    connectivity: List[Tuple[int, int]]
    rows: int
    cols: int
    normal: Point3 = (0.0, 0.0, 1.0)


def build_workplane_grid(
    *,
    origin: Point3,
    axis_u: Point3,
    axis_v: Point3,
    width: float,
    height: float,
    rows: int,
    cols: int,
    clip_polygon: Optional[Sequence[Point2]] = None,
    holes: Sequence[Sequence[Point2]] = (),
) -> WorkplaneGridGeom:
    rows = max(1, int(rows))
    cols = max(1, int(cols))
    ou = np.array(axis_u, dtype=float)
    ov = np.array(axis_v, dtype=float)
    o = np.array(origin, dtype=float)
    du = float(width) / max(cols - 1, 1)
    dv = float(height) / max(rows - 1, 1)
    pts: List[Point3] = []
    mask: List[bool] = []
    for j in range(rows):
        for i in range(cols):
            p = o + ou * (i * du) + ov * (j * dv)
            pp = (float(p[0]), float(p[1]), float(p[2]))
            keep = True
            if clip_polygon is not None:
                keep = point_in_polygon((pp[0], pp[1]), clip_polygon)
                if keep:
                    for h in holes:
                        if point_in_polygon((pp[0], pp[1]), h):
                            keep = False
                            break
            pts.append(pp)
            mask.append(bool(keep))
    conn: List[Tuple[int, int]] = []
    for j in range(rows):
        for i in range(cols):
            idx = j * cols + i
            if i + 1 < cols:
                conn.append((idx, idx + 1))
            if j + 1 < rows:
                conn.append((idx, idx + cols))
    n = np.cross(ou, ov)
    ln = float(np.linalg.norm(n))
    normal = (0.0, 0.0, 1.0) if ln <= 1e-12 else (float(n[0] / ln), float(n[1] / ln), float(n[2] / ln))
    return WorkplaneGridGeom(points_xyz=pts, mask=mask, connectivity=conn, rows=rows, cols=cols, normal=normal)


def mask_points_by_openings(
    points_wall_uv: Sequence[Point2],
    opening_polys_uv: Sequence[Sequence[Point2]],
) -> List[bool]:
    keep: List[bool] = [True] * len(points_wall_uv)
    for i, p in enumerate(points_wall_uv):
        for poly in opening_polys_uv:
            if point_in_polygon((float(p[0]), float(p[1])), poly):
                keep[i] = False
                break
    return keep


def build_vertical_grid_on_wall(
    wall: SurfaceSpec,
    *,
    rows: int,
    cols: int,
    openings: Sequence[OpeningSpec] = (),
    subrect_u0: Optional[float] = None,
    subrect_u1: Optional[float] = None,
    subrect_v0: Optional[float] = None,
    subrect_v1: Optional[float] = None,
) -> WorkplaneGridGeom:
    if len(wall.vertices) < 3:
        raise ValueError("vertical grid wall must have at least 3 vertices")
    rows = max(1, int(rows))
    cols = max(1, int(cols))
    origin, u, v, n = wall_basis(wall)
    wall_uv = project_points_to_uv(wall.vertices, origin, u, v)
    us = [float(p[0]) for p in wall_uv]
    vs = [float(p[1]) for p in wall_uv]
    u0, u1 = min(us), max(us)
    v0, v1 = min(vs), max(vs)
    if subrect_u0 is not None:
        u0 = max(u0, float(subrect_u0))
    if subrect_u1 is not None:
        u1 = min(u1, float(subrect_u1))
    if subrect_v0 is not None:
        v0 = max(v0, float(subrect_v0))
    if subrect_v1 is not None:
        v1 = min(v1, float(subrect_v1))
    if u1 <= u0 or v1 <= v0:
        raise ValueError("invalid sub-rectangle bounds for vertical wall grid")
    base = lift_uv_to_3d([(u0, v0)], origin, u, v)[0]
    grid = build_workplane_grid(
        origin=base,
        axis_u=(float(u[0]), float(u[1]), float(u[2])),
        axis_v=(float(v[0]), float(v[1]), float(v[2])),
        width=float(u1 - u0),
        height=float(v1 - v0),
        rows=rows,
        cols=cols,
    )
    grid_uv = project_points_to_uv(grid.points_xyz, origin, u, v)
    mask = [point_in_polygon(p, wall_uv) for p in grid_uv]
    if openings:
        host_ops = [o for o in openings if o.host_surface_id == wall.id]
        if host_ops:
            opening_uvs = [opening_uv_polygon(o, wall) for o in host_ops]
            keep = mask_points_by_openings(grid_uv, opening_uvs)
            mask = [bool(mask[i] and keep[i]) for i in range(len(mask))]
    return WorkplaneGridGeom(
        points_xyz=grid.points_xyz,
        mask=mask,
        connectivity=grid.connectivity,
        rows=rows,
        cols=cols,
        normal=(float(n[0]), float(n[1]), float(n[2])),
    )


def build_point_set(points: Sequence[Point3]) -> List[Point3]:
    return [tuple(float(v) for v in p) for p in points]


def sample_line_grid(polyline: Sequence[Point3], spacing: float) -> List[Point3]:
    if len(polyline) < 2:
        return list(polyline)
    out: List[Point3] = [tuple(float(v) for v in polyline[0])]
    step = max(float(spacing), 1e-6)
    for i in range(len(polyline) - 1):
        a = np.array(polyline[i], dtype=float)
        b = np.array(polyline[i + 1], dtype=float)
        d = b - a
        ln = float(np.linalg.norm(d))
        if ln <= 1e-12:
            continue
        n = max(1, int(math.floor(ln / step)))
        for j in range(1, n + 1):
            t = min(1.0, (j * step) / ln)
            p = a + d * t
            out.append((float(p[0]), float(p[1]), float(p[2])))
    return out


@dataclass(frozen=True)
class Viewpoint:
    position: Point3
    look_dir: Point3
    up_dir: Point3
    fov_deg: float
    near_clip: float = 0.1
    far_clip: float = 200.0


def luminaire_points_in_view(view: Viewpoint, luminaire_points: Sequence[Point3]) -> List[Point3]:
    pos = np.array(view.position, dtype=float)
    look = np.array(view.look_dir, dtype=float)
    up = np.array(view.up_dir, dtype=float)
    look_n = look / max(float(np.linalg.norm(look)), 1e-12)
    up_n = up / max(float(np.linalg.norm(up)), 1e-12)
    right = np.cross(look_n, up_n)
    right /= max(float(np.linalg.norm(right)), 1e-12)
    half = math.radians(float(view.fov_deg) * 0.5)
    ct = math.cos(half)
    out: List[Point3] = []
    for p in luminaire_points:
        v = np.array(p, dtype=float) - pos
        d = float(np.linalg.norm(v))
        if d < float(view.near_clip) or d > float(view.far_clip):
            continue
        v_n = v / max(d, 1e-12)
        if float(np.dot(v_n, look_n)) < ct:
            continue
        out.append((float(p[0]), float(p[1]), float(p[2])))
    return out
