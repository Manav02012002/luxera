from __future__ import annotations

import json
import shutil
from pathlib import Path

from luxera.cli import main
from luxera.export.report_model import build_report_model
from luxera.project.io import load_project_schema


def test_roadway_run_all_workflow(tmp_path: Path) -> None:
    src = Path("examples/roadway_basic").resolve()
    dst = tmp_path / "roadway_basic"
    shutil.copytree(src, dst)
    project_path = dst / "road.luxera.json"

    assert main(["run-all", str(project_path), "--job", "roadway_job", "--report", "--bundle"]) == 0
    assert main(["export-roadway-report", str(project_path), "roadway_job", "--out", str(dst / "roadway.html")]) == 0

    project = load_project_schema(project_path)
    ref = next((r for r in project.results if r.job_id == "roadway_job"), None)
    assert ref is not None
    result_dir = Path(ref.result_dir)
    assert (result_dir / "road_grid.csv").exists()
    assert (result_dir / "road_summary.json").exists()
    assert (result_dir / "road_heatmap.png").exists()
    assert (result_dir / "report.pdf").exists()
    assert (dst / "roadway.html").exists()
    result_meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    summary = result_meta.get("summary", {})
    assert "mean_lux" in summary
    assert "uniformity_ratio" in summary
    assert "ul_longitudinal" in summary
    assert "lane_metrics" in summary
    assert "observer_luminance_views" in summary

    unified = build_report_model(project, "roadway_job", ref)
    roadway = unified.get("roadway")
    assert isinstance(roadway, dict)
    assert isinstance(roadway.get("lane_metrics"), list)
    assert isinstance(roadway.get("observer_luminance_views"), list)
    assert isinstance(roadway.get("luminance_metrics"), dict)

    manifest = json.loads((result_dir / "manifest.json").read_text(encoding="utf-8"))
    meta = manifest.get("metadata", {})
    road_params = meta.get("road_parameters", {})
    assert "lane_width_m" in road_params
    assert "num_lanes" in road_params
    assert "pole_spacing_m" in road_params
