from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")  # headless-safe for servers/CI
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import numpy as np  # noqa: E402

from luxera.parser.ies_parser import ParsedIES


@dataclass(frozen=True)
class PlotPaths:
    intensity_png: Path
    polar_png: Path
    heatmap_png: Optional[Path] = None


def _ensure_outdir(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)


def _choose_plane_indices(horizontal_deg: Sequence[float], max_planes: int = 4) -> List[int]:
    """
    Pick up to max_planes horizontal planes spaced across available angles.
    Deterministic: first, last, and evenly spaced in-between.
    """
    H = len(horizontal_deg)
    if H <= max_planes:
        return list(range(H))
    # choose indices spaced roughly evenly
    idxs = [0]
    for k in range(1, max_planes - 1):
        idxs.append(round(k * (H - 1) / (max_planes - 1)))
    idxs.append(H - 1)
    # unique + sorted
    return sorted(set(int(i) for i in idxs))


def _nearest_plane_index(horizontal_deg: Sequence[float], target_deg: float) -> int:
    if not horizontal_deg:
        raise ValueError("No horizontal angles available")
    target = float(target_deg) % 360.0
    best_i = 0
    best_d = float("inf")
    for i, h in enumerate(horizontal_deg):
        hv = float(h) % 360.0
        d = abs(hv - target)
        d = min(d, 360.0 - d)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _nearest_angle_value(horizontal_deg: Sequence[float], target_deg: float) -> float:
    return float(horizontal_deg[_nearest_plane_index(horizontal_deg, target_deg)])


def _resolve_polar_plane_pairs(
    horizontal_deg: Sequence[float],
    horizontal_plane_deg: Optional[float] = None,
) -> List[Tuple[float, float]]:
    if not horizontal_deg:
        raise ValueError("No horizontal angles available")
    if horizontal_plane_deg is not None:
        primary = _nearest_angle_value(horizontal_deg, float(horizontal_plane_deg))
        opposite = _nearest_angle_value(horizontal_deg, (primary + 180.0) % 360.0)
        return [(primary, opposite)]
    planes: List[Tuple[float, float]] = []
    hvals = [float(v) for v in horizontal_deg]
    if any(abs(v - 0.0) < 0.5 for v in hvals):
        planes.append((0.0, _nearest_angle_value(horizontal_deg, 180.0)))
    if any(abs(v - 90.0) < 0.5 for v in hvals):
        planes.append((90.0, _nearest_angle_value(horizontal_deg, 270.0)))
    if not planes:
        v0 = float(horizontal_deg[0])
        planes = [(v0, _nearest_angle_value(horizontal_deg, (v0 + 180.0) % 360.0))]
    return planes


def plot_intensity_curves(
    doc: ParsedIES,
    outpath: Path,
    plane_indices: Optional[Iterable[int]] = None,
    horizontal_plane_deg: Optional[float] = None,
) -> Path:
    """
    Save a line plot: candela (scaled) vs vertical angle, for selected horizontal planes.
    """
    if doc.angles is None or doc.candela is None:
        raise ValueError("Need angles + candela to plot intensity curves")

    v = doc.angles.vertical_deg
    h = doc.angles.horizontal_deg
    H = len(h)

    if horizontal_plane_deg is not None:
        plane_indices = [_nearest_plane_index(h, float(horizontal_plane_deg))]
    elif plane_indices is None:
        plane_indices = _choose_plane_indices(h, max_planes=4)

    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(list(plane_indices))))
    
    for i, hi in enumerate(plane_indices):
        if hi < 0 or hi >= H:
            continue
        y = doc.candela.values_cd_scaled[hi]
        ax.plot(v, y, label=f"C{h[hi]:g}°", linewidth=2, color=colors[i])

    ax.set_xlabel("Vertical Angle γ (degrees)", fontsize=11)
    ax.set_ylabel("Luminous Intensity (cd)", fontsize=11)
    ax.set_title("Intensity Distribution", fontsize=12, fontweight='bold')
    ax.legend(loc="best", framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(v[0], v[-1])
    ax.set_ylim(bottom=0)
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    return outpath


def plot_polar_photometric(
    doc: ParsedIES, 
    outpath: Path, 
    planes: Optional[List[Tuple[float, float]]] = None,
    horizontal_plane_deg: Optional[float] = None,
) -> Path:
    """
    Save a proper photometric polar plot.
    
    Standard photometric polar plots show:
    - 0° at bottom (nadir)
    - 90° horizontal (to the sides)
    - 180° at top (zenith)
    
    Typically shows C0-C180 plane and C90-C270 plane overlaid.
    
    Args:
        doc: Parsed IES document
        outpath: Output path for PNG
        planes: List of (C_angle, opposite_C_angle) pairs to plot.
                Default is [(0, 180), (90, 270)] if available.
    """
    if doc.angles is None or doc.candela is None:
        raise ValueError("Need angles + candela to plot polar plot")

    v_deg = doc.angles.vertical_deg
    h_deg = doc.angles.horizontal_deg
    candela = doc.candela.values_cd_scaled
    
    # Find indices for requested planes
    def find_plane_index(target: float) -> Optional[int]:
        for i, h in enumerate(h_deg):
            if abs(h - target) < 0.5:
                return i
        return None
    
    # Default planes: C0-C180 and C90-C270, or nearest selected horizontal plane pair.
    if planes is None:
        planes = _resolve_polar_plane_pairs(h_deg, horizontal_plane_deg=horizontal_plane_deg)
    
    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection='polar')
    
    # Set up polar plot with 0° at bottom (nadir)
    ax.set_theta_zero_location('S')  # South = bottom
    ax.set_theta_direction(-1)  # Clockwise
    
    colors = ['#2E86AB', '#E94F37', '#A23B72', '#F18F01']
    
    max_intensity = 0
    
    for plane_idx, (c_angle, c_opposite) in enumerate(planes):
        idx1 = find_plane_index(c_angle)
        idx2 = find_plane_index(c_opposite)
        
        if idx1 is None:
            continue
        
        color = colors[plane_idx % len(colors)]
        
        # Plot the primary half (0° to 180° vertical on one side)
        theta1 = [math.radians(v) for v in v_deg]
        r1 = candela[idx1]
        ax.plot(theta1, r1, color=color, linewidth=2, 
                label=f'C{c_angle}°-C{c_opposite}°')
        max_intensity = max(max_intensity, max(r1))
        
        # Plot the opposite half if different plane exists
        if idx2 is not None and idx2 != idx1:
            # Mirror the angles to the other side
            theta2 = [math.radians(360 - v) for v in v_deg]
            r2 = candela[idx2]
            ax.plot(theta2, r2, color=color, linewidth=2)
            max_intensity = max(max_intensity, max(r2))
        elif idx1 is not None:
            # Same plane both sides (symmetric) - mirror
            theta2 = [math.radians(360 - v) for v in v_deg]
            r2 = candela[idx1]
            ax.plot(theta2, r2, color=color, linewidth=2, linestyle='--', alpha=0.7)
    
    # Configure axes
    ax.set_rlabel_position(45)
    ax.set_title("Polar Intensity Distribution", fontsize=12, fontweight='bold', pad=20)
    
    # Set sensible angle labels
    ax.set_thetagrids([0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330])
    
    # Add nadir/zenith/horizontal labels
    ax.annotate('Nadir (0°)', xy=(math.radians(0), max_intensity * 0.15), 
                ha='center', fontsize=9, color='gray')
    ax.annotate('90°', xy=(math.radians(90), max_intensity * 1.05), 
                ha='center', fontsize=9, color='gray')
    ax.annotate('180°', xy=(math.radians(180), max_intensity * 0.15), 
                ha='center', fontsize=9, color='gray')
    ax.annotate('270°', xy=(math.radians(270), max_intensity * 1.05), 
                ha='center', fontsize=9, color='gray')
    
    ax.legend(loc='upper right', bbox_to_anchor=(1.15, 1.0))
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    return outpath


