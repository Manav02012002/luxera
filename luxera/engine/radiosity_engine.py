from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from luxera.calculation.radiosity import RadiositySettings, RadiositySolver
from luxera.geometry.core import Room
from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance


@dataclass(frozen=True)
class RadiosityEngineResult:
    avg_illuminance: float
    total_flux: float
    iterations: int
    converged: bool
    residuals: List[float]
    stop_reason: str
    surface_illuminance: Dict[str, float]
    floor_values: List[float]


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

    solver = RadiositySolver(settings)
    result = solver.solve(surfaces, direct_illuminance)

    surface_ill = {s.id: s.illuminance for s in result.surfaces}
    floor_values: List[float] = []
    for p in result.patches:
        if "floor" in p.parent_surface.id.lower():
            floor_values.append(p.irradiance)

    return RadiosityEngineResult(
        avg_illuminance=result.avg_illuminance,
        total_flux=result.total_flux,
        iterations=result.iterations,
        converged=result.converged,
        residuals=result.residuals,
        stop_reason=result.stop_reason,
        surface_illuminance=surface_ill,
        floor_values=floor_values,
    )
