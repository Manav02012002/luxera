from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib import colors

from luxera.export.en12464_report import EN12464ReportModel
from luxera.viz.contours import compute_contour_levels


def _kv_table(rows):
    t = Table(rows, colWidths=[5.2 * cm, 12.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _draw_header_footer(canvas, doc, project_name: str) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(doc.leftMargin, A4[1] - 1.2 * cm, f"Luxera EN 12464-1 Compliance Report — {project_name}")
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.9 * cm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _embed_image(story, image_path: Path, max_w_cm: float = 17.5, max_h_cm: float = 20.0) -> None:
    if not image_path.exists():
        return
    img = Image(str(image_path))
    img._restrictSize(max_w_cm * cm, max_h_cm * cm)
    story.append(img)


def _first_grid_levels(result_dir: Path) -> list[float]:
    grids_dir = result_dir / "grids"
    if not grids_dir.exists():
        return []
    for p in sorted(grids_dir.glob("*.csv")):
        try:
            arr = np.loadtxt(str(p), delimiter=",", skiprows=1, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.shape[1] < 4:
                continue
            order = np.lexsort((arr[:, 0], arr[:, 1]))
            arr = arr[order]
            nx = int(np.unique(arr[:, 0]).size)
            ny = int(np.unique(arr[:, 1]).size)
            if nx <= 1 or ny <= 1:
                continue
            z = arr[:, 3].reshape(ny, nx)
            levels = compute_contour_levels(z, n_levels=8)
            return [float(v) for v in levels]
        except Exception:
            continue
    return []


def render_en12464_pdf(model: EN12464ReportModel, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="EN 12464 Report",
        author="Luxera",
        pageCompression=0,
    )

    story = []
    story.append(Paragraph("EN 12464 Report", title_style))
    story.append(Spacer(1, 0.25 * cm))

    audit = model.audit
    story.append(Paragraph("Audit Header", h2))
    audit_rows = [
        ["Project", audit.project_name],
        ["Project Revision", str(audit.schema_version)],
        ["Job ID", audit.job_id],
        ["Job Hash", audit.job_hash],
        ["Solver Version", str(audit.solver.get("package_version", "-"))],
        ["Git Commit", str(audit.solver.get("git_commit", "-"))],
        ["Photometry Hashes", str(audit.asset_hashes)],
        ["Coordinate Convention", str(audit.coordinate_convention or "-")],
        ["Units", str(audit.units or {})],
    ]
    story.append(_kv_table(audit_rows))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Inputs", h2))
    if model.inputs.get("rooms"):
        room = model.inputs["rooms"][0]
        story.append(
            _kv_table(
                [
                    ["Room", str(room.get("name", "-"))],
                    ["Dimensions", f"{room.get('width', '-') } x {room.get('length', '-') } x {room.get('height', '-') } m"],
                ]
            )
        )
    if model.inputs.get("reflectances"):
        refl = model.inputs["reflectances"][0]
        story.append(
            _kv_table(
                [
                    ["Floor reflectance", str(refl.get("floor_reflectance", "-"))],
                    ["Wall reflectance", str(refl.get("wall_reflectance", "-"))],
                    ["Ceiling reflectance", str(refl.get("ceiling_reflectance", "-"))],
                ]
            )
        )
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Luminaire Schedule", h2))
    if model.luminaire_schedule:
        lrows = [["Count", "Asset", "Mounting H (m)", "Rotation/Aim", "LLF", "Flux Mult", "Tilt"]]
        for l in model.luminaire_schedule:
            rot = l.get("rotation", {})
            lrows.append(
                [
                    str(l.get("count", 1)),
                    str(l.get("asset_name", l.get("asset_id", "-"))),
                    str(l.get("mounting_height_m", "-")),
                    str(rot if rot else l.get("aim", "-")),
                    str(l.get("llf", l.get("maintenance_factor", "-"))),
                    str(l.get("flux_multiplier", "-")),
                    str(l.get("tilt_deg", "-")),
                ]
            )
        story.append(_kv_table(lrows))
    else:
        story.append(Paragraph("No luminaires.", body))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Per-Grid Statistics", h2))
    if model.per_grid_stats:
        rows = [["Type", "ID", "min", "mean", "max", "uniformity"]]
        for obj in model.per_grid_stats:
            if not isinstance(obj, dict):
                continue
            s = obj.get("summary", {}) if isinstance(obj.get("summary"), dict) else {}
            rows.append(
                [
                    str(obj.get("type", "-")),
                    str(obj.get("id", "-")),
                    str(s.get("min_lux", "-")),
                    str(s.get("mean_lux", "-")),
                    str(s.get("max_lux", "-")),
                    str(s.get("uniformity_ratio", "-")),
                ]
            )
        story.append(_kv_table(rows))
    else:
        story.append(Paragraph("No per-grid stats.", body))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Maintenance Factor Decomposition", h2))
    if model.maintenance_factor_table:
        mrows = [["Luminaire", "Mode", "LLMF", "LSF", "LMF", "RSF", "MF"]]
        for row in model.maintenance_factor_table:
            mrows.append(
                [
                    str(row.get("luminaire_id", "-")),
                    str(row.get("mode", "-")),
                    str(row.get("llmf", "-")),
                    str(row.get("lsf", "-")),
                    str(row.get("lmf", "-")),
                    str(row.get("rsf", "-")),
                    str(row.get("maintenance_factor", "-")),
                ]
            )
        story.append(_kv_table(mrows))
    else:
        story.append(Paragraph("No maintenance decomposition data available.", body))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Calculation Tables", h2))
    tbl = model.tables or {}
    rendered = False
    if isinstance(tbl, dict):
        for section, title in (
            ("grids", "Grid Tables"),
            ("vertical_planes", "Vertical Plane Tables"),
            ("point_sets", "Point Set Tables"),
        ):
            vals = tbl.get(section, [])
            if not isinstance(vals, list) or not vals:
                continue
            story.append(Spacer(1, 0.12 * cm))
            story.append(Paragraph(title, body))
            rows = [["Type", "ID", "Name", "Points", "Spacing", "Area", "Min", "Mean", "Max", "U0"]]
            for r in vals:
                if not isinstance(r, dict):
                    continue
                rows.append(
                    [
                        str(r.get("type", "-")),
                        str(r.get("id", "-")),
                        str(r.get("name", "-")),
                        str(r.get("point_count", "-")),
                        str(r.get("spacing", "-")),
                        str(r.get("area", "-")),
                        str(r.get("min_lux", "-")),
                        str(r.get("mean_lux", "-")),
                        str(r.get("max_lux", "-")),
                        str(r.get("uniformity_min_avg", "-")),
                    ]
                )
            story.append(_kv_table(rows))
            rendered = True
    if not rendered:
        story.append(Paragraph("No calculation tables available.", body))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Worst-Case Summary", h2))
    wcs = model.worst_case_summary or {}
    if isinstance(wcs, dict) and wcs:
        story.append(_kv_table([[k, str(v)] for k, v in wcs.items()]))
    else:
        story.append(Paragraph("No worst-case aggregate available.", body))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Compliance", h2))
    compliance = model.compliance or {}
    if isinstance(compliance, dict):
        rows = [[k, str(v)] for k, v in compliance.items()]
        story.append(_kv_table(rows if rows else [["Compliance", "-"]]))
        reasons = compliance.get("pass_fail_reasons")
        if isinstance(reasons, list) and reasons:
            story.append(Spacer(1, 0.15 * cm))
            story.append(_kv_table([[f"Reason {i+1}", str(r)] for i, r in enumerate(reasons)]))
        leni = compliance.get("leni")
        if isinstance(leni, dict):
            story.append(Spacer(1, 0.25 * cm))
            story.append(Paragraph("LENI Energy (EN 15193)", h2))
            story.append(
                _kv_table(
                    [
                        ["LENI (kWh/m²·year)", str(leni.get("leni_kWh_per_m2_year", "-"))],
                        ["Total Energy (kWh/year)", str(leni.get("total_energy_kWh", "-"))],
                        ["Lighting Energy (kWh/year)", str(leni.get("energy_lighting_kWh", "-"))],
                        ["Parasitic Energy (kWh/year)", str(leni.get("energy_parasitic_kWh", "-"))],
                        ["Power Density (W/m²)", str(leni.get("power_density_W_per_m2", "-"))],
                        ["LENI Limit (kWh/m²·year)", str(leni.get("limit_kWh_per_m2_year", "-"))],
                        ["LENI Compliant", str(leni.get("compliant", "-"))],
                    ]
                )
            )
    else:
        story.append(Paragraph("Compliance data unavailable.", body))

    if audit.assumptions:
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Assumptions", h2))
        story.append(_kv_table([[f"A{i+1}", a] for i, a in enumerate(audit.assumptions)]))
    if model.assumptions:
        story.append(Spacer(1, 0.25 * cm))
        story.append(_kv_table([[f"M{i+1}", a] for i, a in enumerate(model.assumptions)]))

    if audit.unsupported_features:
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Unsupported Features", h2))
        story.append(_kv_table([[f"U{i+1}", a] for i, a in enumerate(audit.unsupported_features)]))

    result_dir = Path(model.result_dir).expanduser().resolve()

    if model.layout_path:
        lp = Path(model.layout_path)
        if lp.exists():
            story.append(PageBreak())
            story.append(Paragraph("Room Layout", h2))
            story.append(Spacer(1, 0.2 * cm))
            _embed_image(story, lp, max_w_cm=18.0, max_h_cm=22.0)

    if model.heatmap_paths:
        story.append(PageBreak())
        story.append(Paragraph("Illuminance Heatmap", h2))
        story.append(Spacer(1, 0.2 * cm))
        for p in model.heatmap_paths:
            _embed_image(story, Path(p), max_w_cm=18.0, max_h_cm=18.0)
            story.append(Spacer(1, 0.15 * cm))
        summary = model.worst_case_summary if isinstance(model.worst_case_summary, dict) else {}
        story.append(
            Paragraph(
                f"Min/Avg/Max (lux): {summary.get('global_worst_min_lux', '-')} / "
                f"{summary.get('global_mean_of_means_lux', '-')} / {summary.get('global_highest_lux', summary.get('global_worst_max_lux', '-'))}",
                body,
            )
        )
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph("Legend: Inferno scale from low (dark) to high (bright).", body))

    if model.isolux_paths:
        story.append(PageBreak())
        story.append(Paragraph("Isolux Contours", h2))
        story.append(Spacer(1, 0.2 * cm))
        for p in model.isolux_paths:
            _embed_image(story, Path(p), max_w_cm=18.0, max_h_cm=18.0)
            story.append(Spacer(1, 0.15 * cm))
        levels = _first_grid_levels(result_dir)
        if levels:
            levels_txt = ", ".join(f"{v:.0f}" for v in levels)
            story.append(Paragraph(f"Contour level legend (lux): {levels_txt}", body))
        else:
            story.append(Paragraph("Contour level legend: auto-scaled from grid values.", body))

    if model.polar_paths:
        story.append(PageBreak())
        story.append(Paragraph("Photometric Data", h2))
        story.append(Spacer(1, 0.2 * cm))
        meta_by_asset = {str(m.get("asset_id")): m for m in (model.polar_meta or []) if isinstance(m, dict)}
        for p in model.polar_paths:
            pp = Path(p)
            _embed_image(story, pp, max_w_cm=10.0, max_h_cm=10.0)
            stem = pp.stem
            aid = stem.replace("polar_", "", 1)
            meta = meta_by_asset.get(aid, {})
            story.append(
                _kv_table(
                    [
                        ["Asset ID", str(meta.get("asset_id", aid))],
                        ["Filename", str(meta.get("filename", "-"))],
                        ["Total Lumens", str(meta.get("total_lumens", "-"))],
                        ["Beam Angle (deg)", str(meta.get("beam_angle", "-"))],
                    ]
                )
            )
            story.append(Spacer(1, 0.2 * cm))

    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_header_footer(c, d, model.audit.project_name),
        onLaterPages=lambda c, d: _draw_header_footer(c, d, model.audit.project_name),
    )

    if model.image_temp_dir:
        tmp = Path(model.image_temp_dir).expanduser()
        if tmp.exists() and tmp.name.startswith("luxera_en12464_"):
            shutil.rmtree(tmp, ignore_errors=True)
    return out_path
