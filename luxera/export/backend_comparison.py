from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


def load_backend_comparison(result_dir: Path) -> Dict[str, Any]:
    p = result_dir / "backend_comparison.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def render_backend_comparison_html(result_dir: Path, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_backend_comparison(result_dir)
    if not data:
        html = "<html><body><h1>Backend Comparison</h1><p>No comparison data found.</p></body></html>"
        out_path.write_text(html, encoding="utf-8")
        return out_path

    stats = data.get("stats", {})
    thr = data.get("thresholds", {})
    ok = data.get("pass", False)
    html = f"""
<!doctype html>
<html>
<head><meta charset='utf-8'><title>Backend Comparison</title></head>
<body>
<h1>Backend Comparison</h1>
<p>Status: <strong>{'PASS' if ok else 'FAIL'}</strong></p>
<h2>Thresholds</h2>
<table border='1' cellspacing='0' cellpadding='4'>
<tr><th>Max Mean Relative Error</th><td>{thr.get('max_mean_rel_error')}</td></tr>
<tr><th>Max Absolute Lux Error</th><td>{thr.get('max_abs_lux_error')}</td></tr>
</table>
<h2>Stats</h2>
<table border='1' cellspacing='0' cellpadding='4'>
{''.join([f"<tr><th>{k}</th><td>{v}</td></tr>" for k,v in stats.items()])}
</table>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
