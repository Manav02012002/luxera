from pathlib import Path
import json

from luxera.export.backend_comparison import render_backend_comparison_html


def test_render_backend_comparison_html(tmp_path: Path):
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    payload = {
        "points_compared": 4,
        "thresholds": {"max_mean_rel_error": 0.5, "max_abs_lux_error": 150.0},
        "stats": {"delta_mean_rel": 0.1, "delta_max_abs_lux": 10.0},
        "pass": True,
    }
    (result_dir / "backend_comparison.json").write_text(json.dumps(payload), encoding="utf-8")

    out = render_backend_comparison_html(result_dir, tmp_path / "compare.html")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Backend Comparison" in text
    assert "PASS" in text
