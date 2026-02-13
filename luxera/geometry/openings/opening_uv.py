from __future__ import annotations

from typing import List, Tuple

from luxera.geometry.openings.project_uv import project_points_to_uv, wall_basis
from luxera.geometry.tolerance import EPS_PLANE
from luxera.geometry.param.model import OpeningParam
from luxera.project.schema import OpeningSpec, SurfaceSpec


Point2 = Tuple[float, float]


def opening_uv_polygon(opening_param: OpeningParam | OpeningSpec, wall_surface: SurfaceSpec) -> List[Point2]:
    """Return opening polygon in host wall UV coordinates."""
    origin, u, v, _n = wall_basis(wall_surface)

    if isinstance(opening_param, OpeningSpec):
        if len(opening_param.vertices) < 3:
            raise ValueError("opening requires at least 3 vertices")
        return project_points_to_uv(opening_param.vertices, origin, u, v)

    wall_uv = project_points_to_uv(wall_surface.vertices, origin, u, v)
    us = [p[0] for p in wall_uv]
    vs = [p[1] for p in wall_uv]
    u_min, u_max = min(us), max(us)
    v_min, v_max = min(vs), max(vs)

    width = float(opening_param.width)
    height = float(opening_param.height)
    sill = float(opening_param.sill)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("opening width/height must be > 0")

    uc = u_min + (u_max - u_min) * float(opening_param.anchor)
    ou0 = max(u_min, uc - width * 0.5)
    ou1 = min(u_max, ou0 + width)
    ov0 = v_min + sill
    ov1 = min(v_max - EPS_PLANE, ov0 + height)
    if ou1 - ou0 <= EPS_PLANE or ov1 - ov0 <= EPS_PLANE:
        raise ValueError("opening does not fit host wall")

    return [(ou0, ov0), (ou1, ov0), (ou1, ov1), (ou0, ov1)]
