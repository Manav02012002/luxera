from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, TYPE_CHECKING

import numpy as np

from luxera.geometry.core import Surface

if TYPE_CHECKING:
    from luxera.engine.radiosity.solver import SolverStatus


class CCTConverter:
    """Convert correlated colour temperature to normalized RGB."""

    @staticmethod
    def cct_to_xy(cct_kelvin: float) -> Tuple[float, float]:
        """
        CIE xy chromaticity from CCT using Hernandez-Andres et al. formula.
        Valid range: 1667K to 25000K.
        """
        t = float(max(1667.0, min(25000.0, cct_kelvin)))
        if t <= 4000.0:
            x = -0.2661239e9 / (t**3) - 0.2343589e6 / (t**2) + 0.8776956e3 / t + 0.179910
        else:
            x = -3.0258469e9 / (t**3) + 2.1070379e6 / (t**2) + 0.2226347e3 / t + 0.240390

        if t <= 2222.0:
            y = -1.1063814 * (x**3) - 1.34811020 * (x**2) + 2.18555832 * x - 0.20219683
        elif t <= 4000.0:
            y = -0.9549476 * (x**3) - 1.37418593 * (x**2) + 2.09137015 * x - 0.16748867
        else:
            y = 3.0817580 * (x**3) - 5.87338670 * (x**2) + 3.75112997 * x - 0.37001483
        return float(x), float(y)

    @staticmethod
    def xy_to_rgb(x: float, y: float) -> Tuple[float, float, float]:
        """
        CIE xy → XYZ (with Y=1) → linear sRGB.
        Clamp negatives to 0, normalize so max channel = 1.0.
        """
        yy = max(float(y), 1e-9)
        xx = float(x)
        X = xx / yy
        Y = 1.0
        Z = max((1.0 - xx - yy) / yy, 0.0)

        r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
        g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
        b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
        rgb = np.array([max(r, 0.0), max(g, 0.0), max(b, 0.0)], dtype=float)
        mx = float(np.max(rgb))
        if mx <= 1e-12:
            return (1.0, 1.0, 1.0)
        rgb = rgb / mx
        return float(rgb[0]), float(rgb[1]), float(rgb[2])

    @staticmethod
    def cct_to_rgb(cct_kelvin: float) -> Tuple[float, float, float]:
        """Full pipeline: CCT → xy → RGB. Clamp CCT to [1667, 25000]."""
        x, y = CCTConverter.cct_to_xy(cct_kelvin)
        return CCTConverter.xy_to_rgb(x, y)

    @staticmethod
    def cct_to_photopic_rgb_scale(cct_kelvin: float) -> Tuple[float, float, float]:
        """
        Return RGB scaling such that 683*(0.2126*R + 0.7152*G + 0.0722*B) == 1.
        """
        rgb = np.array(CCTConverter.cct_to_rgb(cct_kelvin), dtype=float)
        y_w = float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
        if y_w <= 1e-12:
            return (1.0 / 683.0, 1.0 / 683.0, 1.0 / 683.0)
        rgb = rgb / (683.0 * y_w)
        return float(rgb[0]), float(rgb[1]), float(rgb[2])


@dataclass(frozen=True)
class SpectralMaterial:
    """Material with per-channel reflectance."""

    name: str
    reflectance_rgb: Tuple[float, float, float]  # (R, G, B) each in [0,1]

    @classmethod
    def from_scalar(cls, name: str, reflectance: float, tint: str = "neutral"):
        """
        Convert scalar reflectance to RGB using tint presets.
        """
        r = max(0.0, min(1.0, float(reflectance)))
        presets: Dict[str, Tuple[float, float, float]] = {
            "neutral": (1.0, 1.0, 1.0),
            "warm_wood": (1.20, 1.00, 0.75),
            "cool_concrete": (0.95, 1.00, 1.08),
            "red_brick": (1.25, 0.70, 0.55),
            "green_paint": (0.75, 1.20, 0.75),
            "blue_carpet": (0.70, 0.80, 1.25),
            "cream_wall": (1.15, 1.08, 0.92),
            "dark_floor": (1.02, 1.00, 0.90),
        }
        ratios = presets.get(tint, presets["neutral"])
        base = np.array(ratios, dtype=float)
        base /= max(float(np.mean(base)), 1e-12)
        rgb = np.clip(r * base, 0.0, 1.0)
        return cls(name=name, reflectance_rgb=(float(rgb[0]), float(rgb[1]), float(rgb[2])))


