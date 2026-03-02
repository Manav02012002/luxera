from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from luxera.calculation.illuminance import (
    DirectCalcSettings,
    IlluminanceResult,
    Luminaire,
    _is_occluded,
)
from luxera.engine.direct_illuminance import DirectGridResult, OcclusionContext, build_grid_from_spec
from luxera.geometry.core import Vector3
from luxera.photometry.interp import sample_lut_intensity_cd
from luxera.photometry.sample import sample_intensity_cd
from luxera.project.schema import CalcGrid, Project


def compute_cylindrical_illuminance(
    point: np.ndarray,
    luminaire_position: np.ndarray,
    intensity_cd: float,
) -> float:
    """
    Cylindrical illuminance contribution from a single luminaire.

    E_cyl = (I / d^2) * cos(alpha) / pi
    with cos(alpha) = horizontal_distance / distance.
    """
    p = np.asarray(point, dtype=float).reshape(3)
    l = np.asarray(luminaire_position, dtype=float).reshape(3)
    vec = l - p
    d2 = float(np.dot(vec, vec))
    if d2 <= 1e-12:
        return 0.0
    d = float(np.sqrt(d2))
    horizontal = float(np.hypot(vec[0], vec[1]))
    cos_alpha = horizontal / d
    if cos_alpha <= 0.0:
        return 0.0
    return float(intensity_cd) * cos_alpha / (np.pi * d2)


def compute_semicylindrical_illuminance(
    point: np.ndarray,
    luminaire_position: np.ndarray,
    intensity_cd: float,
    facing_direction: np.ndarray,
) -> float:
    """
    Semi-cylindrical illuminance contribution from a single luminaire.

    E_sc = (I / d^2) * cos(alpha) * max(cos(beta), 0)
    """
    p = np.asarray(point, dtype=float).reshape(3)
    l = np.asarray(luminaire_position, dtype=float).reshape(3)
    f = np.asarray(facing_direction, dtype=float).reshape(2)
    f_norm = float(np.hypot(f[0], f[1]))
    if f_norm <= 1e-12:
        return 0.0
    f_unit = f / f_norm

    vec = l - p
    d2 = float(np.dot(vec, vec))
    if d2 <= 1e-12:
        return 0.0
    d = float(np.sqrt(d2))
    horizontal_vec = vec[:2]
    horizontal = float(np.hypot(horizontal_vec[0], horizontal_vec[1]))
    if horizontal <= 1e-12:
        return 0.0

    cos_alpha = horizontal / d
    dir_h = horizontal_vec / horizontal
    cos_beta = float(np.dot(dir_h, f_unit))
    if cos_alpha <= 0.0 or cos_beta <= 0.0:
        return 0.0
    return float(intensity_cd) * cos_alpha * cos_beta / d2


def _sample_luminaire_intensity(luminaire: Luminaire, direction_world: Vector3) -> float:
    to_local = Vector3.from_array(luminaire.transform.get_rotation_matrix().T @ direction_world.to_array())
    if to_local.z >= 0.0:
        return 0.0
    tilt_data = luminaire.photometry.tilt
    tilt_active = bool(
        tilt_data is not None and str(getattr(tilt_data, "type", "")).upper() in {"INCLUDE", "FILE"}
    )
    use_lut = luminaire.lut is not None and abs(float(luminaire.tilt_deg)) <= 1e-12 and not tilt_active
    if use_lut:
        cd = sample_lut_intensity_cd(luminaire.lut, to_local)
    else:
        cd = sample_intensity_cd(luminaire.photometry, to_local, tilt_deg=luminaire.tilt_deg)
    return float(cd) * float(luminaire.flux_multiplier)


class CylindricalIlluminanceEngine:
    """Compute cylindrical and semi-cylindrical illuminance on calculation grids."""

    def compute_grid(
        self,
        project: "Project",
        grid_spec: "CalcGrid",
        luminaires: List["Luminaire"],
        metric: str = "cylindrical",
        facing_direction: Optional[Tuple[float, float]] = None,
        occlusion_ctx: Optional["OcclusionContext"] = None,
    ) -> "DirectGridResult":
        del project  # compatibility: kept for signature parity with runner call sites
        grid = build_grid_from_spec(grid_spec)
        points = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
        values = np.zeros((points.shape[0],), dtype=float)

        metric_norm = str(metric).strip().lower()
        if metric_norm not in {"cylindrical", "semicylindrical"}:
            raise ValueError(f"Unsupported cylindrical metric: {metric}")

        face = np.array(facing_direction if facing_direction is not None else (1.0, 0.0), dtype=float)
        if np.hypot(face[0], face[1]) <= 1e-12:
            face = np.array([1.0, 0.0], dtype=float)

        settings = DirectCalcSettings(use_occlusion=occlusion_ctx is not None, occlusion_epsilon=1e-6)
        tris = occlusion_ctx.triangles if occlusion_ctx is not None else []
        bvh = occlusion_ctx.bvh if occlusion_ctx is not None else None

        for idx in range(points.shape[0]):
            p_arr = points[idx]
            p_vec = Vector3(float(p_arr[0]), float(p_arr[1]), float(p_arr[2]))
            total = 0.0
            for lum in luminaires:
                lum_pos = lum.transform.position
                if settings.use_occlusion and _is_occluded(
                    p_vec,
                    lum_pos,
                    tris,
                    settings.occlusion_epsilon,
                    bvh=bvh,
                    surface_normal=None,
                ):
                    continue
                ray = p_vec - lum_pos
                dist = ray.length()
                if dist <= 1e-9:
                    continue
                direction_world = ray / dist  # luminaire -> point
                intensity_cd = _sample_luminaire_intensity(lum, direction_world)
                if intensity_cd <= 0.0:
                    continue
                lum_arr = np.array([lum_pos.x, lum_pos.y, lum_pos.z], dtype=float)
                if metric_norm == "cylindrical":
                    total += compute_cylindrical_illuminance(p_arr, lum_arr, intensity_cd)
                else:
                    total += compute_semicylindrical_illuminance(p_arr, lum_arr, intensity_cd, face)
            values[idx] = total

        values_2d = values.reshape(grid.ny, grid.nx)
        return DirectGridResult(
            points=points,
            values=values,
            nx=grid.nx,
            ny=grid.ny,
            result=IlluminanceResult(grid=grid, values=values_2d),
        )

