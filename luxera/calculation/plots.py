"""
Illuminance result visualization.

Provides publication-quality plots for lighting calculation results,
including iso-lux contours and false-color renders.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from luxera.calculation.illuminance import IlluminanceResult, CalculationGrid


def plot_isolux(
    result: IlluminanceResult,
    outpath: Path,
    contour_levels: Optional[List[float]] = None,
    show_values: bool = True,
    colormap: str = "YlOrRd",
    title: Optional[str] = None,
) -> Path:
    """
    Create an iso-lux contour plot of illuminance distribution.
    
    Args:
        result: Illuminance calculation result
        outpath: Output file path
        contour_levels: Specific lux levels for contours (auto if None)
        show_values: Show value labels on contours
        colormap: Matplotlib colormap name
        title: Plot title (auto-generated if None)
    
    Returns:
        Path to saved plot
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    
    grid = result.grid
    values = result.values
    
    # Create coordinate arrays
    x = np.linspace(grid.origin.x, grid.origin.x + grid.width, grid.nx)
    y = np.linspace(grid.origin.y, grid.origin.y + grid.height, grid.ny)
    X, Y = np.meshgrid(x, y)
    
    # Determine contour levels
    if contour_levels is None:
        vmin, vmax = result.min_lux, result.max_lux
        if vmax - vmin < 1:
            contour_levels = [vmin, (vmin + vmax) / 2, vmax]
        else:
            # Create nice round number levels
            nice_levels = [50, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000]
            contour_levels = [l for l in nice_levels if vmin < l < vmax]
            if not contour_levels:
                contour_levels = list(np.linspace(vmin, vmax, 8)[1:-1])
    
    # Filled contours for background
    cf = ax.contourf(X, Y, values, levels=50, cmap=colormap, alpha=0.9)
    
    # Line contours
    cs = ax.contour(X, Y, values, levels=contour_levels, colors='black', linewidths=1)
    
    if show_values:
        ax.clabel(cs, inline=True, fontsize=9, fmt='%.0f lx')
    
    # Colorbar
    cbar = fig.colorbar(cf, ax=ax, label='Illuminance (lux)', pad=0.02)
    
    # Labels
    ax.set_xlabel('X (m)', fontsize=11)
    ax.set_ylabel('Y (m)', fontsize=11)
    ax.set_aspect('equal')
    
    if title is None:
        title = (f"Illuminance Distribution\n"
                f"Eavg={result.mean_lux:.0f} lx, Emin={result.min_lux:.0f} lx, "
                f"Emax={result.max_lux:.0f} lx, U₀={result.uniformity_ratio:.2f}")
    ax.set_title(title, fontsize=12, fontweight='bold')
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    
    return outpath


