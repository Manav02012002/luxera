from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from luxera.geometry.tolerance import EPS_ANG, EPS_POS


Point3 = Tuple[float, float, float]
Face = Tuple[int, ...]
TriangleIdx = Tuple[int, int, int]


@dataclass(frozen=True)
class TriangulationConfig:
    """Deterministic triangulation configuration for mesh ingestion."""

    merge_epsilon: float = EPS_ANG


def merge_vertices(vertices: Sequence[Point3], epsilon: float = EPS_ANG) -> Tuple[List[Point3], List[int]]:
    """
    Deterministically merge near-identical vertices.

    Vertices are bucketed using epsilon quantization. First occurrence in input
    order wins, guaranteeing stable vertex ordering across runs.
    """
    merged: List[Point3] = []
    remap: List[int] = []
    index_by_bucket: dict[Tuple[int, int, int], int] = {}

    inv_eps = 1.0 / max(epsilon, EPS_POS)
    for vx, vy, vz in vertices:
        bucket = (int(round(vx * inv_eps)), int(round(vy * inv_eps)), int(round(vz * inv_eps)))
        idx = index_by_bucket.get(bucket)
        if idx is None:
            idx = len(merged)
            index_by_bucket[bucket] = idx
            merged.append((float(vx), float(vy), float(vz)))
        remap.append(idx)
    return merged, remap


def normalize_faces(faces: Iterable[Sequence[int]], remap: Sequence[int] | None = None) -> List[Face]:
    """Normalize faces to remapped integer indices while preserving read order."""
    out: List[Face] = []
    for face in faces:
        if len(face) < 3:
            continue
        if remap is None:
            out.append(tuple(int(i) for i in face))
        else:
            out.append(tuple(int(remap[int(i)]) for i in face))
    return out


def triangulate_face(face: Sequence[int]) -> List[TriangleIdx]:
    """Fan triangulation with deterministic ordering."""
    if len(face) < 3:
        return []
    head = int(face[0])
    return [(head, int(face[i]), int(face[i + 1])) for i in range(1, len(face) - 1)]


def triangulate_faces(faces: Iterable[Sequence[int]]) -> List[TriangleIdx]:
    tris: List[TriangleIdx] = []
    for face in faces:
        tris.extend(triangulate_face(face))
    return tris


def triangulate_polygon_vertices(vertices: Sequence[Point3]) -> List[Tuple[Point3, Point3, Point3]]:
    """Triangulate one polygon by fan from vertex 0, preserving winding order."""
    if len(vertices) < 3:
        return []
    v0 = vertices[0]
    return [(v0, vertices[i], vertices[i + 1]) for i in range(1, len(vertices) - 1)]


def canonicalize_mesh(
    vertices: Sequence[Point3],
    faces: Iterable[Sequence[int]],
    config: TriangulationConfig | None = None,
) -> Tuple[List[Point3], List[Face], List[TriangleIdx]]:
    """
    Produce deterministic vertex, face, and triangle ordering.

    Contract: stable vertex ordering, stable triangle ordering, stable merge
    threshold policy (see docs/spec/solver_contracts.md).
    """
    cfg = config or TriangulationConfig()
    merged_vertices, remap = merge_vertices(vertices, epsilon=cfg.merge_epsilon)
    normalized_faces = normalize_faces(faces, remap=remap)
    triangles = triangulate_faces(normalized_faces)
    return merged_vertices, normalized_faces, triangles
