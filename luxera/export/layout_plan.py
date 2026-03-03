from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import numpy as np  # noqa: E402

from luxera.project.schema import Project


class LayoutPlanGenerator:
    """
    Generate 2D reflected ceiling plan (RCP) and section drawings.
    """

    def generate_rcp(
        self,
        project: Project,
        results: Optional[Dict] = None,
        output_format: str = "svg",
        output_path: Optional[Path] = None,
        options: Optional[Dict] = None,
    ) -> Any:
        opts = dict(options or {})
        fmt = str(output_format).lower()
        if fmt not in {"svg", "pdf", "dxf"}:
            raise ValueError(f"Unsupported output_format: {output_format}")

        out = Path(output_path).expanduser().resolve() if output_path is not None else Path.cwd() / f"rcp.{fmt}"
        out.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "dxf":
            return self._generate_rcp_dxf(project, out, opts)

        fig, ax = plt.subplots(figsize=(11.7, 8.3), dpi=170)

        room_bounds: List[Tuple[float, float, float, float]] = []
        for room in project.geometry.rooms:
            ox, oy, _ = room.origin
            w = float(room.width)
            l = float(room.length)
            room_bounds.append((float(ox), float(oy), w, l))
            r = mpatches.Rectangle((ox, oy), w, l, fill=False, edgecolor="black", linewidth=1.8)
            ax.add_patch(r)

        for op in project.geometry.openings:
            verts = [(float(v[0]), float(v[1])) for v in op.vertices]
            if len(verts) < 2:
                continue
            xs = [p[0] for p in verts] + [verts[0][0]]
            ys = [p[1] for p in verts] + [verts[0][1]]
            ax.plot(xs, ys, linestyle="--", linewidth=1.0, color="#616161")

        tag_labels = self._tag_labels(len(project.luminaires))
        for idx, lum in enumerate(project.luminaires):
            x, y, _z = lum.transform.position
            lum_type = str(getattr(lum, "mounting_type", None) or "auto")
            symbol = self.generate_luminaire_symbol(lum_type)
            self._draw_symbol(ax, float(x), float(y), symbol, scale=0.12, gid=f"luminaire-symbol-{lum.id}")
            ax.text(float(x) + 0.14, float(y) + 0.14, tag_labels[idx], fontsize=8, color="#111111")

        for g in project.grids:
            gx, gy, _gz = g.origin
            rect = mpatches.Rectangle((gx, gy), g.width, g.height, fill=False, edgecolor="#1565C0", linewidth=1.0, linestyle="--")
            ax.add_patch(rect)

        if opts.get("show_iso_lux", False) and isinstance(results, dict):
            self._overlay_isolux(ax, results)
        if opts.get("show_values", False) and isinstance(results, dict):
            self._overlay_values(ax, results)

        if opts.get("show_dimensions", True):
            self._draw_dimensions(ax, room_bounds)

        self._draw_scale_bar(ax, room_bounds)
        self._draw_north_arrow(ax, room_bounds)
        title_block = self._draw_title_block(project, scale=str(opts.get("scale", "1:100")))
        self._draw_title_block_plot(ax, title_block, room_bounds)

        xmin, xmax, ymin, ymax = self._bounds(room_bounds)
        pad = max((xmax - xmin), (ymax - ymin), 1.0) * 0.12
        ax.set_xlim(xmin - pad, xmax + pad)
        ax.set_ylim(ymin - pad, ymax + pad)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title("Reflected Ceiling Plan")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.grid(alpha=0.2)

        fig.tight_layout()
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        return out

    def generate_section(
        self,
        project: Project,
        section_axis: str = "x",
        section_position: float = 0.5,
        output_format: str = "svg",
        output_path: Optional[Path] = None,
    ) -> Any:
        fmt = str(output_format).lower()
        if fmt not in {"svg", "pdf"}:
            raise ValueError("Section export supports svg/pdf")
        out = Path(output_path).expanduser().resolve() if output_path is not None else Path.cwd() / f"section.{fmt}"
        out.parent.mkdir(parents=True, exist_ok=True)

        if not project.geometry.rooms:
            raise ValueError("Project has no rooms")
        room = project.geometry.rooms[0]
        ox, oy, oz = room.origin
        w, l, h = float(room.width), float(room.length), float(room.height)

        axis = str(section_axis).lower()
        if axis not in {"x", "y"}:
            raise ValueError("section_axis must be 'x' or 'y'")

        cut_norm = min(1.0, max(0.0, float(section_position)))
        if axis == "x":
            sec_at = oy + l * cut_norm
            horiz_len = w
            coord = lambda lum: float(lum.transform.position[0] - ox)
            off = lambda lum: abs(float(lum.transform.position[1] - sec_at))
        else:
            sec_at = ox + w * cut_norm
            horiz_len = l
            coord = lambda lum: float(lum.transform.position[1] - oy)
            off = lambda lum: abs(float(lum.transform.position[0] - sec_at))

        workplane = 0.8
        tol = max(horiz_len * 0.08, 0.25)

        fig, ax = plt.subplots(figsize=(11.7, 6.2), dpi=170)
        ax.plot([0, horiz_len], [0, 0], color="black", linewidth=1.8)
        ax.plot([0, 0], [0, h], color="black", linewidth=1.8)
        ax.plot([horiz_len, horiz_len], [0, h], color="black", linewidth=1.8)
        ax.plot([0, horiz_len], [h, h], color="black", linewidth=1.8)
        ax.plot([0, horiz_len], [workplane, workplane], color="#666", linewidth=1.0, linestyle="--")
        ax.text(horiz_len * 0.02, workplane + 0.05, "Workplane", fontsize=8, color="#555")

        for lum in project.luminaires:
            if off(lum) > tol:
                continue
            lx = coord(lum)
            lz = float(lum.transform.position[2] - oz)
            ax.scatter([lx], [lz], marker="s", s=35, c="#C62828")
            ax.text(lx + 0.08, lz + 0.08, lum.id, fontsize=7)
            ax.plot([lx, lx], [lz, workplane], color="#888", linewidth=0.9)

            beam = self._beam_angle_deg(project, lum.photometry_asset_id)
            half = np.radians(max(5.0, min(85.0, beam / 2.0)))
            run = max((lz - workplane) * np.tan(half), 0.0)
            ax.plot([lx, lx - run], [lz, workplane], color="#FF8F00", linewidth=0.8, alpha=0.9)
            ax.plot([lx, lx + run], [lz, workplane], color="#FF8F00", linewidth=0.8, alpha=0.9)
            ax.text(lx + 0.05, (lz + workplane) * 0.5, f"{lz:.2f}m", fontsize=7, color="#333")

        ax.annotate("", xy=(horiz_len + 0.4, h), xytext=(horiz_len + 0.4, 0), arrowprops=dict(arrowstyle="<->", lw=1.0))
        ax.text(horiz_len + 0.45, h * 0.5, f"{h:.2f}m", rotation=90, va="center", fontsize=8)

        ax.set_xlim(-0.2, horiz_len + 0.8)
        ax.set_ylim(-0.2, h + 0.6)
        ax.set_title(f"Section View ({axis.upper()} cut at {sec_at:.2f}m)")
        ax.set_xlabel("Distance (m)")
        ax.set_ylabel("Height (m)")
        ax.grid(alpha=0.2)

        fig.tight_layout()
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        return out

    def generate_luminaire_symbol(
        self,
        luminaire_type: str,
        size_mm: float = 8.0,
    ) -> List[Dict]:
        s = max(float(size_mm), 1.0) / 1000.0
        t = str(luminaire_type).strip().lower()

        if t in {"recessed", "recessed_square"}:
            return [
                {"type": "rect", "x": -s / 2, "y": -s / 2, "w": s, "h": s, "fill": True},
                {"type": "line", "x1": -s / 2, "y1": -s / 2, "x2": s / 2, "y2": s / 2},
                {"type": "line", "x1": -s / 2, "y1": s / 2, "x2": s / 2, "y2": -s / 2},
            ]
        if t in {"surface", "surface_mount"}:
            return [{"type": "rect", "x": -s / 2, "y": -s / 2, "w": s, "h": s, "fill": False}]
        if t in {"pendant"}:
            return [
                {"type": "line", "x1": 0.0, "y1": s * 0.65, "x2": 0.0, "y2": s * 0.18},
                {"type": "circle", "x": 0.0, "y": 0.0, "r": s * 0.18, "fill": False},
            ]
        if t in {"downlight"}:
            return [
                {"type": "circle", "x": 0.0, "y": 0.0, "r": s * 0.33, "fill": False},
                {"type": "circle", "x": 0.0, "y": 0.0, "r": s * 0.10, "fill": True},
            ]
        if t in {"linear"}:
            return [
                {"type": "rect", "x": -s * 0.7, "y": -s * 0.18, "w": s * 1.4, "h": s * 0.36, "fill": False},
                {"type": "line", "x1": -s * 0.65, "y1": 0.0, "x2": s * 0.65, "y2": 0.0},
            ]
        return self.generate_luminaire_symbol("recessed_square", size_mm=size_mm)

    def _draw_title_block(self, project: Project, scale: str) -> List[Dict]:
        return [
            {"label": "Project", "value": str(project.name or "Untitled")},
            {"label": "Date", "value": datetime.now().strftime("%Y-%m-%d")},
            {"label": "Scale", "value": str(scale)},
            {"label": "Drawing", "value": "RCP-01"},
        ]

    def _draw_symbol(self, ax, x: float, y: float, primitives: List[Dict], scale: float = 1.0, gid: Optional[str] = None) -> None:
        for p in primitives:
            typ = p.get("type")
            if typ == "line":
                art = ax.plot(
                    [x + scale * float(p["x1"]), x + scale * float(p["x2"])],
                    [y + scale * float(p["y1"]), y + scale * float(p["y2"])],
                    color="black",
                    linewidth=1.0,
                )[0]
            elif typ == "rect":
                art = mpatches.Rectangle(
                    (x + scale * float(p["x"]), y + scale * float(p["y"])),
                    scale * float(p["w"]),
                    scale * float(p["h"]),
                    fill=bool(p.get("fill", False)),
                    facecolor="#212121" if bool(p.get("fill", False)) else "none",
                    edgecolor="black",
                    linewidth=1.0,
                )
                ax.add_patch(art)
            elif typ == "circle":
                art = mpatches.Circle(
                    (x + scale * float(p["x"]), y + scale * float(p["y"])),
                    radius=scale * float(p["r"]),
                    fill=bool(p.get("fill", False)),
                    facecolor="#212121" if bool(p.get("fill", False)) else "none",
                    edgecolor="black",
                    linewidth=1.0,
                )
                ax.add_patch(art)
            else:
                continue
            if gid is not None:
                art.set_gid(gid)

    def _draw_dimensions(self, ax, room_bounds: List[Tuple[float, float, float, float]]) -> None:
        if not room_bounds:
            return
        xmin, xmax, ymin, ymax = self._bounds(room_bounds)
        ax.annotate("", xy=(xmin, ymin - 0.35), xytext=(xmax, ymin - 0.35), arrowprops=dict(arrowstyle="<->", lw=1.0))
        ax.text((xmin + xmax) * 0.5, ymin - 0.45, f"{(xmax - xmin):.2f} m", ha="center", va="top", fontsize=8)
        ax.annotate("", xy=(xmax + 0.35, ymin), xytext=(xmax + 0.35, ymax), arrowprops=dict(arrowstyle="<->", lw=1.0))
        ax.text(xmax + 0.45, (ymin + ymax) * 0.5, f"{(ymax - ymin):.2f} m", rotation=90, va="center", fontsize=8)

    def _draw_scale_bar(self, ax, room_bounds: List[Tuple[float, float, float, float]]) -> None:
        xmin, xmax, ymin, ymax = self._bounds(room_bounds)
        span = max(xmax - xmin, ymax - ymin, 1.0)
        length = max(1.0, round(span / 4.0, 1))
        x0 = xmin + 0.1 * span
        y0 = ymin - 0.7
        ax.plot([x0, x0 + length], [y0, y0], color="black", linewidth=2)
        for t in [0.0, 0.5, 1.0]:
            xt = x0 + length * t
            ax.plot([xt, xt], [y0 - 0.05, y0 + 0.05], color="black", linewidth=1)
            ax.text(xt, y0 - 0.1, f"{length * t:.1f}", ha="center", va="top", fontsize=7)
        ax.text(x0 + length + 0.1, y0 - 0.1, "m", fontsize=7, va="top")

    def _draw_north_arrow(self, ax, room_bounds: List[Tuple[float, float, float, float]]) -> None:
        xmin, xmax, ymin, ymax = self._bounds(room_bounds)
        span = max(xmax - xmin, ymax - ymin, 1.0)
        x = xmax + 0.5
        y = ymax - 0.3
        ax.annotate("N", xy=(x, y + 0.45), xytext=(x, y), arrowprops=dict(arrowstyle="->", lw=1.6), ha="center", fontsize=10)

    def _draw_title_block_plot(self, ax, items: List[Dict], room_bounds: List[Tuple[float, float, float, float]]) -> None:
        xmin, xmax, ymin, _ymax = self._bounds(room_bounds)
        w = max(3.5, (xmax - xmin) * 0.28)
        h = 1.2
        x0 = xmax - w
        y0 = ymin - 1.25
        rect = mpatches.Rectangle((x0, y0), w, h, fill=False, linewidth=1.0, edgecolor="black")
        ax.add_patch(rect)
        row_h = h / max(len(items), 1)
        for i, item in enumerate(items):
            yy = y0 + h - (i + 0.75) * row_h
            ax.text(x0 + 0.08, yy, f"{item.get('label')}: {item.get('value')}", fontsize=7, va="center")

    def _generate_rcp_dxf(self, project: Project, out_path: Path, options: Dict[str, Any]) -> Path:
        try:
            import ezdxf  # type: ignore

            doc = ezdxf.new(dxfversion="R2010")
            msp = doc.modelspace()
            for room in project.geometry.rooms:
                ox, oy, _ = room.origin
                pts = [(ox, oy), (ox + room.width, oy), (ox + room.width, oy + room.length), (ox, oy + room.length)]
                msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "ROOM"})
            for op in project.geometry.openings:
                pts = [(float(v[0]), float(v[1])) for v in op.vertices]
                if len(pts) >= 2:
                    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "OPENINGS", "linetype": "DASHED"})
            for idx, lum in enumerate(project.luminaires):
                x, y, _ = lum.transform.position
                msp.add_circle((x, y), radius=0.12, dxfattribs={"layer": "LUMINAIRES"})
                msp.add_text(self._tag_labels(len(project.luminaires))[idx], dxfattribs={"height": 0.14, "layer": "ANNOT"}).set_placement((x + 0.15, y + 0.15))
            doc.saveas(str(out_path))
            return out_path
        except Exception:
            # Fallback: minimal ASCII DXF content without external dependency.
            lines: List[str] = ["0", "SECTION", "2", "ENTITIES"]
            for room in project.geometry.rooms:
                ox, oy, _ = room.origin
                pts = [(ox, oy), (ox + room.width, oy), (ox + room.width, oy + room.length), (ox, oy + room.length), (ox, oy)]
                for a, b in zip(pts[:-1], pts[1:]):
                    lines.extend(["0", "LINE", "8", "ROOM", "10", f"{a[0]}", "20", f"{a[1]}", "30", "0", "11", f"{b[0]}", "21", f"{b[1]}", "31", "0"])
            lines.extend(["0", "ENDSEC", "0", "EOF"])
            out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return out_path

    def _overlay_isolux(self, ax, results: Dict[str, Any]) -> None:
        try:
            z, x, y = self._result_grid(results)
            levels = np.linspace(float(np.min(z)), float(np.max(z)), 8)
            if np.allclose(levels[0], levels[-1]):
                return
            cs = ax.contour(x, y, z, levels=levels, colors="#2E7D32", linewidths=0.7, alpha=0.8)
            ax.clabel(cs, inline=True, fontsize=6, fmt="%.0f")
        except Exception:
            return

    def _overlay_values(self, ax, results: Dict[str, Any]) -> None:
        try:
            z, x, y = self._result_grid(results)
            ny, nx = z.shape
            if nx * ny > 150:
                return
            for j in range(ny):
                for i in range(nx):
                    ax.text(float(x[j, i]), float(y[j, i]), f"{z[j, i]:.0f}", fontsize=5, ha="center", va="center", color="#1B5E20")
        except Exception:
            return

    def _result_grid(self, results: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if all(k in results for k in ("grid_values", "grid_nx", "grid_ny", "grid_points")):
            nx = int(results["grid_nx"])
            ny = int(results["grid_ny"])
            z = np.asarray(results["grid_values"], dtype=float).reshape(ny, nx)
            p = np.asarray(results["grid_points"], dtype=float).reshape(-1, 3)
            x = p[:, 0].reshape(ny, nx)
            y = p[:, 1].reshape(ny, nx)
            return z, x, y
        calc = results.get("calc_objects")
        if isinstance(calc, list):
            grid = next((o for o in calc if isinstance(o, dict) and str(o.get("type")) == "grid"), None)
            if grid is not None:
                nx = int(grid.get("nx", 0) or 0)
                ny = int(grid.get("ny", 0) or 0)
                z = np.asarray(grid.get("values", []), dtype=float).reshape(ny, nx)
                p = np.asarray(grid.get("points", []), dtype=float).reshape(-1, 3)
                x = p[:, 0].reshape(ny, nx)
                y = p[:, 1].reshape(ny, nx)
                return z, x, y
        raise ValueError("No grid result payload")

    def _bounds(self, room_bounds: List[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
        if not room_bounds:
            return 0.0, 10.0, 0.0, 8.0
        xmin = min(b[0] for b in room_bounds)
        ymin = min(b[1] for b in room_bounds)
        xmax = max(b[0] + b[2] for b in room_bounds)
        ymax = max(b[1] + b[3] for b in room_bounds)
        return float(xmin), float(xmax), float(ymin), float(ymax)

    def _tag_labels(self, n: int) -> List[str]:
        labels: List[str] = []
        for i in range(max(0, int(n))):
            x = i
            tag = ""
            while True:
                tag = chr(ord("A") + (x % 26)) + tag
                x = x // 26 - 1
                if x < 0:
                    break
            labels.append(tag)
        return labels

    def _beam_angle_deg(self, project: Project, asset_id: str) -> float:
        asset = next((a for a in project.photometry_assets if a.id == asset_id), None)
        if asset is None or not isinstance(asset.metadata, dict):
            return 60.0
        val = asset.metadata.get("beam_angle_deg")
        try:
            return float(val)
        except Exception:
            return 60.0
