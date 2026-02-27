from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/coordinate_conventions.md."""

from dataclasses import dataclass, field
from typing import Dict, List

from luxera.calculation.radiosity import RadiosityMethod, RadiositySettings
from luxera.geometry.core import Room
from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance
from luxera.engine.radiosity.solver import RadiosityConfig, solve_radiosity


@dataclass(frozen=True)
class RadiosityEngineResult:
    avg_illuminance: float
    total_flux: float
    iterations: int
    converged: bool
    residuals: List[float]
    energy_balance_history: List[float]
    stop_reason: str
    surface_illuminance: Dict[str, float]
    floor_values: List[float]
    solver_status: Dict[str, object] = field(default_factory=dict)
    energy: Dict[str, float] = field(default_factory=dict)


def run_radiosity(
    room: Room,
    luminaires: List[Luminaire],
    settings: RadiositySettings,
) -> RadiosityEngineResult:
    surfaces = room.get_surfaces()
    direct_illuminance: Dict[str, float] = {}

    for surface in surfaces:
        centroid = surface.centroid
        normal = surface.normal
        total_E = 0.0
        for luminaire in luminaires:
            total_E += calculate_direct_illuminance(centroid, normal, luminaire)
        direct_illuminance[surface.id] = total_E

    cfg = RadiosityConfig(
        max_iters=int(getattr(settings, "max_iterations", 100)),
        tol=float(getattr(settings, "convergence_threshold", 1e-3)),
        damping=float(getattr(settings, "damping", 1.0)),
        patch_max_area=float(getattr(settings, "patch_max_area", 0.5)),
        use_visibility=bool(getattr(settings, "use_visibility", True)),
        form_factor_method=("analytic" if settings.method == RadiosityMethod.MATRIX else "monte_carlo"),
        monte_carlo_samples=int(getattr(settings, "monte_carlo_samples", 16)),
        seed=int(getattr(settings, "seed", 0)),
    )
    solve = solve_radiosity(surfaces, direct_illuminance, config=cfg)

    # Aggregate patch data back to parent surfaces.
    by_surface_num: Dict[str, float] = {}
    by_surface_den: Dict[str, float] = {}
    floor_values: List[float] = []
    for i, patch in enumerate(solve.patches):
        sid = patch.id.split("__patch_", 1)[0]
        irr = float(solve.irradiance[i]) if i < len(solve.irradiance) else 0.0
        by_surface_num[sid] = by_surface_num.get(sid, 0.0) + irr * patch.area
        by_surface_den[sid] = by_surface_den.get(sid, 0.0) + patch.area
        if "floor" in sid.lower():
            floor_values.append(irr)
    surface_ill = {
        sid: (by_surface_num[sid] / by_surface_den[sid]) if by_surface_den.get(sid, 0.0) > 1e-12 else 0.0
        for sid in by_surface_num
    }
    avg_floor = float(sum(floor_values) / len(floor_values)) if floor_values else 0.0

    return RadiosityEngineResult(
        avg_illuminance=avg_floor,
        total_flux=float(solve.energy.total_exitance),
        iterations=int(solve.status.iterations),
        converged=bool(solve.status.converged),
        residuals=[float(solve.status.residual)],
        energy_balance_history=[float(solve.energy.total_exitance - solve.energy.total_emitted)],
        stop_reason=("converged" if solve.status.converged else "max_iterations"),
        surface_illuminance=surface_ill,
        floor_values=floor_values,
        solver_status={
            "converged": bool(solve.status.converged),
            "iterations": int(solve.status.iterations),
            "residual": float(solve.status.residual),
            "warnings": list(solve.status.warnings),
        },
        energy={
            "total_emitted": float(solve.energy.total_emitted),
            "total_absorbed": float(solve.energy.total_absorbed),
            "total_reflected": float(solve.energy.total_reflected),
            "total_exitance": float(solve.energy.total_exitance),
        },
    )


__all__ = [
    "RadiosityEngineResult",
    "RadiosityMethod",
    "RadiositySettings",
    "run_radiosity",
]