def plot_false_color(
    result: IlluminanceResult,
    outpath: Path,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    colormap: str = "jet",
    title: Optional[str] = None,
) -> Path:
    """
    Create a false-color illuminance plot.
    
    This style is common in professional lighting software and
    provides an intuitive visualization of light levels.
    
    Args:
        result: Illuminance calculation result
        outpath: Output file path
        vmin: Minimum value for colormap (auto if None)
        vmax: Maximum value for colormap (auto if None)
        colormap: Matplotlib colormap name
        title: Plot title
    
    Returns:
        Path to saved plot
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    
    grid = result.grid
    values = result.values
    
    # Create coordinate arrays
    x = np.linspace(grid.origin.x, grid.origin.x + grid.width, grid.nx)
    y = np.linspace(grid.origin.y, grid.origin.y + grid.height, grid.ny)
    
    if vmin is None:
        vmin = result.min_lux
    if vmax is None:
        vmax = result.max_lux
    
    im = ax.imshow(
        values,
        extent=[x[0], x[-1], y[0], y[-1]],
        origin='lower',
        cmap=colormap,
        vmin=vmin,
        vmax=vmax,
        aspect='equal',
    )
    
    cbar = fig.colorbar(im, ax=ax, label='Illuminance (lux)', pad=0.02)
    
    ax.set_xlabel('X (m)', fontsize=11)
    ax.set_ylabel('Y (m)', fontsize=11)
    
    if title is None:
        title = (f"False Color Illuminance\n"
                f"Eavg={result.mean_lux:.0f} lx, U₀={result.uniformity_ratio:.2f}")
    ax.set_title(title, fontsize=12, fontweight='bold')
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    
    return outpath


def plot_3d_surface(
    result: IlluminanceResult,
    outpath: Path,
    colormap: str = "viridis",
    title: Optional[str] = None,
) -> Path:
    """
    Create a 3D surface plot of illuminance distribution.
    
    Args:
        result: Illuminance calculation result
        outpath: Output file path
        colormap: Matplotlib colormap name
        title: Plot title
    
    Returns:
        Path to saved plot
    """
    from mpl_toolkits.mplot3d import Axes3D
    
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection='3d')
    
    grid = result.grid
    values = result.values
    
    x = np.linspace(grid.origin.x, grid.origin.x + grid.width, grid.nx)
    y = np.linspace(grid.origin.y, grid.origin.y + grid.height, grid.ny)
    X, Y = np.meshgrid(x, y)
    
    surf = ax.plot_surface(X, Y, values, cmap=colormap, alpha=0.9,
                          linewidth=0, antialiased=True)
    
    fig.colorbar(surf, ax=ax, label='Illuminance (lux)', shrink=0.6, pad=0.1)
    
    ax.set_xlabel('X (m)', fontsize=10)
    ax.set_ylabel('Y (m)', fontsize=10)
    ax.set_zlabel('Illuminance (lux)', fontsize=10)
    
    if title is None:
        title = f"3D Illuminance Surface (Eavg={result.mean_lux:.0f} lx)"
    ax.set_title(title, fontsize=12, fontweight='bold')
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    
    return outpath


def plot_room_with_luminaires(
    result: IlluminanceResult,
    luminaire_positions: List[Tuple[float, float]],
    outpath: Path,
    room_width: Optional[float] = None,
    room_length: Optional[float] = None,
) -> Path:
    """
    Create a plan view showing luminaire positions and iso-lux contours.
    
    Args:
        result: Illuminance calculation result
        luminaire_positions: List of (x, y) positions
        outpath: Output file path
        room_width: Room width (auto from grid if None)
        room_length: Room length (auto from grid if None)
    
    Returns:
        Path to saved plot
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    
    grid = result.grid
    values = result.values
    
    x = np.linspace(grid.origin.x, grid.origin.x + grid.width, grid.nx)
    y = np.linspace(grid.origin.y, grid.origin.y + grid.height, grid.ny)
    X, Y = np.meshgrid(x, y)
    
    # Iso-lux contours
    cf = ax.contourf(X, Y, values, levels=30, cmap='YlOrRd', alpha=0.8)
    cs = ax.contour(X, Y, values, levels=8, colors='black', linewidths=0.5)
    ax.clabel(cs, inline=True, fontsize=8, fmt='%.0f')
    
    # Luminaire positions
    for i, (lx, ly) in enumerate(luminaire_positions):
        ax.plot(lx, ly, 'ko', markersize=12, markerfacecolor='yellow',
               markeredgewidth=2)
        ax.annotate(f'L{i+1}', (lx, ly), textcoords="offset points",
                   xytext=(5, 5), fontsize=9)
    
    # Room outline
    if room_width and room_length:
        rect = plt.Rectangle((0, 0), room_width, room_length,
                             fill=False, edgecolor='black', linewidth=2)
        ax.add_patch(rect)
    
    cbar = fig.colorbar(cf, ax=ax, label='Illuminance (lux)', pad=0.02)
    
    ax.set_xlabel('X (m)', fontsize=11)
    ax.set_ylabel('Y (m)', fontsize=11)
    ax.set_aspect('equal')
    ax.set_title(f"Room Layout with Illuminance\n"
                f"Eavg={result.mean_lux:.0f} lx, U₀={result.uniformity_ratio:.2f}",
                fontsize=12, fontweight='bold')
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    
    return outpath


def generate_calculation_report(
    result: IlluminanceResult,
    outdir: Path,
    stem: str = "calculation",
    luminaire_positions: Optional[List[Tuple[float, float]]] = None,
) -> dict:
    """
    Generate all standard calculation plots.
    
    Args:
        result: Illuminance calculation result
        outdir: Output directory
        stem: Filename stem
        luminaire_positions: Optional luminaire positions for layout plot
    
    Returns:
        Dictionary of plot paths
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    paths = {
        'isolux': plot_isolux(result, outdir / f"{stem}_isolux.png"),
        'false_color': plot_false_color(result, outdir / f"{stem}_false_color.png"),
        'surface_3d': plot_3d_surface(result, outdir / f"{stem}_3d.png"),
    }
    
    if luminaire_positions:
        paths['room_layout'] = plot_room_with_luminaires(
            result, 
            luminaire_positions,
            outdir / f"{stem}_room.png"
        )
    
    return paths
