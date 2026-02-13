from __future__ import annotations

import json
import shutil
from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema


def _run_example(tmp_path: Path, folder_name: str) -> dict:
    src = Path("examples/roadway_basic").resolve()
    dst = tmp_path / folder_name
    shutil.copytree(src, dst)
    project_path = dst / "road.luxera.json"
    assert main(["run-all", str(project_path), "--job", "roadway_job"]) == 0
    project = load_project_schema(project_path)
    ref = next((r for r in project.results if r.job_id == "roadway_job"), None)
    assert ref is not None
    result_meta = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    return result_meta.get("summary", {})


def test_roadway_summary_contains_lane_and_overall_metrics(tmp_path: Path) -> None:
    summary = _run_example(tmp_path, "run1")
    assert isinstance(summary, dict)

    for key in ("lanes", "overall", "num_lanes", "mean_lux", "min_lux", "max_lux", "uniformity_ratio"):
        assert key in summary

    lanes = summary.get("lanes", [])
    overall = summary.get("overall", {})
    assert isinstance(lanes, list)
    assert isinstance(overall, dict)
    assert len(lanes) == int(summary.get("num_lanes", 0))

    for lane in lanes:
        assert "lane_index" in lane
        assert "lane_number" in lane
        assert "mean_lux" in lane
        assert "min_lux" in lane
        assert "max_lux" in lane
        assert "uniformity_min_avg" in lane
        assert "sample_count" in lane
        assert "nx" in lane
        assert "ny" in lane

    for key in ("avg_lux", "min_lux", "max_lux", "u0"):
        assert key in overall


def test_roadway_example_is_deterministic(tmp_path: Path) -> None:
    s1 = _run_example(tmp_path, "run_a")
    s2 = _run_example(tmp_path, "run_b")
    keys = ["mean_lux", "min_lux", "max_lux", "uniformity_ratio", "ul_longitudinal"]
    for k in keys:
        assert abs(float(s1[k]) - float(s2[k])) <= 1e-9
