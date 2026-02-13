from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from luxera.project.schema import JobResultRef, Project
from luxera.reporting.schedules import build_luminaire_schedule


def _kv_table(rows: List[List[str]]) -> Table:
    t = Table(rows, colWidths=[6.0 * cm, 11.7 * cm])
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


def _summary_rows(summary: Dict[str, Any]) -> List[List[str]]:
    keys = [
        "road_class",
        "mean_lux",
        "min_lux",
        "max_lux",
        "uniformity_ratio",
        "ul_longitudinal",
        "road_luminance_mean_cd_m2",
        "threshold_increment_ti_proxy_percent",
        "surround_ratio_proxy",
        "lane_width_m",
        "num_lanes",
        "road_length_m",
        "mounting_height_m",
        "setback_m",
        "pole_spacing_m",
    ]
    rows: List[List[str]] = []
    for k in keys:
        if k in summary:
            rows.append([k, str(summary[k])])
    return rows


def render_roadway_pdf_report(project: Project, job_ref: JobResultRef, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_dir = Path(job_ref.result_dir)
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    summary = meta.get("summary", {}) if isinstance(meta, dict) else {}
    compliance = summary.get("compliance", {}) if isinstance(summary, dict) else {}
    schedule = build_luminaire_schedule(project, asset_hashes=meta.get("assets", {}) if isinstance(meta.get("assets"), dict) else {})

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
        title="Roadway Lighting Report",
        author="Luxera",
        pageCompression=0,
    )

    story = [Paragraph("Roadway Lighting Report", title_style), Spacer(1, 0.25 * cm)]
    story.append(
        _kv_table(
            [
                ["Project", project.name],
                ["Job ID", job_ref.job_id],
                ["Job Hash", job_ref.job_hash],
                ["Solver Version", str(meta.get("solver", {}).get("package_version", "-"))],
                ["Coordinate Convention", str(meta.get("coordinate_convention", "-"))],
            ]
        )
    )
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("Layout Parameters", h2))
    story.append(_kv_table(_summary_rows(summary if isinstance(summary, dict) else {})))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("Luminaire Schedule", h2))
    lum_rows: List[List[str]] = [["asset_id", "hash", "count", "mount_h", "tilt", "MF"]]
    for r in schedule:
        lum_rows.append([str(r.get("asset_id")), str(r.get("photometry_hash")), str(r.get("count")), str(r.get("mounting_height_m")), str(r.get("tilt_deg")), str(r.get("maintenance_factor"))])
    story.append(_kv_table(lum_rows))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("Grid and Compliance", h2))
    comp_rows: List[List[str]] = []
    if isinstance(compliance, dict):
        for k, v in compliance.items():
            if k == "thresholds":
                continue
            comp_rows.append([str(k), str(v)])
    if not comp_rows:
        comp_rows = [["compliance", "n/a"]]
    story.append(_kv_table(comp_rows))
    story.append(Spacer(1, 0.25 * cm))

    lane_metrics = summary.get("lane_metrics", []) if isinstance(summary, dict) else []
    story.append(Paragraph("Luminance Tables", h2))
    if isinstance(lane_metrics, list) and lane_metrics:
        rows: List[List[str]] = [["lane", "mean_lux", "u0", "ul", "luminance_mean_cd_m2"]]
        for lm in lane_metrics:
            if not isinstance(lm, dict):
                continue
            rows.append(
                [
                    str(lm.get("lane_number", lm.get("lane_index", "-"))),
                    str(lm.get("mean_lux", "-")),
                    str(lm.get("uniformity_ratio", "-")),
                    str(lm.get("ul_longitudinal", "-")),
                    str(lm.get("luminance_mean_cd_m2", "-")),
                ]
            )
        story.append(_kv_table(rows))
    else:
        story.append(Paragraph("No lane luminance table available.", body))
    story.append(Spacer(1, 0.25 * cm))

    heatmap = result_dir / "road_heatmap.png"
    if not heatmap.exists():
        heatmap = result_dir / "grid_heatmap.png"
    if heatmap.exists():
        story.append(Paragraph("Plot: Road Heatmap", h2))
        story.append(Image(str(heatmap), width=16 * cm, height=9 * cm))
        story.append(Spacer(1, 0.2 * cm))

    assumptions = meta.get("assumptions", [])
    unsupported = meta.get("unsupported_features", [])
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Audit", h2))
    story.append(
        _kv_table(
            [
                ["solver", str(meta.get("solver", {}))],
                ["backend", str(meta.get("backend", {}))],
                ["units", str(meta.get("units", {}))],
                ["coordinate_convention", str(meta.get("coordinate_convention", "-"))],
            ]
        )
    )
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Assumptions", h2))
    if isinstance(assumptions, list) and assumptions:
        for a in assumptions:
            story.append(Paragraph(f"- {a}", body))
    else:
        story.append(Paragraph("- n/a", body))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Limitations", h2))
    if isinstance(unsupported, list) and unsupported:
        for u in unsupported:
            story.append(Paragraph(f"- {u}", body))
    else:
        story.append(Paragraph("- n/a", body))

    doc.build(story)
    return out_path