def plot_candela_heatmap(doc: ParsedIES, outpath: Path) -> Path:
    """
    Save a heatmap of candela values across all angles.
    
    X-axis: Horizontal angle (C-plane)
    Y-axis: Vertical angle (gamma)
    Color: Intensity (candela)
    """
    if doc.angles is None or doc.candela is None:
        raise ValueError("Need angles + candela to plot heatmap")
    
    v_deg = doc.angles.vertical_deg
    h_deg = doc.angles.horizontal_deg
    candela = doc.candela.values_cd_scaled
    
    # Convert to numpy array for plotting
    # candela is [H][V], we want [V][H] for imshow with V on y-axis
    data = np.array(candela).T  # Shape: [V, H]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Create heatmap
    im = ax.imshow(
        data,
        aspect='auto',
        origin='lower',
        cmap='inferno',
        extent=[h_deg[0], h_deg[-1], v_deg[0], v_deg[-1]],
    )
    
    # Add colorbar
    cbar = fig.colorbar(im, ax=ax, label='Luminous Intensity (cd)', pad=0.02)
    
    ax.set_xlabel('Horizontal Angle C (degrees)', fontsize=11)
    ax.set_ylabel('Vertical Angle γ (degrees)', fontsize=11)
    ax.set_title('Candela Distribution Heatmap', fontsize=12, fontweight='bold')
    
    # Add contour lines
    H_mesh, V_mesh = np.meshgrid(h_deg, v_deg)
    contours = ax.contour(H_mesh, V_mesh, data, colors='white', alpha=0.5, linewidths=0.5)
    ax.clabel(contours, inline=True, fontsize=8, fmt='%.0f')
    
    fig.tight_layout()
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)
    return outpath


def plot_polar(doc: ParsedIES, outpath: Path, plane_indices: Optional[Iterable[int]] = None) -> Path:
    """
    Legacy polar plot function - now calls the improved photometric polar plot.
    Kept for backward compatibility.
    """
    return plot_polar_photometric(doc, outpath)


def save_default_plots(
    doc: ParsedIES,
    outdir: Path,
    stem: str = "luxera_view",
    horizontal_plane_deg: Optional[float] = None,
) -> PlotPaths:
    """
    Convenience: save all default plots into outdir.
    """
    _ensure_outdir(outdir)
    intensity_png = outdir / f"{stem}_intensity.png"
    polar_png = outdir / f"{stem}_polar.png"
    heatmap_png = outdir / f"{stem}_heatmap.png"

    plot_intensity_curves(doc, intensity_png, horizontal_plane_deg=horizontal_plane_deg)
    plot_polar_photometric(doc, polar_png, horizontal_plane_deg=horizontal_plane_deg)
    plot_candela_heatmap(doc, heatmap_png)

    return PlotPaths(
        intensity_png=intensity_png, 
        polar_png=polar_png,
        heatmap_png=heatmap_png,
    )
