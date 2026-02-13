from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image

from luxera.project.schema import JobResultRef, Project
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


def render_daylight_pdf_report(project: Project, job_ref: JobResultRef, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_dir = Path(job_ref.result_dir)
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    summary = meta.get("summary", {}) if isinstance(meta, dict) else {}
    schedule = build_luminaire_schedule(project, asset_hashes=meta.get("assets", {}) if isinstance(meta.get("assets"), dict) else {})

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    story = [Paragraph("Daylight Report", styles["Title"]), Spacer(1, 0.2 * cm)]
    story.append(_kv([["Project", project.name], ["Job ID", job_ref.job_id], ["Mode", str(summary.get("mode", "-"))]]))
    story.append(Spacer(1, 0.2 * cm))

    thr = summary.get("thresholds", {}) if isinstance(summary, dict) else {}
    rows = [["sDA area mean (%)", str(summary.get("sda_area_percent_mean", "-"))], ["ASE area mean (%)", str(summary.get("ase_area_percent_mean", "-"))], ["UDI mean (%)", str(summary.get("udi_percent_mean", "-"))]]
    for k, v in (thr.items() if isinstance(thr, dict) else []):
        rows.append([str(k), str(v)])
    story.append(Paragraph("Metrics", styles["Heading2"]))
    story.append(_kv(rows))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Luminaire Schedule", styles["Heading2"]))
    srows = [["asset_id", "hash", "count", "mount_h", "tilt"]]
    for r in schedule:
        srows.append([str(r.get("asset_id")), str(r.get("photometry_hash")), str(r.get("count")), str(r.get("mounting_height_m")), str(r.get("tilt_deg"))])
    story.append(_kv(srows))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Audit", styles["Heading2"]))
    story.append(
        _kv(
            [
                ["solver", str(meta.get("solver", {}))],
                ["backend", str(meta.get("backend", {}))],
                ["units", str(meta.get("units", {}))],
                ["coordinate_convention", str(meta.get("coordinate_convention", "-"))],
            ]
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    for png in sorted(result_dir.glob("sda_*.png"))[:2]:
        story.append(Paragraph(f"Plot: {png.name}", styles["BodyText"]))
        story.append(Image(str(png), width=16 * cm, height=8 * cm))
    for png in sorted(result_dir.glob("*_falsecolor.png"))[:2]:
        story.append(Paragraph(f"False-colour: {png.name}", styles["BodyText"]))
        story.append(Image(str(png), width=16 * cm, height=8 * cm))

    doc.build(story)
    return out_path
