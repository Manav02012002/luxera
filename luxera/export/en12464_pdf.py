from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
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
    )

    story = []
    story.append(Paragraph("EN 12464 Report", title_style))
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
    ]
    story.append(_kv_table(audit_rows))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Compliance", h2))
    compliance = model.compliance or {}
    if isinstance(compliance, dict):
        rows = [[k, str(v)] for k, v in compliance.items()]
        story.append(_kv_table(rows if rows else [["Compliance", "-"]]))
    else:
        story.append(Paragraph("Compliance data unavailable.", body))

    doc.build(story)
    return out_path
