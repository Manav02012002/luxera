from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")  # headless-safe for servers/CI
import matplotlib.pyplot as plt  # noqa: E402

from luxera.parser.ies_parser import ParsedIES


@dataclass(frozen=True)
class PlotPaths:
    intensity_png: Path
    polar_png: Path


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


def plot_intensity_curves(doc: ParsedIES, outpath: Path, plane_indices: Optional[Iterable[int]] = None) -> Path:
    """
    Save a line plot: candela (scaled) vs vertical angle, for selected horizontal planes.
    """
    if doc.angles is None or doc.candela is None:
        raise ValueError("Need angles + candela to plot intensity curves")

    v = doc.angles.vertical_deg
    h = doc.angles.horizontal_deg
    H = len(h)

    if plane_indices is None:
        plane_indices = _choose_plane_indices(h, max_planes=4)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    for hi in plane_indices:
        if hi < 0 or hi >= H:
            continue
        y = doc.candela.values_cd_scaled[hi]
        ax.plot(v, y, label=f"H={h[hi]:g}°")

    ax.set_xlabel("Vertical angle (deg)")
    ax.set_ylabel("Candela (cd)")
    ax.set_title("Intensity curves (candela vs vertical angle)")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)
    return outpath


def plot_polar(doc: ParsedIES, outpath: Path, plane_indices: Optional[Iterable[int]] = None) -> Path:
    """
    Save a polar plot: intensity vs vertical angle, for selected horizontal planes.
    Uses polar axes with theta = vertical angle (in radians).
    """
    if doc.angles is None or doc.candela is None:
        raise ValueError("Need angles + candela to plot polar plot")

    v_deg = doc.angles.vertical_deg
    h_deg = doc.angles.horizontal_deg
    H = len(h_deg)

    if plane_indices is None:
        plane_indices = _choose_plane_indices(h_deg, max_planes=4)

    # Convert vertical angles to radians for polar plotting
    import math
    theta = [math.radians(x) for x in v_deg]

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="polar")
    for hi in plane_indices:
        if hi < 0 or hi >= H:
            continue
        r = doc.candela.values_cd_scaled[hi]
        ax.plot(theta, r, label=f"H={h_deg[hi]:g}°")

    ax.set_title("Polar intensity plot (theta = vertical angle)")
    ax.legend(loc="best", bbox_to_anchor=(1.15, 1.05))
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)
    return outpath


def save_default_plots(doc: ParsedIES, outdir: Path, stem: str = "luxera_view") -> PlotPaths:
    """
    Convenience: save both default plots into outdir.
    """
    _ensure_outdir(outdir)
    intensity_png = outdir / f"{stem}_intensity.png"
    polar_png = outdir / f"{stem}_polar.png"

    plot_intensity_curves(doc, intensity_png)
    plot_polar(doc, polar_png)

    return PlotPaths(intensity_png=intensity_png, polar_png=polar_png)
