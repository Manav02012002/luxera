from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from luxera.calculation.radiosity import BVHNode, build_bvh
from luxera.engine.radiosity.form_factors import FormFactorConfig, build_form_factor_matrix
from luxera.geometry.core import Surface


@dataclass(frozen=True)
class SolverStatus:
    converged: bool
    iterations: int
    residual: float
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class EnergyAccounting:
    total_emitted: float
    total_absorbed: float
    total_reflected: float
    total_exitance: float


@dataclass(frozen=True)
class RadiosityConfig:
    max_iters: int = 100
    tol: float = 1e-3
    damping: float = 1.0
    patch_max_area: float = 0.5
    use_visibility: bool = True
    form_factor_method: str = "monte_carlo"
    monte_carlo_samples: int = 16
    seed: int = 0


@dataclass(frozen=True)
class RadiositySolveResult:
    patches: List[Surface]
    form_factors: np.ndarray
    status: SolverStatus
    energy: EnergyAccounting
    radiosity: np.ndarray
    irradiance: np.ndarray


def _create_patch_surfaces(surfaces: List[Surface], patch_max_area: float) -> List[Surface]:
    patches: List[Surface] = []
    for s in surfaces:
        for poly in s.polygon.subdivide(max(float(patch_max_area), 1e-6)):
            patches.append(Surface(id=f"{s.id}__patch_{len(patches)}", polygon=poly, material=s.material))
    return patches


def _energy(radiosity: np.ndarray, irradiance: np.ndarray, areas: np.ndarray, refl: np.ndarray, emission: np.ndarray) -> EnergyAccounting:
    return EnergyAccounting(
        total_emitted=float(np.sum(emission * areas)),
        total_absorbed=float(np.sum((1.0 - refl) * irradiance * areas)),
        total_reflected=float(np.sum(refl * irradiance * areas)),
        total_exitance=float(np.sum(radiosity * areas)),
    )


def solve_radiosity(
    surfaces: List[Surface],
    direct_illuminance: Optional[Dict[str, float]],
    *,
    config: RadiosityConfig,
) -> RadiositySolveResult:
    if not surfaces:
        empty = np.zeros((0, 0), dtype=float)
        z = np.zeros((0,), dtype=float)
        return RadiositySolveResult(
            patches=[],
            form_factors=empty,
            status=SolverStatus(converged=True, iterations=0, residual=0.0, warnings=[]),
            energy=EnergyAccounting(0.0, 0.0, 0.0, 0.0),
            radiosity=z,
            irradiance=z,
        )

    warnings: List[str] = []
    patches = _create_patch_surfaces(surfaces, config.patch_max_area)
    rng = np.random.default_rng(int(config.seed))
    bvh: Optional[BVHNode] = build_bvh(surfaces) if config.use_visibility else None
    F = build_form_factor_matrix(
        patches,
        surfaces,
        config=FormFactorConfig(
            method="analytic" if str(config.form_factor_method).lower().startswith("an") else "monte_carlo",
            use_visibility=bool(config.use_visibility),
            monte_carlo_samples=int(config.monte_carlo_samples),
        ),
        rng=rng,
        bvh=bvh,
    )

    n = len(patches)
    areas = np.array([max(p.area, 1e-12) for p in patches], dtype=float)
    reflectance = np.array([max(0.0, min(1.0, p.material.reflectance)) for p in patches], dtype=float)
    emission = np.zeros((n,), dtype=float)
    if direct_illuminance:
        for i, p in enumerate(patches):
            pid = str(p.id).split("__patch_", 1)[0]
            E = float(direct_illuminance.get(pid, 0.0))
            # diffuse-only radiosity for inter-reflections
            emission[i] = E * reflectance[i]

    B = emission.copy()
    alpha = max(0.0, min(1.0, float(config.damping)))
    if alpha <= 0.0:
        warnings.append("damping<=0 forces static solution; set damping in (0,1].")
        alpha = 1.0

    residual = 0.0
    converged = False
    max_iters = max(1, int(config.max_iters))
    tol = max(float(config.tol), 1e-12)
    I = F @ B
    for it in range(max_iters):
        candidate = emission + reflectance * (F @ B)
        if not np.all(np.isfinite(candidate)):
            warnings.append("non-finite radiosity detected; clamped and stopped.")
            candidate = np.nan_to_num(candidate, nan=0.0, posinf=0.0, neginf=0.0)
            B = candidate
            I = F @ B
            residual = float("inf")
            break
        B_next = ((1.0 - alpha) * B) + (alpha * candidate)
        residual = float(np.max(np.abs(B_next - B)))
        B = B_next
        I = F @ B

        e = _energy(B, I, areas, reflectance, emission)
        if e.total_exitance > max(1.0, 10.0 * max(e.total_emitted, 1e-9)):
            warnings.append("energy blow-up detected; stopping at stability cap.")
            break
        if residual <= tol:
            converged = True
            break
    else:
        warnings.append("max iterations reached before convergence.")

    status = SolverStatus(
        converged=converged,
        iterations=(it + 1) if n > 0 else 0,
        residual=float(residual),
        warnings=warnings,
    )
    return RadiositySolveResult(
        patches=patches,
        form_factors=F,
        status=status,
        energy=_energy(B, I, areas, reflectance, emission),
        radiosity=B,
        irradiance=I,
    )

