from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _table_rows(d: Dict[str, Any], keys: List[str]) -> str:
    rows: List[str] = []
    for k in keys:
        if k in d:
            rows.append(f"<tr><th>{html.escape(k)}</th><td>{html.escape(_fmt(d[k]))}</td></tr>")
    return "\n".join(rows)


def render_roadway_report_html(result_dir: Path, out_html: Path) -> Path:
    result_dir = Path(result_dir).expanduser().resolve()
    out_html = Path(out_html).expanduser().resolve()
    out_html.parent.mkdir(parents=True, exist_ok=True)

    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    summary = meta.get("summary", {}) if isinstance(meta, dict) else {}
    compliance = summary.get("compliance", {}) if isinstance(summary, dict) else {}
    views = summary.get("observer_luminance_views", []) if isinstance(summary, dict) else []

    key_metrics = [
        "road_class",
        "mean_lux",
        "min_lux",
        "max_lux",
        "uniformity_ratio",
        "ul_longitudinal",
        "road_luminance_mean_cd_m2",
        "lane_width_m",
        "num_lanes",
        "road_length_m",
        "mounting_height_m",
        "setback_m",
        "pole_spacing_m",
    ]

    view_rows = ""
    for v in views if isinstance(views, list) else []:
        if not isinstance(v, dict):
            continue
        view_rows += (
            "<tr>"
            f"<td>{html.escape(_fmt(v.get('observer_index')))}</td>"
            f"<td>{html.escape(_fmt(v.get('x')))}</td>"
            f"<td>{html.escape(_fmt(v.get('y')))}</td>"
            f"<td>{html.escape(_fmt(v.get('z')))}</td>"
            f"<td>{html.escape(_fmt(v.get('luminance_cd_m2')))}</td>"
            "</tr>"
        )

    compliance_rows = ""
    if isinstance(compliance, dict):
        for k, v in compliance.items():
            if k == "thresholds":
                continue
            compliance_rows += f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(_fmt(v))}</td></tr>"

    thresholds_rows = ""
    thresholds = compliance.get("thresholds", {}) if isinstance(compliance, dict) else {}
    if isinstance(thresholds, dict):
        for k, v in thresholds.items():
            thresholds_rows += f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(_fmt(v))}</td></tr>"

    heatmap = "grid_heatmap.png" if (result_dir / "grid_heatmap.png").exists() else ""
    isolux = "grid_isolux.png" if (result_dir / "grid_isolux.png").exists() else ""

    html_doc = f"""<!doctype html>
<html lang=\"en\"> 
<head>
  <meta charset=\"utf-8\" />
  <title>Luxera Roadway Report</title>
  <style>
    body {{ font-family: Helvetica, Arial, sans-serif; margin: 24px; color: #111; }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px 0; }}
    th, td {{ border: 1px solid #d0d0d0; text-align: left; padding: 6px 8px; font-size: 13px; }}
    th {{ background: #f7f7f7; width: 40%; }}
    .img {{ max-width: 100%; border: 1px solid #ddd; padding: 6px; }}
    .muted {{ color: #666; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Roadway Lighting Report</h1>
  <p class=\"muted\">Job: {html.escape(str(meta.get('job_id', 'unknown')))} | Hash: {html.escape(str(meta.get('job_hash', 'unknown')))}</p>

  <div class=\"grid\">
    <section>
      <h2>Key Metrics</h2>
      <table>{_table_rows(summary if isinstance(summary, dict) else {{}}, key_metrics)}</table>
    </section>
    <section>
      <h2>Compliance</h2>
      <table>{compliance_rows}</table>
      <h2>Thresholds</h2>
      <table>{thresholds_rows}</table>
    </section>
  </div>

  <section>
    <h2>Observer Luminance Views</h2>
    <table>
      <tr><th>index</th><th>x</th><th>y</th><th>z</th><th>luminance_cd_m2</th></tr>
      {view_rows}
    </table>
  </section>

  <section>
    <h2>Plots</h2>
    {f'<p><img class="img" src="{heatmap}" alt="Roadway heatmap" /></p>' if heatmap else ''}
    {f'<p><img class="img" src="{isolux}" alt="Roadway isolux" /></p>' if isolux else ''}
  </section>

  <section>
    <h2>Assumptions</h2>
    <p>{html.escape('; '.join(meta.get('assumptions', [])) if isinstance(meta.get('assumptions'), list) else '')}</p>
    <h2>Unsupported Features</h2>
    <p>{html.escape('; '.join(meta.get('unsupported_features', [])) if isinstance(meta.get('unsupported_features'), list) else '')}</p>
  </section>
</body>
</html>
"""

    out_html.write_text(html_doc, encoding="utf-8")
    return out_html
