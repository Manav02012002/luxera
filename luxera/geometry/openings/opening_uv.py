from __future__ import annotations

import warnings
from typing import List, Optional, Sequence, Tuple

from luxera.geometry.openings.project_uv import project_points_to_uv, wall_basis
from luxera.geometry.tolerance import EPS_PLANE
from luxera.geometry.param.model import OpeningParam
from luxera.project.schema import OpeningSpec, SurfaceSpec


Point2 = Tuple[float, float]


def _resolve_opening_center_u(
    opening_param: OpeningParam,
    *,
    u_min: float,
    u_max: float,
    width: float,
    peer_openings: Optional[Sequence[OpeningParam]] = None,
) -> float:
    span_u = max(0.0, float(u_max - u_min))
    mode = str(opening_param.anchor_mode)
    uc = u_min + span_u * float(opening_param.anchor)
    if mode == "from_start_distance":
        d = float(opening_param.from_start_distance if opening_param.from_start_distance is not None else 0.0)
        uc = u_min + d + 0.5 * width
    elif mode == "from_end_distance":
        d = float(opening_param.from_end_distance if opening_param.from_end_distance is not None else 0.0)
        uc = u_max - d - 0.5 * width
    elif mode == "center_at_fraction" or mode == "snap_to_nearest":
        frac = float(opening_param.center_at_fraction if opening_param.center_at_fraction is not None else opening_param.anchor)
        uc = u_min + span_u * frac
    elif mode == "nearest_gridline_center":
        frac = float(opening_param.center_at_fraction if opening_param.center_at_fraction is not None else opening_param.anchor)
        uc = u_min + span_u * frac
    elif mode == "equal_spacing":
        group = None
        if opening_param.spacing_group_id:
            group = str(opening_param.spacing_group_id)
        peers = list(peer_openings or [])
        if group is not None:
            peers = [x for x in peers if x.wall_id == opening_param.wall_id and str(x.spacing_group_id or "") == group]
        else:
            peers = [x for x in peers if x.wall_id == opening_param.wall_id and str(x.anchor_mode) == "equal_spacing"]
        peers = sorted(peers, key=lambda x: str(x.id))
        if peers and any(x.id == opening_param.id for x in peers):
            idx = [x.id for x in peers].index(opening_param.id)
            uc = u_min + span_u * float(idx + 1) / float(len(peers) + 1)
        else:
            frac = float(opening_param.center_at_fraction if opening_param.center_at_fraction is not None else opening_param.anchor)
            uc = u_min + span_u * frac

    spacing = opening_param.gridline_spacing
    if (opening_param.snap_to_nearest or mode in {"snap_to_nearest", "nearest_gridline_center"}) and spacing is not None:
        g = float(spacing)
        if g > EPS_PLANE:
            uc = u_min + round((uc - u_min) / g) * g
    return uc


def opening_uv_polygon(
    opening_param: OpeningParam | OpeningSpec,
    wall_surface: SurfaceSpec,
    *,
    peer_openings: Optional[Sequence[OpeningParam]] = None,
) -> List[Point2]:
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

    if opening_param.polygon2d:
        # Authoring-local polygon in wall UV space.
        return [(float(p[0]), float(p[1])) for p in opening_param.polygon2d]

    uc_raw = _resolve_opening_center_u(opening_param, u_min=u_min, u_max=u_max, width=width, peer_openings=peer_openings)
    legal_min = u_min + 0.5 * width
    legal_max = u_max - 0.5 * width
    if legal_max < legal_min - EPS_PLANE:
        warnings.warn(
            f"Opening {opening_param.id} does not fit host wall after edits; width={width:.3f} span={u_max-u_min:.3f}",
            RuntimeWarning,
            stacklevel=2,
        )
        raise ValueError("opening does not fit host wall length")
    uc = min(max(uc_raw, legal_min), legal_max)
    _ = uc_raw  # shift/clamp is expected behavior; warn only on impossible placement.
    ou0 = max(u_min, uc - width * 0.5)
    ou1 = min(u_max, ou0 + width)
    ov0 = v_min + sill
    ov1 = min(v_max - EPS_PLANE, ov0 + height)
    if ou1 - ou0 <= EPS_PLANE or ov1 - ov0 <= EPS_PLANE:
        raise ValueError("opening does not fit host wall")

    return [(ou0, ov0), (ou1, ov0), (ou1, ov1), (ou0, ov1)]
