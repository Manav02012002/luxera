from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance
from luxera.geometry.core import Vector3


@dataclass(frozen=True)
class FacadeSpec:
    """Defines a building facade to be illuminated."""

    name: str
    width_m: float
    height_m: float
    position: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    reflectance: float = 0.3
    grid_spacing: float = 1.0


class FacadeLightingEngine:
    """Compute vertical illuminance on building facades."""

    def generate_grid_points(self, facade: FacadeSpec) -> np.ndarray:
        spacing = max(1e-3, float(facade.grid_spacing))
        nx = max(1, int(float(facade.width_m) / spacing))
        ny = max(1, int(float(facade.height_m) / spacing))

        origin = np.asarray(facade.position, dtype=float)
        n = np.asarray(facade.normal, dtype=float)
        n_norm = np.linalg.norm(n)
        if n_norm <= 1e-12:
            raise ValueError("Facade normal must be non-zero")
        n = n / n_norm

        up = np.array([0.0, 0.0, 1.0], dtype=float)
        if abs(float(np.dot(up, n))) > 0.99:
            up = np.array([1.0, 0.0, 0.0], dtype=float)

        u = np.cross(up, n)
        u = u / max(np.linalg.norm(u), 1e-12)
        v = np.cross(n, u)
        v = v / max(np.linalg.norm(v), 1e-12)

        pts: List[np.ndarray] = []
        for j in range(ny):
            z_off = (j + 0.5) * spacing
            for i in range(nx):
                x_off = (i + 0.5) * spacing
                pts.append(origin + u * x_off + v * z_off)
        return np.asarray(pts, dtype=float)

    def compute(self, facade: FacadeSpec, luminaires: List[Luminaire]) -> Dict[str, Any]:
        points = self.generate_grid_points(facade)
        spacing = max(1e-3, float(facade.grid_spacing))
        nx = max(1, int(float(facade.width_m) / spacing))
        ny = max(1, int(float(facade.height_m) / spacing))

        normal_v = Vector3(*facade.normal).normalize()
        values = np.zeros((ny, nx), dtype=float)

        k = 0
        for j in range(ny):
            for i in range(nx):
                p = points[k]
                pt = Vector3(float(p[0]), float(p[1]), float(p[2]))
                e = 0.0
                for lum in luminaires:
                    e += calculate_direct_illuminance(pt, normal_v, lum)
                values[j, i] = e
                k += 1

        flat = values.reshape(-1)
        e_avg = float(np.mean(flat)) if flat.size else 0.0
        e_min = float(np.min(flat)) if flat.size else 0.0
        e_max = float(np.max(flat)) if flat.size else 0.0
        u0 = e_min / e_avg if e_avg > 1e-12 else 0.0

        return {
            "facade_name": facade.name,
            "grid_points": points,
            "grid_values": values,
            "values_flat": flat,
            "nx": nx,
            "ny": ny,
            "E_avg": e_avg,
            "E_min": e_min,
            "E_max": e_max,
            "U0": u0,
            "uniformity": u0,
        }
