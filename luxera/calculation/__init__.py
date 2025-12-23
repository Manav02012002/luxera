"""
Luxera Calculation Module

This module provides illuminance and photometric calculations,
including direct illuminance, inter-reflections via radiosity,
and result visualization.
"""

from luxera.calculation.illuminance import (
    Point3D,
    Luminaire,
    CalculationGrid,
    IlluminanceResult,
    calculate_direct_illuminance,
    calculate_grid_illuminance,
    create_room_luminaire_layout,
    quick_room_calculation,
    interpolate_candela,
)

from luxera.calculation.radiosity import (
    RadiosityMethod,
    RadiositySettings,
    RadiositySolver,
    RadiosityResult,
    Patch,
    compute_form_factor_analytic,
    calculate_room_lighting,
)

from luxera.calculation.plots import (
    plot_isolux,
    plot_false_color,
    plot_3d_surface,
    plot_room_with_luminaires,
    generate_calculation_report,
)

__all__ = [
    # Illuminance
    "Point3D",
    "Luminaire",
    "CalculationGrid",
    "IlluminanceResult",
    "calculate_direct_illuminance",
    "calculate_grid_illuminance",
    "create_room_luminaire_layout",
    "quick_room_calculation",
    "interpolate_candela",
    # Radiosity
    "RadiosityMethod",
    "RadiositySettings",
    "RadiositySolver",
    "RadiosityResult",
    "Patch",
    "compute_form_factor_analytic",
    "calculate_room_lighting",
    # Plotting
    "plot_isolux",
    "plot_false_color",
    "plot_3d_surface",
    "plot_room_with_luminaires",
    "generate_calculation_report",
]
