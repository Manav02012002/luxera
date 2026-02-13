from __future__ import annotations

from typing import Dict, List, Tuple

from luxera.geometry.mesh import TriMesh
from luxera.geometry.openings.project_uv import lift_uv_to_3d
from luxera.geometry.openings.subtract import UVPolygon
from luxera.geometry.tolerance import EPS_POS, EPS_WELD


Point2 = Tuple[float, float]
TriangleIdx = Tuple[int, int, int]


def _quantized_key(p: Point2, eps: float = EPS_WELD) -> Tuple[int, int]:
    s = 1.0 / max(float(eps), EPS_POS)
    return (int(round(float(p[0]) * s)), int(round(float(p[1]) * s)))


def _fan_triangulate(poly: List[Point2]) -> Tuple[List[Point2], List[TriangleIdx]]:
    if len(poly) < 3:
        return [], []
    faces: List[TriangleIdx] = []
    for i in range(1, len(poly) - 1):
        faces.append((0, i, i + 1))
    return list(poly), faces


def _triangulate_polygon_with_holes_vertices(poly_uv: UVPolygon) -> Tuple[List[Point2], List[TriangleIdx]]:
    if not poly_uv.holes:
        return _fan_triangulate(poly_uv.outer)

    try:
        from shapely.geometry import Point, Polygon  # type: ignore
        from shapely.ops import triangulate  # type: ignore

        poly = Polygon(poly_uv.outer, holes=poly_uv.holes)
        tris = triangulate(poly)
        vertices: List[Point2] = []
        index: Dict[Tuple[int, int], int] = {}
        faces: List[TriangleIdx] = []
        for tri in tris:
            rp = tri.representative_point()
            if not poly.covers(Point(rp.x, rp.y)):
                continue
            coords = [(float(x), float(y)) for x, y in list(tri.exterior.coords)[:-1]]
            if len(coords) != 3:
                continue
            idxs: List[int] = []
            for p in coords:
                k = _quantized_key(p)
                if k not in index:
                    index[k] = len(vertices)
                    vertices.append(p)
                idxs.append(index[k])
            if idxs[0] != idxs[1] and idxs[1] != idxs[2] and idxs[2] != idxs[0]:
                faces.append((idxs[0], idxs[1], idxs[2]))
        return vertices, faces
    except Exception:
        # Fallback if robust triangulation backend is unavailable.
        return _fan_triangulate(poly_uv.outer)


def triangulate_polygon_with_holes(poly_uv: UVPolygon) -> List[TriangleIdx]:
    _verts, faces = _triangulate_polygon_with_holes_vertices(poly_uv)
    return faces


def wall_mesh_from_uv(poly_uv: UVPolygon, origin, u, v) -> TriMesh:
    verts_uv, faces = _triangulate_polygon_with_holes_vertices(poly_uv)
    verts3d = lift_uv_to_3d(verts_uv, origin, u, v)
    mesh = TriMesh(vertices=verts3d, faces=faces)
    mesh.validate()
    return mesh
