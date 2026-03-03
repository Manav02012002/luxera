from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from luxera.geometry.core import Polygon, Surface


class AdaptiveRadiosityMesh:
    """
    Adaptive patch mesh for radiosity computation.

    Strategy:
    1. Initial coarse mesh.
    2. Refine near luminaires.
    3. Refine near material boundaries.
    4. Optional gradient-driven post-solve refinement.
    """

    def __init__(
        self,
        initial_max_area: float = 1.0,
        refined_max_area: float = 0.1,
        luminaire_proximity_m: float = 3.0,
        gradient_threshold: float = 0.3,
        max_refinement_passes: int = 2,
    ):
        self.initial_max_area = max(float(initial_max_area), 1e-6)
        self.refined_max_area = max(float(refined_max_area), 1e-6)
        self.luminaire_proximity_m = max(float(luminaire_proximity_m), 0.0)
        self.gradient_threshold = max(float(gradient_threshold), 0.0)
        self.max_passes = max(1, int(max_refinement_passes))

    @staticmethod
    def _parent_id(surface_id: str) -> str:
        return str(surface_id).split("__patch_", 1)[0]

    @staticmethod
    def _point_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
        ab = b - a
        den = float(np.dot(ab, ab))
        if den <= 1e-18:
            return float(np.linalg.norm(p - a))
        t = float(np.dot(p - a, ab) / den)
        t = min(1.0, max(0.0, t))
        q = a + t * ab
        return float(np.linalg.norm(p - q))

    def _surface_has_material_boundary(self, surface: Surface, surfaces: List[Surface]) -> bool:
        s_refl = float(getattr(surface.material, "reflectance", 0.0))
        s_verts = [np.array(v.to_tuple(), dtype=float) for v in surface.polygon.vertices]
        tol = 1e-6
        for other in surfaces:
            if other.id == surface.id:
                continue
            o_refl = float(getattr(other.material, "reflectance", 0.0))
            if abs(s_refl - o_refl) <= 1e-9:
                continue
            o_verts = [np.array(v.to_tuple(), dtype=float) for v in other.polygon.vertices]
            shared = 0
            for va in s_verts:
                for vb in o_verts:
                    if float(np.linalg.norm(va - vb)) <= tol:
                        shared += 1
                        break
            if shared >= 1:
                return True
        return False

    def _is_boundary_region(self, parent: Surface, patch: Surface, surfaces: List[Surface]) -> bool:
        if not self._surface_has_material_boundary(parent, surfaces):
            return False
        p = np.array(patch.centroid.to_tuple(), dtype=float)
        verts = [np.array(v.to_tuple(), dtype=float) for v in parent.polygon.vertices]
        if len(verts) < 2:
            return False
        min_d = float("inf")
        for i in range(len(verts)):
            a = verts[i]
            b = verts[(i + 1) % len(verts)]
            min_d = min(min_d, self._point_segment_distance(p, a, b))
        band = 0.75 * math.sqrt(self.refined_max_area)
        return min_d <= band

    def create_adaptive_mesh(
        self,
        surfaces: List[Surface],
        luminaire_positions: List[np.ndarray],
    ) -> List[Surface]:
        """
        Create initial adaptive mesh using proximity and boundary markers.
        """
        patches: List[Surface] = []
        idx = 0
        lum_pos = [np.asarray(p, dtype=float).reshape(3) for p in luminaire_positions]

        for parent in surfaces:
            base_polys = parent.polygon.subdivide(self.initial_max_area) if parent.area > self.initial_max_area else [parent.polygon]
            for poly in base_polys:
                coarse = Surface(id=f"{parent.id}__coarse_{idx}", polygon=poly, material=parent.material)
                idx += 1
                c = np.array(coarse.centroid.to_tuple(), dtype=float)

                near_lum = False
                if lum_pos:
                    min_dist = min(float(np.linalg.norm(c - lp)) for lp in lum_pos)
                    near_lum = min_dist < self.luminaire_proximity_m

                boundary = self._is_boundary_region(parent, coarse, surfaces)

                if near_lum or boundary:
                    refined = self._subdivide_patch(coarse, self.refined_max_area)
                    for r in refined:
                        patches.append(
                            Surface(
                                id=f"{parent.id}__patch_{len(patches)}",
                                polygon=r.polygon,
                                material=parent.material,
                            )
                        )
                else:
                    patches.append(
                        Surface(
                            id=f"{parent.id}__patch_{len(patches)}",
                            polygon=coarse.polygon,
                            material=parent.material,
                        )
                    )
        return patches

    def refine_by_gradient(
        self,
        patches: List[Surface],
        radiosity: np.ndarray,
        adjacency: Optional[np.ndarray] = None,
    ) -> Tuple[List[Surface], np.ndarray]:
        """
        Post-solve refinement using relative radiosity gradients.
        """
        n = len(patches)
        if n == 0 or radiosity.size == 0:
            return patches, np.asarray(radiosity, dtype=float)

        B = np.asarray(radiosity, dtype=float).reshape(-1)
        if B.size != n:
            raise ValueError("radiosity length must match patch count")

        centers = np.array([p.centroid.to_tuple() for p in patches], dtype=float)
        areas = np.array([max(float(p.area), 1e-12) for p in patches], dtype=float)

        if adjacency is None:
            adjacency = np.zeros((n, n), dtype=bool)
            for i in range(n):
                for j in range(i + 1, n):
                    d = float(np.linalg.norm(centers[i] - centers[j]))
                    th = 2.0 * math.sqrt(max(areas[i], areas[j]))
                    if d <= th:
                        adjacency[i, j] = True
                        adjacency[j, i] = True
        else:
            adjacency = np.asarray(adjacency, dtype=bool)
            if adjacency.shape != (n, n):
                raise ValueError("adjacency must be shape (n, n)")

        refine_mask = np.zeros((n,), dtype=bool)
        for i in range(n):
            nbrs = np.flatnonzero(adjacency[i])
            for j in nbrs:
                den = max(abs(float(B[i])), abs(float(B[j])), 1e-6)
                grad = abs(float(B[i]) - float(B[j])) / den
                if grad > self.gradient_threshold:
                    refine_mask[i] = True
                    refine_mask[j] = True

        if not np.any(refine_mask):
            return patches, B

        new_patches: List[Surface] = []
        new_B: List[float] = []
        for i, p in enumerate(patches):
            parent = self._parent_id(p.id)
            if refine_mask[i]:
                children = self._subdivide_patch(p, self.refined_max_area)
                for c in children:
                    new_patches.append(
                        Surface(
                            id=f"{parent}__patch_{len(new_patches)}",
                            polygon=c.polygon,
                            material=p.material,
                        )
                    )
                    new_B.append(float(B[i]))
            else:
                new_patches.append(
                    Surface(
                        id=f"{parent}__patch_{len(new_patches)}",
                        polygon=p.polygon,
                        material=p.material,
                    )
                )
                new_B.append(float(B[i]))

        return new_patches, np.asarray(new_B, dtype=float)

    def _subdivide_patch(self, patch: Surface, max_area: float) -> List[Surface]:
        """
        Subdivide a patch using polygon subdivision, with quad fallback.
        """
        area_lim = max(float(max_area), 1e-9)
        try:
            polys = patch.polygon.subdivide(area_lim)
            if polys:
                return [Surface(id=f"{patch.id}__sub_{k}", polygon=poly, material=patch.material) for k, poly in enumerate(polys)]
        except Exception:
            polys = []

        verts = list(patch.polygon.vertices)
        if len(verts) == 4:
            v0, v1, v2, v3 = verts
            m01 = (v0 + v1) * 0.5
            m12 = (v1 + v2) * 0.5
            m23 = (v2 + v3) * 0.5
            m30 = (v3 + v0) * 0.5
            c = patch.polygon.get_centroid()
            quads = [
                Polygon([v0, m01, c, m30]),
                Polygon([m01, v1, m12, c]),
                Polygon([c, m12, v2, m23]),
                Polygon([m30, c, m23, v3]),
            ]
            return [Surface(id=f"{patch.id}__sub_{k}", polygon=q, material=patch.material) for k, q in enumerate(quads)]

        return [patch]
