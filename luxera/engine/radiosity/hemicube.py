from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from luxera.geometry.bvh import BVHNode
from luxera.geometry.core import Surface, Vector3
from luxera.geometry.triangulate import triangulate_polygon_vertices


@dataclass(frozen=True)
class _SceneTriangle:
    vertices: np.ndarray  # (3, 3) world-space XYZ
    patch_index: int


class HemicubeEngine:
    """
    Hemicube form factor computation engine.

    Computes the NxN form factor matrix F[i,j] by rasterizing the scene
    from each patch's viewpoint onto a hemicube. Each hemicube has 5 faces:
    top (NxN), and 4 sides (N x N/2 each, since sides only cover the upper
    hemisphere).

    Pre-computed delta form factors for each pixel encode the differential
    solid angle weighted by cos(theta), so F[i,j] = sum of delta_ff for
    all pixels where patch j is the closest visible patch.
    """

    def __init__(self, resolution: int = 128):
        """
        resolution: pixels per hemicube face edge. 64=fast/rough, 128=good,
                    256=high quality. The top face is resolution x resolution.
                    Each side face is resolution x (resolution//2).
        """
        self.resolution = max(8, int(resolution))
        self.side_height = max(1, self.resolution // 2)
        self._delta_top = self._precompute_delta_top()
        self._delta_side = self._precompute_delta_side()

    def _precompute_delta_top(self) -> np.ndarray:
        """
        Return (resolution, resolution) array of delta form factors for top face.
        Use meshgrid of pixel centers in [-1,1] range.
        """
        res = self.resolution
        step = 2.0 / float(res)
        coords = -1.0 + (np.arange(res, dtype=float) + 0.5) * step
        u, v = np.meshgrid(coords, coords, indexing="xy")
        d_a = step * step
        denom = np.pi * np.power(u * u + v * v + 1.0, 2.0)
        return d_a / np.maximum(denom, 1e-18)

    def _precompute_delta_side(self) -> np.ndarray:
        """
        Return (resolution//2, resolution) array for one side face.
        v ranges [-1,1], w ranges (0,1] (lower hemisphere excluded).
        """
        res = self.resolution
        h = self.side_height
        step_u = 2.0 / float(res)
        step_w = 1.0 / float(h)
        v_coords = -1.0 + (np.arange(res, dtype=float) + 0.5) * step_u
        w_coords = (np.arange(h, dtype=float) + 0.5) * step_w
        v, w = np.meshgrid(v_coords, w_coords, indexing="xy")
        d_a = step_u * step_w
        denom = np.pi * np.power(1.0 + v * v + w * w, 2.0)
        return (w / np.maximum(denom, 1e-18)) * d_a

    def compute_matrix(
        self,
        patches: List[Surface],
        all_surfaces: List[Surface],
        bvh: Optional[BVHNode] = None,
    ) -> np.ndarray:
        """
        Compute full NxN form factor matrix.

        For each patch i:
        1. Build local coordinate frame: normal N, tangent T, bitangent B.
           Use Gram-Schmidt: pick world axis least parallel to N, cross to get T, cross again for B.
        2. For each hemicube face (top, +T, -T, +B, -B):
           a. Allocate id_buffer (int, init -1) and z_buffer (float, init +inf)
              sized to match the face dimensions.
           b. For each OTHER patch j, project j's polygon vertices into
              hemicube face coordinates, then rasterize the projected
              triangle(s) with z-buffer test.
           c. After rasterizing all patches, sum delta_ff for all pixels
              where id_buffer == j to accumulate F[i,j].
        3. Enforce reciprocity: F[i,j] = (F[i,j]*A[i] + F[j,i]*A[j]) / (2*A[i])
           (symmetrize the transport matrix).
        """
        _ = bvh  # Rasterized hemicube visibility uses per-face Z-buffering.
        n = len(patches)
        F = np.zeros((n, n), dtype=float)
        if n == 0:
            return F

        areas = np.array([max(float(p.area), 1e-12) for p in patches], dtype=float)
        id_to_index = {str(p.id): i for i, p in enumerate(patches)}
        scene = self._build_scene_triangles(patches if patches else all_surfaces, id_to_index)

        faces = ("top", "+T", "-T", "+B", "-B")

        for i, patch in enumerate(patches):
            center = np.array([patch.centroid.x, patch.centroid.y, patch.centroid.z], dtype=float)
            n_vec = np.array([patch.normal.x, patch.normal.y, patch.normal.z], dtype=float)
            t_vec, b_vec, n_unit = self._build_local_frame(n_vec)

            for face in faces:
                if face == "top":
                    h = self.resolution
                    w = self.resolution
                    delta_ff = self._delta_top
                else:
                    h = self.side_height
                    w = self.resolution
                    delta_ff = self._delta_side

                id_buffer = np.full((h, w), -1, dtype=np.int32)
                z_buffer = np.full((h, w), np.inf, dtype=float)

                for tri in scene:
                    j = tri.patch_index
                    if j < 0 or j == i:
                        continue
                    projected = self._project_vertices_to_face(tri.vertices, center, t_vec, b_vec, n_unit, face)
                    if projected is None or projected.shape[0] < 3:
                        continue
                    # Triangulate clipped polygon (fan) and rasterize.
                    for k in range(1, projected.shape[0] - 1):
                        self._rasterize_triangle(projected[0], projected[k], projected[k + 1], j, id_buffer, z_buffer)

                flat_ids = id_buffer.ravel()
                valid = flat_ids >= 0
                if np.any(valid):
                    contrib = np.bincount(flat_ids[valid], weights=delta_ff.ravel()[valid], minlength=n)
                    F[i, :] += contrib[:n]

            F[i, i] = 0.0

        # Enforce reciprocity.
        for i in range(n):
            for j in range(i + 1, n):
                phi_ij = 0.5 * (F[i, j] * areas[i] + F[j, i] * areas[j])
                F[i, j] = phi_ij / areas[i]
                F[j, i] = phi_ij / areas[j]

        np.fill_diagonal(F, 0.0)
        F = np.clip(F, 0.0, 1.0)
        row_sums = np.sum(F, axis=1)
        over = row_sums > 1.0
        if np.any(over):
            F[over, :] = F[over, :] / row_sums[over, None]
        return F

    def _build_local_frame(self, normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (tangent, bitangent, normal) orthonormal frame."""
        n = np.asarray(normal, dtype=float)
        n_norm = float(np.linalg.norm(n))
        if n_norm < 1e-12:
            n = np.array([0.0, 0.0, 1.0], dtype=float)
        else:
            n = n / n_norm

        axes = (
            np.array([1.0, 0.0, 0.0], dtype=float),
            np.array([0.0, 1.0, 0.0], dtype=float),
            np.array([0.0, 0.0, 1.0], dtype=float),
        )
        helper = min(axes, key=lambda a: abs(float(np.dot(a, n))))
        t = np.cross(helper, n)
        t_norm = float(np.linalg.norm(t))
        if t_norm < 1e-12:
            helper = np.array([0.0, 1.0, 0.0], dtype=float)
            t = np.cross(helper, n)
            t_norm = float(np.linalg.norm(t))
        t = t / max(t_norm, 1e-12)
        b = np.cross(n, t)
        b = b / max(float(np.linalg.norm(b)), 1e-12)
        return t, b, n

    def _project_vertices_to_face(
        self,
        vertices: np.ndarray,
        center: np.ndarray,
        T: np.ndarray,
        B: np.ndarray,
        N: np.ndarray,
        face: str,
    ) -> Optional[np.ndarray]:
        """
        Project vertices onto hemicube face. Returns (n_verts, 3) array
        of (pixel_x, pixel_y, depth) or None if all vertices behind face.
        face is one of: "top", "+T", "-T", "+B", "-B"
        """
        rel = np.asarray(vertices, dtype=float) - center[None, :]
        x = rel @ T
        y = rel @ B
        z = rel @ N
        poly = np.stack((x, y, z), axis=1)
        eps = 1e-9

        def _clip(poly_pts: np.ndarray, fn) -> np.ndarray:
            if poly_pts.shape[0] == 0:
                return poly_pts
            out: List[np.ndarray] = []
            count = poly_pts.shape[0]
            for idx in range(count):
                a = poly_pts[idx]
                b = poly_pts[(idx + 1) % count]
                fa = float(fn(a))
                fb = float(fn(b))
                keep_a = fa >= 0.0
                keep_b = fb >= 0.0
                if keep_a and keep_b:
                    out.append(b)
                elif keep_a and not keep_b:
                    den = fa - fb
                    if abs(den) < 1e-18:
                        continue
                    t = fa / den
                    out.append(a + t * (b - a))
                elif (not keep_a) and keep_b:
                    den = fa - fb
                    if abs(den) < 1e-18:
                        out.append(b)
                        continue
                    t = fa / den
                    out.append(a + t * (b - a))
                    out.append(b)
            if not out:
                return np.zeros((0, 3), dtype=float)
            return np.stack(out, axis=0)

        def _clip_many(poly_pts: np.ndarray, planes) -> np.ndarray:
            out = poly_pts
            for plane in planes:
                out = _clip(out, plane)
                if out.shape[0] < 3:
                    return np.zeros((0, 3), dtype=float)
            return out

        if face == "top":
            poly = _clip_many(
                poly,
                (
                    lambda p: p[2] - eps,
                    lambda p: p[2] - p[0],
                    lambda p: p[2] + p[0],
                    lambda p: p[2] - p[1],
                    lambda p: p[2] + p[1],
                ),
            )
            if poly.shape[0] < 3:
                return None
            denom = poly[:, 2]
            u = poly[:, 0] / np.maximum(denom, eps)
            v = poly[:, 1] / np.maximum(denom, eps)
            px = (u + 1.0) * 0.5 * self.resolution
            py = (1.0 - (v + 1.0) * 0.5) * self.resolution
            depth = denom
        elif face == "+T":
            poly = _clip_many(
                poly,
                (
                    lambda p: p[0] - eps,
                    lambda p: p[2],
                    lambda p: p[0] - p[1],
                    lambda p: p[0] + p[1],
                    lambda p: p[0] - p[2],
                ),
            )
            if poly.shape[0] < 3:
                return None
            denom = poly[:, 0]
            v = poly[:, 1] / np.maximum(denom, eps)
            w = poly[:, 2] / np.maximum(denom, eps)
            px = (v + 1.0) * 0.5 * self.resolution
            py = (1.0 - w) * self.side_height
            depth = denom
        elif face == "-T":
            poly = _clip_many(
                poly,
                (
                    lambda p: -p[0] - eps,
                    lambda p: p[2],
                    lambda p: -p[0] - p[1],
                    lambda p: -p[0] + p[1],
                    lambda p: -p[0] - p[2],
                ),
            )
            if poly.shape[0] < 3:
                return None
            denom = -poly[:, 0]
            v = -poly[:, 1] / np.maximum(denom, eps)
            w = poly[:, 2] / np.maximum(denom, eps)
            px = (v + 1.0) * 0.5 * self.resolution
            py = (1.0 - w) * self.side_height
            depth = denom
        elif face == "+B":
            poly = _clip_many(
                poly,
                (
                    lambda p: p[1] - eps,
                    lambda p: p[2],
                    lambda p: p[1] - p[0],
                    lambda p: p[1] + p[0],
                    lambda p: p[1] - p[2],
                ),
            )
            if poly.shape[0] < 3:
                return None
            denom = poly[:, 1]
            v = -poly[:, 0] / np.maximum(denom, eps)
            w = poly[:, 2] / np.maximum(denom, eps)
            px = (v + 1.0) * 0.5 * self.resolution
            py = (1.0 - w) * self.side_height
            depth = denom
        elif face == "-B":
            poly = _clip_many(
                poly,
                (
                    lambda p: -p[1] - eps,
                    lambda p: p[2],
                    lambda p: -p[1] - p[0],
                    lambda p: -p[1] + p[0],
                    lambda p: -p[1] - p[2],
                ),
            )
            if poly.shape[0] < 3:
                return None
            denom = -poly[:, 1]
            v = poly[:, 0] / np.maximum(denom, eps)
            w = poly[:, 2] / np.maximum(denom, eps)
            px = (v + 1.0) * 0.5 * self.resolution
            py = (1.0 - w) * self.side_height
            depth = denom
        else:
            return None

        projected = np.stack((px, py, depth), axis=1)
        if not np.any(np.isfinite(projected[:, :2])):
            return None
        return projected

    def _rasterize_triangle(
        self,
        v0,
        v1,
        v2,
        patch_id: int,
        id_buffer: np.ndarray,
        z_buffer: np.ndarray,
    ):
        """
        Rasterize single triangle into buffers using scanline with
        barycentric interpolation for depth. Handle clipping by skipping
        pixels outside buffer bounds.
        """
        p0 = np.asarray(v0, dtype=float)
        p1 = np.asarray(v1, dtype=float)
        p2 = np.asarray(v2, dtype=float)
        if not np.all(np.isfinite(p0)) or not np.all(np.isfinite(p1)) or not np.all(np.isfinite(p2)):
            return

        x0, y0, z0 = float(p0[0]), float(p0[1]), float(p0[2])
        x1, y1, z1 = float(p1[0]), float(p1[1]), float(p1[2])
        x2, y2, z2 = float(p2[0]), float(p2[1]), float(p2[2])

        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-12:
            return

        h, w = id_buffer.shape
        min_x = max(0, int(np.floor(min(x0, x1, x2))))
        max_x = min(w - 1, int(np.ceil(max(x0, x1, x2))))
        min_y = max(0, int(np.floor(min(y0, y1, y2))))
        max_y = min(h - 1, int(np.ceil(max(y0, y1, y2))))
        if min_x > max_x or min_y > max_y:
            return

        inv_den = 1.0 / den
        for py in range(min_y, max_y + 1):
            cy = py + 0.5
            for px in range(min_x, max_x + 1):
                cx = px + 0.5
                w0 = ((y1 - y2) * (cx - x2) + (x2 - x1) * (cy - y2)) * inv_den
                w1 = ((y2 - y0) * (cx - x2) + (x0 - x2) * (cy - y2)) * inv_den
                w2 = 1.0 - w0 - w1
                if w0 < -1e-10 or w1 < -1e-10 or w2 < -1e-10:
                    continue
                depth = w0 * z0 + w1 * z1 + w2 * z2
                if depth <= 0.0:
                    continue
                if depth < z_buffer[py, px]:
                    z_buffer[py, px] = depth
                    id_buffer[py, px] = int(patch_id)

    def check_conservation(self, F: np.ndarray, areas: np.ndarray) -> float:
        """For a closed scene, each row should sum to ~1.0. Return max deviation."""
        _ = areas
        if F.size == 0:
            return 0.0
        row_sums = np.sum(F, axis=1)
        return float(np.max(np.abs(row_sums - 1.0)))

    def _build_scene_triangles(self, surfaces: List[Surface], id_to_index: dict[str, int]) -> List[_SceneTriangle]:
        scene: List[_SceneTriangle] = []
        for s in surfaces:
            verts = np.array([[v.x, v.y, v.z] for v in s.polygon.vertices], dtype=float)
            for a, b, c in triangulate_polygon_vertices([tuple(row) for row in verts]):
                tri = np.array([a, b, c], dtype=float)
                scene.append(_SceneTriangle(vertices=tri, patch_index=id_to_index.get(str(s.id), -1)))
        return scene
