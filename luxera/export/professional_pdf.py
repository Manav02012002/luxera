from __future__ import annotations

import io
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.project.schema import Project
from luxera.reporting.schedules import build_luminaire_schedule
from luxera.viz.falsecolour import FalseColourRenderer


class ProfessionalReportBuilder:
    """
    Generate a professional multi-page lighting report PDF.
    Comparable to AGi32's printed output.
    """

    def __init__(self, project: Project, results: Dict[str, Any]):
        self.project = project
        self.results = results
        self.styles = self._default_styles()
        self.sections = [
            "Project Summary",
            "Luminaire Schedule",
            "Layout Plan",
            "Calculation Results",
            "Iso-lux Contour",
            "False-colour Heatmap",
            "UGR Results",
            "Compliance Summary",
            "LENI Energy Summary",
            "Maintenance Factors",
            "Appendix - Polar Plots",
        ]

    def build(self, output_path: Path):
        """
        Generate complete PDF with these pages:
        1. Cover page (project name, date, Luxera logo placeholder, client info)
        2. Table of contents (auto-generated from sections)
        3. Project summary (room dimensions, surface materials, luminaire count)
        4. Luminaire schedule table (tag, manufacturer, catalog #, quantity,
           lumens, wattage, mounting height, MF, total watts)
        5. Layout plan (matplotlib top-down view showing room outline,
           luminaire positions as symbols, grid boundary, scale bar, north arrow)
        6. Calculation results (E_avg, E_min, E_max, U0, per grid)
        7. Iso-lux contour plot (embedded from matplotlib)
        8. False-colour illuminance heatmap (embedded from matplotlib)
        9. UGR results table (if applicable)
        10. Compliance summary (EN 12464 pass/fail table with green/red)
        11. LENI energy summary (if computed)
        12. Maintenance factor summary (LLMF, LSF, LMF, RSF breakdown)
        13. Appendix: photometric polar plot for each unique luminaire type
        """
        out_path = Path(output_path).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=A4,
            leftMargin=1.6 * cm,
            rightMargin=1.6 * cm,
            topMargin=1.8 * cm,
            bottomMargin=1.8 * cm,
            title=f"Professional Lighting Report - {self.project.name}",
            author="Luxera",
            pageCompression=0,
        )

        story: List[Any] = []

        story.extend(self._cover_story())
        story.append(PageBreak())
        story.extend(self._toc_page())
        story.append(PageBreak())
        story.extend(self._project_summary())
        story.append(PageBreak())
        story.extend(self._luminaire_schedule_table())
        story.append(PageBreak())
        story.extend(self._layout_plan())
        story.append(PageBreak())
        story.extend(self._results_table())
        story.append(PageBreak())
        story.extend(self._isolux_plot())
        story.append(PageBreak())
        story.extend(self._heatmap_plot())
        story.append(PageBreak())
        story.extend(self._ugr_table())
        story.append(PageBreak())
        story.extend(self._compliance_table())
        story.append(PageBreak())
        story.extend(self._leni_summary())
        story.append(PageBreak())
        story.extend(self._maintenance_summary())
        story.append(PageBreak())
        story.extend(self._polar_plots())

        doc.build(story, onFirstPage=self._cover_page, onLaterPages=self._draw_footer)

    def _cover_page(self, canvas, doc):
        self._draw_footer(canvas, doc)

    def _draw_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, 0.9 * cm, f"Luxera Professional Report | {self.project.name}")
        canvas.drawRightString(A4[0] - doc.rightMargin, 0.9 * cm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    def _cover_story(self) -> List[Any]:
        rows = [
            ["Project", self.project.name or "Untitled Project"],
            ["Date", datetime.now().strftime("%Y-%m-%d")],
            ["Client", str(self.results.get("client", "Client Name"))],
            ["Prepared by", "Luxera"],
        ]
        logo = Table([["LUXERA"]], colWidths=[5.0 * cm], rowHeights=[2.0 * cm])
        logo.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 20),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1f4e79")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f4e79")),
                ]
            )
        )

        return [
            Spacer(1, 2.2 * cm),
            logo,
            Spacer(1, 0.8 * cm),
            Paragraph("Professional Lighting Calculation Report", self.styles["title"]),
            Spacer(1, 0.35 * cm),
            Paragraph("Client Deliverable", self.styles["heading"]),
            Spacer(1, 0.35 * cm),
            self._styled_table(rows, [5.0 * cm, 11.7 * cm]),
        ]

    def _toc_page(self):
        content: List[Any] = [Paragraph("Table of Contents", self.styles["heading"]), Spacer(1, 0.25 * cm)]
        rows = [["Section", "Page"]]
        for idx, title in enumerate(self.sections, start=3):
            rows.append([title, str(idx)])
        content.append(self._styled_table(rows, [13.0 * cm, 3.7 * cm], header_bg=colors.HexColor("#2d6a9f")))
        return content

    def _project_summary(self):
        rooms = self.project.geometry.rooms
        lum_count = len(self.project.luminaires)
        room_text = "-"
        if rooms:
            parts = []
            for r in rooms[:5]:
                parts.append(f"{r.name}: {r.width:.2f}m x {r.length:.2f}m x {r.height:.2f}m")
            room_text = "<br/>".join(parts)

        mats = self.project.materials
        material_text = ", ".join(m.name for m in mats[:8]) if mats else "Not specified"

        rows = [
            ["Project", self.project.name or "-"],
            ["Rooms", room_text],
            ["Surface Materials", material_text],
            ["Luminaire Instances", str(lum_count)],
            ["Calculation Grids", str(len(self.project.grids))],
        ]
        return [
            Paragraph("Project Summary", self.styles["heading"]),
            Spacer(1, 0.2 * cm),
            self._styled_table(rows, [5.0 * cm, 11.7 * cm]),
        ]

    def _luminaire_schedule_table(self):
        schedule = build_luminaire_schedule(self.project, asset_hashes=self._asset_hashes())
        by_asset = {a.id: a for a in self.project.photometry_assets}
        rows: List[List[str]] = [
            [
                "Tag",
                "Manufacturer",
                "Catalog #",
                "Qty",
                "Lumens",
                "W",
                "Mount (m)",
                "MF",
                "Total W",
            ]
        ]
        for r in schedule:
            asset = by_asset.get(str(r.get("asset_id", "")))
            metadata = asset.metadata if asset and isinstance(asset.metadata, dict) else {}
            qty = int(r.get("count", 0) or 0)
            watt = self._to_float(metadata.get("wattage") or metadata.get("watts"))
            total_w = watt * qty if watt is not None else None
            rows.append(
                [
                    str(r.get("asset_id", "-")),
                    str(metadata.get("manufacturer") or r.get("manufacturer") or "-"),
                    str(metadata.get("catalog") or metadata.get("lumcat") or "-"),
                    str(qty),
                    self._fmt_num(metadata.get("lumens") or metadata.get("lumens_per_lamp")),
                    self._fmt_num(watt),
                    self._fmt_num(r.get("mounting_height_m")),
                    self._fmt_num(r.get("maintenance_factor")),
                    self._fmt_num(total_w),
                ]
            )

        col_w = [1.7 * cm, 2.5 * cm, 2.2 * cm, 1.0 * cm, 1.7 * cm, 1.4 * cm, 1.8 * cm, 1.2 * cm, 1.8 * cm]
        return [
            Paragraph("Luminaire Schedule", self.styles["heading"]),
            Spacer(1, 0.15 * cm),
            self._styled_table(rows, col_w),
        ]

    def _layout_plan(self):
        fig, ax = plt.subplots(figsize=(9, 5.5), dpi=160)
        rooms = self.project.geometry.rooms
        x_min = 0.0
        y_min = 0.0
        x_max = 8.0
        y_max = 8.0

        if rooms:
            x_vals: List[float] = []
            y_vals: List[float] = []
            for room in rooms:
                ox, oy, _ = room.origin
                rect = plt.Rectangle((ox, oy), room.width, room.length, fill=False, linewidth=2.0, edgecolor="#1f4e79")
                ax.add_patch(rect)
                ax.text(ox + room.width * 0.5, oy + room.length * 0.5, room.name, ha="center", va="center", fontsize=9)
                x_vals.extend([ox, ox + room.width])
                y_vals.extend([oy, oy + room.length])
            x_min, x_max = min(x_vals), max(x_vals)
            y_min, y_max = min(y_vals), max(y_vals)

        if self.project.grids:
            g = self.project.grids[0]
            gx, gy, _ = g.origin
            grid_rect = plt.Rectangle((gx, gy), g.width, g.height, fill=False, linewidth=1.5, linestyle="--", edgecolor="#f57c00")
            ax.add_patch(grid_rect)
            ax.text(gx, gy, f"Grid: {g.name}", fontsize=8, color="#f57c00", va="bottom")

        xs = [l.transform.position[0] for l in self.project.luminaires]
        ys = [l.transform.position[1] for l in self.project.luminaires]
        if xs and ys:
            ax.scatter(xs, ys, marker="*", s=130, color="#c62828", edgecolors="white", linewidths=0.8, label="Luminaires")
            for i, (x, y) in enumerate(zip(xs, ys), start=1):
                ax.text(x, y, f"L{i}", fontsize=7, ha="left", va="bottom", color="#7f0000")

        span = max(x_max - x_min, y_max - y_min, 1.0)
        scale_len = max(1.0, round(span / 5.0, 1))
        x0 = x_min + span * 0.05
        y0 = y_min - span * 0.08
        ax.plot([x0, x0 + scale_len], [y0, y0], color="black", linewidth=2)
        ax.plot([x0, x0], [y0 - 0.05, y0 + 0.05], color="black", linewidth=1)
        ax.plot([x0 + scale_len, x0 + scale_len], [y0 - 0.05, y0 + 0.05], color="black", linewidth=1)
        ax.text(x0 + scale_len / 2.0, y0 - 0.12, f"{scale_len:g} m", ha="center", va="top", fontsize=8)

        nx = x_max + span * 0.05
        ny = y_max - span * 0.15
        ax.annotate("N", xy=(nx, ny + span * 0.1), xytext=(nx, ny), arrowprops=dict(arrowstyle="->", lw=1.8), ha="center", fontsize=10)

        ax.set_title("Layout Plan (Top View)")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.grid(alpha=0.25)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(x_min - span * 0.12, x_max + span * 0.15)
        ax.set_ylim(y_min - span * 0.2, y_max + span * 0.1)
        if xs:
            ax.legend(loc="upper right", fontsize=8)

        plan_img = self._fig_to_image(fig, width_cm=17.2, height_cm=9.0)

        # Section/elevation companion view.
        fig2, ax2 = plt.subplots(figsize=(9, 3.2), dpi=160)
        room_h = max((r.height for r in rooms), default=3.0)
        room_l = max((r.length for r in rooms), default=8.0)
        ax2.plot([0, room_l], [0, 0], color="#5d4037", linewidth=2)
        ax2.plot([0, 0], [0, room_h], color="#1f4e79", linewidth=1.5)
        ax2.plot([room_l, room_l], [0, room_h], color="#1f4e79", linewidth=1.5)
        ax2.plot([0, room_l], [room_h, room_h], color="#1f4e79", linewidth=1.5)
        z_vals = [l.transform.position[2] for l in self.project.luminaires]
        if z_vals and xs:
            x_norm = np.linspace(0.5, max(0.6, room_l - 0.5), num=len(z_vals))
            ax2.scatter(x_norm, z_vals, marker="o", s=45, color="#c62828", label="Luminaire Mount")
        ax2.set_title("Section View")
        ax2.set_xlabel("Length (m)")
        ax2.set_ylabel("Height (m)")
        ax2.set_xlim(-0.2, room_l + 0.2)
        ax2.set_ylim(0, room_h + 0.6)
        ax2.grid(alpha=0.25)
        section_img = self._fig_to_image(fig2, width_cm=17.2, height_cm=6.0)

        return [
            Paragraph("Layout Plan", self.styles["heading"]),
            Spacer(1, 0.15 * cm),
            plan_img,
            Spacer(1, 0.3 * cm),
            section_img,
        ]

    def _results_table(self):
        summary = self._summary()
        rows = [["Grid", "E_avg (lux)", "E_min (lux)", "E_max (lux)", "U0"]]
        default_row = [
            "overall",
            self._fmt_num(summary.get("mean_lux")),
            self._fmt_num(summary.get("min_lux")),
            self._fmt_num(summary.get("max_lux")),
            self._fmt_num(summary.get("uniformity_ratio") or summary.get("u0")),
        ]

        table_rows = self._extract_grid_rows_from_result()
        rows.extend(table_rows if table_rows else [default_row])

        return [
            Paragraph("Calculation Results", self.styles["heading"]),
            Spacer(1, 0.15 * cm),
            self._styled_table(rows, [4.0 * cm, 3.1 * cm, 3.1 * cm, 3.1 * cm, 2.4 * cm]),
        ]

    def _isolux_plot(self):
        x, y, z = self._grid_for_plot()
        renderer = FalseColourRenderer(colour_scale="viridis", vmin=float(np.min(z)), vmax=float(np.max(z) + 1e-9))
        levels = np.linspace(float(np.min(z)), float(np.max(z)), 8).tolist()
        fig = renderer.render_isolux_contours(
            grid_values=z,
            grid_origin=(float(np.min(x)), float(np.min(y))),
            grid_width=float(np.max(x) - np.min(x)),
            grid_height=float(np.max(y) - np.min(y)),
            levels=levels,
            luminaire_positions=[(float(l.transform.position[0]), float(l.transform.position[1])) for l in self.project.luminaires],
        )
        img = self._fig_to_image(fig, width_cm=17.0, height_cm=10.5)
        return [Paragraph("Iso-lux Contour", self.styles["heading"]), Spacer(1, 0.15 * cm), img]

    def _heatmap_plot(self):
        x, y, z = self._grid_for_plot()
        renderer = FalseColourRenderer(colour_scale="luxera", vmin=float(np.min(z)), vmax=float(np.max(z) + 1e-9))
        levels = np.linspace(float(np.min(z)), float(np.max(z)), 8).tolist()
        fig = renderer.render_grid_heatmap(
            grid_values=z,
            grid_origin=(float(np.min(x)), float(np.min(y))),
            grid_width=float(np.max(x) - np.min(x)),
            grid_height=float(np.max(y) - np.min(y)),
            title="False-colour Illuminance Heatmap",
            contour_levels=levels,
        )
        img = self._fig_to_image(fig, width_cm=17.0, height_cm=10.5)
        return [Paragraph("False-colour Heatmap", self.styles["heading"]), Spacer(1, 0.15 * cm), img]

    def _ugr_table(self):
        summary = self._summary()
        ugr_keys = [k for k in summary.keys() if "ugr" in str(k).lower()]
        rows = [["Metric", "Value"]]
        if ugr_keys:
            for k in sorted(ugr_keys):
                rows.append([str(k), self._fmt_num(summary.get(k))])
        else:
            rows.append(["UGR", "Not computed for this job"])  # still a populated table
        return [Paragraph("UGR Results", self.styles["heading"]), Spacer(1, 0.15 * cm), self._styled_table(rows, [8.0 * cm, 8.7 * cm])]

    def _compliance_table(self):
        summary = self._summary()
        compliance = summary.get("compliance") if isinstance(summary.get("compliance"), dict) else self.results.get("compliance", {})
        rows = [["Requirement", "Result"]]
        if isinstance(compliance, dict) and compliance:
            for k, v in compliance.items():
                rows.append([str(k), str(v)])
        else:
            rows.append(["status", str(summary.get("status", "n/a"))])
            rows.append(["mean_lux", self._fmt_num(summary.get("mean_lux"))])
            rows.append(["uniformity_ratio", self._fmt_num(summary.get("uniformity_ratio"))])

        table = self._styled_table(rows, [8.0 * cm, 8.7 * cm])
        style_ops = []
        for i in range(1, len(rows)):
            value = rows[i][1].strip().lower()
            if any(tok in value for tok in ("pass", "true", "ok")):
                style_ops.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#1b5e20")))
                style_ops.append(("BACKGROUND", (1, i), (1, i), colors.HexColor("#e8f5e9")))
            if any(tok in value for tok in ("fail", "false", "no")):
                style_ops.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#b71c1c")))
                style_ops.append(("BACKGROUND", (1, i), (1, i), colors.HexColor("#ffebee")))
        if style_ops:
            table.setStyle(TableStyle(style_ops))

        return [Paragraph("Compliance Summary", self.styles["heading"]), Spacer(1, 0.15 * cm), table]

    def _leni_summary(self):
        summary = self._summary()
        leni_keys = [k for k in summary.keys() if "leni" in str(k).lower() or "energy" in str(k).lower()]
        rows = [["Metric", "Value"]]
        if leni_keys:
            for k in sorted(leni_keys):
                rows.append([str(k), self._fmt_num(summary.get(k))])
        else:
            rows.extend(
                [
                    ["LENI", "Not computed"],
                    ["Connected load", self._fmt_num(self._estimated_connected_load_w()) + " W"],
                ]
            )
        return [Paragraph("LENI Energy Summary", self.styles["heading"]), Spacer(1, 0.15 * cm), self._styled_table(rows, [8.0 * cm, 8.7 * cm])]

    def _maintenance_summary(self):
        rows = [["Luminaire", "LLMF", "LSF", "LMF", "RSF", "MF"]]
        for lum in self.project.luminaires:
            comp = lum.maintenance_components if isinstance(lum.maintenance_components, dict) else {}
            llmf = self._to_float(comp.get("llmf")) or 1.0
            lsf = self._to_float(comp.get("lsf")) or 1.0
            lmf = self._to_float(comp.get("lmf")) or 1.0
            rsf = self._to_float(comp.get("rsf")) or 1.0
            mf = self._to_float(lum.maintenance_factor) or (llmf * lsf * lmf * rsf)
            rows.append([lum.id, self._fmt_num(llmf), self._fmt_num(lsf), self._fmt_num(lmf), self._fmt_num(rsf), self._fmt_num(mf)])
        if len(rows) == 1:
            rows.append(["-", "1.00", "1.00", "1.00", "1.00", "1.00"])

        return [Paragraph("Maintenance Factor Summary", self.styles["heading"]), Spacer(1, 0.15 * cm), self._styled_table(rows, [3.7 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm])]

    def _polar_plots(self):
        content: List[Any] = [Paragraph("Appendix: Photometric Polar Plots", self.styles["heading"]), Spacer(1, 0.15 * cm)]
        by_asset = {a.id: a for a in self.project.photometry_assets}
        used_assets = sorted({l.photometry_asset_id for l in self.project.luminaires})
        if not used_assets:
            content.append(Paragraph("No luminaires available.", self.styles["body"]))
            return content

        for asset_id in used_assets:
            asset = by_asset.get(asset_id)
            meta = asset.metadata if asset and isinstance(asset.metadata, dict) else {}
            beam = self._to_float(meta.get("beam_angle_deg")) or 60.0
            fig = None
            if asset is not None and asset.path:
                p = Path(asset.path).expanduser()
                if not p.is_absolute() and self.project.root_dir:
                    p = (Path(self.project.root_dir).expanduser() / p).resolve()
                if p.exists():
                    try:
                        txt = p.read_text(encoding="utf-8", errors="replace")
                        if str(asset.format).upper() == "LDT":
                            phot = photometry_from_parsed_ldt(parse_ldt_text(txt))
                        else:
                            phot = photometry_from_parsed_ies(parse_ies_text(txt, source_path=p))
                        fig = FalseColourRenderer(colour_scale="viridis").render_polar_candela(
                            photometry=phot,
                            title=f"Luminaire {asset_id}",
                        )
                    except Exception:
                        fig = None

            if fig is None:
                n = max(1.0, min(16.0, 180.0 / beam))
                theta = np.linspace(0, 2 * np.pi, 360)
                intensity = np.clip(np.cos(theta) ** (2 * n), 0, None)
                intensity = intensity / max(np.max(intensity), 1e-9)
                fig = plt.figure(figsize=(5.3, 4.2), dpi=170)
                ax = fig.add_subplot(111, projection="polar")
                ax.plot(theta, intensity, color="#1f4e79", linewidth=1.8)
                ax.fill(theta, intensity, color="#90caf9", alpha=0.35)
                ax.set_title(f"Luminaire {asset_id}", va="bottom", fontsize=10)
                ax.set_rticks([0.25, 0.5, 0.75, 1.0])

            img = self._fig_to_image(fig, width_cm=11.5, height_cm=8.0)

            table = self._styled_table(
                [
                    ["Asset", asset_id],
                    ["Manufacturer", str(meta.get("manufacturer", "-"))],
                    ["Catalog", str(meta.get("catalog", "-"))],
                    ["Beam Angle (deg)", self._fmt_num(beam)],
                ],
                [4.2 * cm, 5.7 * cm],
            )
            content.extend([Paragraph(f"Luminaire Type: {asset_id}", self.styles["body_bold"]), Spacer(1, 0.1 * cm), img, Spacer(1, 0.1 * cm), table, Spacer(1, 0.3 * cm)])

        return content

    def _default_styles(self) -> Dict[str, ParagraphStyle]:
        """
        Professional typography:
        - Title: 18pt bold
        - Heading: 14pt bold
        - Body: 10pt
        - Table header: 9pt bold, blue background
        - Table body: 9pt
        - Footer: 8pt italic with page numbers
        - All text: Helvetica (built into reportlab)
        """
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle("pro_title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#13324b")),
            "heading": ParagraphStyle("pro_heading", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#1f4e79")),
            "body": ParagraphStyle("pro_body", parent=base["BodyText"], fontName="Helvetica", fontSize=10, leading=13),
            "body_bold": ParagraphStyle("pro_body_bold", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=13),
            "table_header": ParagraphStyle("pro_table_header", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.white),
            "table_body": ParagraphStyle("pro_table_body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=11),
            "footer": ParagraphStyle("pro_footer", parent=base["BodyText"], fontName="Helvetica-Oblique", fontSize=8, leading=9),
        }

    def _styled_table(self, rows: List[List[str]], col_widths: List[float], header_bg: colors.Color = colors.HexColor("#1f4e79")) -> Table:
        data: List[List[Any]] = []
        for ridx, row in enumerate(rows):
            out_row: List[Any] = []
            for cell in row:
                style = self.styles["table_header"] if ridx == 0 else self.styles["table_body"]
                out_row.append(Paragraph(str(cell), style))
            data.append(out_row)

        table = Table(data, colWidths=col_widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f4f7fb"), colors.white]),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#b0bec5")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cfd8dc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        table.setStyle(TableStyle(style))
        return table

    def _fig_to_image(self, fig: plt.Figure, width_cm: float, height_cm: float) -> Image:
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=170)
        plt.close(fig)
        buf.seek(0)
        return Image(buf, width=width_cm * cm, height=height_cm * cm)

    def _summary(self) -> Dict[str, Any]:
        s = self.results.get("summary", {})
        return s if isinstance(s, dict) else {}

    def _result_dir(self) -> Path | None:
        rd = self.results.get("result_dir")
        if not rd:
            return None
        p = Path(str(rd)).expanduser().resolve()
        return p if p.exists() else None

    def _extract_grid_rows_from_result(self) -> List[List[str]]:
        rows: List[List[str]] = []
        result_dir = self._result_dir()
        if result_dir is None:
            return rows
        result_json = result_dir / "result.json"
        if not result_json.exists():
            return rows
        try:
            payload = json.loads(result_json.read_text(encoding="utf-8"))
        except Exception:
            return rows

        tables = payload.get("tables", {}) if isinstance(payload, dict) else {}
        for section in ("grids", "vertical_planes", "point_sets"):
            vals = tables.get(section, []) if isinstance(tables, dict) else []
            if not isinstance(vals, list):
                continue
            for r in vals:
                if not isinstance(r, dict):
                    continue
                rows.append(
                    [
                        str(r.get("id", r.get("name", section))),
                        self._fmt_num(r.get("mean_lux")),
                        self._fmt_num(r.get("min_lux")),
                        self._fmt_num(r.get("max_lux")),
                        self._fmt_num(r.get("uniformity_min_avg") or r.get("uniformity_ratio")),
                    ]
                )
        return rows[:20]

    def _grid_for_plot(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        result_dir = self._result_dir()
        if result_dir is not None:
            grids_dir = result_dir / "grids"
            if grids_dir.exists():
                for csv in sorted(grids_dir.glob("*.csv")):
                    parsed = self._parse_grid_csv(csv)
                    if parsed is not None:
                        return parsed

        x = np.linspace(0.0, 8.0, 24)
        y = np.linspace(0.0, 8.0, 20)
        xx, yy = np.meshgrid(x, y)
        z = np.zeros_like(xx)
        if self.project.luminaires:
            for lum in self.project.luminaires:
                lx, ly, lz = lum.transform.position
                sigma = max(0.8, (lz or 2.5) * 0.55)
                z += 450.0 / (1.0 + ((xx - lx) ** 2 + (yy - ly) ** 2) / (sigma**2))
        else:
            z = 300.0 + 80.0 * np.sin(xx / 2.0) * np.cos(yy / 2.5)
        z = np.clip(z, 1.0, None)
        return xx, yy, z

    def _parse_grid_csv(self, csv_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        try:
            arr = np.loadtxt(str(csv_path), delimiter=",", skiprows=1, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.shape[1] < 4:
                return None
            xvals = np.unique(arr[:, 0])
            yvals = np.unique(arr[:, 1])
            if xvals.size < 2 or yvals.size < 2:
                return None
            order = np.lexsort((arr[:, 0], arr[:, 1]))
            arr = arr[order]
            z = arr[:, 3].reshape(yvals.size, xvals.size)
            xx, yy = np.meshgrid(xvals, yvals)
            return xx, yy, z
        except Exception:
            return None

    def _asset_hashes(self) -> Dict[str, str]:
        assets = self.results.get("assets", {})
        if isinstance(assets, dict):
            return {str(k): str(v) for k, v in assets.items()}
        return {}

    def _to_float(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _fmt_num(self, value: Any) -> str:
        v = self._to_float(value)
        if v is None:
            return "-"
        if math.isfinite(v) and abs(v) >= 100:
            return f"{v:.1f}"
        return f"{v:.2f}"

    def _estimated_connected_load_w(self) -> float:
        total = 0.0
        by_asset = {a.id: a for a in self.project.photometry_assets}
        for lum in self.project.luminaires:
            asset = by_asset.get(lum.photometry_asset_id)
            metadata = asset.metadata if asset and isinstance(asset.metadata, dict) else {}
            watt = self._to_float(metadata.get("wattage") or metadata.get("watts"))
            if watt is not None:
                total += watt
        return total
