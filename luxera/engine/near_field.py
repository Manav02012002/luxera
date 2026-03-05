from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/near_field.md."""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

import numpy as np

from luxera.geometry.core import Vector3
from luxera.photometry.sample import sample_intensity_cd

if TYPE_CHECKING:
    from luxera.geometry.core import Transform
    from luxera.photometry.model import Photometry


NEAR_FIELD_RATIO = 5.0  # distance/max_dimension threshold


@dataclass(frozen=True)
class LuminousArea:
    """Physical luminous opening dimensions of a luminaire."""

    width_m: float
    length_m: float
    shape: str = "rectangular"  # "rectangular" or "circular"

    @property
    def max_dimension(self) -> float:
        return max(float(self.width_m), float(self.length_m))

    @property
    def area_m2(self) -> float:
        if self.shape == "circular":
            return math.pi * (self.max_dimension / 2.0) ** 2
        return float(self.width_m) * float(self.length_m)


def _estimate_beam_angle_deg(phot: "Photometry") -> float:
    gamma = np.asarray(phot.gamma_angles_deg, dtype=float)
    candela = np.asarray(phot.candela, dtype=float)
    if gamma.size < 2 or candela.size == 0:
        return 90.0

    row = candela[0] if candela.ndim >= 2 else candela
    row = np.asarray(row, dtype=float)
    if row.size != gamma.size:
        return float(max(gamma[-1] - gamma[0], 90.0))

    peak = float(np.max(row))
    if peak <= 0.0:
        return float(max(gamma[-1] - gamma[0], 90.0))

    half = 0.5 * peak
    half_gamma = None
    for i in range(1, row.size):
        a = float(row[i - 1])
        b = float(row[i])
        if a >= half >= b:
            g0 = float(gamma[i - 1])
            g1 = float(gamma[i])
            t = 0.0 if abs(a - b) <= 1e-12 else (half - a) / (b - a)
            half_gamma = g0 + t * (g1 - g0)
            break

    if half_gamma is None:
        half_gamma = float(gamma[min(int(np.argmax(row)) + 1, row.size - 1)])

    return max(1.0, min(180.0, 2.0 * float(half_gamma)))


def _coerce_dimension_to_m(value: float | None, phot: "Photometry") -> float | None:
    if value is None:
        return None
    x = float(value)
    if x <= 0.0:
        return None

    # IES can legally encode photometric dimensions in feet.
    if getattr(phot, "ies_units_type", None) == 1:
        return x * 0.3048

    # Defensive fallback if a raw mm value leaks through ingest.
    if x > 20.0:
        return x / 1000.0
    return x


def extract_luminous_area_from_photometry(phot: "Photometry") -> LuminousArea:
    """
    Extract luminous opening dimensions from parsed photometry data.

    Falls back to beam-angle-based estimates when dimensions are unavailable.
    """
    width_m = _coerce_dimension_to_m(getattr(phot, "luminous_width_m", None), phot)
    length_m = _coerce_dimension_to_m(getattr(phot, "luminous_length_m", None), phot)

    if width_m is not None and length_m is not None:
        return LuminousArea(width_m=width_m, length_m=length_m, shape="rectangular")

    if width_m is None and length_m is not None:
        return LuminousArea(width_m=length_m, length_m=length_m, shape="circular")

    if length_m is None and width_m is not None:
        return LuminousArea(width_m=width_m, length_m=width_m, shape="circular")

    beam_angle = _estimate_beam_angle_deg(phot)
    if beam_angle < 30.0:
        return LuminousArea(width_m=0.1, length_m=0.1, shape="rectangular")
    if beam_angle <= 80.0:
        return LuminousArea(width_m=0.3, length_m=0.3, shape="rectangular")
    return LuminousArea(width_m=0.6, length_m=1.2, shape="rectangular")


def is_near_field(
    luminaire_position: np.ndarray,
    calc_point: np.ndarray,
    luminous_area: LuminousArea,
) -> bool:
    """
    Determine if a calculation point is in the near-field of a luminaire.
    Returns True if distance / max_dimension < NEAR_FIELD_RATIO.
    """
    distance = float(np.linalg.norm(np.asarray(calc_point, dtype=float) - np.asarray(luminaire_position, dtype=float)))
    max_dim = max(float(luminous_area.max_dimension), 1e-9)
    return (distance / max_dim) < NEAR_FIELD_RATIO


class AreaSourceSubdivision:
    """
    Subdivide a luminaire's luminous area into sub-sources for near-field accuracy.
    """

    def __init__(self, subdivisions: int = 4):
        self.n = max(1, int(subdivisions))

    def _generate_rectangular(
        self,
        luminaire_position: np.ndarray,
        rotation: np.ndarray,
        luminous_area: LuminousArea,
    ) -> List[Dict[str, Any]]:
        width = float(luminous_area.width_m)
        length = float(luminous_area.length_m)
        out: List[Dict[str, Any]] = []

        for i in range(self.n):
            for j in range(self.n):
                x = (-0.5 * width) + ((i + 0.5) * width / self.n)
                y = (-0.5 * length) + ((j + 0.5) * length / self.n)
                local = np.array([x, y, 0.0], dtype=float)
                world = np.asarray(luminaire_position, dtype=float) + rotation @ local
                out.append(
                    {
                        "position": world,
                        "local_offset": (x, y),
                    }
                )
        return out

    def _generate_circular(
        self,
        luminaire_position: np.ndarray,
        rotation: np.ndarray,
        luminous_area: LuminousArea,
    ) -> List[Dict[str, Any]]:
        total = self.n * self.n
        radius = 0.5 * float(luminous_area.max_dimension)
        radii = [0.3 * radius, 0.6 * radius, 0.9 * radius]

        base = [max(1, int(round(total * w))) for w in (0.2, 0.3, 0.5)]
        while sum(base) > total:
            idx = int(np.argmax(base))
            if base[idx] > 1:
                base[idx] -= 1
            else:
                break
        while sum(base) < total:
            idx = int(np.argmin(base))
            base[idx] += 1

        out: List[Dict[str, Any]] = []
        for r, count in zip(radii, base):
            for k in range(count):
                angle = (2.0 * math.pi * k) / count
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                local = np.array([x, y, 0.0], dtype=float)
                world = np.asarray(luminaire_position, dtype=float) + rotation @ local
                out.append(
                    {
                        "position": world,
                        "local_offset": (x, y),
                    }
                )
        return out

    def generate_sub_sources(
        self,
        luminaire_position: np.ndarray,
        luminaire_transform: "Transform",
        luminous_area: LuminousArea,
        total_flux_lumens: float,
    ) -> List[Dict[str, Any]]:
        """
        Generate sub-source centers and flux fractions in world coordinates.
        """
        _ = float(total_flux_lumens)
        rotation = np.asarray(luminaire_transform.get_rotation_matrix(), dtype=float)

        if luminous_area.shape == "circular":
            raw = self._generate_circular(luminaire_position, rotation, luminous_area)
        else:
            raw = self._generate_rectangular(luminaire_position, rotation, luminous_area)

        if not raw:
            return []

        frac = 1.0 / float(len(raw))
        for src in raw:
            src["flux_fraction"] = frac
        return raw

    def compute_illuminance_area_source(
        self,
        sub_sources: List[Dict[str, Any]],
        calc_point: np.ndarray,
        photometry: "Photometry",
        luminaire_transform: "Transform",
        total_flux: float,
        flux_multiplier: float,
        maintenance_factor: float,
        occlusion_fn=None,
        surface_normal: np.ndarray | None = None,
    ) -> float:
        """
        Compute illuminance at calc_point from an area source.
        """
        _ = float(total_flux)
        if not sub_sources:
            return 0.0

        calc = np.asarray(calc_point, dtype=float)
        normal = np.asarray(surface_normal if surface_normal is not None else np.array([0.0, 0.0, 1.0]), dtype=float)
        n_len = float(np.linalg.norm(normal))
        if n_len <= 1e-12:
            normal = np.array([0.0, 0.0, 1.0], dtype=float)
        else:
            normal = normal / n_len

        rotation = np.asarray(luminaire_transform.get_rotation_matrix(), dtype=float)
        scale = max(0.0, float(flux_multiplier) * float(maintenance_factor))
        total_e = 0.0

        for src in sub_sources:
            src_pos = np.asarray(src["position"], dtype=float)
            to_source = src_pos - calc
            dist = float(np.linalg.norm(to_source))
            if dist <= 1e-9:
                continue
            dir_to_source = to_source / dist
            dir_from_source = -dir_to_source

            if occlusion_fn is not None and occlusion_fn(calc, dir_to_source, dist):
                continue

            local_dir = rotation.T @ dir_from_source
            if float(local_dir[2]) >= 0.0:
                continue

            intensity = sample_intensity_cd(photometry, Vector3.from_array(local_dir))
            cos_incidence = float(np.dot(dir_to_source, normal))
            if cos_incidence <= 0.0:
                continue

            contrib = intensity * cos_incidence / (dist * dist)
            contrib *= float(src.get("flux_fraction", 0.0)) * scale
            total_e += contrib

        return max(0.0, float(total_e))
