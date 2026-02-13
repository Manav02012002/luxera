from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
)

from luxera.parser.pipeline import LuxeraViewResult
from luxera.plotting.plots import PlotPaths
from luxera.project.schema import JobResultRef, Project
from luxera.reporting.pdf import render_project_pdf
from luxera.export.templates.daylight_report import render_daylight_pdf_report
from luxera.export.templates.emergency_report import render_emergency_pdf_report
from luxera.export.templates.roadway_report import render_roadway_pdf_report


@dataclass(frozen=True)
class PDFPaths:
    pdf_path: Path


def _first_kw(doc, key: str) -> str:
    vals = doc.keywords.get(key, [])
    if not vals:
        return "-"
    v = vals[0].strip()
    return v if v else "-"


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


def _findings_table(result: LuxeraViewResult):
    if result.report is None:
        return None

    rows = [["Severity", "Rule ID", "Title", "Message"]]
    for f in result.report.findings:
        rows.append([f.severity, f.id, f.title, f.message])

    t = Table(rows, colWidths=[2.2 * cm, 4.5 * cm, 4.5 * cm, 6.5 * cm])
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
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def build_pdf_report(
    result: LuxeraViewResult,
    plots: PlotPaths,
    out_pdf_path: Path,
    source_file: Optional[Path] = None,
) -> PDFPaths:
    """
    Create a shareable Luxera View PDF report:
      - Metadata / header
      - Derived metrics + validation summary
      - Embedded plots
      - Findings table (if any)
    """
    out_pdf_path = out_pdf_path.expanduser().resolve()
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    doc = result.doc
    ph = doc.photometry
    ang = doc.angles

    pdf = SimpleDocTemplate(
        str(out_pdf_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="Luxera View Report",
        author="Luxera",
    )

    story = []

    story.append(Paragraph("Luxera View Report", title_style))
    story.append(Spacer(1, 0.25 * cm))

    src = str(source_file) if source_file is not None else "-"
    story.append(Paragraph(f"<b>Source</b>: {src}", body))
    if doc.standard_line:
        story.append(Paragraph(f"<b>Standard</b>: {doc.standard_line}", body))
    if doc.tilt_line:
        story.append(Paragraph(f"<b>TILT</b>: {doc.tilt_line}", body))
    story.append(Spacer(1, 0.35 * cm))

    # Metadata table
    story.append(Paragraph("Metadata", h2))
    meta_rows = [
        ["Manufacturer", _first_kw(doc, "MANUFAC")],
        ["Luminaire Catalog", _first_kw(doc, "LUMCAT")],
        ["Luminaire", _first_kw(doc, "LUMINAIRE")],
        ["Lamp", _first_kw(doc, "LAMPCAT")],
        ["Test Lab", _first_kw(doc, "TESTLAB")],
        ["Date", _first_kw(doc, "DATE")],
    ]
    story.append(_kv_table(meta_rows))
    story.append(Spacer(1, 0.35 * cm))

    # Photometry summary
    story.append(Paragraph("Photometry Summary", h2))
    if ph is None or ang is None:
        story.append(Paragraph("Photometry/angles not parsed; report is incomplete.", body))
    else:
        units = "m" if ph.units_type == 2 else "ft"
        phot_rows = [
            ["Number of lamps", str(ph.num_lamps)],
            ["Lumens per lamp", f"{ph.lumens_per_lamp:g}"],
            ["Candela multiplier", f"{ph.candela_multiplier:g}"],
            ["Vertical angles (count)", str(ph.num_vertical_angles)],
            ["Horizontal angles (count)", str(ph.num_horizontal_angles)],
            ["Photometric type", str(ph.photometric_type)],
            ["Units", units],
            ["Width", f"{ph.width:g} {units}"],
            ["Length", f"{ph.length:g} {units}"],
            ["Height", f"{ph.height:g} {units}"],
            ["Vertical range", f"{ang.vertical_deg[0]:g}° to {ang.vertical_deg[-1]:g}°"],
            ["Horizontal range", f"{ang.horizontal_deg[0]:g}° to {ang.horizontal_deg[-1]:g}°"],
        ]
        story.append(_kv_table(phot_rows))

    story.append(Spacer(1, 0.35 * cm))

    # Derived + Validation
    story.append(Paragraph("Derived Metrics & Validation", h2))
    if result.derived is not None:
        dm = result.derived
        derived_rows = [
            ["Peak candela (scaled)", f"{dm.peak_candela:g}"],
            ["Peak location (H, V)", f"({dm.peak_location[0]:g}°, {dm.peak_location[1]:g}°)"],
            ["Symmetry inferred", dm.symmetry_inferred],
            ["Candela stats (scaled)", f"min={dm.candela_stats['min']:g}, max={dm.candela_stats['max']:g}, mean={dm.candela_stats['mean']:g}, p95={dm.candela_stats['p95']:g}"],
        ]
        story.append(_kv_table(derived_rows))
        story.append(Spacer(1, 0.25 * cm))
    else:
        story.append(Paragraph("Derived metrics unavailable (need angles + candela).", body))

    if result.report is not None:
        s = result.report.summary
        story.append(
            Paragraph(
                f"<b>Findings summary</b>: {s['errors']} error(s), {s['warnings']} warning(s), {s['info']} info",
                body,
            )
        )
    else:
        story.append(Paragraph("Validation report unavailable.", body))

    story.append(Spacer(1, 0.45 * cm))

    # Plots page
    story.append(PageBreak())
    story.append(Paragraph("Plots", h2))
    story.append(Spacer(1, 0.25 * cm))

    # Embed images; scale to page width
    max_w = 17.0 * cm
    img1 = Image(str(plots.intensity_png))
    img1._restrictSize(max_w, 12.5 * cm)
    story.append(Paragraph("<b>Intensity curves</b>", body))
    story.append(img1)
    story.append(Spacer(1, 0.35 * cm))

    img2 = Image(str(plots.polar_png))
    img2._restrictSize(max_w, 12.5 * cm)
    story.append(Paragraph("<b>Polar plot</b>", body))
    story.append(img2)

    # Findings page only if there are any
    if result.report is not None and result.report.findings:
        story.append(PageBreak())
        story.append(Paragraph("Validation Findings", h2))
        story.append(Spacer(1, 0.25 * cm))
        t = _findings_table(result)
        if t is not None:
            story.append(t)

    pdf.build(story)
    return PDFPaths(pdf_path=out_pdf_path)


def build_project_pdf_report(project: Project, job_ref: JobResultRef, out_pdf_path: Path) -> Path:
    """Render a project-job PDF report using job-kind templates."""
    job = next((j for j in project.jobs if j.id == job_ref.job_id), None)
    if job is None:
        raise ValueError(f"Job not found for report: {job_ref.job_id}")
    if job.type == "roadway":
        return render_roadway_pdf_report(project, job_ref, out_pdf_path)
    if job.type == "daylight":
        return render_daylight_pdf_report(project, job_ref, out_pdf_path)
    if job.type == "emergency":
        return render_emergency_pdf_report(project, job_ref, out_pdf_path)
    # Generic reporting path includes summary, false-colour overlays, schedule, and audit metadata.
    return render_project_pdf(project, job_ref, out_pdf_path)
