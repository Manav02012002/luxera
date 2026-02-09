from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def write_surface_heatmaps(out_dir: Path, surface_illuminance: Dict[str, float]) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for surface_id, value in surface_illuminance.items():
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.imshow([[value]], cmap="inferno")
        ax.set_title(surface_id)
        ax.set_xticks([])
        ax.set_yticks([])
        out_path = out_dir / f"{surface_id}_heatmap.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        out[surface_id] = out_path
    return out
