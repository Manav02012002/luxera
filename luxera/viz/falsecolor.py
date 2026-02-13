from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from luxera.metrics.core import compute_basic_metrics
from luxera.viz.contours import compute_contour_levels


def render_falsecolor_plane(
    *,
    values: np.ndarray,
    nx: int,
    ny: int,
    out_path: Path,
    title: str = "False Colour",
    with_contours: bool = True,
) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size != int(nx) * int(ny):
        raise ValueError(f"values size {arr.size} does not match nx*ny={int(nx)*int(ny)}")
    grid = arr.reshape(int(ny), int(nx))
    m = compute_basic_metrics(arr.tolist())

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    im = ax.imshow(grid, cmap="inferno", origin="lower", aspect="auto")
    if with_contours:
        levels = compute_contour_levels(grid, n_levels=8)
        if len(levels) >= 2:
            cs = ax.contour(grid, levels=levels, colors="white", linewidths=0.6, alpha=0.7)
            ax.clabel(cs, fmt="%.1f", fontsize=7)
    ax.set_title(title)
    ax.set_xlabel("X index")
    ax.set_ylabel("Y index")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("lux")
    fig.text(
        0.01,
        0.01,
        f"min={m.E_min:.2f}  avg={m.E_avg:.2f}  max={m.E_max:.2f}  U0={m.U0:.3f}",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path

