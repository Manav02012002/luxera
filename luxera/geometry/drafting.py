from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from luxera.geometry.tolerance import EPS_ANG, EPS_POS, EPS_WELD
from luxera.geometry.views.cutplane import PlanView, view_basis
from luxera.geometry.views.hiddenline import depth_sort_primitives
from luxera.geometry.views.intersect import Plane, Polyline3D, intersect_trimesh_with_plane, stitch_segments_to_polylines
from luxera.geometry.views.project import DrawingPrimitive, polylines_to_primitives
from luxera.project.schema import CalcGrid, Project, SurfaceSpec


Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]
Segment2 = Tuple[Point2, Point2]


@dataclass(frozen=True)
class PlanProjection:
    cut_z: float
    edges: List[Segment2] = field(default_factory=list)
    cut_segments: List[Segment2] = field(default_factory=list)
    silhouettes: List[Segment2] = field(default_factory=list)


@dataclass(frozen=True)
class DimensionAnnotation:
    id: str
    start: Point2
    end: Point2
    line: Segment2
    extension_1: Segment2
    extension_2: Segment2
    text_anchor: Point2
    value: float


@dataclass(frozen=True)
class LeaderAnnotation:
    id: str
    points: List[Point2]
    text_anchor: Point2


def _seg_key(a: Point2, b: Point2, eps: float = EPS_WELD) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    s = 1.0 / max(eps, EPS_ANG)
    aa = (int(round(float(a[0]) * s)), int(round(float(a[1]) * s)))
    bb = (int(round(float(b[0]) * s)), int(round(float(b[1]) * s)))
    return (aa, bb) if aa <= bb else (bb, aa)


def _poly_edges_xy(vertices: Sequence[Point3]) -> List[Segment2]:
    out: List[Segment2] = []
    for i in range(len(vertices)):
        a = vertices[i]
        b = vertices[(i + 1) % len(vertices)]
        out.append(((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    return out


def _cut_polygon_at_z(vertices: Sequence[Point3], cut_z: float) -> List[Segment2]:
    pts: List[Point2] = []
    n = len(vertices)
    for i in range(n):
        a = np.asarray(vertices[i], dtype=float)
        b = np.asarray(vertices[(i + 1) % n], dtype=float)
        za, zb = float(a[2]), float(b[2])
        if (za - cut_z) * (zb - cut_z) > 0.0:
            continue
        if abs(zb - za) <= EPS_POS:
            continue
        t = (cut_z - za) / (zb - za)
        if 0.0 <= t <= 1.0:
            p = a + (b - a) * t
            pts.append((float(p[0]), float(p[1])))
    out: List[Segment2] = []
    if len(pts) >= 2:
        for i in range(0, len(pts) - 1, 2):
            out.append((pts[i], pts[i + 1]))
    return out


def project_plan_view(
    surfaces: Sequence[SurfaceSpec],
    *,
    cut_z: float,
    include_below: bool = True,
) -> PlanProjection:
    edges: List[Segment2] = []
    cut_segments: List[Segment2] = []
    edge_counts: Dict[Tuple[Tuple[int, int], Tuple[int, int]], int] = {}

    for s in surfaces:
        verts = [tuple(float(v) for v in p) for p in s.vertices]
        if len(verts) < 3:
            continue
        zvals = [p[2] for p in verts]
        if include_below and min(zvals) <= float(cut_z):
            for e in _poly_edges_xy(verts):
                edges.append(e)
                k = _seg_key(*e)
                edge_counts[k] = edge_counts.get(k, 0) + 1
        cut_segments.extend(_cut_polygon_at_z(verts, cut_z))

    silhouettes = [e for e in edges if edge_counts.get(_seg_key(*e), 0) == 1]
    if not silhouettes and cut_segments:
        # For pure wall-plan cut scenarios, cut segments are the usable silhouette.
        silhouettes = list(cut_segments)
    return PlanProjection(cut_z=float(cut_z), edges=edges, cut_segments=cut_segments, silhouettes=silhouettes)


def make_dimension_annotation(
    *,
    ann_id: str,
    start: Point2,
    end: Point2,
    offset: float = 0.5,
) -> DimensionAnnotation:
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    dx, dy = x1 - x0, y1 - y0
    L = float(np.hypot(dx, dy))
    if L <= EPS_POS:
        raise ValueError("dimension start/end must differ")
    nx, ny = -dy / L, dx / L
    a = (x0 + nx * float(offset), y0 + ny * float(offset))
    b = (x1 + nx * float(offset), y1 + ny * float(offset))
    text = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
    return DimensionAnnotation(
        id=ann_id,
        start=(x0, y0),
        end=(x1, y1),
        line=(a, b),
        extension_1=((x0, y0), a),
        extension_2=((x1, y1), b),
        text_anchor=text,
        value=L,
    )


def make_leader_annotation(
    *,
    ann_id: str,
    anchor: Point2,
    text_anchor: Point2,
    elbow: Optional[Point2] = None,
) -> LeaderAnnotation:
    pts = [tuple(float(v) for v in anchor)]
    if elbow is not None:
        pts.append(tuple(float(v) for v in elbow))
    pts.append(tuple(float(v) for v in text_anchor))
    return LeaderAnnotation(id=ann_id, points=pts, text_anchor=tuple(float(v) for v in text_anchor))


def grid_linework_xy(grids: Iterable[CalcGrid]) -> List[Segment2]:
    out: List[Segment2] = []
    for g in grids:
        nx, ny = max(1, int(g.nx)), max(1, int(g.ny))
        ox, oy = float(g.origin[0]), float(g.origin[1])
        w, h = float(g.width), float(g.height)
        dx = w / max(nx - 1, 1)
        dy = h / max(ny - 1, 1)
        for j in range(ny):
            y = oy + j * dy
            out.append(((ox, y), (ox + w, y)))
        for i in range(nx):
            x = ox + i * dx
            out.append(((x, oy), (x, oy + h)))
    return out


def luminaire_symbol_inserts(project: Project) -> List[Tuple[str, Point2, float]]:
    out: List[Tuple[str, Point2, float]] = []
    for lum in project.luminaires:
        x, y, _z = lum.transform.position
        out.append((lum.id, (float(x), float(y)), 1.0))
    return out


def plan_linework_from_meshes(
    meshes: Sequence[object],
    *,
    cut_z: float,
    range_zmin: float,
    range_zmax: float,
    layer: str = "CUT",
) -> List[DrawingPrimitive]:
    """
    Deterministic plan linework extraction from triangle meshes.

    Any mesh object with `vertices` and `faces` attributes compatible with TriMesh
    is accepted to keep integration minimal.
    """
    view = PlanView(cut_z=float(cut_z), range_zmin=float(range_zmin), range_zmax=float(range_zmax))
    basis = view_basis(view)
    plane = Plane(origin=(0.0, 0.0, float(cut_z)), normal=(0.0, 0.0, 1.0))
    polylines: List[Polyline3D] = []
    for m in meshes:
        segs = intersect_trimesh_with_plane(m, plane)  # type: ignore[arg-type]
        polylines.extend(stitch_segments_to_polylines(segs))
    prims = polylines_to_primitives(polylines, basis, layer=layer)
    return depth_sort_primitives(prims, back_to_front=False)
