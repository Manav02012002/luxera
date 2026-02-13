from __future__ import annotations

from pathlib import Path
from typing import List
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from luxera.project.schema import JobResultRef, Project
from luxera.results.contracts import SummaryResult
from luxera.reporting.audit import load_audit_metadata
from luxera.reporting.schedules import build_luminaire_schedule


def _kv(rows: List[List[str]]) -> Table:
    t = Table(rows, colWidths=[6.0 * cm, 11.7 * cm])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]
        )
    )
    return t


def render_project_pdf(project: Project, job_ref: JobResultRef, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_dir = Path(job_ref.result_dir).expanduser().resolve()
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    raw_summary = meta.get("summary", {}) if isinstance(meta, dict) else {}
    summary = SummaryResult.from_mapping(raw_summary).to_dict()
    audit = load_audit_metadata(result_dir)
    assets = meta.get("assets", {}) if isinstance(meta, dict) else {}
    schedule = build_luminaire_schedule(project, asset_hashes=assets if isinstance(assets, dict) else {})

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    story = [Paragraph("Luxera Calculation Report", styles["Title"]), Spacer(1, 0.2 * cm)]
    story.append(_kv([["Project", project.name], ["Job ID", job_ref.job_id], ["Job Hash", job_ref.job_hash]]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Summary", styles["Heading2"]))
    if isinstance(summary, dict):
        rows = [[str(k), str(v)] for k, v in summary.items() if not isinstance(v, (dict, list))]
    else:
        rows = [["summary", "n/a"]]
    story.append(_kv(rows[:24] if rows else [["summary", "n/a"]]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Luminaire Schedule", styles["Heading2"]))
    srows = [["asset_id", "hash", "count", "mount_h", "tilt", "MF"]]
    for r in schedule:
        srows.append(
            [
                str(r.get("asset_id", "-")),
                str(r.get("photometry_hash", "-")),
                str(r.get("count", "-")),
                str(r.get("mounting_height_m", "-")),
                str(r.get("tilt_deg", "-")),
                str(r.get("maintenance_factor", "-")),
            ]
        )
    story.append(_kv(srows))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Audit Metadata", styles["Heading2"]))
    arows = [
        ["Solver", str(audit.get("solver", {}))],
        ["Backend", str(audit.get("backend", {}))],
        ["Units", str(audit.get("units", {}))],
        ["Coordinate Convention", str(audit.get("coordinate_convention", "-"))],
        ["Seed", str(audit.get("seed", "-"))],
    ]
    story.append(_kv(arows))
    story.append(Spacer(1, 0.2 * cm))

    image_candidates = sorted(result_dir.glob("*_falsecolor.png")) + sorted(result_dir.glob("*heatmap*.png")) + sorted(result_dir.glob("*isolux*.png"))
    if image_candidates:
        story.append(Paragraph("Plan / False-Colour Views", styles["Heading2"]))
    for png in image_candidates[:3]:
        story.append(Paragraph(png.name, styles["BodyText"]))
        story.append(Image(str(png), width=16 * cm, height=8.5 * cm))
        story.append(Spacer(1, 0.15 * cm))

    doc.build(story)
    return out_path
