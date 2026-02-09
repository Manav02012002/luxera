from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def write_grid_heatmap_and_isolux(
    out_dir: Path,
    points: np.ndarray,
    values: np.ndarray,
    nx: int,
    ny: int,
) -> Dict[str, Path]:
    """
    Write direct-grid visualization artifacts:
    - heatmap
    - isolux contour plot
    """
    out: Dict[str, Path] = {}
    if nx <= 0 or ny <= 0:
        return out
    if points.shape[0] != nx * ny or values.shape[0] != nx * ny:
        return out

    x = points[:, 0].reshape(ny, nx)
    y = points[:, 1].reshape(ny, nx)
    z = values.reshape(ny, nx)

    # Heatmap
    fig_h, ax_h = plt.subplots(figsize=(6, 4))
    xmin = float(np.min(x))
    xmax = float(np.max(x))
    ymin = float(np.min(y))
    ymax = float(np.max(y))
    if abs(xmax - xmin) < 1e-12:
        xmin -= 0.5
        xmax += 0.5
    if abs(ymax - ymin) < 1e-12:
        ymin -= 0.5
        ymax += 0.5

    im = ax_h.imshow(
        z,
        origin="lower",
        extent=[xmin, xmax, ymin, ymax],
        aspect="auto",
        cmap="inferno",
    )
    ax_h.set_title("Illuminance Heatmap (lux)")
    ax_h.set_xlabel("X (m)")
    ax_h.set_ylabel("Y (m)")
    cbar = fig_h.colorbar(im, ax=ax_h)
    cbar.set_label("lux")
    heatmap_path = out_dir / "grid_heatmap.png"
    fig_h.tight_layout()
    fig_h.savefig(heatmap_path, dpi=150, bbox_inches="tight")
    plt.close(fig_h)
    out["heatmap"] = heatmap_path

    # Isolux contour (requires at least 2x2 grid for contouring)
    if nx >= 2 and ny >= 2:
        fig_c, ax_c = plt.subplots(figsize=(6, 4))
        vmin = float(np.min(z))
        vmax = float(np.max(z))
        if abs(vmax - vmin) < 1e-9:
            levels = np.array([vmin])
        else:
            levels = np.linspace(vmin, vmax, 10)
        cs = ax_c.contour(x, y, z, levels=levels, linewidths=1.0)
        ax_c.clabel(cs, inline=True, fontsize=8, fmt="%.0f")
        ax_c.set_title("Isolux Contours (lux)")
        ax_c.set_xlabel("X (m)")
        ax_c.set_ylabel("Y (m)")
        contour_path = out_dir / "grid_isolux.png"
        fig_c.tight_layout()
        fig_c.savefig(contour_path, dpi=150, bbox_inches="tight")
        plt.close(fig_c)
        out["isolux"] = contour_path

    return out
