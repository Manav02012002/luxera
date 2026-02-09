from __future__ import annotations

from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from luxera.export.report_model import EN13032ReportModel


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


def render_en13032_pdf(model: EN13032ReportModel, out_path: Path) -> Path:
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
        title="EN 13032 Report",
        author="Luxera",
    )

    story = []
    story.append(Paragraph("EN 13032 Report", title_style))
    story.append(Spacer(1, 0.25 * cm))

    audit = model.audit
    story.append(Paragraph("Audit Header", h2))
    audit_rows = [
        ["Project", audit.project_name],
        ["Schema Version", str(audit.schema_version)],
        ["Job ID", audit.job_id],
        ["Job Hash", audit.job_hash],
        ["Solver Version", str(audit.solver.get("package_version", "-"))],
        ["Git Commit", str(audit.solver.get("git_commit", "-"))],
        ["Coordinate Convention", str(audit.coordinate_convention or "-")],
        ["Units", str(audit.units or {})],
    ]
    story.append(_kv_table(audit_rows))
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("Photometry Assets", h2))
    if model.photometry:
        rows = [["Asset ID", "Format", "Filename", "Hash"]]
        for p in model.photometry:
            rows.append([p.asset_id, p.format, p.filename or "-", p.content_hash or "-"])
        t = Table(rows, colWidths=[3.5 * cm, 2.0 * cm, 5.0 * cm, 7.0 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ]
            )
        )
        story.append(t)
    else:
        story.append(Paragraph("No photometry assets recorded.", body))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Geometry", h2))
    geom_rows = []
    rooms = model.geometry.get("rooms", [])
    if rooms:
        for r in rooms:
            geom_rows.append([f"Room {r.get('name')}", f"{r.get('width')} x {r.get('length')} x {r.get('height')} m"])
            geom_rows.append(["Reflectance (floor/wall/ceiling)", f"{r.get('floor_reflectance')}/{r.get('wall_reflectance')}/{r.get('ceiling_reflectance')}"])
    else:
        geom_rows.append(["Rooms", "-"])
    story.append(_kv_table(geom_rows))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Calculation Method", h2))
    method_rows = [[k, str(v)] for k, v in model.method.items()]
    story.append(_kv_table(method_rows if method_rows else [["Method", "-"]]))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Summary", h2))
    summary_rows = [[k, str(v)] for k, v in model.summary.items()]
    story.append(_kv_table(summary_rows if summary_rows else [["Summary", "-"]]))

    if model.compliance is not None:
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Compliance (EN 12464)", h2))
        comp_rows = [[k, str(v)] for k, v in model.compliance.items()]
        story.append(_kv_table(comp_rows if comp_rows else [["Compliance", "-"]]))

    if audit.assumptions:
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Assumptions", h2))
        story.append(_kv_table([[f"A{i+1}", a] for i, a in enumerate(audit.assumptions)]))

    if audit.unsupported_features:
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Unsupported Features", h2))
        story.append(_kv_table([[f"U{i+1}", a] for i, a in enumerate(audit.unsupported_features)]))

    doc.build(story)
    return out_path
