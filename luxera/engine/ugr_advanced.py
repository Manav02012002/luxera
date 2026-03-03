from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.geometry.core import Room, Vector3
from luxera.geometry.spatial import point_in_polygon
from luxera.photometry.sample import sample_intensity_cd_world


@dataclass(frozen=True)
class AdvancedUGRResult:
    ugr_max: float
    ugr_by_observer: List[Dict[str, Any]]
    worst_observer_position: Tuple[float, float, float]
    worst_viewing_direction: Tuple[float, float]
    background_luminance: float
    top_contributors: List[Dict[str, Any]]
    observer_count: int


class AdvancedUGREngine:
    """
    Complete CIE UGR computation with full observer set and shielding.
    """

    # Polynomial coefficients for log10(p) approximation on normalized variables.
    # Dimensions: [i][j] for t^i * s^j.
    _GUTH_COEFFS: Tuple[Tuple[float, ...], ...] = (
        (0.08, 0.22, 0.06),
        (0.95, 0.18, 0.02),
        (0.24, 0.04, 0.00),
    )

    def __init__(self, shielding_angle_deg: float = 20.0):
        self.shielding_angle_deg = max(0.0, min(80.0, float(shielding_angle_deg)))

    def compute(
        self,
        room: Room,
        luminaires: List[Luminaire],
        observer_height: float = 1.2,
        observer_grid_spacing: float = 2.0,
        viewing_directions: Optional[List[Tuple[float, float]]] = None,
    ) -> AdvancedUGRResult:
        observers = self._generate_observer_positions(room, observer_height, observer_grid_spacing)
        dirs = viewing_directions or [(1.0, 0.0), (0.0, 1.0)]

        total_flux = 0.0
        for lum in luminaires:
            total_flux += float(lum.photometry.luminous_flux_lm or 0.0) * float(lum.flux_multiplier)
        if total_flux <= 0.0:
            total_flux = float(len(luminaires)) * 2000.0

        ceiling_area = max(room.floor_area, 1e-6)
        indirect_E_ceiling = 0.3 * total_flux / ceiling_area

        worst_ugr = 0.0
        worst_pos = (0.0, 0.0, float(observer_height))
        worst_dir = (1.0, 0.0)
        worst_contributors: List[Dict[str, Any]] = []
        by_observer: List[Dict[str, Any]] = []
        background_luminance = 10.0

        for obs in observers:
            obs_arr = np.asarray(obs, dtype=float)
            Lb = self._background_luminance(room, obs_arr, indirect_E_ceiling)
            background_luminance = Lb

            for view_xy in dirs:
                vx, vy = float(view_xy[0]), float(view_xy[1])
                if abs(vx) + abs(vy) < 1e-12:
                    continue
                view = np.array([vx, vy, 0.0], dtype=float)
                view /= max(np.linalg.norm(view), 1e-12)
                up = np.array([0.0, 0.0, 1.0], dtype=float)
                right = np.cross(view, up)
                if np.linalg.norm(right) <= 1e-12:
                    right = np.array([1.0, 0.0, 0.0], dtype=float)
                right /= max(np.linalg.norm(right), 1e-12)

                sum_term = 0.0
                contributions: List[Dict[str, Any]] = []

                for i, lum in enumerate(luminaires):
                    lum_pos = np.asarray(lum.transform.position.to_tuple(), dtype=float)
                    to_lum = lum_pos - obs_arr
                    d = float(np.linalg.norm(to_lum))
                    if d <= 1e-6:
                        continue
                    u_obs_to_lum = to_lum / d
                    forward = float(np.dot(u_obs_to_lum, view))
                    if forward <= 0.0:
                        continue

                    lum_normal = self._luminaire_normal(lum)
                    u_lum_to_obs = (obs_arr - lum_pos) / d
                    cos_emit = float(np.dot(lum_normal, u_lum_to_obs))
                    if cos_emit <= 0.0:
                        continue

                    off_axis = math.degrees(math.acos(max(-1.0, min(1.0, cos_emit))))
                    visible_limit = max(5.0, 90.0 - self.shielding_angle_deg)
                    if off_axis > visible_limit:
                        continue

                    width = float(lum.photometry.luminous_width_m or 0.6)
                    length = float(lum.photometry.luminous_length_m or 0.6)
                    area = max(width * length, 1e-6)

                    omega = self._luminous_solid_angle(obs_arr, lum_pos, lum_normal, width, length)
                    if omega <= 0.0:
                        continue

                    dir_world = Vector3.from_array(obs_arr - lum_pos)
                    intensity = float(sample_intensity_cd_world(lum.photometry, lum.transform, dir_world)) * float(lum.flux_multiplier)
                    A_proj = max(area * cos_emit, 1e-6)
                    L = max(0.0, intensity / A_proj)
                    if L <= 0.0:
                        continue

                    lateral = float(np.dot(u_obs_to_lum, right))
                    vertical = float(np.dot(u_obs_to_lum, up))
                    T_deg = math.degrees(math.atan2(abs(lateral), max(forward, 1e-9)))
                    S_deg = math.degrees(math.atan2(vertical, max(forward, 1e-9)))
                    p = self._guth_position_index(T_deg, S_deg)

                    term = (L * L * omega) / max(p * p, 1e-9)
                    if term <= 0.0:
                        continue
                    sum_term += term
                    contributions.append(
                        {
                            "luminaire_index": i,
                            "L": L,
                            "omega": omega,
                            "p": p,
                            "T_deg": T_deg,
                            "S_deg": S_deg,
                            "contribution": term,
                        }
                    )

                if sum_term <= 0.0:
                    ugr = 0.0
                else:
                    ugr = 8.0 * math.log10((0.25 / max(Lb, 1e-6)) * sum_term)
                    ugr = max(0.0, ugr)

                by_observer.append(
                    {
                        "observer_position": obs,
                        "viewing_direction": (vx, vy),
                        "ugr": ugr,
                        "background_luminance": Lb,
                        "contributors": sorted(contributions, key=lambda x: x["contribution"], reverse=True),
                    }
                )

                if ugr > worst_ugr:
                    worst_ugr = ugr
                    worst_pos = obs
                    worst_dir = (vx, vy)
                    worst_contributors = sorted(contributions, key=lambda x: x["contribution"], reverse=True)[:3]

        return AdvancedUGRResult(
            ugr_max=float(worst_ugr),
            ugr_by_observer=by_observer,
            worst_observer_position=worst_pos,
            worst_viewing_direction=worst_dir,
            background_luminance=float(background_luminance),
            top_contributors=worst_contributors,
            observer_count=len(observers),
        )

    def _guth_position_index(self, T_deg: float, S_deg: float) -> float:
        """
        CIE 117 Guth position index approximation with polynomial coefficients.
        """
        T_eff = max(5.0, float(abs(T_deg)))
        S_eff = float(abs(S_deg))

        t = math.log10(T_eff)
        s = min(1.5, S_eff / 90.0)

        log10_p = 0.0
        for i, row in enumerate(self._GUTH_COEFFS):
            for j, aij in enumerate(row):
                log10_p += float(aij) * (t**i) * (s**j)

        p = 10.0 ** log10_p
        return max(1.0, min(200.0, p))

    def _luminous_solid_angle(
        self,
        observer_pos: np.ndarray,
        luminaire_pos: np.ndarray,
        luminaire_normal: np.ndarray,
        luminous_width: float,
        luminous_length: float,
    ) -> float:
        """Compute solid angle of luminous area from observer position."""
        v = observer_pos - luminaire_pos
        d = float(np.linalg.norm(v))
        if d <= 1e-6:
            return 0.0
        u = v / d
        cos_theta = float(np.dot(luminaire_normal / max(np.linalg.norm(luminaire_normal), 1e-12), u))
        if cos_theta <= 0.0:
            return 0.0
        area = max(float(luminous_width) * float(luminous_length), 1e-6)
        omega = area * cos_theta / (d * d)
        return max(0.0, float(omega))

    def _background_luminance(
        self,
        room: Room,
        observer_pos: np.ndarray,
        indirect_E_ceiling: float,
    ) -> float:
        """
        Background luminance Lb.
        Lb = E_indirect_at_observer_eye / π
        E_indirect ≈ (ceiling_avg_illuminance × ceiling_reflectance) / π
        """
        _ = observer_pos
        rho_c = float(getattr(room.ceiling_material, "reflectance", 0.7) or 0.7)
        E_indirect = max(0.0, float(indirect_E_ceiling) * rho_c / math.pi)
        Lb = E_indirect / math.pi
        return max(1.0, float(Lb))

    def _generate_observer_positions(self, room: Room, observer_height: float, spacing: float) -> List[Tuple[float, float, float]]:
        poly = [(float(v.x), float(v.y)) for v in room.floor_vertices]
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        s = max(0.2, float(spacing))

        points: List[Tuple[float, float, float]] = []
        x = min(xs) + 0.5 * s
        while x < max(xs):
            y = min(ys) + 0.5 * s
            while y < max(ys):
                if point_in_polygon((x, y), poly):
                    points.append((float(x), float(y), float(observer_height)))
                y += s
            x += s

        if not points:
            cx = 0.5 * (min(xs) + max(xs))
            cy = 0.5 * (min(ys) + max(ys))
            points.append((float(cx), float(cy), float(observer_height)))
        return points

    def _luminaire_normal(self, luminaire: Luminaire) -> np.ndarray:
        R = luminaire.transform.get_rotation_matrix()
        n = R @ np.array([0.0, 0.0, -1.0], dtype=float)
        ln = float(np.linalg.norm(n))
        if ln <= 1e-12:
            return np.array([0.0, 0.0, -1.0], dtype=float)
        return n / ln
