from __future__ import annotations

from pathlib import Path
from luxera.export.en12464_report import EN12464ReportModel


def render_en12464_html(model: EN12464ReportModel, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    audit = model.audit
    rows = "".join([f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in {
        "Project": audit.project_name,
        "Schema Version": audit.schema_version,
        "Job ID": audit.job_id,
        "Job Hash": audit.job_hash,
        "Solver Version": audit.solver.get("package_version", "-"),
        "Git Commit": audit.solver.get("git_commit", "-"),
    }.items()])

    comp_rows = "".join([f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in (model.compliance or {}).items()])

    html = f"""
<!doctype html>
<html>
<head><meta charset='utf-8'><title>EN 12464 Report</title></head>
<body>
<h1>EN 12464 Report</h1>
<h2>Audit Header</h2>
<table border='1' cellspacing='0' cellpadding='4'>{rows}</table>
<h2>Compliance</h2>
<table border='1' cellspacing='0' cellpadding='4'>{comp_rows or '<tr><td>No data</td></tr>'}</table>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
