from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from luxera.engine.radiosity.form_factors import FormFactorConfig, build_form_factor_matrix
from luxera.geometry.bvh import BVHNode, build_bvh, triangulate_surfaces
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
    """Create radiosity patches, subdividing polygons larger than patch_max_area."""
    patches: List[Surface] = []
    max_area = max(float(patch_max_area), 1e-6)
    for s in surfaces:
        if s.polygon.get_area() > max_area:
            polys = s.polygon.subdivide(max_area)
        else:
            polys = [s.polygon]
        for poly in polys:
            patches.append(Surface(id=f"{s.id}__patch_{len(patches)}", polygon=poly, material=s.material))
    return patches


def _energy(radiosity: np.ndarray, irradiance: np.ndarray, areas: np.ndarray, refl: np.ndarray, emission: np.ndarray) -> EnergyAccounting:
    """Compute energy accounting terms from final radiosity state."""
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
    """
    Solve radiosity using progressive refinement (shooting method).

    Uses diffuse energy balance:
        B_i = E_i + rho_i * sum_j(F_ij * B_j)

    Progressive refinement tracks unshot radiosity and repeatedly shoots the
    patch with highest unshot flux until residual unshot energy falls below tolerance.

    Note on `emission` in this implementation:
    `direct_illuminance` is treated as precomputed direct incident irradiance per
    parent surface. For interreflection solving we initialize emitted radiosity as
    the reflected direct component, `rho * E_direct`, per patch. This is a
    workflow-specific approximation (not a full luminaire-emitter radiosity setup).
    """
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
    bvh: Optional[BVHNode] = build_bvh(triangulate_surfaces(surfaces)) if config.use_visibility else None
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
            # Treat direct incident irradiance as source for secondary diffuse bounce.
            emission[i] = E * reflectance[i]

    # Progressive radiosity state.
    # B tracks total radiosity; unshot tracks radiosity yet to be distributed.
    B = emission.copy()
    unshot = emission.copy()
    alpha = max(0.0, min(1.0, float(config.damping)))
    if alpha <= 0.0:
        warnings.append("damping<=0 forces static solution; set damping in (0,1].")
        alpha = 1.0

    total_emitted = float(np.sum(emission * areas))
    residual = 0.0 if total_emitted <= 1e-12 else 1.0
    converged = False
    max_iters = max(1, int(config.max_iters))
    tol = max(float(config.tol), 1e-12)

    it = 0
    for it in range(max_iters):
        unshot_flux = unshot * areas
        source_idx = int(np.argmax(unshot_flux))
        source_flux = float(unshot_flux[source_idx])
        if source_flux <= 1e-15:
            residual = 0.0
            converged = True
            break

        if total_emitted > 1e-12:
            residual = float(np.sum(unshot_flux) / total_emitted)
        else:
            # When there is no emitted energy, system is trivially converged.
            residual = 0.0
            converged = True
            break

        if residual <= tol:
            converged = True
            break

        # Shoot a damped fraction of the source patch unshot radiosity.
        shot = alpha * unshot[source_idx]
        unshot[source_idx] -= shot

        # F @ B convention means column `source_idx` contains transfer from source to all receivers.
        delta_irradiance = F[:, source_idx] * shot
        delta_radiosity = reflectance * delta_irradiance
        B += delta_radiosity
        unshot += delta_radiosity

        if not np.all(np.isfinite(B)) or not np.all(np.isfinite(unshot)):
            warnings.append("non-finite radiosity detected; clamped and stopped.")
            B = np.nan_to_num(B, nan=0.0, posinf=0.0, neginf=0.0)
            unshot = np.nan_to_num(unshot, nan=0.0, posinf=0.0, neginf=0.0)
            residual = float("inf")
            break
    else:
        warnings.append("max iterations reached before convergence.")

    # Ambient catch-up: distribute residual unshot flux as uniform irradiance.
    # TODO: replace with geometry-aware residual redistribution for non-convex scenes.
    remaining_unshot_flux = float(np.sum(unshot * areas))
    total_area = float(np.sum(areas))
    if remaining_unshot_flux > 0.0 and total_area > 1e-12:
        ambient_irradiance = remaining_unshot_flux / total_area
        ambient_delta = reflectance * ambient_irradiance
        B += ambient_delta
        unshot[:] = 0.0
        residual = 0.0 if total_emitted <= 1e-12 else float(max(0.0, residual))

    I = F @ B
    e = _energy(B, I, areas, reflectance, emission)
    denom = max(e.total_emitted, 1e-9)
    balance_error = abs(e.total_emitted - (e.total_absorbed + e.total_reflected)) / denom
    if balance_error > 0.05:
        warnings.append(f"energy conservation error exceeds 5% ({100.0 * balance_error:.2f}%).")

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
