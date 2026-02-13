from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema


def _csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        rows = list(r)
    return max(len(rows) - 1, 0)


def test_roadway_lane_csv_dimensions_match_summary(tmp_path: Path) -> None:
    src = Path("examples/roadway_basic").resolve()
    dst = tmp_path / "roadway_basic"
    shutil.copytree(src, dst)
    project_path = dst / "road.luxera.json"

    assert main(["run-all", str(project_path), "--job", "roadway_job"]) == 0
    project = load_project_schema(project_path)
    ref = next((r for r in project.results if r.job_id == "roadway_job"), None)
    assert ref is not None
    result_dir = Path(ref.result_dir)

    summary = json.loads((result_dir / "road_summary.json").read_text(encoding="utf-8"))
    lane_metrics = summary.get("lane_metrics", [])
    assert isinstance(lane_metrics, list)
    assert lane_metrics

    for lane in lane_metrics:
        lane_num = int(lane.get("lane_number", int(lane.get("lane_index", 0)) + 1))
        nx = int(lane.get("nx", 0))
        ny = int(lane.get("ny", 0))
        sample_count = int(lane.get("sample_count", 0))
        lane_csv = result_dir / f"road_grid_{lane_num}.csv"
        assert lane_csv.exists()
        assert _csv_rows(lane_csv) == sample_count
        assert sample_count == nx * ny