SPECTRAL_MATERIAL_LIBRARY: Dict[str, SpectralMaterial] = {
    "white_plaster": SpectralMaterial("white_plaster", (0.85, 0.85, 0.84)),
    "ivory_paint": SpectralMaterial("ivory_paint", (0.81, 0.79, 0.72)),
    "cream_wall": SpectralMaterial("cream_wall", (0.78, 0.74, 0.62)),
    "grey_carpet": SpectralMaterial("grey_carpet", (0.29, 0.30, 0.31)),
    "dark_grey_carpet": SpectralMaterial("dark_grey_carpet", (0.14, 0.14, 0.15)),
    "oak_floor": SpectralMaterial("oak_floor", (0.46, 0.37, 0.25)),
    "maple_floor": SpectralMaterial("maple_floor", (0.55, 0.47, 0.35)),
    "walnut_floor": SpectralMaterial("walnut_floor", (0.30, 0.22, 0.15)),
    "red_brick": SpectralMaterial("red_brick", (0.36, 0.18, 0.13)),
    "concrete_raw": SpectralMaterial("concrete_raw", (0.33, 0.34, 0.35)),
    "concrete_polished": SpectralMaterial("concrete_polished", (0.42, 0.43, 0.45)),
    "painted_concrete": SpectralMaterial("painted_concrete", (0.62, 0.64, 0.67)),
    "green_paint": SpectralMaterial("green_paint", (0.20, 0.44, 0.23)),
    "blue_carpet": SpectralMaterial("blue_carpet", (0.13, 0.20, 0.37)),
    "navy_carpet": SpectralMaterial("navy_carpet", (0.07, 0.10, 0.22)),
    "terracotta_tile": SpectralMaterial("terracotta_tile", (0.41, 0.25, 0.18)),
    "white_tile": SpectralMaterial("white_tile", (0.83, 0.84, 0.86)),
    "black_tile": SpectralMaterial("black_tile", (0.05, 0.05, 0.05)),
    "ceiling_tile": SpectralMaterial("ceiling_tile", (0.79, 0.81, 0.82)),
    "acoustic_panel": SpectralMaterial("acoustic_panel", (0.67, 0.70, 0.71)),
    "glass_clear": SpectralMaterial("glass_clear", (0.08, 0.08, 0.08)),
    "glass_tinted": SpectralMaterial("glass_tinted", (0.06, 0.08, 0.10)),
    "aluminium": SpectralMaterial("aluminium", (0.72, 0.73, 0.75)),
    "stainless_steel": SpectralMaterial("stainless_steel", (0.62, 0.63, 0.66)),
    "fabric_beige": SpectralMaterial("fabric_beige", (0.48, 0.43, 0.34)),
}


@dataclass(frozen=True)
class SpectralRadiosityResult:
    radiosity_rgb: np.ndarray  # (N, 3)
    irradiance_rgb: np.ndarray  # (N, 3)
    illuminance_photopic: np.ndarray  # (N,)
    chromaticity_xy: np.ndarray  # (N, 2)
    status: "SolverStatus"
    energy_rgb: np.ndarray  # (3,)


def rgb_to_chromaticity_xy(rgb: np.ndarray) -> np.ndarray:
    """(N,3) linear sRGB → (N,2) CIE xy via inverse sRGB matrix → XYZ → xy."""
    arr = np.asarray(rgb, dtype=float)
    if arr.size == 0:
        return np.zeros((0, 2), dtype=float)
    M = np.array(
        [
            [0.4124, 0.3576, 0.1805],
            [0.2126, 0.7152, 0.0722],
            [0.0193, 0.1192, 0.9505],
        ],
        dtype=float,
    )
    xyz = arr @ M.T
    s = np.sum(xyz, axis=1)
    out = np.zeros((arr.shape[0], 2), dtype=float)
    valid = s > 1e-12
    out[valid, 0] = xyz[valid, 0] / s[valid]
    out[valid, 1] = xyz[valid, 1] / s[valid]
    out[~valid, 0] = 0.3127
    out[~valid, 1] = 0.3290
    return out


def estimate_cct_from_xy(xy: np.ndarray) -> np.ndarray:
    """McCamy's approximation from CIE xy."""
    arr = np.asarray(xy, dtype=float)
    if arr.size == 0:
        return np.zeros((0,), dtype=float)
    x = arr[:, 0]
    y = arr[:, 1]
    den = 0.1858 - y
    den = np.where(np.abs(den) < 1e-9, np.sign(den) * 1e-9 + (den == 0.0) * 1e-9, den)
    n = (x - 0.3320) / den
    return 449.0 * n**3 + 3525.0 * n**2 + 6823.3 * n + 5520.33


