from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors

from luxera.export.en12464_report import EN12464ReportModel


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
    heatmap = result_dir / "heatmap.png"
    isolux = result_dir / "isolux.png"
    if heatmap.exists() or isolux.exists():
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Plots", h2))
        for p in (heatmap, isolux):
            if p.exists():
                img = Image(str(p))
                img._restrictSize(17.0 * cm, 10.0 * cm)
                story.append(img)
                story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
    return out_path
