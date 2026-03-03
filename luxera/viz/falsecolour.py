from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

from luxera.metrics.core import compute_basic_metrics


class FalseColourRenderer:
    """
    Generate false-colour illuminance visualisations using matplotlib.
    """

    COLOUR_SCALES = {
        "jet": "standard rainbow (not recommended for accessibility)",
        "viridis": "perceptually uniform (default, accessible)",
        "plasma": "warm tones, good for illuminance",
        "luxera": "custom scale matching industry convention",
    }

    def __init__(self, colour_scale: str = "viridis", vmin: float = 0, vmax: float = 1000):
        self.cmap_name = str(colour_scale)
        self.vmin = float(vmin)
        self.vmax = float(vmax)

    def _resolve_cmap(self):
        if self.cmap_name == "luxera":
            return self._custom_luxera_cmap()
        return plt.get_cmap(self.cmap_name)

    def render_grid_heatmap(
        self,
        grid_values: np.ndarray,
        grid_origin: Tuple[float, float],
        grid_width: float,
        grid_height: float,
        title: str = "Illuminance (lux)",
        show_values: bool = False,
        contour_levels: Optional[List[float]] = None,
    ) -> Figure:
        vals = np.asarray(grid_values, dtype=float)
        if vals.ndim != 2:
            raise ValueError("grid_values must be shape (ny, nx)")

        ny, nx = vals.shape
        ox, oy = float(grid_origin[0]), float(grid_origin[1])
        gx = np.linspace(ox, ox + float(grid_width), nx)
        gy = np.linspace(oy, oy + float(grid_height), ny)
        xg, yg = np.meshgrid(gx, gy)

        fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=160)
        im = ax.imshow(
            vals,
            origin="lower",
            extent=[gx.min(), gx.max(), gy.min(), gy.max()],
            aspect="auto",
            cmap=self._resolve_cmap(),
            vmin=self.vmin,
            vmax=self.vmax,
            interpolation="bilinear",
        )
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("Illuminance (lux)")

        if contour_levels is not None and len(contour_levels) > 0:
            cs = ax.contour(xg, yg, vals, levels=contour_levels, colors="black", linewidths=0.8, alpha=0.75)
            ax.clabel(cs, fmt="%.0f", fontsize=7)

        if show_values and nx * ny <= 100:
            for j in range(ny):
                for i in range(nx):
                    ax.text(xg[j, i], yg[j, i], f"{vals[j, i]:.0f}", ha="center", va="center", fontsize=6, color="black")

        rect = plt.Rectangle((ox, oy), float(grid_width), float(grid_height), fill=False, edgecolor="black", linewidth=1.2)
        ax.add_patch(rect)

        stats = compute_basic_metrics(vals.reshape(-1).tolist())
        subtitle = f"E_avg={stats.E_avg:.1f} lux   E_min={stats.E_min:.1f} lux   E_max={stats.E_max:.1f} lux   U0={stats.U0:.3f}"
        ax.set_title(f"{title}\n{subtitle}")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.grid(alpha=0.2)
        fig.tight_layout()
        return fig

    def render_isolux_contours(
        self,
        grid_values: np.ndarray,
        grid_origin: Tuple[float, float],
        grid_width: float,
        grid_height: float,
        levels: Optional[List[float]] = None,
        luminaire_positions: Optional[List[Tuple[float, float]]] = None,
    ) -> Figure:
        vals = np.asarray(grid_values, dtype=float)
        if vals.ndim != 2:
            raise ValueError("grid_values must be shape (ny, nx)")

        ny, nx = vals.shape
        ox, oy = float(grid_origin[0]), float(grid_origin[1])
        gx = np.linspace(ox, ox + float(grid_width), nx)
        gy = np.linspace(oy, oy + float(grid_height), ny)
        xg, yg = np.meshgrid(gx, gy)

        fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=160)

        if not levels:
            eavg = float(np.mean(vals))
            levels = [0.5 * eavg, 0.75 * eavg, eavg, 1.25 * eavg, 1.5 * eavg]
        levels = sorted(float(v) for v in levels)

        cf = ax.contourf(xg, yg, vals, levels=levels, cmap=self._resolve_cmap(), alpha=0.85)
        cs = ax.contour(xg, yg, vals, levels=levels, colors="black", linewidths=0.9)
        ax.clabel(cs, inline=True, fontsize=8, fmt="%.0f")
        cbar = fig.colorbar(cf, ax=ax)
        cbar.set_label("Illuminance (lux)")

        if luminaire_positions:
            lx = [float(p[0]) for p in luminaire_positions]
            ly = [float(p[1]) for p in luminaire_positions]
            ax.scatter(lx, ly, marker="x", s=50, c="white", linewidths=1.3, label="Luminaires")
            ax.legend(loc="upper right", fontsize=8)

        rect = plt.Rectangle((ox, oy), float(grid_width), float(grid_height), fill=False, edgecolor="black", linewidth=1.2)
        ax.add_patch(rect)

        ax.set_title("Iso-lux Contour Plan")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.grid(alpha=0.2)
        fig.tight_layout()
        return fig

    def render_room_3d(
        self,
        room_surfaces: List[Dict],
        luminaire_positions: List[Tuple[float, float, float]],
        grid_values: Optional[np.ndarray] = None,
        grid_points: Optional[np.ndarray] = None,
    ) -> Figure:
        fig = plt.figure(figsize=(9.0, 6.0), dpi=160)
        ax = fig.add_subplot(111, projection="3d")

        cmap = self._resolve_cmap()
        norm = plt.Normalize(vmin=self.vmin, vmax=self.vmax)

        poly_list = []
        face_cols = []
        all_pts: List[np.ndarray] = []
        for s in room_surfaces:
            verts = [tuple(float(v) for v in p) for p in s.get("vertices", [])]
            if len(verts) < 3:
                continue
            all_pts.extend(np.asarray(verts, dtype=float))
            poly_list.append(verts)
            illum = float(s.get("illuminance", 0.0))
            face_cols.append(cmap(norm(illum)))

        if poly_list:
            coll = Poly3DCollection(poly_list, facecolors=face_cols, edgecolors="black", linewidths=0.6, alpha=0.9)
            ax.add_collection3d(coll)

        if luminaire_positions:
            lp = np.asarray(luminaire_positions, dtype=float)
            ax.scatter(lp[:, 0], lp[:, 1], lp[:, 2], c="black", marker="x", s=35, label="Luminaires")

        if grid_values is not None and grid_points is not None:
            gv = np.asarray(grid_values, dtype=float).reshape(-1)
            gp = np.asarray(grid_points, dtype=float)
            if gp.ndim == 2 and gp.shape[1] == 3 and gv.shape[0] == gp.shape[0]:
                ax.scatter(gp[:, 0], gp[:, 1], gp[:, 2], c=gv, cmap=cmap, norm=norm, s=8, alpha=0.6)
                all_pts.extend(gp)

        if all_pts:
            arr = np.asarray(all_pts, dtype=float)
            mins = np.min(arr, axis=0)
            maxs = np.max(arr, axis=0)
            pad = np.maximum((maxs - mins) * 0.08, 0.2)
            ax.set_xlim(mins[0] - pad[0], maxs[0] + pad[0])
            ax.set_ylim(mins[1] - pad[1], maxs[1] + pad[1])
            ax.set_zlim(mins[2] - pad[2], maxs[2] + pad[2])

        mappable = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        mappable.set_array([])
        cbar = fig.colorbar(mappable, ax=ax, shrink=0.7, pad=0.08)
        cbar.set_label("Illuminance (lux)")

        ax.set_title("3D False-colour Room View")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.set_zlabel("Z (m)")
        ax.view_init(elev=24, azim=-52)
        fig.tight_layout()
        return fig

    def render_polar_candela(
        self,
        photometry: "Photometry",
        planes: Optional[List[float]] = None,
        title: str = "Candela Distribution",
    ) -> Figure:
        h_angles = np.asarray(photometry.c_angles_deg, dtype=float)
        g_angles = np.asarray(photometry.gamma_angles_deg, dtype=float)
        candela = np.asarray(photometry.candela, dtype=float)

        if planes is None:
            planes = [0.0, 90.0, 180.0, 270.0]

        fig = plt.figure(figsize=(6.5, 5.5), dpi=160)
        ax = fig.add_subplot(111, projection="polar")
        cmap = self._resolve_cmap()

        for k, plane in enumerate(planes):
            plane = float(plane) % 360.0
            idx = int(np.argmin(np.abs(h_angles - plane)))
            vals = candela[idx, :]
            theta = np.deg2rad(g_angles)
            ax.plot(theta, vals, color=cmap(k / max(1, len(planes) - 1)), linewidth=1.8, label=f"C{plane:.0f}\N{DEGREE SIGN}")

        ax.set_title(title)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_thetagrids(np.arange(0, 360, 15))
        ax.set_rlabel_position(135)
        ax.grid(alpha=0.35)
        ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), fontsize=8)
        fig.tight_layout()
        return fig

    def save(self, fig: Figure, path: Path, dpi: int = 150):
        fig.savefig(str(path), dpi=dpi, bbox_inches="tight")

    @staticmethod
    def _custom_luxera_cmap():
        colors = [
            (0.0, "#000033"),
            (0.15, "#0000CC"),
            (0.30, "#0099FF"),
            (0.45, "#00CC66"),
            (0.60, "#FFFF00"),
            (0.80, "#FF6600"),
            (1.0, "#CC0000"),
        ]
        return LinearSegmentedColormap.from_list("luxera", colors)


def render_falsecolor_plane(
    *,
    values: np.ndarray,
    nx: int,
    ny: int,
    out_path: Path,
    title: str = "False Colour",
    with_contours: bool = True,
) -> Path:
    """Backward-compatible helper used by existing tests/callers."""
    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size != int(nx) * int(ny):
        raise ValueError(f"values size {arr.size} does not match nx*ny={int(nx) * int(ny)}")
    grid = arr.reshape(int(ny), int(nx))
    renderer = FalseColourRenderer(colour_scale="luxera", vmin=float(np.min(grid)), vmax=float(np.max(grid) + 1e-9))
    levels = None
    if with_contours:
        levels = np.linspace(float(np.min(grid)), float(np.max(grid)), 8).tolist()
    fig = renderer.render_grid_heatmap(
        grid_values=grid,
        grid_origin=(0.0, 0.0),
        grid_width=float(max(nx - 1, 1)),
        grid_height=float(max(ny - 1, 1)),
        title=title,
        contour_levels=levels,
    )
    renderer.save(fig, out_path, dpi=160)
    plt.close(fig)
    return out_path