class SpectralRadiositySolver:
    """
    3-channel progressive shooting radiosity.
    Same algorithm as scalar solver in solver.py but operating on (N, 3)
    arrays for emission, radiosity, and reflectance.
    """

    def solve(
        self,
        patches: List[Surface],
        form_factors: np.ndarray,
        direct_illuminance_rgb: Dict[str, Tuple[float, float, float]],
        reflectance_rgb: np.ndarray,
        max_iters: int = 100,
        tol: float = 1e-3,
        damping: float = 1.0,
    ) -> SpectralRadiosityResult:
        """
        Progressive shooting on 3 channels simultaneously.
        """
        from luxera.engine.radiosity.solver import SolverStatus

        n = len(patches)
        B = np.zeros((n, 3), dtype=float)
        unshot = np.zeros((n, 3), dtype=float)
        areas = np.array([max(float(p.area), 1e-12) for p in patches], dtype=float)

        for i, p in enumerate(patches):
            pid = str(p.id).split("__patch_", 1)[0]
            direct_rgb = np.array(direct_illuminance_rgb.get(pid, (0.0, 0.0, 0.0)), dtype=float)
            B[i, :] = np.clip(reflectance_rgb[i, :] * direct_rgb, 0.0, None)
            unshot[i, :] = B[i, :]

        alpha = max(0.0, min(1.0, float(damping)))
        warnings: List[str] = []
        if alpha <= 0.0:
            warnings.append("damping<=0 forces static solution; set damping in (0,1].")
            alpha = 1.0

        emitted_rgb = np.sum(B * areas[:, None], axis=0)
        total_emitted = float(np.sum(emitted_rgb))
        residual = 0.0 if total_emitted <= 1e-12 else 1.0
        converged = False
        max_iters = max(1, int(max_iters))
        tol = max(float(tol), 1e-12)

        it = 0
        for it in range(max_iters):
            unshot_flux_rgb = unshot * areas[:, None]
            unshot_flux = np.sum(unshot_flux_rgb, axis=1)
            source_idx = int(np.argmax(unshot_flux))
            source_flux = float(unshot_flux[source_idx])
            if source_flux <= 1e-15:
                residual = 0.0
                converged = True
                break

            if total_emitted > 1e-12:
                residual = float(np.sum(unshot_flux) / total_emitted)
            else:
                residual = 0.0
                converged = True
                break

            if residual <= tol:
                converged = True
                break

            shot = alpha * unshot[source_idx, :]
            unshot[source_idx, :] -= shot

            transfer = form_factors[:, source_idx][:, None]
            delta_irradiance = transfer * shot[None, :]
            delta_radiosity = reflectance_rgb * delta_irradiance
            B += delta_radiosity
            unshot += delta_radiosity

            if not np.all(np.isfinite(B)) or not np.all(np.isfinite(unshot)):
                warnings.append("non-finite spectral radiosity detected; clamped and stopped.")
                B = np.nan_to_num(B, nan=0.0, posinf=0.0, neginf=0.0)
                unshot = np.nan_to_num(unshot, nan=0.0, posinf=0.0, neginf=0.0)
                residual = float("inf")
                break
        else:
            warnings.append("max iterations reached before convergence.")

        remaining_unshot_flux_rgb = np.sum(unshot * areas[:, None], axis=0)
        total_area = float(np.sum(areas))
        if np.any(remaining_unshot_flux_rgb > 0.0) and total_area > 1e-12:
            ambient_irradiance_rgb = remaining_unshot_flux_rgb / total_area
            ambient_delta = reflectance_rgb * ambient_irradiance_rgb[None, :]
            B += ambient_delta
            unshot[:, :] = 0.0
            residual = 0.0 if total_emitted <= 1e-12 else 0.0
            converged = True

        I = form_factors @ B
        illuminance_photopic = 683.0 * (0.2126 * I[:, 0] + 0.7152 * I[:, 1] + 0.0722 * I[:, 2])
        xy = rgb_to_chromaticity_xy(I)
        status = SolverStatus(
            converged=converged,
            iterations=(it + 1) if n > 0 else 0,
            residual=float(residual),
            warnings=warnings,
        )
        return SpectralRadiosityResult(
            radiosity_rgb=B,
            irradiance_rgb=I,
            illuminance_photopic=illuminance_photopic,
            chromaticity_xy=xy,
            status=status,
            energy_rgb=emitted_rgb,
        )
