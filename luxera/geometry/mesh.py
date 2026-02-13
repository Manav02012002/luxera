from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from luxera.geometry.primitives import Extrusion


@dataclass
class TriMesh:
    vertices: List[Tuple[float, float, float]]
    faces: List[Tuple[int, int, int]]
    normals: Optional[List[Tuple[float, float, float]]] = None
    uvs: Optional[List[Tuple[float, float]]] = None
    materials: Optional[List[Optional[str]]] = None
    adjacency: Optional[Dict[int, List[int]]] = None

    def validate(self) -> None:
        n = len(self.vertices)
        if n == 0:
            raise ValueError("TriMesh has no vertices")
        for f in self.faces:
            if len(f) != 3:
                raise ValueError("TriMesh faces must be triangles")
            for idx in f:
                if idx < 0 or idx >= n:
                    raise ValueError(f"TriMesh face index out of range: {idx}")


@dataclass
class ManifoldMesh:
    mesh: TriMesh

    def validate(self) -> None:
        self.mesh.validate()
        edge_count: Dict[Tuple[int, int], int] = {}
        for a, b, c in self.mesh.faces:
            for u, v in ((a, b), (b, c), (c, a)):
                e = (u, v) if u < v else (v, u)
                edge_count[e] = edge_count.get(e, 0) + 1
        # 2-manifold bound for closed meshes. Authoring meshes may be open; keep a soft bound.
        for e, count in edge_count.items():
            if count > 2:
                raise ValueError(f"Non-manifold edge {e} with incidence {count}")


def extrusion_to_trimesh(extrusion: Extrusion, z0: float = 0.0) -> TriMesh:
    if extrusion.height <= 0.0:
        raise ValueError("Extrusion height must be > 0")
    poly = list(extrusion.profile2d.points)
    if len(poly) < 3:
        raise ValueError("Extrusion profile requires at least 3 points")
    z1 = z0 + float(extrusion.height)
    n = len(poly)
    vertices: List[Tuple[float, float, float]] = []
    for x, y in poly:
        vertices.append((float(x), float(y), float(z0)))
    for x, y in poly:
        vertices.append((float(x), float(y), float(z1)))

    faces: List[Tuple[int, int, int]] = []
    # Side faces.
    for i in range(n):
        j = (i + 1) % n
        b0, b1 = i, j
        t0, t1 = i + n, j + n
        faces.append((b0, b1, t1))
        faces.append((b0, t1, t0))
    # Fan triangulation for caps.
    if extrusion.cap_bottom:
        for i in range(1, n - 1):
            faces.append((0, i + 1, i))
    if extrusion.cap_top:
        for i in range(1, n - 1):
            faces.append((n, n + i, n + i + 1))

    mesh = TriMesh(vertices=vertices, faces=faces)
    mesh.validate()
    return mesh
